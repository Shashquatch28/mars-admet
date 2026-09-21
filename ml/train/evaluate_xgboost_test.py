"""
Score the promoted XGBoost artifacts (14 endpoints x 5 seeds) on the held-out TEST set.

No model or calibrator is fit or modified. Reads ``ml/artifacts/`` and the canonical
processed splits; writes ONLY to a separate output directory (default
``ml/runs/test_evaluations/``). It refuses to write into ``ml/artifacts/`` or
``ml/runs/evaluations/`` (the validation-fold reports), and refuses to overwrite an
existing report unless ``--force``.

An endpoint whose artifacts cannot be evaluated is recorded as BLOCKED with the
reason and is never filled in with validation metrics.

Usage
-----
    cd ml && PYTHONPATH=. python train/evaluate_xgboost_test.py
    cd ml && PYTHONPATH=. python train/evaluate_xgboost_test.py --endpoints hia_absorption
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from data.loaders import load_endpoint
from eval.heldout_evaluation import (
    EvaluationBlocked,
    HeldOutEvaluationReport,
    evaluate_endpoint_on_test,
)
from featurize.cache import FeatureCache
from mars_contracts.endpoints import ML_ENDPOINTS

DEFAULT_PREP_ID = "20260830T200000Z"  # the snapshot all 70 sweep runs trained under


def _assert_safe_output(out_dir: Path, ml_root: Path) -> None:
    out = out_dir.resolve()
    for forbidden in (ml_root / "artifacts", ml_root / "runs" / "evaluations"):
        f = forbidden.resolve()
        if out == f or f in out.parents:
            raise SystemExit(
                f"Refusing to write held-out results inside {forbidden}: that would mix "
                "test metrics with promoted artifacts / validation reports."
            )


def main(argv: list[str] | None = None) -> int:
    ml_root = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prep-id", default=DEFAULT_PREP_ID)
    p.add_argument("--artifacts-root", default=str(ml_root / "artifacts"))
    p.add_argument("--cache-root", default=str(ml_root / "data" / "cache"))
    p.add_argument("--out-dir", default=str(ml_root / "runs" / "test_evaluations"))
    p.add_argument("--endpoints", nargs="*", default=None, help="Subset of endpoint keys.")
    p.add_argument("--no-verify-calibrator", action="store_true")
    p.add_argument("--force", action="store_true", help="Overwrite existing held-out reports.")
    args = p.parse_args(argv)

    prep_dir = ml_root / "data" / "processed" / args.prep_id
    out_dir = Path(args.out_dir)
    _assert_safe_output(out_dir, ml_root)
    if not prep_dir.exists():
        print(f"Processed snapshot not found: {prep_dir}", file=sys.stderr)
        return 2

    cache = FeatureCache(Path(args.cache_root))
    keys = args.endpoints or [e.value for e in ML_ENDPOINTS]

    done: dict[str, HeldOutEvaluationReport] = {}
    blocked: dict[str, str] = {}
    for key in keys:
        target = out_dir / f"{key}.json"
        if target.exists() and not args.force:
            print(f"SKIP {key}: {target} exists (use --force)", flush=True)
            continue
        t0 = time.time()
        # Mirror the sweep: DILI was trained on the DILIst-augmented pool. Its TEST set
        # is bit-identical to the base set (verified by tests), so this is the same split.
        use_aug = key == "dili_liver_injury"
        try:
            data = load_endpoint(prep_dir, key, use_augmented_dili=use_aug)
            report = evaluate_endpoint_on_test(
                data,
                endpoint_key=key,
                artifacts_root=args.artifacts_root,
                cache=cache,
                prep_id=args.prep_id,
                test_csv_path=prep_dir / data.dataset_key / "test.csv",
                verify_calibrator_seed=not args.no_verify_calibrator,
                validation_report_path=ml_root / "runs" / "evaluations" / f"{key}.json",
            )
        except EvaluationBlocked as exc:
            blocked[key] = exc.reason
            print(f"BLOCKED {key}: {exc.reason}", flush=True)
            continue
        report.save(target)
        done[key] = report
        agg = report.aggregated_test_raw
        headline = (
            f"AUROC {agg['auroc_mean']:.3f}+-{agg['auroc_std']:.3f}"
            if report.task_type == "classification"
            else f"MAE {agg['mae_mean']:.3f}+-{agg['mae_std']:.3f}"
        )
        print(f"OK {key:24s} n_test={report.n_test:5d} {headline}  ({time.time() - t0:.0f}s)", flush=True)

    summary = {
        "prep_id": args.prep_id,
        "split": "test",
        "evaluated": sorted(done),
        "blocked": blocked,
        "note": "Held-out TEST metrics. Validation-fold metrics live in ml/runs/evaluations/.",
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(f"\nevaluated={len(done)} blocked={len(blocked)} -> {out_dir}")
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
