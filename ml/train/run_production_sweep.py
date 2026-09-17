"""Phase 3 — the M2 production XGBoost baseline sweep: 14 endpoints x 5
FIXED_SEEDS = 70 runs. Each run uses the exact same production code path as
`run_xgboost_baseline.py` (`train.train_xgboost.train_one_seed`,
`use_wandb=True`) — this script is an in-process driver over that same
function so 70 runs don't pay 70 separate Python-process startup costs, and
so results can be collected for per-endpoint promotion + aggregation
without re-parsing files.

Writes one JSON-lines record per attempted run to
`ml/runs/production_sweep_results.jsonl` AS IT GOES (not just at the end),
so a crash partway through still leaves a durable, inspectable record of
what completed. After each endpoint's seeds finish, promotes every
successful seed into the ml/serve/ registry and builds + saves that
endpoint's EvaluationReport.

Usage (from ml/, in ml/.venv):
    PYTHONPATH=. python train/run_production_sweep.py --prep-id 20260830T200000Z
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from dataclasses import asdict
from pathlib import Path

from configs.experiment_config import FIXED_SEEDS, ExperimentConfig
from data.loaders import load_endpoint
from eval.evaluate import build_evaluation_report
from eval.leakage_audit import run_leakage_audit
from featurize.cache import FeatureCache
from mars_contracts.endpoints import ML_ENDPOINTS
from serve.registry import ModelRegistry, promote_seed_artifact

from train.train_xgboost import train_one_seed


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--prep-id", required=True)
    p.add_argument("--processed-dir", default=None)
    p.add_argument("--runs-dir", default=None)
    p.add_argument("--artifacts-root", default=None)
    p.add_argument("--cache-root", default=None)
    p.add_argument("--no-wandb", action="store_true", default=False)
    args = p.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    ml_root = repo_root / "ml"
    processed_dir = Path(args.processed_dir) if args.processed_dir else ml_root / "data" / "processed"
    prep_dir = processed_dir / args.prep_id
    runs_dir = Path(args.runs_dir) if args.runs_dir else ml_root / "runs"
    artifacts_root = Path(args.artifacts_root) if args.artifacts_root else ml_root / "artifacts"
    cache_root = Path(args.cache_root) if args.cache_root else ml_root / "data" / "cache"
    use_wandb = not args.no_wandb

    cache = FeatureCache(cache_root)
    results_path = runs_dir / "production_sweep_results.jsonl"
    results_path.parent.mkdir(parents=True, exist_ok=True)

    sweep_started = time.monotonic()
    n_attempted = 0
    n_completed = 0
    n_failed = 0
    endpoint_summaries: dict[str, dict] = {}

    with results_path.open("a", encoding="utf-8") as results_file:
        for ep in ML_ENDPOINTS:
            endpoint_key = ep.value
            use_aug = endpoint_key == "dili_liver_injury"
            print(f"\n=== {endpoint_key} (use_augmented_dili={use_aug}) ===", flush=True)

            try:
                endpoint_data = load_endpoint(prep_dir, endpoint_key, use_augmented_dili=use_aug)
            except Exception as exc:
                print(f"STOP-WORTHY: could not load {endpoint_key}: {exc}", file=sys.stderr)
                for seed in FIXED_SEEDS:
                    n_attempted += 1
                    n_failed += 1
                    record = {
                        "endpoint": endpoint_key, "seed": seed, "status": "failed",
                        "error": f"load_endpoint failed: {exc}",
                    }
                    results_file.write(json.dumps(record) + "\n")
                    results_file.flush()
                continue

            seed_results = []
            for seed in FIXED_SEEDS:
                n_attempted += 1
                config = ExperimentConfig(
                    endpoint=endpoint_key, model_family="xgboost", seed=seed,
                    prep_id=args.prep_id, use_augmented_dili=use_aug,
                )
                run_started = time.monotonic()
                record: dict = {"endpoint": endpoint_key, "seed": seed}
                try:
                    result = train_one_seed(
                        endpoint_data, config, cache, seed,
                        runs_dir=runs_dir, repo_root=repo_root, use_wandb=use_wandb,
                    )
                    elapsed = time.monotonic() - run_started
                    model_path_exists = (result.model_path / "model.json").exists()
                    if not model_path_exists:
                        raise RuntimeError(f"train_one_seed reported success but {result.model_path}/model.json is missing")

                    record.update({
                        "status": "completed",
                        "run_id": result.run_id,
                        "n_train": result.n_train,
                        "n_val": result.n_val,
                        "n_dropped_train": result.n_dropped_train,
                        "n_dropped_val": result.n_dropped_val,
                        "best_iteration": result.best_iteration,
                        "val_metrics": asdict(result.val_metrics),
                        "model_path": str(result.model_path),
                        "wandb_url": result.wandb_url,
                        "elapsed_seconds": round(elapsed, 2),
                    })
                    seed_results.append(result)
                    n_completed += 1
                    print(
                        f"  [OK] seed={seed} run_id={result.run_id} elapsed={elapsed:.1f}s "
                        f"n_train={result.n_train} n_val={result.n_val} wandb={bool(result.wandb_url)}",
                        flush=True,
                    )
                except Exception as exc:
                    elapsed = time.monotonic() - run_started
                    record.update({
                        "status": "failed",
                        "error": str(exc),
                        "traceback": traceback.format_exc(),
                        "elapsed_seconds": round(elapsed, 2),
                    })
                    n_failed += 1
                    print(f"  [FAIL] seed={seed} elapsed={elapsed:.1f}s error={exc}", file=sys.stderr, flush=True)

                results_file.write(json.dumps(record) + "\n")
                results_file.flush()

            # Promote every successfully trained seed, then build the
            # endpoint's 5-seed (or fewer, if some failed) evaluation report.
            promoted_seeds = []
            for result in seed_results:
                try:
                    promote_seed_artifact(
                        endpoint_key, result.seed, result.model_path, endpoint_data, cache,
                        artifacts_root=artifacts_root,
                    )
                    promoted_seeds.append(result.seed)
                except Exception as exc:
                    print(f"  [PROMOTE-FAIL] seed={result.seed}: {exc}", file=sys.stderr, flush=True)

            eval_report_path = None
            if seed_results:
                try:
                    report = build_evaluation_report(
                        seed_results, endpoint_key=endpoint_key, model_family="xgboost",
                        prep_id=args.prep_id, task_type=endpoint_data.task_type,
                    )
                    eval_report_path = runs_dir / "evaluations" / f"{endpoint_key}.json"
                    report.save(eval_report_path)
                except Exception as exc:
                    print(f"  [EVAL-REPORT-FAIL] {endpoint_key}: {exc}", file=sys.stderr, flush=True)

            registry = ModelRegistry(cache, artifacts_root=artifacts_root)
            ad_index = registry.load_ad_index(endpoint_key)
            calibrator = registry.load_calibrator(endpoint_key)
            split_method = endpoint_data.provenance.get("split_method")
            if split_method is None and use_aug:
                # Same fallback as preflight_sweep.py: the augmented DILI
                # variant's own provenance.json never records split_method
                # (a real gap in dilist_augment.py, not fixed here — see
                # mistakes.md). Its test set is provably the unmodified base
                # adopted-benchmark test set regardless (augmentation only
                # ever adds to train_val), so fall back to the base dataset's
                # recorded method for this classification.
                try:
                    split_method = load_endpoint(prep_dir, endpoint_key, use_augmented_dili=False).provenance.get(
                        "split_method"
                    )
                except Exception:
                    pass
            try:
                audit = run_leakage_audit(endpoint_data, ad_index=ad_index, calibrator=calibrator)
                # Documented non-blocking exception (see mistakes.md, M2
                # production sweep preflight, 2026-09-17): RDKit-vs-TDC
                # Murcko-scaffold-bucket noise on adopted-benchmark splits —
                # zero actual compound duplication (exact-SMILES check still
                # passes), only differs from how TDC itself assigned a
                # handful of scaffold buckets.
                blocking = [
                    c for c in audit.failed_checks
                    if not (c.name == "test_disjoint_from_train_val_scaffolds" and split_method == "adopt_benchmark")
                ]
                leakage_ok = not blocking
            except Exception as exc:
                leakage_ok = None
                print(f"  [LEAKAGE-AUDIT-FAIL] {endpoint_key}: {exc}", file=sys.stderr, flush=True)

            endpoint_summaries[endpoint_key] = {
                "seeds_completed": [r.seed for r in seed_results],
                "seeds_promoted": promoted_seeds,
                "eval_report_path": str(eval_report_path) if eval_report_path else None,
                "leakage_audit_ok": leakage_ok,
                "registry_coverage": str(registry.coverage(endpoint_key)),
            }
            print(f"  Endpoint summary: {endpoint_summaries[endpoint_key]}", flush=True)

    total_elapsed = time.monotonic() - sweep_started
    summary = {
        "n_endpoints": len(ML_ENDPOINTS),
        "n_seeds_per_endpoint": len(FIXED_SEEDS),
        "n_attempted": n_attempted,
        "n_completed": n_completed,
        "n_failed": n_failed,
        "total_elapsed_seconds": round(total_elapsed, 1),
        "endpoint_summaries": endpoint_summaries,
    }
    summary_path = runs_dir / "production_sweep_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n=== SWEEP DONE in {total_elapsed / 60:.1f} min: {n_completed}/{n_attempted} completed, {n_failed} failed ===")
    print(f"Summary: {summary_path}")
    return 0 if n_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
