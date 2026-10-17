"""Tests for ml/eval/tier0_regression.py: regression records are reported only when they can be reported honestly."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from eval.tier0_regression import compare, load_arm, main, render_markdown

ARM = "toy__reg"
EP = "toy_endpoint"
MAES = [1.0, 1.2, 0.8, 1.1, 0.9]


def _write_arm(root: Path, *, seeds=range(5), mae=MAES, n_test=50, prep="prepA", status="skipped_regression") -> None:
    for seed in seeds:
        d = root / ARM / f"seed{seed}"
        d.mkdir(parents=True)
        record = {
            "task_type": "regression",
            "status": status,
            "prep_id": prep,
            "model_id": "mars-kermt-single-v1",
            "n_test_labeled": n_test,
            "test_metrics_raw": {"mae": mae[seed], "n_samples": n_test},
        }
        (d / "lab_summary.json").write_text(json.dumps({"seed": seed, "calibration": {EP: record}}), encoding="utf-8")


def _write_xgb(root: Path, *, n_test=50, task="regression", seeds=5.0) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    report = {
        "task_type": task,
        "split": "test",
        "n_test": n_test,
        "aggregated_test_raw": {"mae_mean": 1.5, "mae_std": 0.1, "n_valid_seeds": seeds},
    }
    (root / f"{EP}.json").write_text(json.dumps(report), encoding="utf-8")
    return root


def test_aggregates_mean_and_sample_std(tmp_path):
    _write_arm(tmp_path)
    (run,) = load_arm(tmp_path, ARM)
    assert run.mae_mean == pytest.approx(np.mean(MAES))
    assert run.mae_std == pytest.approx(np.std(MAES, ddof=1))
    assert run.seeds == (0, 1, 2, 3, 4)


def test_classification_arm_is_refused(tmp_path):
    with pytest.raises(NotImplementedError, match="regression-only"):
        load_arm(tmp_path, "toy__cls")


def test_partial_arm_is_refused(tmp_path):
    _write_arm(tmp_path, seeds=range(3))
    with pytest.raises(ValueError, match="need 5"):
        load_arm(tmp_path, ARM)


def test_non_regression_record_is_refused(tmp_path):
    _write_arm(tmp_path, status="fitted")
    with pytest.raises(ValueError, match="not a regression record"):
        load_arm(tmp_path, ARM)


def test_nan_mae_is_refused(tmp_path):
    _write_arm(tmp_path, mae=[1.0, float("nan"), 1.0, 1.0, 1.0])
    with pytest.raises(ValueError, match="test MAE"):
        load_arm(tmp_path, ARM)


def test_compare_reports_signed_difference(tmp_path):
    _write_arm(tmp_path / "k")
    (run,) = load_arm(tmp_path / "k", ARM)
    row = compare(run, _write_xgb(tmp_path / "x"))
    assert row.difference == pytest.approx(np.mean(MAES) - 1.5)
    assert row.xgb_mae_std == 0.1


def test_compare_refuses_different_test_size(tmp_path):
    _write_arm(tmp_path / "k")
    (run,) = load_arm(tmp_path / "k", ARM)
    with pytest.raises(ValueError, match="not on the same test set"):
        compare(run, _write_xgb(tmp_path / "x", n_test=51))


def test_compare_refuses_classification_report(tmp_path):
    _write_arm(tmp_path / "k")
    (run,) = load_arm(tmp_path / "k", ARM)
    with pytest.raises(ValueError, match="regression test-split"):
        compare(run, _write_xgb(tmp_path / "x", task="classification"))


def test_table_names_no_winner(tmp_path, capsys):
    _write_arm(tmp_path / "k")
    _write_xgb(tmp_path / "x")
    assert main(["--results-dir", str(tmp_path / "k"), "--xgb-dir", str(tmp_path / "x"), "--arms", ARM]) == 0
    text = capsys.readouterr().out
    assert EP in text and "not a ranking" in text
    lowered = text.lower()
    for word in ("winner:", "better", "best", "outperform"):
        assert word not in lowered.replace("no winner is named", "")


def test_render_lists_snapshot_ids(tmp_path):
    _write_arm(tmp_path / "k")
    (run,) = load_arm(tmp_path / "k", ARM)
    text = render_markdown([compare(run, _write_xgb(tmp_path / "x"))], prep_ids={EP: run.prep_id})
    assert "`prepA`" in text
