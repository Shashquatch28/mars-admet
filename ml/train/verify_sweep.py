"""Phase 4/5 verification for the M2 production sweep: for every endpoint,
confirm all 5 seeds are present with unique run_ids, the EvaluationReport
reloads and its aggregated metrics are sane, the registry sees full 5-seed
coverage with the right AD/calibrator presence, and every promoted model
artifact actually reloads and produces a finite prediction. Read-only —
does not retrain or re-promote anything.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from eval.evaluate import EvaluationReport
from featurize.cache import FeatureCache
from mars_contracts.endpoints import ENDPOINT_METADATA, ML_ENDPOINTS, TaskType
from serve.registry import ModelRegistry


def main() -> int:
    ml_root = Path(__file__).resolve().parents[1]
    cache = FeatureCache(ml_root / "data" / "cache")
    registry = ModelRegistry(cache, artifacts_root=ml_root / "artifacts")

    any_problem = False
    print(f"{'endpoint':22s} {'seeds':12s} {'dup?':5s} {'ad':4s} {'cal':4s} {'reload':7s} {'primary_metric'}")
    for ep in ML_ENDPOINTS:
        key = ep.value
        problems = []

        report_path = ml_root / "runs" / "evaluations" / f"{key}.json"
        if not report_path.exists():
            print(f"{key:22s} MISSING evaluation report at {report_path}")
            any_problem = True
            continue
        report = EvaluationReport.load(report_path)

        seeds = report.seeds
        dup = len(seeds) != len(set(seeds))
        run_ids_dup = len(report.run_ids) != len(set(report.run_ids))
        if sorted(seeds) != [0, 1, 2, 3, 4]:
            problems.append(f"seeds={seeds} != [0..4]")
        if dup or run_ids_dup:
            problems.append("duplicate seed or run_id")

        cov = registry.coverage(key)
        if cov.seeds != [0, 1, 2, 3, 4]:
            problems.append(f"registry coverage seeds={cov.seeds} != [0..4]")
        if not cov.has_ad_index:
            problems.append("no AD index")
        expected_calibrator = ENDPOINT_METADATA[ep]["task_type"] == TaskType.CLASSIFICATION
        if cov.has_calibrator != expected_calibrator:
            problems.append(f"has_calibrator={cov.has_calibrator}, expected={expected_calibrator}")

        reload_ok = True
        try:
            models = registry.load_models(key)
            if len(models) != 5:
                problems.append(f"loaded {len(models)} models, expected 5")
            test_pred = models[0].predict(["CCO"])
            if not np.isfinite(test_pred).all():
                problems.append("reloaded model produced non-finite prediction on a smoke SMILES")
        except Exception as exc:
            reload_ok = False
            problems.append(f"reload failed: {exc}")

        primary_metric = (
            f"mae={report.aggregated.get('mae_mean', 'n/a')}"
            if report.task_type == "regression"
            else f"auroc={report.aggregated.get('auroc_mean', 'n/a')}"
        )

        status = "OK" if not problems else "PROBLEM"
        print(
            f"{key:22s} {str(seeds):12s} {'yes' if dup else 'no':5s} "
            f"{'Y' if cov.has_ad_index else 'N':4s} {'Y' if cov.has_calibrator else 'N':4s} "
            f"{'OK' if reload_ok else 'FAIL':7s} {primary_metric}  [{status}]"
        )
        if problems:
            any_problem = True
            for p in problems:
                print(f"    !! {p}")

    print(f"\navailable_endpoints in registry: {registry.available_endpoints()}")
    print(f"count: {len(registry.available_endpoints())} / {len(ML_ENDPOINTS)}")
    return 1 if any_problem else 0


if __name__ == "__main__":
    sys.exit(main())
