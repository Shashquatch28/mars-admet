"""Held-out-error band (ADR-024): the half-width is a measured quantile, refuses when it cannot be stated,
and reaches the served prediction only for regression endpoints that have a built band."""

from __future__ import annotations

import json

import numpy as np
import pytest
from eval.error_band import (
    ERROR_BAND_FILENAME,
    ErrorBand,
    build_error_band,
    conformal_halfwidth,
    pooled_residuals,
)
from mars_contracts.endpoints import Endpoint
from serve.predictor import predict_endpoint
from serve.registry import ModelRegistry


def test_halfwidth_is_the_conformal_rank_of_the_sorted_residuals():
    r = np.arange(1, 100) / 100.0  # n = 99 -> ceil(100 * 0.9) = 90th smallest = 0.90
    assert conformal_halfwidth(r, 0.9) == pytest.approx(0.90)
    assert conformal_halfwidth(r, 0.8) == pytest.approx(0.80)


def test_halfwidth_ignores_sign_and_order():
    assert conformal_halfwidth([-3.0, 1.0, -2.0, 0.5] * 5, 0.5) == conformal_halfwidth([0.5, 1.0, 2.0, 3.0] * 5, 0.5)


def test_halfwidth_refuses_instead_of_extrapolating():
    with pytest.raises(ValueError, match="too few"):
        conformal_halfwidth([0.1, 0.2, 0.3], 0.9)
    with pytest.raises(ValueError, match="level"):
        conformal_halfwidth([0.1] * 50, 1.0)
    with pytest.raises(ValueError, match="NaN"):
        conformal_halfwidth([0.1] * 20 + [float("nan")], 0.9)
    with pytest.raises(ValueError):
        conformal_halfwidth([], 0.9)


class _Fixed:
    """A 'model' that predicts a constant offset from the label, so residuals are known exactly."""

    def __init__(self, labels, offset, nan_for=()):
        self.labels, self.offset, self.nan_for = labels, offset, set(nan_for)
        self.model_id = "toy-model"

    def predict(self, smiles):
        return np.array([np.nan if s in self.nan_for else self.labels[s] + self.offset for s in smiles])


def _folds(n_per_fold=20, seeds=(0, 1)):
    out, labels = [], {}
    for seed in seeds:
        valid = [f"s{seed}_{i}" for i in range(n_per_fold)]
        labels.update({s: float(i) for i, s in enumerate(valid)})
        out.append((seed, [], valid))
    return out, labels


def test_pooled_residuals_are_each_seeds_own_validation_errors_with_nan_dropped():
    folds, labels = _folds()
    models = {0: _Fixed(labels, 1.0, nan_for=["s0_3"]), 1: _Fixed(labels, -2.0)}
    r = pooled_residuals(models, folds, labels)
    assert len(r) == 39  # one molecule the first seed could not featurize is dropped, not imputed
    assert sorted(set(r.tolist())) == [1.0, 2.0]


def test_pooled_residuals_need_every_folds_model():
    folds, labels = _folds()
    with pytest.raises(ValueError, match="seed 1"):
        pooled_residuals({0: _Fixed(labels, 1.0)}, folds, labels)


def test_build_error_band_records_what_it_was_measured_over():
    folds, labels = _folds()
    models = {0: _Fixed(labels, 1.0), 1: _Fixed(labels, -2.0)}
    band = build_error_band("toy_endpoint", models, folds, labels, level=0.5)
    assert (band.endpoint, band.level, band.n_residuals, band.n_seeds) == ("toy_endpoint", 0.5, 40, 2)
    assert band.halfwidth in (1.0, 2.0)


def test_band_round_trips_and_rejects_an_unknown_version(tmp_path):
    band = ErrorBand(endpoint="toy_endpoint", level=0.9, halfwidth=1.23, n_residuals=450, n_seeds=5)
    path = tmp_path / ERROR_BAND_FILENAME
    band.save(path)
    assert ErrorBand.load(path) == band
    raw = json.loads(path.read_text())
    raw["version"] = "something-else"
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="version"):
        ErrorBand.load(path)


# --- serving: the band reaches the prediction for regression only ------------------------------------------


class _Registry:
    def __init__(self, models, band):
        self._models, self._band = models, band

    def load_models(self, key):
        return self._models

    def load_ad_index(self, key):
        return None

    def load_calibrator(self, key):
        return None

    def load_error_band(self, key):
        return self._band


def _served(endpoint, band):
    labels = {"CCO": 0.5}
    return predict_endpoint(_Registry([_Fixed(labels, 0.0)], band), endpoint, "CCO")


def test_regression_prediction_carries_the_band():
    band = ErrorBand(endpoint=Endpoint.SOLUBILITY.value, level=0.9, halfwidth=1.677, n_residuals=4700, n_seeds=5)
    result = _served(Endpoint.SOLUBILITY.value, band)
    assert (result.heldout_error_halfwidth, result.heldout_error_level, result.heldout_error_n) == (1.677, 0.9, 4700)


def test_regression_without_a_built_band_carries_none():
    result = _served(Endpoint.SOLUBILITY.value, None)
    assert (result.heldout_error_halfwidth, result.heldout_error_level, result.heldout_error_n) == (None, None, None)


def test_classification_never_carries_a_band_even_if_a_file_exists():
    band = ErrorBand(endpoint=Endpoint.HIA.value, level=0.9, halfwidth=0.3, n_residuals=500, n_seeds=5)
    result = _served(Endpoint.HIA.value, band)
    assert result.heldout_error_halfwidth is None


def test_registry_reads_the_band_file_and_reports_none_when_absent(tmp_path):
    registry = ModelRegistry(cache=None, artifacts_root=tmp_path, revalidate_seconds=0)  # type: ignore[arg-type]
    assert registry.load_error_band("solubility_logs") is None
    (tmp_path / "solubility_logs").mkdir()
    band = ErrorBand(endpoint="solubility_logs", level=0.9, halfwidth=1.677, n_residuals=4700, n_seeds=5)
    band.save(tmp_path / "solubility_logs" / ERROR_BAND_FILENAME)
    assert registry.load_error_band("solubility_logs") == band
    rebuilt = ErrorBand(endpoint="solubility_logs", level=0.9, halfwidth=2.0, n_residuals=4700, n_seeds=5)
    rebuilt.save(tmp_path / "solubility_logs" / ERROR_BAND_FILENAME)
    assert registry.load_error_band("solubility_logs") == rebuilt  # a rebuilt band is picked up, not served stale
