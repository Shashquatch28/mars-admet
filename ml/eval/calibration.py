"""
Module 4 — probability calibration (blueprint §"Decision — method differs by
model type, not one-size-fits-all").

Two calibrators, matching the blueprint's explicit per-model-type split:

  * **PlattCalibrator** — XGBoost baseline. A 1-D logistic regression fit on
    the model's own (already-probabilistic) output vs. true labels. Preferred
    over isotonic regression per the blueprint's cited 2026 finding that
    isotonic can degrade calibration on tabular models.
  * **TemperatureScaler** — GNN / KERMT. A single scalar T dividing the
    pre-sigmoid logit before it is squashed to a probability. KERMT does not
    exist yet (M2 Run 3+), so this is an interface-complete stub validated
    with synthetic logits; it will be wired to real KERMT output when that
    model lands.

Both calibrators MUST be fit on the calibration split only (carved from
train_val at M1 prepare-time, disjoint from test — see `data/loaders.py`).
Fitting on train_val or test data defeats the purpose: the calibration split
exists so the reported probability is checked against data the model never
trained or was selected on.

Regression endpoints have no probability to calibrate — this module is
classification-only.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

CALIBRATION_VERSION = "mars-calibration-v1"
_EPS = 1e-12


def _binary_cross_entropy(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    p = np.clip(y_prob, _EPS, 1.0 - _EPS)
    return float(-np.mean(y_true * np.log(p) + (1 - y_true) * np.log(1 - p)))


# ---------------------------------------------------------------------------- #
# Platt scaling (XGBoost)
# ---------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PlattCalibrator:
    """Platt scaling: calibrated_prob = sigmoid(A * raw_prob + B).

    Fit via 1-D logistic regression on (raw_prob, y_true) pairs from the
    calibration split. A and B are the standard Platt scaling coefficients.
    """

    A: float
    B: float
    n_fit_samples: int
    version: str = CALIBRATION_VERSION

    def transform(self, raw_probs: np.ndarray) -> np.ndarray:
        raw_probs = np.asarray(raw_probs, dtype=float)
        z = self.A * raw_probs + self.B
        return 1.0 / (1.0 + np.exp(-z))

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> PlattCalibrator:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(**data)


def fit_platt_calibrator(raw_probs: np.ndarray, y_true: np.ndarray) -> PlattCalibrator:
    """Fit Platt scaling on calibration-split predictions.

    Parameters
    ----------
    raw_probs:
        The model's own positive-class probabilities (e.g. XGBoostModel.predict
        output) computed on the calibration split — NEVER on train_val or test.
    y_true:
        True binary labels for the same calibration-split molecules.
    """
    raw_probs = np.asarray(raw_probs, dtype=float)
    y_true = np.asarray(y_true, dtype=int)
    if len(raw_probs) == 0:
        raise ValueError("raw_probs is empty")
    if len(raw_probs) != len(y_true):
        raise ValueError(
            f"Length mismatch: raw_probs has {len(raw_probs)}, y_true has {len(y_true)}"
        )
    if len(np.unique(y_true)) < 2:
        raise ValueError("Platt scaling requires both classes present in the calibration split")

    from sklearn.linear_model import (
        LogisticRegression,  # lazy: training-only dep, not needed to serve
    )

    lr = LogisticRegression()
    lr.fit(raw_probs.reshape(-1, 1), y_true)
    return PlattCalibrator(
        A=float(lr.coef_[0][0]),
        B=float(lr.intercept_[0]),
        n_fit_samples=len(raw_probs),
    )


# ---------------------------------------------------------------------------- #
# Temperature scaling (KERMT / GNN) — interface stub, synthetic-logit tested
# ---------------------------------------------------------------------------- #


@dataclass(frozen=True)
class TemperatureScaler:
    """Temperature scaling: calibrated_prob = sigmoid(logit / T).

    T > 1 softens overconfident predictions (the typical GNN failure mode);
    T < 1 sharpens. A single scalar per endpoint (blueprint default; sharing
    one T per cluster is a documented alternative to test empirically once
    KERMT multi-task clusters exist).

    Does not exist as a trained artifact yet — KERMT is M2 Run 3+. This class
    and its fit function are validated with synthetic logits now so the
    mechanism is correct before any real model output is available.
    """

    temperature: float
    n_fit_samples: int
    version: str = CALIBRATION_VERSION

    def transform_logits(self, logits: np.ndarray) -> np.ndarray:
        logits = np.asarray(logits, dtype=float)
        z = logits / self.temperature
        return 1.0 / (1.0 + np.exp(-z))

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> TemperatureScaler:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(**data)


def fit_temperature_scaler(
    logits: np.ndarray,
    y_true: np.ndarray,
    *,
    bounds: tuple[float, float] = (0.05, 10.0),
) -> TemperatureScaler:
    """Fit scalar temperature T minimizing NLL on calibration-split logits.

    Parameters
    ----------
    logits:
        Pre-sigmoid model outputs (raw logits, not probabilities) computed on
        the calibration split.
    y_true:
        True binary labels for the same calibration-split molecules.
    bounds:
        Search range for T. A single scalar, bounded search is sufficient
        (the NLL-vs-T curve is well-behaved / near-convex for this 1-D problem).
    """
    logits = np.asarray(logits, dtype=float)
    y_true = np.asarray(y_true, dtype=int)
    if len(logits) == 0:
        raise ValueError("logits is empty")
    if len(logits) != len(y_true):
        raise ValueError(f"Length mismatch: logits has {len(logits)}, y_true has {len(y_true)}")
    if len(np.unique(y_true)) < 2:
        raise ValueError("Temperature scaling requires both classes present in the calibration split")

    from scipy.optimize import minimize_scalar  # lazy: training-only dep, not needed to serve

    def nll(temperature: float) -> float:
        probs = 1.0 / (1.0 + np.exp(-(logits / temperature)))
        return _binary_cross_entropy(y_true, probs)

    result = minimize_scalar(nll, bounds=bounds, method="bounded")
    return TemperatureScaler(temperature=float(result.x), n_fit_samples=len(logits))
