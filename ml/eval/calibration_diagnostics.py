"""
Calibration fit diagnostics — what must be recorded whenever a calibrator is fit.

Motivation
----------
``eval.calibration.fit_temperature_scaler`` and ``fit_platt_calibrator`` both
return an artifact carrying only ``(parameters, n_fit_samples)``. That is not
enough to tell a good fit from a degenerate one after the fact, and both have
silent degenerate modes:

* **Boundary pinning.** ``fit_temperature_scaler`` runs
  ``scipy.optimize.minimize_scalar(..., bounds=(0.05, 10.0), method="bounded")``
  and never inspects ``result.success``. If the calibration logits are perfectly
  separable the NLL is monotone decreasing in ``1/T`` and the optimiser walks to
  the low end; if they are anti-correlated with the labels it pins to ``T=10.0``.
  Either way a ``TemperatureScaler`` is returned that looks ordinary.
* **Degenerate class balance.** Both fitters reject a strictly single-class
  calibration split, but not a nearly single-class one. ``hia_absorption``'s
  promoted Platt calibrator was fit on 50 molecules of which **49 are positive**
  (``ml/artifacts/hia_absorption/calibrator.json``) — technically valid, not
  meaningfully calibrated.

This module **does not change how fitting works**. It observes a fit and reports
what happened, so a run's calibration quality is auditable from
``ExperimentRun``/W&B rather than inferred later.

CPU-only. Safe to call on real or synthetic logits.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from eval.calibration import (
    TEMPERATURE_BOUNDS_DEFAULT,
    TemperatureScaler,
    _binary_cross_entropy,
    fit_temperature_scaler,
)
from eval.metrics import expected_calibration_error

DIAGNOSTICS_VERSION = "mars-calibration-diagnostics-v1"

# Relative distance from a bound at which the fit is treated as pinned. This is
# an *observability* threshold for flagging, not an accept/reject rule — no
# project document defines an acceptable temperature range.
_BOUNDARY_REL_TOL = 1e-3


@dataclass(frozen=True)
class CalibrationFitDiagnostics:
    """Everything needed to audit one calibrator fit after the fact.

    Every field is a measurement. None of them encodes a pass/fail judgement
    except ``at_boundary`` and ``optimizer_success``, which report what the
    optimiser actually did.
    """

    endpoint_key: str
    seed: int
    n_fit_samples: int
    n_positive: int
    n_negative: int
    positive_rate: float
    temperature: float
    at_boundary: bool
    optimizer_success: bool
    nll_before: float
    nll_after: float
    ece_before: float
    ece_after: float
    version: str = DIAGNOSTICS_VERSION

    @property
    def nll_improved(self) -> bool:
        return self.nll_after <= self.nll_before

    @property
    def ece_improved(self) -> bool:
        return self.ece_after <= self.ece_before

    def to_dict(self) -> dict:
        d = asdict(self)
        d["nll_improved"] = self.nll_improved
        d["ece_improved"] = self.ece_improved
        return d


def is_temperature_at_boundary(
    temperature: float,
    bounds: tuple[float, float] = TEMPERATURE_BOUNDS_DEFAULT,
) -> bool:
    """True when the fitted T sits at either end of its search interval.

    A pinned temperature means the NLL had no interior optimum — normally
    perfectly separable calibration logits (low end) or logits anti-correlated
    with the labels (high end). The fit is not usable as a calibration even
    though nothing raised.
    """
    lo, hi = bounds
    span = hi - lo
    return (temperature - lo) <= _BOUNDARY_REL_TOL * span or (
        hi - temperature
    ) <= _BOUNDARY_REL_TOL * span


def diagnose_temperature_fit(
    logits: np.ndarray,
    y_true: np.ndarray,
    *,
    endpoint_key: str,
    seed: int,
    bounds: tuple[float, float] = TEMPERATURE_BOUNDS_DEFAULT,
    n_bins: int = 10,
) -> tuple[TemperatureScaler, CalibrationFitDiagnostics]:
    """Fit a temperature scaler and report how the fit behaved.

    Returns the scaler exactly as ``fit_temperature_scaler`` would — this adds
    observation, it does not alter the fit or reject anything.

    Raises
    ------
    ValueError
        Propagated from ``fit_temperature_scaler`` (empty input, length
        mismatch, single-class calibration split).
    """
    logits = np.asarray(logits, dtype=float)
    y_true = np.asarray(y_true, dtype=int)

    scaler = fit_temperature_scaler(logits, y_true, bounds=bounds)

    raw_probs = 1.0 / (1.0 + np.exp(-logits))
    cal_probs = scaler.transform_logits(logits)

    n_pos = int(y_true.sum())
    n_neg = int(len(y_true) - n_pos)

    # minimize_scalar's own convergence flag, which fit_temperature_scaler
    # discards. Re-derived here rather than changing that function's contract.
    from scipy.optimize import minimize_scalar

    def _nll(t: float) -> float:
        return _binary_cross_entropy(y_true, 1.0 / (1.0 + np.exp(-(logits / t))))

    opt = minimize_scalar(_nll, bounds=bounds, method="bounded")

    diagnostics = CalibrationFitDiagnostics(
        endpoint_key=endpoint_key,
        seed=seed,
        n_fit_samples=len(logits),
        n_positive=n_pos,
        n_negative=n_neg,
        positive_rate=float(n_pos / len(y_true)),
        temperature=scaler.temperature,
        at_boundary=is_temperature_at_boundary(scaler.temperature, bounds),
        optimizer_success=bool(getattr(opt, "success", False)),
        nll_before=_binary_cross_entropy(y_true, raw_probs),
        nll_after=_binary_cross_entropy(y_true, cal_probs),
        ece_before=expected_calibration_error(y_true, raw_probs, n_bins=n_bins),
        ece_after=expected_calibration_error(y_true, cal_probs, n_bins=n_bins),
    )
    return scaler, diagnostics
