"""Tests for ml/eval/cluster_eval.py — cluster predictions -> per-endpoint results."""

from __future__ import annotations

import numpy as np
import pytest
from eval.cluster_eval import (
    ClusterSeedResult,
    cluster_results_to_endpoint_reports,
    decompose_cluster_predictions,
)
from eval.evaluate import EvaluationReport
from eval.metrics import ClassificationMetrics, RegressionMetrics
from mars_contracts.endpoints import TaskType

CYP = "cyp3a4_inhibition"
CLR = "clearance_microsomal"
KEYS = [CYP, CLR]
TYPES = {CYP: TaskType.CLASSIFICATION, CLR: TaskType.REGRESSION}


def _y_true() -> np.ndarray:
    # Row 2 has no CYP label; row 0 has no clearance label.
    return np.array(
        [
            [1.0, np.nan],
            [0.0, 10.0],
            [np.nan, 20.0],
            [1.0, 30.0],
            [0.0, 40.0],
        ]
    )


def _y_pred() -> np.ndarray:
    return np.array(
        [
            [0.9, 11.0],
            [0.2, 11.0],
            [0.7, 21.0],
            [0.8, 29.0],
            [0.1, 41.0],
        ]
    )


def test_each_column_is_scored_with_its_own_task_type():
    out = decompose_cluster_predictions(_y_true(), _y_pred(), KEYS, TYPES)
    assert isinstance(out[CYP], ClassificationMetrics)
    assert isinstance(out[CLR], RegressionMetrics)


def test_missing_labels_are_masked_not_counted():
    out = decompose_cluster_predictions(_y_true(), _y_pred(), KEYS, TYPES)
    # 4 CYP labels (row 2 missing), 4 clearance labels (row 0 missing).
    assert out[CYP].n_samples == 4
    assert out[CLR].n_samples == 4


def test_masking_uses_each_columns_own_labels_not_a_shared_row_mask():
    """A shared mask would drop rows 0 and 2 from BOTH columns, giving n=3."""
    out = decompose_cluster_predictions(_y_true(), _y_pred(), KEYS, TYPES)
    assert out[CYP].n_samples == 4
    assert out[CLR].n_samples == 4


def test_regression_mae_ignores_the_unlabelled_row():
    out = decompose_cluster_predictions(_y_true(), _y_pred(), KEYS, TYPES)
    # Labelled clearance rows: |11-10| + |21-20| + |29-30| + |41-40| = 4 -> MAE 1.0
    assert out[CLR].mae == pytest.approx(1.0)


def test_nan_predictions_are_dropped_too():
    """A model may decline a column (e.g. a logits-only path leaves reg NaN)."""
    y_pred = _y_pred().copy()
    y_pred[1, 1] = np.nan
    out = decompose_cluster_predictions(_y_true(), y_pred, KEYS, TYPES)
    assert out[CLR].n_samples == 3


def test_column_with_no_usable_rows_raises():
    y_true = _y_true().copy()
    y_true[:, 0] = np.nan
    with pytest.raises(ValueError, match="no rows with both a label"):
        decompose_cluster_predictions(y_true, _y_pred(), KEYS, TYPES)


def test_shape_mismatches_are_rejected():
    with pytest.raises(ValueError, match="shape mismatch"):
        decompose_cluster_predictions(_y_true(), _y_pred()[:3], KEYS, TYPES)
    with pytest.raises(ValueError, match="must be 2-D"):
        decompose_cluster_predictions(np.array([1.0, 0.0]), np.array([0.5, 0.5]), KEYS, TYPES)
    with pytest.raises(ValueError, match="endpoint_keys were given"):
        decompose_cluster_predictions(_y_true(), _y_pred(), [CYP], TYPES)


def _seed_result(seed: int) -> ClusterSeedResult:
    return ClusterSeedResult(
        seed=seed,
        run_id=f"run-{seed}",
        model_path=f"/artifacts/seed_{seed}",
        cluster_key="metabolism__mixed",
        endpoint_keys=list(KEYS),
        per_endpoint_metrics=decompose_cluster_predictions(
            _y_true(), _y_pred(), KEYS, TYPES
        ),
        n_train=100,
        n_val=20,
        per_endpoint_n_labeled={CYP: 4, CLR: 4},
        log_sigma_final={CYP: 0.1, CLR: -0.2},
    )


def test_fan_out_produces_one_report_per_endpoint():
    results = [_seed_result(s) for s in range(5)]
    reports = cluster_results_to_endpoint_reports(
        results,
        cluster_key="metabolism__mixed",
        model_family="kermt_mixed",
        prep_id="20260920T000000Z",
        task_types=TYPES,
    )
    assert set(reports) == set(KEYS)
    assert all(isinstance(r, EvaluationReport) for r in reports.values())
    assert reports[CYP].seeds == [0, 1, 2, 3, 4]
    assert reports[CYP].run_ids == [f"run-{s}" for s in range(5)]


def test_reports_carry_cluster_key_so_they_are_never_read_as_single_task():
    reports = cluster_results_to_endpoint_reports(
        [_seed_result(s) for s in range(2)],
        cluster_key="metabolism__mixed",
        model_family="kermt_mixed",
        prep_id="p",
        task_types=TYPES,
    )
    assert reports[CYP].cluster_key == "metabolism__mixed"
    assert reports[CYP].model_family == "kermt_mixed"


def test_report_task_type_is_per_endpoint_not_per_cluster():
    reports = cluster_results_to_endpoint_reports(
        [_seed_result(s) for s in range(2)],
        cluster_key="metabolism__mixed",
        model_family="kermt_mixed",
        prep_id="p",
        task_types=TYPES,
    )
    assert reports[CYP].task_type == "classification"
    assert reports[CLR].task_type == "regression"


def test_report_roundtrips_through_disk(tmp_path):
    reports = cluster_results_to_endpoint_reports(
        [_seed_result(s) for s in range(2)],
        cluster_key="metabolism__mixed",
        model_family="kermt_mixed",
        prep_id="p",
        task_types=TYPES,
    )
    path = tmp_path / "cyp.json"
    reports[CYP].save(path)
    restored = EvaluationReport.load(path)
    assert restored.cluster_key == "metabolism__mixed"
    assert restored.seeds == reports[CYP].seeds


def test_duplicate_seeds_rejected():
    with pytest.raises(ValueError, match="Duplicate seeds"):
        cluster_results_to_endpoint_reports(
            [_seed_result(0), _seed_result(0)],
            cluster_key="c",
            model_family="kermt_mixed",
            prep_id="p",
            task_types=TYPES,
        )


def test_empty_results_rejected():
    with pytest.raises(ValueError, match="results is empty"):
        cluster_results_to_endpoint_reports(
            [], cluster_key="c", model_family="kermt_mixed", prep_id="p", task_types=TYPES
        )


def test_seeds_disagreeing_on_membership_are_rejected():
    """A partial sweep must be fixed, not silently averaged over fewer endpoints."""
    good = _seed_result(0)
    partial = _seed_result(1)
    partial.endpoint_keys = [CYP]
    with pytest.raises(ValueError, match="disagree on endpoint membership"):
        cluster_results_to_endpoint_reports(
            [good, partial],
            cluster_key="c",
            model_family="kermt_mixed",
            prep_id="p",
            task_types=TYPES,
        )
