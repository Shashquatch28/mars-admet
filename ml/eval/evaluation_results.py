"""
Module 11 sections 1-2: the held-out results table, with test-set sampling intervals.

Two tables, kept apart on purpose
---------------------------------
1. **XGBoost, all 14 endpoints.** Every promoted seed model is scored on the untouched test split.
   Per-seed numbers are reported as mean +- sample std over the five seeds (the blueprint's
   protocol). The served score is the mean of the five seeds, so the same split also gives one
   ensemble number per endpoint, and that number gets a 95 % percentile-bootstrap interval over the
   *test molecules*. The two spreads answer different questions: the seed std is training noise; the
   bootstrap interval is how much the number would move on a different draw of test molecules, and
   on the small sets (DILI 96, HIA 117, P-gp 245) it is the larger of the two.
2. **What is served.** The routing table (``ml/serve/routing.json``) sends six endpoints to KERMT.
   Their KERMT five-seed numbers come from the Tier-0 records in git. Per-molecule KERMT test
   predictions are not stored, so no interval is given for them and the table says so.

This module reads artifacts; it fits, selects and tunes nothing. A bootstrap resample that contains a
single class (AUROC undefined) is skipped and the count of skipped resamples is reported.

Usage (from ``ml/``; needs the gitignored artifacts and processed snapshot)
    PYTHONPATH=. python eval/evaluation_results.py --prep-root <.../data/processed> \\
        --artifacts-root <.../artifacts> --cache-root <.../data/cache>
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

from eval.metrics import compute_metrics

DEFAULT_PREP_ID = "20260830T200000Z"
N_BOOT = 2000
BOOT_SEED = 20261024
ML_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ML_ROOT.parent
RESULTS_DIR = REPO_ROOT / "documentation" / "status" / "kermt_tier0_results"
ROUTING = ML_ROOT / "serve" / "routing.json"


@dataclass(frozen=True)
class Interval:
    point: float
    low: float
    high: float
    n_boot: int
    n_skipped: int


@dataclass(frozen=True)
class EndpointResult:
    endpoint: str
    task: str  # "classification" or "regression"
    n_test: int
    n_scored: int
    primary_metric: str  # "AUROC" or "MAE"
    seed_mean: float
    seed_std: float
    ensemble: Interval
    secondary: dict[str, tuple[float, float]]  # name -> (seed mean, seed std)
    # test molecules whose non-acyclic Murcko scaffold also occurs in the training pool, and the ensemble
    # metric on the remaining molecules (None when every scaffold is disjoint or too few molecules remain)
    n_shared_scaffold: int = 0
    scaffold_free: Interval | None = None


def _auroc(y: np.ndarray, p: np.ndarray) -> float:
    return float(roc_auc_score(y, p))


def _mae(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean(np.abs(y - p)))


def bootstrap_interval(
    y: np.ndarray,
    p: np.ndarray,
    metric,
    *,
    n_boot: int = N_BOOT,
    seed: int = BOOT_SEED,
    alpha: float = 0.05,
    needs_both_classes: bool = False,
) -> Interval:
    """Percentile bootstrap over test molecules. Resamples with one class are skipped for AUROC."""
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    rng = np.random.default_rng(seed)
    n = len(y)
    values: list[float] = []
    skipped = 0
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        yb = y[idx]
        if needs_both_classes and (yb.min() == yb.max()):
            skipped += 1
            continue
        values.append(metric(yb, p[idx]))
    if not values:
        raise ValueError("every bootstrap resample was degenerate")
    lo, hi = np.percentile(values, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return Interval(metric(y, p), float(lo), float(hi), len(values), skipped)


def score_endpoint(
    endpoint: str,
    *,
    task: str,
    y_test: np.ndarray,
    seed_preds: list[np.ndarray],
    n_test: int,
    shares_scaffold: np.ndarray | None = None,
) -> EndpointResult:
    """Per-seed and ensemble metrics from the seeds' raw test predictions (NaN = could not be scored).

    ``shares_scaffold`` (one bool per test molecule) marks molecules whose non-acyclic Murcko scaffold also
    occurs in the training pool; the ensemble metric is then repeated on the molecules that do not.
    """
    stacked = np.vstack(seed_preds)
    scored = ~np.isnan(stacked).any(axis=0)
    y_all = np.asarray(y_test, dtype=float)
    y = y_all[scored]
    per_seed = [compute_metrics(y, preds[scored], _task(task)) for preds in seed_preds]
    ens = stacked[:, scored].mean(axis=0)
    if task == "classification":
        aurocs = np.array([m.auroc for m in per_seed])
        secondary = {
            name: _mean_std(np.array([getattr(m, attr) for m in per_seed]))
            for name, attr in (("AUPRC", "auprc"), ("Brier", "brier_score"), ("ECE", "ece"))
        }
        interval = bootstrap_interval(y, ens, _auroc, needs_both_classes=True)
        primary, (mean, std) = "AUROC", _mean_std(aurocs)
    else:
        maes = np.array([m.mae for m in per_seed])
        secondary = {}
        interval = bootstrap_interval(y, ens, _mae)
        primary, (mean, std) = "MAE", _mean_std(maes)
    n_shared = 0
    free: Interval | None = None
    if shares_scaffold is not None:
        shared = np.asarray(shares_scaffold, dtype=bool)
        n_shared = int(shared.sum())
        keep = scored & ~shared
        if n_shared and keep.sum() >= 20:
            try:
                if task == "classification":
                    free = bootstrap_interval(
                        y_all[keep], stacked[:, keep].mean(axis=0), _auroc, needs_both_classes=True
                    )
                else:
                    free = bootstrap_interval(y_all[keep], stacked[:, keep].mean(axis=0), _mae)
            except ValueError:
                free = None
    return EndpointResult(
        endpoint, task, n_test, int(scored.sum()), primary, mean, std, interval, secondary, n_shared, free
    )


def _task(task: str):
    from mars_contracts.endpoints import TaskType

    return TaskType.CLASSIFICATION if task == "classification" else TaskType.REGRESSION


def _mean_std(values: np.ndarray) -> tuple[float, float]:
    return float(values.mean()), float(values.std(ddof=1)) if len(values) > 1 else float("nan")


def _kermt_primary(results_dir: Path) -> dict[str, tuple[str, float, float, int]]:
    """endpoint -> (metric, mean, std, n_test) from the Tier-0 records in git, for every arm that has five seeds."""
    from eval import tier0_classification, tier0_regression

    out: dict[str, tuple[str, float, float, int]] = {}
    for arm in sorted(p.name for p in results_dir.iterdir() if p.is_dir()):
        try:
            if arm.endswith("__reg"):
                for r in tier0_regression.load_arm(results_dir, arm):
                    out[r.endpoint] = ("MAE", r.mae_mean, r.mae_std, r.n_test)
            else:
                for endpoint, n_test, raw in tier0_classification.load_arm(results_dir, arm):
                    out[endpoint] = ("AUROC", raw["auroc_mean"], raw.get("auroc_std"), n_test)
        except (ValueError, KeyError, FileNotFoundError):
            continue
    return out


def _fmt(mean: float, std: float | None, digits: int = 3) -> str:
    if std is None or not np.isfinite(std):
        return f"{mean:.{digits}f}"
    return f"{mean:.{digits}f} ± {std:.{digits}f}"


def render_markdown(results: list[EndpointResult], routing: dict, kermt: dict, *, today: str, prep_id: str) -> str:
    lines = [
        "# Held-out results (Module 11 sections 1-2)",
        "",
        f"Generated {today} by `ml/eval/evaluation_results.py` on processed snapshot `{prep_id}`. Test split only: "
        "nothing here was fit, selected or tuned on it. Raw (uncalibrated) scores, as served.",
        "",
        "## Table 1: XGBoost on all 14 endpoints",
        "",
        "*Seeds* is mean ± sample std over the five seed models (training noise). *Ensemble* is the served "
        "score, the mean of the five seeds, with a 95 % percentile bootstrap interval over the test molecules "
        f"({N_BOOT} resamples; sampling noise). Rank-based classification metrics need both classes in a "
        "resample; resamples without both are skipped and counted.",
        "",
        "| endpoint | n_test | metric | seeds | ensemble [95 % bootstrap] | resamples used | test molecules sharing a scaffold with training | ensemble on the rest [95 % bootstrap] |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        iv = r.ensemble
        if r.n_shared_scaffold:
            share = f"{r.n_shared_scaffold} ({r.n_shared_scaffold / r.n_test:.1%})"
            fr = r.scaffold_free
            rest = f"{fr.point:.3f} [{fr.low:.3f}, {fr.high:.3f}]" if fr else "too few left"
        else:
            share, rest = "0", "-"
        lines.append(
            f"| {r.endpoint} | {r.n_test} | {r.primary_metric} | {_fmt(r.seed_mean, r.seed_std)} | "
            f"{iv.point:.3f} [{iv.low:.3f}, {iv.high:.3f}] | {iv.n_boot} of {iv.n_boot + iv.n_skipped} | {share} | {rest} |"
        )
    lines += [
        "",
        "The last two columns are the scaffold check of `self_audit.md` made visible. A test molecule counts as "
        "sharing when its non-acyclic Murcko scaffold also occurs among the training molecules. For the endpoints "
        "that adopt TDC's benchmark split the overlap is inherited from TDC's split (recorded by M1 in each "
        "`split_report.json`) and is small. DILI is different: the base split has none, and the DILIst-augmented "
        "training pool adds molecules that share scaffolds with a quarter of the test set (Module 1 section 6 "
        "asks for a re-check after merging; the count of 19 was recorded at augmentation time and called expected for "
        "a small chemical space, `mars-status_M1.md` H-5, and the pool was used as it stood). The served DILI model "
        "was trained on that pool, so a number measured on the molecules that share no scaffold with it is the one "
        "to read.",
    ]
    clf = [r for r in results if r.task == "classification"]
    lines += [
        "",
        "Classification, the other metrics (mean ± std over seeds; Brier and ECE are on raw scores, which are "
        "not validated probabilities - `xgboost_c0_raw_vs_calibrated.md`):",
        "",
        "| endpoint | AUPRC | Brier | ECE |",
        "|---|---|---|---|",
    ]
    for r in clf:
        s = r.secondary
        lines.append(
            f"| {r.endpoint} | {_fmt(*s['AUPRC'])} | {_fmt(*s['Brier'])} | {_fmt(*s['ECE'])} |"
        )
    lines += [
        "",
        "## Table 2: what is served",
        "",
        "The routing table (`ml/serve/routing.json`) picks KERMT or XGBoost per endpoint. For an endpoint routed to "
        "KERMT the number is the KERMT Tier-0 five-seed mean ± std from the records in git. No interval is "
        "given for KERMT: per-molecule KERMT test predictions are not stored, so a bootstrap needs the KERMT "
        "service run over the test set.",
        "",
        "| endpoint | served by | metric | served model: seeds | XGBoost ensemble [95 % bootstrap] |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        model = routing["endpoints"].get(r.endpoint, {}).get("model", routing.get("default", "xgboost"))
        xgb = f"{r.ensemble.point:.3f} [{r.ensemble.low:.3f}, {r.ensemble.high:.3f}]"
        if model == "kermt" and r.endpoint in kermt:
            metric, mean, std, n_test = kermt[r.endpoint]
            served = f"{_fmt(mean, std)}" + ("" if n_test == r.n_test else f" (n_test {n_test}!)")
        else:
            served = f"{_fmt(r.seed_mean, r.seed_std)} (XGBoost, as Table 1)"
        lines.append(f"| {r.endpoint} | {model} | {r.primary_metric} | {served} | {xgb} |")
    lines += [
        "",
        "## How to read this, and what it does not show",
        "",
        "- The routing rule chose KERMT where it beat XGBoost on these same test records "
        "(`kermt_routing_evidence.md`), so the six KERMT numbers carry a selection effect and are likely "
        "optimistic relative to a fresh split. The XGBoost column is not selected on the test set.",
        "- The KERMT and XGBoost pools differ; see `kermt_vs_xgboost_pool_matched.md` for the like-for-like rows "
        "and `significance.md` for how little those rows can support.",
        "- The test split is scaffold-based. Performance on molecules unlike the training set is lower; "
        "that is what the applicability-domain flag is for. Module 11 section 5.5 (Lo-Hi, DataSAIL) is not run.",
        "- Small test sets give wide intervals (DILI 96 molecules, HIA 117, P-gp 245). A point estimate on "
        "those is not a precise number.",
        "- These are intervals for the number on this test set. They say nothing about drift, new chemistry or "
        "assay differences.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--prep-id", default=DEFAULT_PREP_ID)
    p.add_argument("--prep-root", default=str(ML_ROOT / "data" / "processed"))
    p.add_argument("--artifacts-root", default=str(ML_ROOT / "artifacts"))
    p.add_argument("--cache-root", default=str(ML_ROOT / "data" / "cache"))
    p.add_argument("--results-dir", default=str(RESULTS_DIR))
    p.add_argument("--out-md", default=str(REPO_ROOT / "documentation" / "status" / "evaluation_results.md"))
    p.add_argument("--out-json", default=str(REPO_ROOT / "documentation" / "status" / "evaluation_results.json"))
    args = p.parse_args(argv)

    from configs.experiment_config import FIXED_SEEDS
    from data.loaders import load_endpoint
    from featurize.cache import FeatureCache
    from featurize.scaffold import murcko_scaffold_from_smiles
    from mars_contracts.endpoints import ML_ENDPOINTS
    from models.xgboost_model import XGBoostModel

    prep_dir = Path(args.prep_root) / args.prep_id
    if not prep_dir.exists():
        print(f"Processed snapshot not found: {prep_dir}", file=sys.stderr)
        return 2
    cache = FeatureCache(Path(args.cache_root))
    results: list[EndpointResult] = []
    for ep in ML_ENDPOINTS:
        key = ep.value
        data = load_endpoint(prep_dir, key, use_augmented_dili=(key == "dili_liver_injury"))
        task = "classification" if data.task_type.value == "classification" else "regression"
        smiles = data.test["standardized_smiles"].tolist()
        y = data.test["label"].astype(float).to_numpy()
        preds = []
        for seed in FIXED_SEEDS:
            model = XGBoostModel.load_with_cache(Path(args.artifacts_root) / key / f"seed_{seed}", cache)
            preds.append(np.asarray(model.predict(smiles), dtype=float))
        tv_scaffolds = {murcko_scaffold_from_smiles(s) for s in data.train_val["standardized_smiles"]} - {""}
        shares = np.array([murcko_scaffold_from_smiles(s) in tv_scaffolds for s in smiles], dtype=bool)
        res = score_endpoint(
            key, task=task, y_test=y, seed_preds=preds, n_test=len(smiles), shares_scaffold=shares
        )
        results.append(res)
        iv = res.ensemble
        print(f"{key:26s} n={res.n_test:5d} {res.primary_metric} {res.seed_mean:.3f}±{res.seed_std:.3f} "
              f"ens {iv.point:.3f} [{iv.low:.3f},{iv.high:.3f}]", flush=True)

    routing = json.loads(ROUTING.read_text(encoding="utf-8"))
    kermt = _kermt_primary(Path(args.results_dir))
    md = render_markdown(results, routing, kermt, today=date.today().isoformat(), prep_id=args.prep_id)
    Path(args.out_md).write_text(md, encoding="utf-8", newline="\n")
    Path(args.out_json).write_text(
        json.dumps(
            {
                "prep_id": args.prep_id,
                "n_boot": N_BOOT,
                "boot_seed": BOOT_SEED,
                "endpoints": {
                    r.endpoint: {
                        "task": r.task,
                        "n_test": r.n_test,
                        "n_scored": r.n_scored,
                        "metric": r.primary_metric,
                        "seed_mean": r.seed_mean,
                        "seed_std": r.seed_std,
                        "ensemble": r.ensemble.point,
                        "ci_low": r.ensemble.low,
                        "ci_high": r.ensemble.high,
                        "n_shared_scaffold": r.n_shared_scaffold,
                        "scaffold_free": (
                            None
                            if r.scaffold_free is None
                            else [r.scaffold_free.point, r.scaffold_free.low, r.scaffold_free.high]
                        ),
                        "secondary": {k: list(v) for k, v in r.secondary.items()},
                    }
                    for r in results
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"\nwrote {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
