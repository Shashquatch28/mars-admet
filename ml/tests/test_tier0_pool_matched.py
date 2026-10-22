"""The pool-matched table only prints rows whose pools, test sets and seeds were checked (B4)."""

from __future__ import annotations

import json

import pytest
from eval import tier0_pool_matched as pm
from eval.tier0_regression import EndpointRuns

REG = "absorption_distribution__reg"
CLS = "absorption_distribution__cls"


def _agg(prefix: str, mean: float, std: float, n_valid: int = 5) -> dict:
    return {f"{prefix}_mean": mean, f"{prefix}_std": std, "n_valid_seeds": n_valid}


def _record(endpoint: str, arm: str, agg: dict, *, n_pool: int, n_test: int, seeds: int = 5) -> dict:
    return {
        "endpoint": endpoint,
        "arm": arm,
        "n_pool_labels": n_pool,
        "n_test": n_test,
        "per_seed": [{}] * seeds,
        "aggregated_test_raw": agg,
    }


@pytest.fixture
def world(tmp_path, monkeypatch):
    runs = EndpointRuns(REG, "solubility_logs", "snap", (0, 1, 2, 3, 4), (0.8,) * 5, 1960, "m")
    monkeypatch.setattr(pm.tier0_regression, "load_arm", lambda d, arm: [runs] if arm == REG else [])
    monkeypatch.setattr(
        pm.tier0_classification, "load_arm",
        lambda d, arm: [("hia_absorption", 117, {**_agg("auroc", 0.926, 0.017), **_agg("auprc", 0.974, 0.008)})] if arm == CLS else [],
    )
    monkeypatch.setattr(pm, "expected_pool_sizes", lambda d, arm: {"solubility_logs": 6698, "hia_absorption": 375})
    xgb = tmp_path / "xgb"
    xgb.mkdir()
    (xgb / "solubility_logs.json").write_text(json.dumps(
        {"task_type": "regression", "split": "test", "n_test": 1960, "aggregated_test_raw": _agg("mae", 0.81, 0.014)}))
    (xgb / "hia_absorption.json").write_text(json.dumps(
        {"task_type": "classification", "split": "test", "n_test": 117,
         "aggregated_test_raw": {**_agg("auroc", 0.972, 0.002), **_agg("auprc", 0.990, 0.001)}}))
    matched = {
        "control": False,
        "records": [
            _record("solubility_logs", REG, _agg("mae", 0.79, 0.01), n_pool=6698, n_test=1960),
            _record("hia_absorption", CLS, {**_agg("auroc", 0.95, 0.01), **_agg("auprc", 0.98, 0.005)}, n_pool=375, n_test=117),
        ],
    }
    return matched, tmp_path, xgb


def test_rows_carry_all_three_sides_and_a_signed_difference(world):
    matched, results, xgb = world
    rows = pm.build_rows(matched, results, xgb)
    assert [(r.endpoint, r.metric) for r in rows] == [
        ("solubility_logs", "MAE"), ("hia_absorption", "AUROC"), ("hia_absorption", "AUPRC")]
    sol = rows[0]
    assert sol.kermt.mean == pytest.approx(0.8) and sol.matched.mean == pytest.approx(0.79) and sol.full.mean == pytest.approx(0.81)
    assert sol.difference == pytest.approx(0.01)
    assert not sol.within_spread  # |0.01| is not smaller than the larger std (0.01)
    assert rows[1].difference == pytest.approx(0.926 - 0.95) and not rows[1].within_spread


def test_within_spread_is_a_comparison_with_the_larger_seed_std():
    row = pm.MetricRow("e", "a", "MAE", 10, 100, pm.Side(1.00, 0.05), pm.Side(1.02, 0.01), pm.Side(1.0, 0.01))
    assert row.within_spread  # |-0.02| < max(0.05, 0.01)
    far = pm.MetricRow("e", "a", "MAE", 10, 100, pm.Side(1.00, 0.01), pm.Side(1.20, 0.01), pm.Side(1.0, 0.01))
    assert not far.within_spread


def test_a_control_file_is_refused(world):
    matched, results, xgb = world
    with pytest.raises(ValueError, match="control"):
        pm.build_rows({**matched, "control": True}, results, xgb)


def test_a_pool_that_is_not_kermts_is_refused(world):
    matched, results, xgb = world
    matched["records"][0]["n_pool_labels"] = 6699
    with pytest.raises(ValueError, match="KERMT trained on"):
        pm.build_rows(matched, results, xgb)


def test_a_different_test_set_is_refused(world):
    matched, results, xgb = world
    matched["records"][1]["n_test"] = 118
    with pytest.raises(ValueError, match="n_test differs"):
        pm.build_rows(matched, results, xgb)


def test_fewer_than_five_seeds_is_refused(world):
    matched, results, xgb = world
    matched["records"][0]["per_seed"] = [{}] * 3
    with pytest.raises(ValueError, match="fewer than"):
        pm.build_rows(matched, results, xgb)


def test_an_arm_that_cannot_be_matched_is_refused(world):
    matched, results, xgb = world
    matched["records"][0]["arm"] = "metabolism__cls"
    with pytest.raises(ValueError, match="pool-matched"):
        pm.build_rows(matched, results, xgb)


def test_rendered_table_names_no_winner_and_lists_what_is_excluded(world):
    matched, results, xgb = world
    text = pm.render_markdown(pm.build_rows(matched, results, xgb))
    assert "KERMT minus XGBoost (pool-matched)" in text
    assert "not a ranking" in text
    for word in ("winner:", "outperform", "superior", "best model"):
        assert word not in text.lower()
    for excluded in ("metabolism__cls", "dili_standalone__cls", "toxicity__cls"):
        assert excluded in text.split("## Not in this table")[1]
