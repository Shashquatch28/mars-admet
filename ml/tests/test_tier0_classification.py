"""The classification report prints both sides and makes no comparison (ship checklist B4 fallback)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from eval import tier0_classification as t

ARM = "absorption_distribution__cls"
EP = "hia_absorption"


def _write(tmp: Path, *, seeds: int = 5, valid: int = 5, n_test: int = 117, xgb_n_test: int = 117, xgb_valid: int = 5):
    results = tmp / "results"
    for s in range(seeds):
        d = results / ARM / f"seed{s}"
        d.mkdir(parents=True)
        (d / "lab_summary.json").write_text(json.dumps({"seed": s, "calibration": {EP: {"n_test_labeled": n_test}}}))
    raw = {"auroc_mean": 0.926, "auroc_std": 0.017, "auprc_mean": 0.974, "auprc_std": 0.008, "n_valid_seeds": valid}
    (results / ARM / "aggregate_5seeds.json").write_text(
        json.dumps({"test_metrics_across_seeds": {EP: {"raw": raw, "calibrated": {}}}})
    )
    xgb = tmp / "xgb"
    xgb.mkdir()
    (xgb / f"{EP}.json").write_text(
        json.dumps(
            {
                "task_type": "classification",
                "split": "test",
                "n_test": xgb_n_test,
                "aggregated_test_raw": {
                    "auroc_mean": 0.972,
                    "auroc_std": 0.002,
                    "auprc_mean": 0.990,
                    "auprc_std": 0.001,
                    "n_valid_seeds": xgb_valid,
                },
            }
        )
    )
    return results, xgb


def _rows(results: Path, xgb: Path):
    return [t.compare(ARM, ep, n, raw, xgb) for ep, n, raw in t.load_arm(results, ARM)]


def test_report_shows_both_sides_and_no_comparison(tmp_path):
    results, xgb = _write(tmp_path)
    text = t.render_markdown(_rows(results, xgb))
    assert "0.926 ± 0.017" in text and "0.972 ± 0.002" in text
    assert "No KERMT-versus-XGBoost claim" in text
    lowered = text.lower()
    for word in ("winner:", "better", "outperform", "minus", "delta", "rank "):
        assert word not in lowered.replace("no ranking and no winner", ""), word
    header = next(line for line in text.splitlines() if line.startswith("| endpoint"))
    assert "minus" not in header.lower() and "diff" not in header.lower()


def test_a_partial_arm_is_refused(tmp_path):
    results, xgb = _write(tmp_path, seeds=2)
    with pytest.raises(ValueError, match="need 5"):
        t.load_arm(results, ARM)


def test_an_arm_with_fewer_valid_seeds_is_refused(tmp_path):
    results, xgb = _write(tmp_path, valid=3)
    with pytest.raises(ValueError, match="valid seeds"):
        t.load_arm(results, ARM)


def test_different_test_sizes_are_refused(tmp_path):
    results, xgb = _write(tmp_path, xgb_n_test=118)
    with pytest.raises(ValueError, match="not the same test set"):
        _rows(results, xgb)


def test_xgboost_with_too_few_seeds_is_refused(tmp_path):
    results, xgb = _write(tmp_path, xgb_valid=4)
    with pytest.raises(ValueError, match="XGBoost report has"):
        _rows(results, xgb)


def test_a_regression_arm_is_refused(tmp_path):
    with pytest.raises(NotImplementedError):
        t.load_arm(tmp_path, "metabolism__reg")


def test_every_default_arm_has_a_pool_note():
    assert set(t.DEFAULT_ARMS) == set(t.ARM_NOTES)
    assert all(t.ARM_NOTES.values())
