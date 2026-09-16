"""
Tests for ml/eval/calibration.py.

Platt scaling tests use real fitted output; temperature scaling is validated
with synthetic logits (KERMT does not exist yet — see module docstring).
"""

from __future__ import annotations

import numpy as np
import pytest
from eval.calibration import (
    PlattCalibrator,
    TemperatureScaler,
    fit_platt_calibrator,
    fit_temperature_scaler,
)
from eval.metrics import expected_calibration_error


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _synthetic_overconfident(n: int, seed: int, steepness: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """True calibrated probs from a logistic model; observed model output is
    systematically overconfident (steeper sigmoid than the true generating process)."""
    rng = np.random.default_rng(seed)
    true_logit = rng.normal(0.0, 1.0, n)
    true_prob = _sigmoid(true_logit)
    y = rng.binomial(1, true_prob)
    overconfident_logit = steepness * true_logit
    overconfident_prob = _sigmoid(overconfident_logit)
    return overconfident_logit, overconfident_prob, y


# ---------------------------------------------------------------------------- #
# Platt scaling
# ---------------------------------------------------------------------------- #


def test_platt_reduces_ece_on_overconfident_probs():
    _, raw_probs, y = _synthetic_overconfident(3000, seed=0, steepness=3.0)
    raw_ece = expected_calibration_error(y, raw_probs)

    cal = fit_platt_calibrator(raw_probs, y)
    calibrated_probs = cal.transform(raw_probs)
    calibrated_ece = expected_calibration_error(y, calibrated_probs)

    assert calibrated_ece < raw_ece


def test_platt_transform_output_in_range():
    _, raw_probs, y = _synthetic_overconfident(500, seed=1, steepness=2.0)
    cal = fit_platt_calibrator(raw_probs, y)
    out = cal.transform(raw_probs)
    assert np.all(out >= 0.0)
    assert np.all(out <= 1.0)


def test_platt_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        fit_platt_calibrator(np.array([]), np.array([]))


def test_platt_length_mismatch_raises():
    with pytest.raises(ValueError, match="mismatch"):
        fit_platt_calibrator(np.array([0.1, 0.9]), np.array([0]))


def test_platt_single_class_raises():
    with pytest.raises(ValueError, match="both classes"):
        fit_platt_calibrator(np.array([0.1, 0.2, 0.3]), np.array([1, 1, 1]))


def test_platt_save_load_roundtrip(tmp_path):
    _, raw_probs, y = _synthetic_overconfident(200, seed=2, steepness=2.0)
    cal = fit_platt_calibrator(raw_probs, y)
    path = tmp_path / "platt.json"
    cal.save(path)
    loaded = PlattCalibrator.load(path)
    assert loaded.A == pytest.approx(cal.A)
    assert loaded.B == pytest.approx(cal.B)
    np.testing.assert_allclose(loaded.transform(raw_probs), cal.transform(raw_probs))


def test_platt_n_fit_samples_recorded():
    _, raw_probs, y = _synthetic_overconfident(150, seed=3, steepness=2.0)
    cal = fit_platt_calibrator(raw_probs, y)
    assert cal.n_fit_samples == 150


# ---------------------------------------------------------------------------- #
# Temperature scaling (synthetic logits — KERMT stub)
# ---------------------------------------------------------------------------- #


def test_temperature_recovers_known_steepness():
    # logits = 3 * true_logit  =>  dividing by T=3 recovers calibrated probs
    logits, _, y = _synthetic_overconfident(4000, seed=4, steepness=3.0)
    scaler = fit_temperature_scaler(logits, y)
    assert scaler.temperature == pytest.approx(3.0, abs=0.5)


def test_temperature_reduces_ece_on_overconfident_logits():
    logits, raw_probs, y = _synthetic_overconfident(3000, seed=5, steepness=4.0)
    raw_ece = expected_calibration_error(y, raw_probs)

    scaler = fit_temperature_scaler(logits, y)
    calibrated_probs = scaler.transform_logits(logits)
    calibrated_ece = expected_calibration_error(y, calibrated_probs)

    assert calibrated_ece < raw_ece


def test_temperature_well_calibrated_logits_near_one():
    # steepness=1.0 means the "raw" logits already match the true generator —
    # fitted T should land close to 1 (no correction needed).
    logits, _, y = _synthetic_overconfident(4000, seed=6, steepness=1.0)
    scaler = fit_temperature_scaler(logits, y)
    assert scaler.temperature == pytest.approx(1.0, abs=0.3)


def test_temperature_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        fit_temperature_scaler(np.array([]), np.array([]))


def test_temperature_length_mismatch_raises():
    with pytest.raises(ValueError, match="mismatch"):
        fit_temperature_scaler(np.array([0.1, 0.9]), np.array([0]))


def test_temperature_single_class_raises():
    with pytest.raises(ValueError, match="both classes"):
        fit_temperature_scaler(np.array([0.1, 0.2, 0.3]), np.array([0, 0, 0]))


def test_temperature_save_load_roundtrip(tmp_path):
    logits, _, y = _synthetic_overconfident(300, seed=7, steepness=2.0)
    scaler = fit_temperature_scaler(logits, y)
    path = tmp_path / "temp_scale.json"
    scaler.save(path)
    loaded = TemperatureScaler.load(path)
    assert loaded.temperature == pytest.approx(scaler.temperature)
    np.testing.assert_allclose(loaded.transform_logits(logits), scaler.transform_logits(logits))


def test_temperature_transform_output_in_range():
    logits, _, y = _synthetic_overconfident(300, seed=8, steepness=2.0)
    scaler = fit_temperature_scaler(logits, y)
    out = scaler.transform_logits(logits)
    assert np.all(out >= 0.0)
    assert np.all(out <= 1.0)


# ---------------------------------------------------------------------------- #
# Calibration split isolation — integration test against real M1 + XGBoost
# ---------------------------------------------------------------------------- #

from pathlib import Path  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "ml" / "data"


def _newest_prep_dir() -> Path | None:
    root = DATA / "processed"
    if not root.exists():
        return None
    dirs = sorted(p for p in root.iterdir() if p.is_dir())
    return dirs[-1] if dirs else None


PREP_DIR = _newest_prep_dir()


def test_platt_fit_uses_only_calibration_split():
    """Train XGBoost on a train_val fold, predict on the calibration split
    ONLY, fit Platt on those predictions — verify no test-set SMILES or
    labels ever enter the fitting call, and that ECE improves on the
    calibration split itself."""
    if PREP_DIR is None:
        pytest.skip("no processed outputs")
    pytest.importorskip("xgboost", reason="xgboost not installed in this environment")

    from data.loaders import load_endpoint
    from data.split import five_seed_train_val_folds
    from featurize.cache import FeatureCache
    from mars_contracts.endpoints import TaskType
    from models.xgboost_model import XGBoostModel

    endpoint_data = load_endpoint(PREP_DIR, "ames_mutagenicity")
    assert endpoint_data.task_type == TaskType.CLASSIFICATION

    tv_smiles = endpoint_data.train_val["standardized_smiles"].tolist()
    smiles_to_label = dict(
        zip(
            endpoint_data.train_val["standardized_smiles"],
            endpoint_data.train_val["label"].astype(float),
            strict=False,
        )
    )
    _, train_smiles, val_smiles = five_seed_train_val_folds(tv_smiles, seeds=(0,))[0]
    y_train = np.array([smiles_to_label[s] for s in train_smiles])
    y_val = np.array([smiles_to_label[s] for s in val_smiles])

    cache = FeatureCache(DATA / "cache")
    model = XGBoostModel(task_type=TaskType.CLASSIFICATION, cache=cache, seed=0)
    model.fit(train_smiles, y_train, X_val=val_smiles, y_val=y_val)

    # Predict ONLY on the calibration split — never train_val, never test.
    cal_smiles = endpoint_data.calibration["standardized_smiles"].tolist()
    cal_labels = endpoint_data.calibration["label"].astype(float).to_numpy()
    cal_preds = model.predict(cal_smiles)
    valid_mask = ~np.isnan(cal_preds)
    cal_preds = cal_preds[valid_mask]
    cal_labels_valid = cal_labels[valid_mask]

    # Structural isolation check: calibration set is disjoint from test (M1 guarantee).
    test_smiles = set(endpoint_data.test["standardized_smiles"])
    assert not (set(cal_smiles) & test_smiles), "calibration split leaked into test"

    calibrator = fit_platt_calibrator(cal_preds, cal_labels_valid)
    assert calibrator.n_fit_samples == len(cal_preds)
    assert calibrator.n_fit_samples == int(valid_mask.sum())

    raw_ece = expected_calibration_error(cal_labels_valid, cal_preds)
    calibrated = calibrator.transform(cal_preds)
    calibrated_ece = expected_calibration_error(cal_labels_valid, calibrated)
    # Platt scaling fit directly on this data should not make in-sample ECE worse.
    assert calibrated_ece <= raw_ece + 1e-9
