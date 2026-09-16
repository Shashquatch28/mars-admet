"""
Tests for ml/eval/evaluate.py.

Most tests use synthetic SeedResult objects (fast, no training). One
integration test runs two real seeds against M1 AMES data end-to-end.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from eval.evaluate import EvaluationReport, build_evaluation_report
from eval.metrics import ClassificationMetrics, RegressionMetrics
from mars_contracts.endpoints import TaskType
from train.train_xgboost import SeedResult


def _fake_clf_metrics(auroc: float) -> ClassificationMetrics:
    return ClassificationMetrics(
        auroc=auroc, auprc=auroc, brier_score=0.1, ece=0.05, n_samples=100, n_positive=50, auroc_valid=True
    )


def _fake_seed_result(seed: int, auroc: float) -> SeedResult:
    return SeedResult(
        seed=seed,
        val_metrics=_fake_clf_metrics(auroc),
        model_path=Path("/fake/path"),
        run_id=f"xgb_fake_endpoint_seed{seed}_00000000T000000Z",
        n_train=100,
        n_val=20,
        n_dropped_train=0,
        n_dropped_val=0,
        best_iteration=50,
    )


# ---------------------------------------------------------------------------- #
# build_evaluation_report — synthetic
# ---------------------------------------------------------------------------- #


def test_build_evaluation_report_basic():
    results = [_fake_seed_result(s, auroc=0.7 + 0.01 * s) for s in range(5)]
    report = build_evaluation_report(
        results,
        endpoint_key="fake_endpoint",
        model_family="xgboost",
        prep_id="test-prep",
        task_type=TaskType.CLASSIFICATION,
    )
    assert isinstance(report, EvaluationReport)
    assert report.seeds == [0, 1, 2, 3, 4]
    assert len(report.run_ids) == 5
    assert len(report.per_seed_metrics) == 5
    assert "auroc_mean" in report.aggregated
    assert "auroc_std" in report.aggregated
    assert report.task_type == "classification"


def test_build_evaluation_report_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        build_evaluation_report(
            [], endpoint_key="e", model_family="xgboost", prep_id="p", task_type=TaskType.CLASSIFICATION
        )


def test_build_evaluation_report_duplicate_seeds_raises():
    results = [_fake_seed_result(0, 0.7), _fake_seed_result(0, 0.8)]
    with pytest.raises(ValueError, match="Duplicate seeds"):
        build_evaluation_report(
            results, endpoint_key="e", model_family="xgboost", prep_id="p", task_type=TaskType.CLASSIFICATION
        )


def test_build_evaluation_report_regression():
    results = [
        SeedResult(
            seed=s,
            val_metrics=RegressionMetrics(mae=0.5 + 0.01 * s, n_samples=50),
            model_path=Path("/fake"),
            run_id=f"xgb_fake_seed{s}",
            n_train=100,
            n_val=20,
            n_dropped_train=0,
            n_dropped_val=0,
            best_iteration=None,
        )
        for s in range(3)
    ]
    report = build_evaluation_report(
        results,
        endpoint_key="fake_reg_endpoint",
        model_family="xgboost",
        prep_id="test-prep",
        task_type=TaskType.REGRESSION,
    )
    assert "mae_mean" in report.aggregated
    assert report.task_type == "regression"


def test_evaluation_report_save_load_roundtrip(tmp_path):
    results = [_fake_seed_result(s, 0.7) for s in range(3)]
    report = build_evaluation_report(
        results, endpoint_key="e", model_family="xgboost", prep_id="p", task_type=TaskType.CLASSIFICATION
    )
    path = tmp_path / "report.json"
    report.save(path)
    loaded = EvaluationReport.load(path)
    assert loaded.endpoint_key == report.endpoint_key
    assert loaded.seeds == report.seeds
    assert loaded.aggregated == report.aggregated
    assert loaded.per_seed_metrics == report.per_seed_metrics


# ---------------------------------------------------------------------------- #
# Integration: two real seeds against M1 AMES data
# ---------------------------------------------------------------------------- #

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "ml" / "data"


def _newest_prep_dir() -> Path | None:
    root = DATA / "processed"
    if not root.exists():
        return None
    dirs = sorted(p for p in root.iterdir() if p.is_dir())
    return dirs[-1] if dirs else None


PREP_DIR = _newest_prep_dir()


def test_integration_two_real_seeds(tmp_path):
    if PREP_DIR is None:
        pytest.skip("no processed outputs")
    pytest.importorskip("xgboost", reason="xgboost not installed in this environment")

    from configs.experiment_config import ExperimentConfig
    from data.loaders import load_endpoint
    from featurize.cache import FeatureCache
    from train.train_xgboost import train_one_seed

    endpoint_data = load_endpoint(PREP_DIR, "ames_mutagenicity")
    config = ExperimentConfig(
        endpoint="ames_mutagenicity", model_family="xgboost", seed=0, prep_id=PREP_DIR.name
    )
    cache = FeatureCache(DATA / "cache")

    results = [
        train_one_seed(
            endpoint_data, config, cache, seed, runs_dir=tmp_path / "runs", repo_root=REPO
        )
        for seed in (0, 1)
    ]

    report = build_evaluation_report(
        results,
        endpoint_key="ames_mutagenicity",
        model_family="xgboost",
        prep_id=PREP_DIR.name,
        task_type=endpoint_data.task_type,
    )
    assert report.seeds == [0, 1]
    assert report.aggregated["n_seeds"] == 2.0
    assert 0.0 <= report.aggregated["auroc_mean"] <= 1.0
