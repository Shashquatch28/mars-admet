"""C0 (AIMS decisions.md 2026-10-08): the served Platt calibrator is off by default.

Uses a fake registry, so no trained artifact or processed data is needed.
"""

from __future__ import annotations

import numpy as np
import pytest
from serve.predictor import APPLY_PLATT_ENV, platt_enabled, predict_endpoint

CLS_ENDPOINT = "hia_absorption"
REG_ENDPOINT = "solubility_logs"


class _Model:
    model_id = "xgb-fake"

    def __init__(self, value: float):
        self._value = value

    def predict(self, smiles):
        return np.array([self._value])


class _Calibrator:
    def transform(self, x):
        return np.asarray(x) * 0.0 + 0.5  # unmistakable: every score becomes 0.5


class _Registry:
    def __init__(self, values):
        self._models = [_Model(v) for v in values]
        self.calibrator_loads = 0

    def load_models(self, endpoint_key):
        return self._models

    def load_calibrator(self, endpoint_key):
        self.calibrator_loads += 1
        return _Calibrator()

    def load_error_band(self, endpoint_key):
        return None

    def load_ad_index(self, endpoint_key):
        return None


def test_platt_is_off_by_default(monkeypatch):
    monkeypatch.delenv(APPLY_PLATT_ENV, raising=False)
    assert not platt_enabled()
    registry = _Registry([0.2, 0.4])
    pred = predict_endpoint(registry, CLS_ENDPOINT, "CCO")
    assert pred.value == pytest.approx(0.3)  # raw ensemble mean
    assert registry.calibrator_loads == 0


@pytest.mark.parametrize("flag", ["1", "true", "YES", "on"])
def test_platt_switch_restores_calibration(monkeypatch, flag):
    monkeypatch.setenv(APPLY_PLATT_ENV, flag)
    registry = _Registry([0.2, 0.4])
    pred = predict_endpoint(registry, CLS_ENDPOINT, "CCO")
    assert pred.value == pytest.approx(0.5)
    assert registry.calibrator_loads == 1


def test_regression_never_calibrated(monkeypatch):
    monkeypatch.setenv(APPLY_PLATT_ENV, "1")
    registry = _Registry([-2.0, -4.0])
    pred = predict_endpoint(registry, REG_ENDPOINT, "CCO")
    assert pred.value == pytest.approx(-3.0)
    assert registry.calibrator_loads == 0
