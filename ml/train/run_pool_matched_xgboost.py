"""
Pool-matched XGBoost: train XGBoost on exactly the molecules a Tier-0 KERMT arm trained on.

Why
---
The production XGBoost models train on each endpoint's full ``train_val``. A KERMT arm trains on a
smaller pool: the molecules in any member endpoint's test set are removed everywhere (leakage-safe
cluster assembly) and every molecule in any member's calibration split is held out of training
(``ClusterData.train_pool(holdout_calibration=True)``). A KERMT-minus-XGBoost difference measured
across those two pools mixes the model with the data. This script removes the data difference: for
each endpoint of an arm it rebuilds that arm's pool, keeps the rows that carry the endpoint's label,
and trains the unchanged XGBoost protocol (``train_xgboost.train_one_seed``: same featurisation, same
hyperparameters, same five-fold-per-seed split) on it. Test scoring is the endpoint's own held-out
test set, the same molecules the production report and KERMT score.

What "pool-matched" means here, and does not
--------------------------------------------
Same labelled molecules available for training. It does not make the train/validation folds
identical: KERMT draws its own fold per seed and XGBoost draws its own, both seeded 0-4. XGBoost
stays single-task and KERMT multi-task on the three absorption/distribution endpoints; that is the
model difference the comparison is meant to show.

Guards
------
* The rebuilt per-endpoint pool size must equal KERMT's recorded pool for that arm
  (``labels_retained - labels_held_out_for_calibration`` in its seed-0 ``config.json``). A different
  processed snapshot, or any change to the loader, shows up here as an error instead of a silently
  different pool.
* ``--control`` trains on the endpoint's FULL train_val with the same code path and compares seed-by-seed
  with the existing production held-out report, so a difference between the new numbers and the
  production ones cannot be blamed on this script.

Nothing is written under ``ml/runs`` or the shared feature cache: pass scratch ``--runs-dir`` and
``--cache-root``. Test molecules are scored once, after training; they never influence training.

Usage (from ``ml/``):
    PYTHONPATH=. python train/run_pool_matched_xgboost.py --arms absorption_distribution__cls \\
        --processed-dir <.../ml/data/processed> --runs-dir <scratch> --cache-root <scratch> --out <file.json>
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PREP_ID = "20260830T200000Z"
DEFAULT_KERMT_RESULTS = REPO_ROOT / "documentation" / "status" / "kermt_tier0_results"
SMILES_COL = "standardized_smiles"
ARMS = ("absorption_distribution__reg", "absorption_distribution__cls", "metabolism__reg")


def expected_pool_sizes(kermt_results: Path, arm: str) -> dict[str, int]:
    """KERMT's recorded training-pool label count per endpoint: retained minus held out for calibration."""
    path = kermt_results / arm / "seed0" / "config.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    retained = config["cluster_split_report"]["labels_retained"]
    held = config["labels_held_out_for_calibration"]
    return {endpoint: int(retained[endpoint]) - int(held[endpoint]) for endpoint in retained}


def check_pool_matches_kermt(rebuilt: dict[str, int], expected: dict[str, int]) -> None:
    if rebuilt != expected:
        raise SystemExit(
            "The rebuilt pool does not match the one KERMT trained on "
            f"(rebuilt {rebuilt}, KERMT recorded {expected}). The processed snapshot or the loader "
            "differs; nothing was trained."
        )


def _evaluate(model, test_frame) -> object:
    import numpy as np
    from eval.metrics import compute_metrics

    preds = model.predict(test_frame[SMILES_COL].tolist())
    y = test_frame["label"].to_numpy(dtype=float)
    keep = ~np.isnan(preds)
    return compute_metrics(y[keep], preds[keep], model.task_type), int((~keep).sum())


