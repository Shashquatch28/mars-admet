"""Module 11 held-out results: the bootstrap interval, the per-seed and ensemble scoring, the TDC table."""

from __future__ import annotations

import numpy as np
import pytest
from eval.evaluation_results import (
    _auroc,
    _mae,
    bootstrap_interval,
    render_markdown,
    score_endpoint,
)
from eval.tdc_leaderboard_table import mars_value
from eval.tdc_leaderboard_table import render_markdown as render_tdc


def test_bootstrap_interval_brackets_the_point_estimate_and_is_reproducible():
    rng = np.random.default_rng(1)
    y = rng.integers(0, 2, 300).astype(float)
    p = np.clip(y * 0.4 + rng.normal(0.3, 0.25, 300), 0, 1)
    a = bootstrap_interval(y, p, _auroc, n_boot=300, needs_both_classes=True)
    b = bootstrap_interval(y, p, _auroc, n_boot=300, needs_both_classes=True)
    assert a == b
    assert a.low <= a.point <= a.high
    assert a.n_boot == 300 and a.n_skipped == 0


def test_a_smaller_test_set_gives_a_wider_interval():
    rng = np.random.default_rng(2)

    def width(n: int) -> float:
        y = rng.integers(0, 2, n).astype(float)
        p = np.clip(y * 0.4 + rng.normal(0.3, 0.25, n), 0, 1)
        iv = bootstrap_interval(y, p, _auroc, n_boot=400, needs_both_classes=True)
        return iv.high - iv.low

    assert width(60) > width(1200)


def test_resamples_with_one_class_are_skipped_and_counted():
    y = np.array([0.0] * 29 + [1.0])  # a resample often misses the single positive
    p = np.linspace(0, 1, 30)
    iv = bootstrap_interval(y, p, _auroc, n_boot=200, needs_both_classes=True)
    assert iv.n_skipped > 0
    assert iv.n_boot + iv.n_skipped == 200


def test_regression_mae_interval_and_all_degenerate_is_refused():
    y = np.arange(50, dtype=float)
    iv = bootstrap_interval(y, y + 1.0, _mae, n_boot=100)
    assert iv.point == pytest.approx(1.0) and iv.low == pytest.approx(1.0) and iv.high == pytest.approx(1.0)
    with pytest.raises(ValueError):
        bootstrap_interval(np.zeros(10), np.zeros(10), _auroc, n_boot=20, needs_both_classes=True)


def test_score_endpoint_uses_only_molecules_every_seed_could_score():
    y = np.array([0, 1, 0, 1, 1, 0, 1, 0, 1, 1], dtype=float)
    base = np.array([0.1, 0.9, 0.2, 0.8, 0.7, 0.3, 0.6, 0.4, 0.9, 0.8])
    a, b = base.copy(), np.clip(base + 0.05, 0, 1)
    b[3] = np.nan  # one seed could not featurize molecule 3
    res = score_endpoint("e", task="classification", y_test=y, seed_preds=[a, b], n_test=10)
    assert res.n_test == 10 and res.n_scored == 9
    assert res.primary_metric == "AUROC"
    assert set(res.secondary) == {"AUPRC", "Brier", "ECE"}


def test_score_endpoint_regression_reports_mae_and_no_secondary():
    y = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    res = score_endpoint(
        "r", task="regression", y_test=y, seed_preds=[y + 0.5, y - 0.5, y + 0.25], n_test=6
    )
    assert res.primary_metric == "MAE" and res.secondary == {}
    assert res.seed_mean == pytest.approx((0.5 + 0.5 + 0.25) / 3)
    assert res.ensemble.point == pytest.approx(abs((0.5 - 0.5 + 0.25) / 3))


def test_the_results_report_names_no_winner():
    y = np.array([0, 1, 0, 1, 1, 0, 1, 0, 1, 1] * 10, dtype=float)
    p = np.clip(y * 0.5 + 0.2, 0, 1)
    res = score_endpoint("e", task="classification", y_test=y, seed_preds=[p, p * 0.99], n_test=100)
    routing = {"default": "xgboost", "endpoints": {"e": {"model": "kermt"}}}
    text = render_markdown([res], routing, {"e": ("AUROC", 0.9, 0.01, 100)}, today="2026-10-24", prep_id="x")
    low = text.lower()
    for word in ("winner", "outperform", "superior", "best model", "beats"):
        assert word not in low
    assert "selection effect" in low


def test_mars_value_picks_the_leaderboard_metric():
    ev = {"metric": "AUROC", "seed_mean": 0.9, "seed_std": 0.01, "secondary": {"AUPRC": [0.8, 0.02]}}
    assert mars_value("AUROC", ev) == (0.9, 0.01)
    assert mars_value("AUPRC", ev) == (0.8, 0.02)
    assert mars_value("MAE", ev) is None


def test_the_tdc_table_states_its_audit_gap_and_never_ranks_mars():
    reference = {
        "accessed": "2026-10-24",
        "audit_status": "The audit was not located.",
        "page_notes": "n",
        "not_comparable": {"ppb_binding": "own split"},
    }
    row = {
        "endpoint": "hia_absorption",
        "ref": {
            "tdc_dataset": "HIA_Hou", "metric": "AUROC", "tdc_size": 578,
            "top": ["MiniMol", 0.993, 0.005],
            "named": {"MapLight": [0.986, 0.0], "MapLight + GNN": [0.989, 0.001]},
        },
        "mars": (0.972, 0.002), "served": "-", "n_test": 117,
    }
    text = render_tdc([row], reference, today="2026-10-24")
    assert "not located" in text and "unaudited" in text and "not listed" in text
    low = text.lower()
    for word in ("winner", "outperform", "superior", "state of the art", "beats", "ranks"):
        assert word not in low
