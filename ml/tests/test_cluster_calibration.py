"""
Tests for eval/cluster_calibration.py — the production temperature-scaling path.

All synthetic and CPU-only. The synthetic logits here characterise the
CALIBRATION MECHANISM (data flow, isolation, persistence); they are not, and do
not pretend to be, KERMT output. What KERMT's real logits do to a 241-molecule
calibration set is not established by anything in this file.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from eval import cluster_calibration as cc
from eval.cluster_calibration import (
    REQUIRED_RECORD_KEYS,
    STATUS_FITTED,
    STATUS_FITTED_AT_BOUNDARY,
    STATUS_SKIPPED_INVALID,
    STATUS_SKIPPED_REGRESSION,
    aggregate_calibration_across_seeds,
    calibrate_endpoints,
    save_calibration_outcomes,
)
from mars_contracts.endpoints import TaskType

CLF = TaskType.CLASSIFICATION
REG = TaskType.REGRESSION
PROV = {"prep_id": "20260830T200000Z", "model_id": "mars-kermt-multitask-v1",
        "checkpoint_sha256": "e9e6649b"}


def _clf_data(n: int, pos_rate: float, seed: int, steepness: float = 2.5):
    rng = np.random.default_rng(seed)
    shift = float(np.log(pos_rate / (1 - pos_rate)))
    true_logit = rng.normal(shift, 2.0, n)
    y = rng.binomial(1, 1.0 / (1.0 + np.exp(-true_logit))).astype(float)
    return true_logit * steepness, y


def _one_clf(cal_n=300, test_n=400, seed=0, cal_rate=0.3, test_rate=0.3):
    cal_s, cal_y = _clf_data(cal_n, cal_rate, seed)
    te_s, te_y = _clf_data(test_n, test_rate, seed + 100)
    return dict(
        endpoint_keys=["cyp3a4_inhibition"],
        task_types={"cyp3a4_inhibition": CLF},
        seed=seed,
        cal_scores=cal_s[:, None],
        cal_labels=cal_y[:, None],
        test_scores=te_s[:, None],
        test_labels=te_y[:, None],
        train_val_positive_rates={"cyp3a4_inhibition": 0.41},
        provenance=PROV,
    )


# ---------------------------------------------------------------------------- #
# Isolation: the calibration fit sees calibration data only
# ---------------------------------------------------------------------------- #


def test_fit_receives_only_the_calibration_split(monkeypatch):
    kw = _one_clf()
    seen: list[tuple[np.ndarray, np.ndarray]] = []
    real = cc.diagnose_temperature_fit

    def spy(logits, y_true, **k):
        seen.append((np.array(logits), np.array(y_true)))
        return real(logits, y_true, **k)

    monkeypatch.setattr(cc, "diagnose_temperature_fit", spy)
    calibrate_endpoints(**kw)

    assert len(seen) == 1
    logits, labels = seen[0]
    np.testing.assert_array_equal(logits, kw["cal_scores"][:, 0])
    np.testing.assert_array_equal(labels, kw["cal_labels"][:, 0].astype(int))
    assert len(logits) == 300  # calibration N, not the 400 test rows


def test_test_labels_cannot_influence_the_fitted_temperature():
    """Same calibration data, wildly different test data -> identical fit."""
    a = _one_clf(seed=1)
    b = _one_clf(seed=1)
    rng = np.random.default_rng(999)
    b["test_labels"] = rng.integers(0, 2, b["test_labels"].shape).astype(float)
    b["test_scores"] = rng.normal(0, 9, b["test_scores"].shape)

    ra = calibrate_endpoints(**a)["cyp3a4_inhibition"]
    rb = calibrate_endpoints(**b)["cyp3a4_inhibition"]

    assert ra.temperature == rb.temperature
    assert ra.diagnostics.to_dict() == rb.diagnostics.to_dict()
    # ...while the test metrics genuinely differ, so the test data was used.
    assert ra.test_metrics_calibrated != rb.test_metrics_calibrated


def test_test_data_is_read_only_evidence_of_no_mutation():
    """Read-only arrays would raise on any in-place write."""
    kw = _one_clf(seed=2)
    for k in ("cal_scores", "cal_labels", "test_scores", "test_labels"):
        kw[k].flags.writeable = False
    before = {k: kw[k].copy() for k in ("cal_scores", "cal_labels", "test_scores", "test_labels")}

    calibrate_endpoints(**kw)  # would raise ValueError on any write

    for k, v in before.items():
        np.testing.assert_array_equal(kw[k], v)


# ---------------------------------------------------------------------------- #
# Validity guards
# ---------------------------------------------------------------------------- #


def test_single_class_calibration_is_skipped_not_fabricated():
    kw = _one_clf(seed=3)
    kw["cal_labels"] = np.ones_like(kw["cal_labels"])  # both classes required

    out = calibrate_endpoints(**kw)["cyp3a4_inhibition"]

    assert out.status == STATUS_SKIPPED_INVALID
    assert "both classes" in out.reason
    assert out.scaler is None
    assert out.test_metrics_calibrated is None
    # Raw metrics are still reported so the run is not silently empty.
    assert out.test_metrics_raw is not None


def test_endpoint_with_no_calibration_labels_is_skipped():
    kw = _one_clf(seed=4)
    kw["cal_labels"] = np.full_like(kw["cal_labels"], np.nan)
    out = calibrate_endpoints(**kw)["cyp3a4_inhibition"]
    assert out.status == STATUS_SKIPPED_INVALID
    assert "no labelled calibration rows" in out.reason


def test_one_bad_endpoint_does_not_abort_the_others():
    a_s, a_y = _clf_data(300, 0.3, 5)
    b_s, b_y = _clf_data(300, 0.3, 6)
    b_y = np.ones_like(b_y)  # endpoint B cannot be calibrated
    t_s, t_y = _clf_data(400, 0.3, 7)
    keys = ["cyp3a4_inhibition", "cyp2d6_inhibition"]
    out = calibrate_endpoints(
        endpoint_keys=keys,
        task_types={k: CLF for k in keys},
        seed=0,
        cal_scores=np.stack([a_s, b_s], 1),
        cal_labels=np.stack([a_y, b_y], 1),
        test_scores=np.stack([t_s, t_s], 1),
        test_labels=np.stack([t_y, t_y], 1),
    )
    assert out["cyp3a4_inhibition"].status in (STATUS_FITTED, STATUS_FITTED_AT_BOUNDARY)
    assert out["cyp2d6_inhibition"].status == STATUS_SKIPPED_INVALID


def test_empty_arrays_are_rejected():
    kw = _one_clf()
    kw["cal_scores"] = kw["cal_scores"][:0]
    kw["cal_labels"] = kw["cal_labels"][:0]
    with pytest.raises(ValueError, match="calibration arrays are empty"):
        calibrate_endpoints(**kw)

    kw = _one_clf()
    kw["test_scores"] = kw["test_scores"][:0]
    kw["test_labels"] = kw["test_labels"][:0]
    with pytest.raises(ValueError, match="test arrays are empty"):
        calibrate_endpoints(**kw)


def test_length_and_shape_mismatches_are_rejected():
    kw = _one_clf()
    kw["cal_labels"] = kw["cal_labels"][:-5]
    with pytest.raises(ValueError, match="shape mismatch"):
        calibrate_endpoints(**kw)

    kw = _one_clf()
    kw["test_labels"] = kw["test_labels"][:-1]
    with pytest.raises(ValueError, match="shape mismatch"):
        calibrate_endpoints(**kw)

    kw = _one_clf()
    kw["endpoint_keys"] = ["cyp3a4_inhibition", "cyp2d6_inhibition"]
    kw["task_types"] = {k: CLF for k in kw["endpoint_keys"]}
    with pytest.raises(ValueError, match="endpoint_keys were given"):
        calibrate_endpoints(**kw)

    kw = _one_clf()
    kw["cal_scores"] = kw["cal_scores"][:, 0]
    with pytest.raises(ValueError, match="must be 2-D"):
        calibrate_endpoints(**kw)


def test_endpoint_with_no_labelled_test_rows_is_a_hard_error():
    kw = _one_clf()
    kw["test_labels"] = np.full_like(kw["test_labels"], np.nan)
    with pytest.raises(ValueError, match="no test rows with both a label and a score"):
        calibrate_endpoints(**kw)


# ---------------------------------------------------------------------------- #
# Diagnostics: boundary, optimizer, NLL, ECE
# ---------------------------------------------------------------------------- #


def test_boundary_is_detected_and_status_reflects_it():
    """Anti-correlated calibration logits pin T to the upper bound."""
    kw = _one_clf(seed=8)
    rng = np.random.default_rng(0)
    logits = rng.normal(0, 3, 241)
    kw["cal_scores"] = logits[:, None]
    kw["cal_labels"] = (logits < 0).astype(float)[:, None]

    out = calibrate_endpoints(**kw)["cyp3a4_inhibition"]

    assert out.diagnostics.at_boundary is True
    assert out.status == STATUS_FITTED_AT_BOUNDARY
    assert out.reason is None  # a boundary fit is reported, never silently rejected


def test_well_behaved_fit_records_optimizer_nll_and_ece():
    out = calibrate_endpoints(**_one_clf(cal_n=833, seed=9))["cyp3a4_inhibition"]
    d = out.diagnostics
    assert out.status == STATUS_FITTED
    assert d.optimizer_success is True
    assert d.at_boundary is False
    assert np.isfinite(d.nll_before) and np.isfinite(d.nll_after)
    assert np.isfinite(d.ece_before) and np.isfinite(d.ece_after)
    assert d.nll_after <= d.nll_before
    assert d.nll_improved is True


def test_calibrated_probabilities_differ_from_raw_when_overconfident():
    out = calibrate_endpoints(**_one_clf(cal_n=800, test_n=800, seed=10))["cyp3a4_inhibition"]
    assert out.temperature > 1.0
    assert not np.allclose(out.test_probs_raw, out.test_probs_calibrated)
    # Softening moves confident probabilities toward 0.5.
    assert np.mean(np.abs(out.test_probs_calibrated - 0.5)) < np.mean(
        np.abs(out.test_probs_raw - 0.5)
    )


def test_calibration_leaves_ranking_metrics_unchanged():
    """Temperature scaling is monotone, so AUROC/AUPRC must not move."""
    out = calibrate_endpoints(**_one_clf(cal_n=500, test_n=600, seed=11))["cyp3a4_inhibition"]
    assert out.test_metrics_calibrated.auroc == pytest.approx(out.test_metrics_raw.auroc)
    assert out.test_metrics_calibrated.auprc == pytest.approx(out.test_metrics_raw.auprc)


def test_fitting_is_deterministic_for_identical_inputs():
    a = calibrate_endpoints(**_one_clf(seed=12))["cyp3a4_inhibition"].to_record()
    b = calibrate_endpoints(**_one_clf(seed=12))["cyp3a4_inhibition"].to_record()
    assert a == b


def test_class_rates_are_recorded_next_to_each_other():
    """The train_val/calibration prior shift must be visible per run."""
    out = calibrate_endpoints(**_one_clf(seed=13, cal_rate=0.11))["cyp3a4_inhibition"]
    rec = out.to_record()
    assert rec["train_val_positive_rate"] == pytest.approx(0.41)
    assert rec["calibration_positive_rate"] == pytest.approx(out.diagnostics.positive_rate)
    assert rec["calibration_positive_rate"] < 0.25


# ---------------------------------------------------------------------------- #
# Regression endpoints are never calibrated
# ---------------------------------------------------------------------------- #


def test_regression_endpoint_never_reaches_the_fitter(monkeypatch):
    calls: list[str] = []
    real = cc.diagnose_temperature_fit

    def spy(logits, y_true, **k):
        calls.append(k["endpoint_key"])
        return real(logits, y_true, **k)

    monkeypatch.setattr(cc, "diagnose_temperature_fit", spy)

    rng = np.random.default_rng(0)
    y = rng.normal(0, 1, 120)
    out = calibrate_endpoints(
        endpoint_keys=["clearance_microsomal"],
        task_types={"clearance_microsomal": REG},
        seed=0,
        cal_scores=np.full((50, 1), np.nan),
        cal_labels=rng.normal(0, 1, (50, 1)),
        test_scores=(y + rng.normal(0, 0.1, 120))[:, None],
        test_labels=y[:, None],
    )["clearance_microsomal"]

    assert calls == []
    assert out.status == STATUS_SKIPPED_REGRESSION
    assert out.scaler is None and out.diagnostics is None
    assert out.test_metrics_raw.mae < 0.2  # scored as regression, not classification
    assert out.test_metrics_calibrated is None


def test_mixed_columns_calibrate_only_the_classification_one(monkeypatch):
    calls: list[str] = []
    real = cc.diagnose_temperature_fit
    monkeypatch.setattr(
        cc,
        "diagnose_temperature_fit",
        lambda logits, y, **k: (calls.append(k["endpoint_key"]), real(logits, y, **k))[1],
    )
    c_s, c_y = _clf_data(300, 0.3, 14)
    t_s, t_y = _clf_data(300, 0.3, 15)
    rng = np.random.default_rng(1)
    reg_y = rng.normal(0, 1, 300)
    keys = ["cyp3a4_inhibition", "clearance_microsomal"]
    out = calibrate_endpoints(
        endpoint_keys=keys,
        task_types={"cyp3a4_inhibition": CLF, "clearance_microsomal": REG},
        seed=0,
        cal_scores=np.stack([c_s, np.full(300, np.nan)], 1),
        cal_labels=np.stack([c_y, reg_y], 1),
        test_scores=np.stack([t_s, reg_y], 1),
        test_labels=np.stack([t_y, reg_y], 1),
    )
    assert calls == ["cyp3a4_inhibition"]
    assert out["clearance_microsomal"].status == STATUS_SKIPPED_REGRESSION
    assert out["cyp3a4_inhibition"].scaler is not None


# ---------------------------------------------------------------------------- #
# Persistence: required metadata
# ---------------------------------------------------------------------------- #


def test_persisted_record_contains_every_required_field(tmp_path):
    out = calibrate_endpoints(**_one_clf(seed=16))
    paths = save_calibration_outcomes(out, tmp_path)

    rec = json.loads(paths["cyp3a4_inhibition"]["diagnostics"].read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED_RECORD_KEYS if k not in rec]
    assert missing == []
    assert rec["prep_id"] == "20260830T200000Z"
    assert rec["model_id"] == "mars-kermt-multitask-v1"
    assert rec["checkpoint_sha256"] == "e9e6649b"
    assert rec["seed"] == 16
    assert rec["n_positive"] + rec["n_negative"] == rec["n_fit_samples"]


def test_scaler_artifact_roundtrips_and_is_not_named_calibrator_json(tmp_path):
    """calibrator.json is the XGBoost registry's PlattCalibrator filename."""
    from eval.calibration import TemperatureScaler

    out = calibrate_endpoints(**_one_clf(seed=17))
    paths = save_calibration_outcomes(out, tmp_path)

    scaler_path = paths["cyp3a4_inhibition"]["temperature_scaler"]
    assert scaler_path.name == "temperature_scaler.json"
    loaded = TemperatureScaler.load(scaler_path)
    assert loaded.temperature == pytest.approx(out["cyp3a4_inhibition"].temperature)