def run_endpoint(endpoint_data, *, seeds, cache, runs_dir, prep_id, label: str) -> dict:
    """Train one endpoint on `endpoint_data.train_val` for each seed and score its test set."""
    from configs.experiment_config import ExperimentConfig
    from eval.metrics import aggregate_seed_metrics
    from models.xgboost_model import XGBoostModel

    from train.train_xgboost import train_one_seed

    config = ExperimentConfig(
        endpoint=endpoint_data.endpoint_key, model_family="xgboost", seed=seeds[0], prep_id=prep_id
    )
    per_seed, metrics_objs = [], []
    for seed in seeds:
        result = train_one_seed(endpoint_data, config, cache, seed, runs_dir=runs_dir, repo_root=REPO_ROOT)
        model = XGBoostModel.load_with_cache(result.model_path, cache)
        metrics, n_dropped = _evaluate(model, endpoint_data.test)
        metrics_objs.append(metrics)
        per_seed.append(
            {
                "seed": seed,
                "n_train": result.n_train,
                "n_val": result.n_val,
                "test_metrics_raw": dataclasses.asdict(metrics),
                "n_test_dropped": n_dropped,
            }
        )
        print(f"  {endpoint_data.endpoint_key} seed {seed}: {dataclasses.asdict(metrics)}", flush=True)
    return {
        "endpoint": endpoint_data.endpoint_key,
        "pool": label,
        "n_pool_labels": len(endpoint_data.train_val),
        "n_test": len(endpoint_data.test),
        "per_seed": per_seed,
        "aggregated_test_raw": aggregate_seed_metrics(metrics_objs),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--arms", nargs="*", default=list(ARMS), choices=ARMS)
    p.add_argument("--endpoints", nargs="*", default=None, help="Only these endpoints (default: every one in the arm).")
    p.add_argument("--seeds", nargs="*", type=int, default=[0, 1, 2, 3, 4])
    p.add_argument("--prep-id", default=DEFAULT_PREP_ID, dest="prep_id")
    p.add_argument("--processed-dir", required=True, dest="processed_dir")
    p.add_argument("--runs-dir", required=True, dest="runs_dir", help="Scratch directory for run records.")
    p.add_argument("--cache-root", required=True, dest="cache_root", help="Scratch feature cache.")
    p.add_argument("--kermt-results-dir", default=str(DEFAULT_KERMT_RESULTS), dest="kermt_results")
    p.add_argument("--control", action="store_true", help="Train on the FULL train_val instead (validates this script).")
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)

    from configs.clusters import type_homogeneous_subgroups
    from data.cluster_loaders import load_cluster
    from featurize.cache import FeatureCache

    prep_dir = Path(args.processed_dir) / args.prep_id
    if not prep_dir.exists():
        print(f"ERROR: prep_dir not found: {prep_dir}", file=sys.stderr)
        return 1
    cache = FeatureCache(Path(args.cache_root))
    records = []
    for arm in args.arms:
        cluster_name = arm.rsplit("__", 1)[0]
        spec = type_homogeneous_subgroups(cluster_name)[arm]
        cluster = load_cluster(prep_dir, list(spec.endpoints), cluster_key=arm)
        pool, _held = cluster.train_pool(holdout_calibration=True)
        rebuilt = {e: int(pool[e].notna().sum()) for e in spec.endpoints}
        check_pool_matches_kermt(rebuilt, expected_pool_sizes(Path(args.kermt_results), arm))
        print(f"{arm}: pool matches KERMT's recorded pool {rebuilt}", flush=True)

        for endpoint in spec.endpoints:
            if args.endpoints and endpoint not in args.endpoints:
                continue
            data = cluster.per_endpoint[endpoint]
            if args.control:
                matched, label = data, "full train_val (control)"
            else:
                frame = pool[[SMILES_COL, endpoint]].dropna().rename(columns={endpoint: "label"})
                matched = dataclasses.replace(data, train_val=frame.reset_index(drop=True))
                label = f"KERMT pool of {arm}"
            record = run_endpoint(
                matched, seeds=tuple(args.seeds), cache=cache, runs_dir=Path(args.runs_dir),
                prep_id=args.prep_id, label=label,
            )
            record["arm"] = arm
            records.append(record)
            Path(args.out).write_text(json.dumps({"prep_id": args.prep_id, "control": args.control, "records": records}, indent=2))
    print(f"wrote {args.out} ({len(records)} endpoint(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
