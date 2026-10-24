"""Module 11 section 6 CPU ablations: calibration method comparison and the DILI paired bootstrap."""

from __future__ import annotations

import numpy as np
import pytest
from eval.calibration_ablation import (
    METHODS,
    EndpointAblation,
    calibrated_scores,
    logit,
    render_markdown,
    score_methods,
    summarise,
)
from eval.dili_augmentation_ablation import paired_auroc_difference
from eval.dili_augmentation_ablation import render_markdown as render_dili


def _toy(n: int, seed: int, shift: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    y = rng.integers(0, 2, n).astype(float)
    p = np.clip(0.5 + (y - 0.5) * 0.5 + rng.normal(shift, 0.2, n), 0.01, 0.99)
    return p, y


def test_logit_is_clipped_so_extreme_probabilities_stay_finite():
    out = logit(np.array([0.0, 1.0, 0.5]))
    assert np.isfinite(out).all() and out[2] == pytest.approx(0.0)


def test_every_method_is_fitted_and_stays_in_the_unit_interval():
    p_cal, y_cal = _toy(300, 1)
    p_te, _ = _toy(200, 2)
    probs, skipped = calibrated_scores(p_cal, y_cal, p_te)
    assert skipped is None and set(probs) == set(METHODS)
    for name in METHODS:
        assert probs[name].shape == p_te.shape
        assert probs[name].min() >= 0.0 and probs[name].max() <= 1.0


def test_a_one_class_calibration_split_is_skipped_not_filled_in():
    p_cal = np.array([0.2, 0.4, 0.6])
    probs, skipped = calibrated_scores(p_cal, np.array([1, 1, 1]), np.array([0.3, 0.7]))
    assert set(probs) == {"raw"} and skipped == "calibration split has one class"
    s = score_methods(p_cal, np.array([1, 1, 1]), np.array([0.3, 0.7, 0.5, 0.2]), np.array([0, 1, 1, 0]))
    assert s.brier["Platt"] is None and s.brier["raw"] is not None


def test_platt_and_temperature_leave_the_ranking_alone():
    p_cal, y_cal = _toy(400, 3)
    p_te, y_te = _toy(400, 4)
    s = score_methods(p_cal, y_cal, p_te, y_te)
    assert s.auroc["Platt"] == pytest.approx(s.auroc["raw"], abs=1e-9)
    assert s.auroc["temperature"] == pytest.approx(s.auroc["raw"], abs=1e-9)


def test_a_calibrator_fixes_a_score_that_is_systematically_too_low():
    p_cal, y_cal = _toy(2000, 5, shift=-0.25)
    p_te, y_te = _toy(2000, 6, shift=-0.25)
    s = score_methods(p_cal, y_cal, p_te, y_te)
    assert s.ece["Platt"] < s.ece["raw"]
    assert s.ece["isotonic"] < s.ece["raw"]


def test_summarise_returns_none_when_any_seed_could_not_be_fitted():
    p_cal, y_cal = _toy(300, 7)
    p_te, y_te = _toy(300, 8)
    good = score_methods(p_cal, y_cal, p_te, y_te)
    bad = score_methods(np.array([0.2, 0.4]), np.array([1, 1]), p_te, y_te)
    assert summarise([good, good], "brier", "Platt") is not None
    assert summarise([good, bad], "brier", "Platt") is None


def test_the_calibration_report_names_no_winner_and_warns_about_small_calibration_sets():
    p_cal, y_cal = _toy(60, 9)
    p_te, y_te = _toy(100, 10)
    s = score_methods(p_cal, y_cal, p_te, y_te)
    text = render_markdown([EndpointAblation("e", 60, int(y_cal.sum()), 100, [s, s], s)], today="2026-10-25", prep_id="x")
    low = text.lower()
    for word in ("winner", "outperform", "superior", "best method", "beats"):
        assert word not in low
    assert "not a ranking" in low and "small" in low


def test_paired_bootstrap_of_identical_scores_is_exactly_zero():
    p, y = _toy(120, 11)
    diff, lo, hi, used = paired_auroc_difference(y, p, p, n_boot=200)
    assert diff == 0.0 and lo == 0.0 and hi == 0.0 and used > 0


def test_paired_bootstrap_sees_a_clear_difference_and_reproduces():
    y = np.tile([0.0, 1.0], 100)
    good = y * 0.6 + 0.2
    rng = np.random.default_rng(12)
    noise = rng.random(200)
    a = paired_auroc_difference(y, good, noise, n_boot=300)
    b = paired_auroc_difference(y, good, noise, n_boot=300)
    assert a == b
    assert a[0] > 0.3 and a[1] > 0.0


def test_the_dili_report_states_the_interval_and_names_no_winner():
    sub = {"n": 96, "auroc_base": 0.9, "auroc_aug": 0.92, "diff": 0.02, "low": -0.03, "high": 0.07, "used": 3990}
    res = {
        "n_test": 96,
        "n_train_base": 378,
        "n_train_aug": 1119,
        "tdc_only": {k: (0.9, 0.01) for k in ("auroc", "auprc", "brier", "ece")},
        "augmented": {k: (0.92, 0.02) for k in ("auroc", "auprc", "brier", "ece")},
        "pos_rates": {"tdc_only_pool": 0.49, "augmented_pool": 0.63, "test": 0.52},
        "subsets": {"all": sub, "free": dict(sub, n=71), "shared": dict(sub, n=25)},
    }
    text = render_dili(res, today="2026-10-25", prep_id="x")
    assert "contains zero" in text and "not a ranking" in text
    low = text.lower()
    for word in ("winner", "outperform", "superior", "better"):
        assert word not in low