def test_skipped_endpoint_still_persists_a_stable_schema(tmp_path):
    kw = _one_clf(seed=18)
    kw["cal_labels"] = np.ones_like(kw["cal_labels"])
    out = calibrate_endpoints(**kw)
    paths = save_calibration_outcomes(out, tmp_path)

    assert "temperature_scaler" not in paths["cyp3a4_inhibition"]
    rec = json.loads(paths["cyp3a4_inhibition"]["diagnostics"].read_text(encoding="utf-8"))
    assert [k for k in REQUIRED_RECORD_KEYS if k not in rec] == []
    assert rec["status"] == STATUS_SKIPPED_INVALID
    assert rec["temperature"] is None


# ---------------------------------------------------------------------------- #
# Across-seed aggregation
# ---------------------------------------------------------------------------- #


def test_aggregation_reports_spread_and_boundary_counts():
    recs = []
    for s in range(5):
        o = calibrate_endpoints(**_one_clf(cal_n=241, seed=20 + s))["cyp3a4_inhibition"]
        recs.append(o.to_record())
    agg = aggregate_calibration_across_seeds(recs)["cyp3a4_inhibition"]

    assert agg["n_seeds"] == 5 and agg["n_fitted"] == 5
    assert agg["temperature_min"] <= agg["temperature_mean"] <= agg["temperature_max"]
    assert agg["temperature_std"] >= 0
    assert agg["n_at_boundary"] == 0
    assert agg["n_optimizer_failed"] == 0


