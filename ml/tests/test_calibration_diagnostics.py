"""
Tests for eval/calibration_diagnostics.py.

These pin the two silent degenerate modes of ``fit_temperature_scaler`` that had
no coverage before: boundary pinning, and technically-valid-but-meaningless fits
on nearly single-class calibration splits. The existing test_calibration.py
suite only exercises N=300-4000 well-behaved synthetic logits.

All synthetic. No KERMT output is fabricated — these characterise the estimator.
"""

from __future__ import annotations

import numpy as np
import pytest
from eval.calibration import TEMPERATURE_BOUNDS_DEFAULT
from eval.calibration_diagnostics import (
    CalibrationFitDiagnostics,
    diagnose_temperature_fit,
    is_temperature_at_boundary,
)


def _overconfident(n: int, pos_rate: float, seed: int, steepness: float = 2.5):
    rng = np.random.default_rng(seed)
    shift = float(np.log(pos_rate / (1 - pos_rate)))
    true_logit = rng.normal(shift, 2.0, n)
    y = rng.binomial(1, 1.0 / (1.0 + np.exp(-true_logit)))
    return true_logit * steepness, y


def test_boundary_helper_flags_both_ends():
    lo, hi = TEMPERATURE_BOUNDS_DEFAULT
    assert is_temperature_at_boundary(lo)
    assert is_temperature_at_boundary(hi)
    assert not is_temperature_at_boundary(1.0)
    assert not is_temperature_at_boundary(2.5)


def test_anti_correlated_logits_pin_to_upper_bound_and_are_flagged():
    """The failure mode that currently returns silently.

    Labels anti-correlated with the logits give a NLL that is monotone in T, so
    the bounded optimiser walks to T=10.0 and fit_temperature_scaler returns it
    with no error and no indication anything went wrong.
    """
    rng = np.random.default_rng(0)
    logits = rng.normal(0, 3, 241)
    y = (logits < 0).astype(int)

    scaler, diag = diagnose_temperature_fit(logits, y, endpoint_key="synthetic", seed=0)

    assert scaler.temperature == pytest.approx(TEMPERATURE_BOUNDS_DEFAULT[1])
    assert diag.at_boundary is True


def test_well_behaved_fit_is_not_flagged_and_improves_both_metrics():
    logits, y = _overconfident(833, 0.132, seed=1)
    _, diag = diagnose_temperature_fit(logits, y, endpoint_key="synthetic", seed=1)

    assert diag.at_boundary is False
    assert diag.optimizer_success is True
    assert diag.nll_improved
    assert diag.ece_improved
    assert diag.temperature > 1.0  # over-confident logits need softening


def test_diagnostics_record_the_class_counts_the_artifact_omits():
    """TemperatureScaler stores only (temperature, n_fit_samples).

    n=241 with 67 positives and n=241 with 2 positives are indistinguishable
    from the artifact alone; the diagnostics separate them.
    """
    logits, y = _overconfident(241, 0.278, seed=2)
    _, diag = diagnose_temperature_fit(logits, y, endpoint_key="cyp3a4_inhibition", seed=2)

    assert diag.n_fit_samples == 241
    assert diag.n_positive + diag.n_negative == 241
    assert diag.positive_rate == pytest.approx(diag.n_positive / 241)
    assert diag.endpoint_key == "cyp3a4_inhibition"
    assert diag.seed == 2


def test_nearly_single_class_fit_succeeds_but_is_visible_in_diagnostics():
    """Mirrors the real hia_absorption calibrator: 50 samples, 49 positive.

    fit_temperature_scaler only rejects a STRICTLY single-class split, so this
    is accepted. Nothing here asserts it is acceptable — the point is that the
    class counts must be recorded so a reviewer can see it.
    """
    rng = np.random.default_rng(3)
    logits = np.concatenate([rng.normal(3, 1, 49), rng.normal(-3, 1, 1)])
    y = np.concatenate([np.ones(49, int), np.zeros(1, int)])

    _, diag = diagnose_temperature_fit(logits, y, endpoint_key="synthetic", seed=0)

    assert diag.n_positive == 49
    assert diag.n_negative == 1
    assert diag.positive_rate == pytest.approx(0.98)


def test_single_class_still_raises_through_the_diagnostic_wrapper():
    with pytest.raises(ValueError, match="both classes"):
        diagnose_temperature_fit(
            np.array([0.1, 0.2, 0.3]), np.array([0, 0, 0]), endpoint_key="x", seed=0
        )


def test_diagnostics_serialize_for_experiment_run():
    logits, y = _overconfident(439, 0.20, seed=4)
    _, diag = diagnose_temperature_fit(logits, y, endpoint_key="cyp2c9_inhibition", seed=4)

    d = diag.to_dict()
    assert isinstance(diag, CalibrationFitDiagnostics)
    assert d["endpoint_key"] == "cyp2c9_inhibition"
    assert "nll_improved" in d and "ece_improved" in d
    import json

    json.dumps(d)  # must be loggable to ExperimentRun / W&B


def test_diagnose_does_not_alter_the_fitted_temperature():
    """The wrapper observes; it must not change the result."""
    from eval.calibration import fit_temperature_scaler

    logits, y = _overconfident(439, 0.20, seed=5)
    plain = fit_temperature_scaler(logits, y)
    wrapped, _ = diagnose_temperature_fit(logits, y, endpoint_key="x", seed=5)
    assert wrapped.temperature == pytest.approx(plain.temperature)
    assert wrapped.n_fit_samples == plain.n_fit_samples
