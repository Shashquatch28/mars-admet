"""
Unit tests for ml/eval/metrics.py.

All synthetic — no disk I/O, no processed data required.
"""

from __future__ import annotations

import warnings

import numpy as np
import pytest
from eval.metrics import (
    ClassificationMetrics,
    RegressionMetrics,
    aggregate_seed_metrics,
    compute_classification_metrics,
    compute_metrics,
    compute_regression_metrics,
    expected_calibration_error,
    format_mean_std,
)
from mars_contracts.endpoints import TaskType

# ---------------------------------------------------------------------------- #
# ECE
# ---------------------------------------------------------------------------- #


def test_ece_perfectly_calibrated():
    # All predictions = 0.5, 50 % positive → ECE = 0
    n = 200
    y_true = np.array([0, 1] * (n // 2))
    y_prob = np.full(n, 0.5)
    ece = expected_calibration_error(y_true, y_prob)
    assert ece == pytest.approx(0.0, abs=1e-9)


def test_ece_overconfident():
    # All predictions = 0.9, 50 % positive → ECE = |0.5 − 0.9| = 0.4
    y_true = np.array([0, 1] * 50)
    y_prob = np.full(100, 0.9)
    ece = expected_calibration_error(y_true, y_prob)
    assert ece == pytest.approx(0.4, abs=1e-6)


def test_ece_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        expected_calibration_error(np.array([]), np.array([]))


def test_ece_perfect_predictor():
    # Perfect predictor: probs = labels → ECE = 0
    y_true = np.array([0, 0, 1, 1])
    y_prob = np.array([0.0, 0.0, 1.0, 1.0])
    ece = expected_calibration_error(y_true, y_prob)
    assert ece == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------- #
# Classification metrics
# ---------------------------------------------------------------------------- #


def test_auroc_perfect_classifier():
    y_true = np.array([0, 0, 1, 1])
    y_prob = np.array([0.1, 0.2, 0.8, 0.9])
    m = compute_classification_metrics(y_true, y_prob)
    assert m.auroc == pytest.approx(1.0)
    assert m.auroc_valid


def test_auroc_worst_classifier():
    # Reversed labels → AUROC = 0
    y_true = np.array([0, 0, 1, 1])
    y_prob = np.array([0.9, 0.8, 0.1, 0.2])
    m = compute_classification_metrics(y_true, y_prob)
    assert m.auroc == pytest.approx(0.0)


def test_auroc_random_classifier():
    rng = np.random.default_rng(42)
    y_true = rng.integers(0, 2, 200)
    y_prob = rng.uniform(0, 1, 200)
    m = compute_classification_metrics(y_true, y_prob)
    assert 0.0 <= m.auroc <= 1.0


def test_single_class_returns_nan_with_warning():
    y_true = np.array([1, 1, 1, 1])
    y_prob = np.array([0.8, 0.9, 0.7, 0.6])
    with pytest.warns(UserWarning, match="class"):
        m = compute_classification_metrics(y_true, y_prob)
    assert np.isnan(m.auroc)
    assert np.isnan(m.auprc)
    assert not m.auroc_valid
    # Brier and ECE should still be finite
    assert np.isfinite(m.brier_score)
    assert np.isfinite(m.ece)


def test_brier_score_perfect():
    y_true = np.array([0, 1])
    y_prob = np.array([0.0, 1.0])
    m = compute_classification_metrics(y_true, y_prob)
    assert m.brier_score == pytest.approx(0.0)


def test_brier_score_worst():
    y_true = np.array([0, 1])
    y_prob = np.array([1.0, 0.0])
    m = compute_classification_metrics(y_true, y_prob)
    assert m.brier_score == pytest.approx(1.0)


def test_n_samples_and_n_positive():
    y_true = np.array([0, 0, 1])
    y_prob = np.array([0.2, 0.3, 0.8])
    m = compute_classification_metrics(y_true, y_prob)
    assert m.n_samples == 3
    assert m.n_positive == 1


def test_classification_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        compute_classification_metrics(np.array([]), np.array([]))


def test_classification_length_mismatch_raises():
    with pytest.raises(ValueError, match="mismatch"):
        compute_classification_metrics(np.array([0, 1]), np.array([0.5]))


def test_prob_out_of_range_raises():
    with pytest.raises(ValueError, match="probabilities"):
        compute_classification_metrics(np.array([0, 1]), np.array([0.5, 1.5]))


def test_prob_negative_raises():
    with pytest.raises(ValueError, match="probabilities"):
        compute_classification_metrics(np.array([0, 1]), np.array([-0.1, 0.9]))


# ---------------------------------------------------------------------------- #
# Regression metrics
# ---------------------------------------------------------------------------- #


def test_mae_exact():
    y_true = np.array([1.0, 2.0, 3.0])
    y_pred = np.array([1.5, 2.5, 3.5])
    m = compute_regression_metrics(y_true, y_pred)
    assert m.mae == pytest.approx(0.5)
    assert m.n_samples == 3


def test_mae_zero():
    y = np.array([1.0, 2.0, 3.0])
    m = compute_regression_metrics(y, y)
    assert m.mae == pytest.approx(0.0)


def test_regression_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        compute_regression_metrics(np.array([]), np.array([]))


def test_regression_length_mismatch_raises():
    with pytest.raises(ValueError, match="mismatch"):
        compute_regression_metrics(np.array([1.0, 2.0]), np.array([1.0]))


# ---------------------------------------------------------------------------- #
# compute_metrics dispatch
# ---------------------------------------------------------------------------- #


def test_dispatch_classification():
    y_true = np.array([0, 1, 0, 1])
    y_prob = np.array([0.2, 0.8, 0.3, 0.7])
    m = compute_metrics(y_true, y_prob, TaskType.CLASSIFICATION)
    assert isinstance(m, ClassificationMetrics)


def test_dispatch_regression():
    y_true = np.array([1.0, 2.0])
    y_pred = np.array([1.1, 2.1])
    m = compute_metrics(y_true, y_pred, TaskType.REGRESSION)
    assert isinstance(m, RegressionMetrics)


def test_dispatch_rule_based_raises():
    with pytest.raises(ValueError, match="Unsupported task_type"):
        compute_metrics(np.array([1.0]), np.array([1.0]), TaskType.RULE_BASED)


# ---------------------------------------------------------------------------- #
# aggregate_seed_metrics
# ---------------------------------------------------------------------------- #


def test_aggregate_classification():
    def _m(seed: int) -> ClassificationMetrics:
        rng = np.random.default_rng(seed)
        y_true = rng.integers(0, 2, 100)
        y_prob = rng.uniform(0, 1, 100)
        return compute_classification_metrics(y_true, y_prob)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        per_seed = [_m(s) for s in range(5)]

    agg = aggregate_seed_metrics(per_seed)
    assert "auroc_mean" in agg
    assert "auroc_std" in agg
    assert "auprc_mean" in agg
    assert "brier_score_mean" in agg
    assert "ece_mean" in agg
    assert 0.0 <= agg["auroc_mean"] <= 1.0
    assert agg["auroc_std"] >= 0.0


def test_aggregate_regression():
    m1 = compute_regression_metrics(np.array([1.0, 2.0]), np.array([1.1, 2.1]))
    m2 = compute_regression_metrics(np.array([1.0, 2.0]), np.array([1.3, 2.3]))
    agg = aggregate_seed_metrics([m1, m2])
    assert "mae_mean" in agg
    assert "mae_std" in agg
    assert agg["mae_mean"] == pytest.approx(0.2)


def test_aggregate_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        aggregate_seed_metrics([])


def test_aggregate_nan_exclusion():
    # Inject a NaN result (single-class fold) and verify mean is over valid seeds only
    m_good = compute_classification_metrics(
        np.array([0, 1, 0, 1]), np.array([0.2, 0.8, 0.3, 0.7])
    )
    m_nan = ClassificationMetrics(
        auroc=float("nan"),
        auprc=float("nan"),
        brier_score=0.25,
        ece=0.1,
        n_samples=4,
        n_positive=4,  # only one class
        auroc_valid=False,
    )
    agg = aggregate_seed_metrics([m_good, m_nan])
    # NaN excluded → mean equals the single valid seed's value
    assert agg["auroc_mean"] == pytest.approx(m_good.auroc)
    assert agg["n_seeds"] == 2.0


# ---------------------------------------------------------------------------- #
# aggregate_seed_metrics: std is UNDEFINED (None) below two valid values, never 0.0
# ---------------------------------------------------------------------------- #


def _good_classification() -> ClassificationMetrics:
    return compute_classification_metrics(np.array([0, 1, 0, 1]), np.array([0.2, 0.8, 0.3, 0.7]))


def _nan_classification() -> ClassificationMetrics:
    return ClassificationMetrics(
        auroc=float("nan"),
        auprc=float("nan"),
        brier_score=0.25,
        ece=0.1,
        n_samples=4,
        n_positive=4,
        auroc_valid=False,
    )


def test_aggregate_single_seed_std_is_undefined_not_zero():
    m = _good_classification()
    agg = aggregate_seed_metrics([m])
    assert agg["n_seeds"] == 1.0
    for k in ("auroc", "auprc", "brier_score", "ece"):
        assert agg[f"{k}_std"] is None, f"{k}_std must be undefined for one seed, not 0.0"
        assert agg[f"{k}_mean"] == pytest.approx(getattr(m, k))


def test_aggregate_single_seed_regression_std_is_undefined():
    m = compute_regression_metrics(np.array([1.0, 2.0]), np.array([1.1, 2.1]))
    agg = aggregate_seed_metrics([m])
    assert agg["n_seeds"] == 1.0
    assert agg["mae_std"] is None
    assert agg["mae_mean"] == pytest.approx(0.1)


def test_aggregate_two_seeds_std_is_the_sample_std():
    m1 = compute_regression_metrics(np.array([1.0, 2.0]), np.array([1.1, 2.1]))
    m2 = compute_regression_metrics(np.array([1.0, 2.0]), np.array([1.3, 2.3]))
    agg = aggregate_seed_metrics([m1, m2])
    assert agg["mae_std"] == pytest.approx(np.std([m1.mae, m2.mae], ddof=1))
    assert agg["mae_std"] > 0.0


def test_aggregate_nan_exclusion_makes_std_undefined_only_where_one_value_is_valid():
    good, bad = _good_classification(), _nan_classification()
    agg = aggregate_seed_metrics([good, bad])
    # auroc/auprc: only one valid value -> mean is that value, std undefined
    assert agg["auroc_mean"] == pytest.approx(good.auroc)
    assert agg["auroc_std"] is None
    assert agg["auprc_std"] is None
    # brier/ece: both seeds contribute a finite value -> an ordinary sample std
    assert agg["brier_score_std"] == pytest.approx(np.std([good.brier_score, bad.brier_score], ddof=1))
    assert agg["ece_std"] == pytest.approx(np.std([good.ece, bad.ece], ddof=1))


def test_aggregate_all_nan_has_nan_mean_and_no_std():
    agg = aggregate_seed_metrics([_nan_classification(), _nan_classification()])
    assert np.isnan(agg["auroc_mean"])
    assert agg["auroc_std"] is None


def test_format_mean_std():
    assert format_mean_std(0.8512, 0.0123) == "0.851+-0.012"
    assert format_mean_std(0.8512, None) == "0.851+-n/a"
    assert format_mean_std(0.8512, 0.0123, digits=2) == "0.85+-0.01"


def test_single_seed_report_round_trips_with_a_null_std(tmp_path):
    from eval.evaluate import EvaluationReport

    agg = aggregate_seed_metrics([compute_regression_metrics(np.array([1.0, 2.0]), np.array([1.1, 2.1]))])
    report = EvaluationReport(
        endpoint_key="clearance_microsomal",
        model_family="kermt_single",
        prep_id="test-prep",
        task_type="regression",
        seeds=[0],
        run_ids=["run0"],
        per_seed_metrics=[],
        aggregated=agg,
    )
    path = tmp_path / "report.json"
    report.save(path)
    assert '"mae_std": null' in path.read_text(encoding="utf-8")
    assert EvaluationReport.load(path).aggregated["mae_std"] is None