def test_aggregation_handles_an_endpoint_that_never_fitted():
    kw = _one_clf(seed=30)
    kw["cal_labels"] = np.ones_like(kw["cal_labels"])
    rec = calibrate_endpoints(**kw)["cyp3a4_inhibition"].to_record()
    agg = aggregate_calibration_across_seeds([rec])["cyp3a4_inhibition"]
    assert agg["n_fitted"] == 0
    assert STATUS_SKIPPED_INVALID in agg["statuses"]


# ---------------------------------------------------------------------------- #
# Test-metric aggregation across seeds (mean ± std, never a single run)
# ---------------------------------------------------------------------------- #


def test_test_metrics_aggregate_across_seeds_raw_and_calibrated():
    recs = [
        calibrate_endpoints(**_one_clf(cal_n=400, test_n=500, seed=40 + s))[
            "cyp3a4_inhibition"
        ].to_record()
        for s in range(5)
    ]
    agg = cc.aggregate_test_metrics_across_seeds(recs)["cyp3a4_inhibition"]

    assert agg["n_seeds"] == 5 and agg["n_calibrated_seeds"] == 5
    assert agg["raw"]["n_seeds"] == 5.0
    for arm in ("raw", "calibrated"):
        assert set(agg[arm]) >= {"auroc_mean", "auroc_std", "ece_mean", "ece_std"}
    # Ranking is untouched by temperature scaling; calibration quality is not.
    assert agg["calibrated"]["auroc_mean"] == pytest.approx(agg["raw"]["auroc_mean"])
    assert agg["calibrated"]["ece_mean"] != pytest.approx(agg["raw"]["ece_mean"])


def test_test_metric_aggregation_shows_partial_calibration_instead_of_hiding_it():
    good = calibrate_endpoints(**_one_clf(seed=50))["cyp3a4_inhibition"].to_record()
    bad_kw = _one_clf(seed=51)
    bad_kw["cal_labels"] = np.ones_like(bad_kw["cal_labels"])
    bad = calibrate_endpoints(**bad_kw)["cyp3a4_inhibition"].to_record()

    agg = cc.aggregate_test_metrics_across_seeds([good, bad])["cyp3a4_inhibition"]
    assert agg["n_seeds"] == 2
    assert agg["n_calibrated_seeds"] == 1  # one seed could not be calibrated
    assert agg["raw"]["n_seeds"] == 2.0


def test_regression_test_metrics_aggregate_as_mae():
    rng = np.random.default_rng(0)
    recs = []
    for s in range(3):
        y = rng.normal(0, 1, 100)
        recs.append(
            calibrate_endpoints(
                endpoint_keys=["clearance_microsomal"],
                task_types={"clearance_microsomal": REG},
                seed=s,
                cal_scores=np.full((10, 1), np.nan),
                cal_labels=np.zeros((10, 1)),
                test_scores=(y + rng.normal(0, 0.2, 100))[:, None],
                test_labels=y[:, None],
            )["clearance_microsomal"].to_record()
        )
    agg = cc.aggregate_test_metrics_across_seeds(recs)["clearance_microsomal"]
    assert agg["calibrated"] is None and agg["n_calibrated_seeds"] == 0
    assert "mae_mean" in agg["raw"]
