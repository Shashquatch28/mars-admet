"""
Tests for ml/eval/tdc_comparison.py.

Comparability logic is data-driven from provenance["split_method"] — tested
against both synthetic provenance dicts and the real M1 AMES snapshot.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from data.loaders import EndpointData
from eval.evaluate import EvaluationReport
from eval.tdc_comparison import (
    TDCBenchmarkEntry,
    TDCComparisonResult,
    build_tdc_comparison,
    determine_comparability,
)
from mars_contracts.endpoints import TaskType


def _fake_endpoint_data(*, endpoint_key: str, split_method: str | None) -> EndpointData:
    df = pd.DataFrame({"standardized_smiles": ["CCO", "CCC"], "label": [0, 1]})
    provenance = {"split_method": split_method} if split_method is not None else {}
    return EndpointData(
        endpoint_key=endpoint_key,
        dataset_key=endpoint_key,
        task_type=TaskType.CLASSIFICATION,
        prep_id="test-prep",
        train_val=df,
        test=df,
        calibration=df,
        provenance=provenance,
    )


def _fake_report(endpoint_key: str) -> EvaluationReport:
    return EvaluationReport(
        endpoint_key=endpoint_key,
        model_family="xgboost",
        prep_id="test-prep",
        task_type="classification",
        seeds=[0, 1, 2, 3, 4],
        run_ids=[f"xgb_{endpoint_key}_seed{s}" for s in range(5)],
        per_seed_metrics=[],
        aggregated={"auroc_mean": 0.85, "auroc_std": 0.02},
    )


# ---------------------------------------------------------------------------- #
# determine_comparability
# ---------------------------------------------------------------------------- #


def test_adopt_benchmark_is_comparable():
    comparable, note = determine_comparability("adopt_benchmark")
    assert comparable
    assert "comparable" in note.lower()


def test_scaffold_is_not_comparable():
    comparable, note = determine_comparability("scaffold")
    assert not comparable
    assert "not" in note.lower() or "NOT" in note


def test_unknown_split_method_raises():
    with pytest.raises(ValueError, match="Unknown split_method"):
        determine_comparability("bogus_method")


# ---------------------------------------------------------------------------- #
# build_tdc_comparison
# ---------------------------------------------------------------------------- #


def test_build_comparison_adopt_benchmark():
    ep = _fake_endpoint_data(endpoint_key="ames_mutagenicity", split_method="adopt_benchmark")
    report = _fake_report("ames_mutagenicity")
    result = build_tdc_comparison(report, ep, mars_metric_name="auroc")
    assert isinstance(result, TDCComparisonResult)
    assert result.comparable
    assert result.mars_metric_mean == pytest.approx(0.85)
    assert result.mars_metric_std == pytest.approx(0.02)
    assert result.split_method == "adopt_benchmark"
    assert result.tdc_reference is None


def test_build_comparison_scaffold_split_not_comparable():
    ep = _fake_endpoint_data(endpoint_key="herg_cardiotoxicity", split_method="scaffold")
    report = _fake_report("herg_cardiotoxicity")
    result = build_tdc_comparison(report, ep, mars_metric_name="auroc")
    assert not result.comparable


def test_build_comparison_endpoint_mismatch_raises():
    ep = _fake_endpoint_data(endpoint_key="ames_mutagenicity", split_method="adopt_benchmark")
    report = _fake_report("solubility_logs")  # different endpoint
    with pytest.raises(ValueError, match="endpoint mismatch"):
        build_tdc_comparison(report, ep, mars_metric_name="auroc")


def test_build_comparison_missing_split_method_raises():
    ep = _fake_endpoint_data(endpoint_key="ames_mutagenicity", split_method=None)
    report = _fake_report("ames_mutagenicity")
    with pytest.raises(ValueError, match="split_method"):
        build_tdc_comparison(report, ep, mars_metric_name="auroc")


def test_build_comparison_missing_metric_raises():
    ep = _fake_endpoint_data(endpoint_key="ames_mutagenicity", split_method="adopt_benchmark")
    report = _fake_report("ames_mutagenicity")
    with pytest.raises(ValueError, match="not found"):
        build_tdc_comparison(report, ep, mars_metric_name="nonexistent_metric")


def test_build_comparison_with_tdc_reference():
    ep = _fake_endpoint_data(endpoint_key="ames_mutagenicity", split_method="adopt_benchmark")
    report = _fake_report("ames_mutagenicity")
    ref = TDCBenchmarkEntry(
        tdc_dataset_name="AMES",
        metric_name="AUROC",
        leaderboard_best=0.873,
        leaderboard_best_method="CNN",
        looked_up_at_utc="2026-09-16T00:00:00Z",
    )
    result = build_tdc_comparison(report, ep, mars_metric_name="auroc", tdc_reference=ref)
    assert result.tdc_reference == ref


# ---------------------------------------------------------------------------- #
# save / load roundtrip
# ---------------------------------------------------------------------------- #


def test_save_load_roundtrip_without_reference(tmp_path):
    ep = _fake_endpoint_data(endpoint_key="ames_mutagenicity", split_method="adopt_benchmark")
    report = _fake_report("ames_mutagenicity")
    result = build_tdc_comparison(report, ep, mars_metric_name="auroc")
    path = tmp_path / "comparison.json"
    result.save(path)
    loaded = TDCComparisonResult.load(path)
    assert loaded == result


def test_save_load_roundtrip_with_reference(tmp_path):
    ep = _fake_endpoint_data(endpoint_key="ames_mutagenicity", split_method="adopt_benchmark")
    report = _fake_report("ames_mutagenicity")
    ref = TDCBenchmarkEntry(
        tdc_dataset_name="AMES",
        metric_name="AUROC",
        leaderboard_best=0.873,
        leaderboard_best_method="CNN",
        looked_up_at_utc="2026-09-16T00:00:00Z",
    )
    result = build_tdc_comparison(report, ep, mars_metric_name="auroc", tdc_reference=ref)
    path = tmp_path / "comparison.json"
    result.save(path)
    loaded = TDCComparisonResult.load(path)
    assert loaded == result
    assert loaded.tdc_reference == ref


# ---------------------------------------------------------------------------- #
# Integration: real M1 AMES provenance
# ---------------------------------------------------------------------------- #

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "ml" / "data"


def _newest_prep_dir() -> Path | None:
    root = DATA / "processed"
    if not root.exists():
        return None
    dirs = sorted(p for p in root.iterdir() if p.is_dir())
    return dirs[-1] if dirs else None


PREP_DIR = _newest_prep_dir()


def test_integration_real_ames_is_comparable():
    if PREP_DIR is None:
        pytest.skip("no processed outputs")
    from data.loaders import load_endpoint

    endpoint_data = load_endpoint(PREP_DIR, "ames_mutagenicity")
    assert endpoint_data.provenance.get("split_method") == "adopt_benchmark"
    report = _fake_report("ames_mutagenicity")
    result = build_tdc_comparison(report, endpoint_data, mars_metric_name="auroc")
    assert result.comparable


def test_integration_real_herg_karim_is_not_comparable():
    """hERG_Karim self-generates its split (no official TDC benchmark split) —
    blueprint-documented non-comparable endpoint."""
    if PREP_DIR is None:
        pytest.skip("no processed outputs")
    from data.loaders import list_available_endpoints, load_endpoint

    available = list_available_endpoints(PREP_DIR)
    herg_key = next((k for k in available if "herg" in k.lower()), None)
    if herg_key is None:
        pytest.skip("no hERG dataset in this processed snapshot")

    endpoint_data = load_endpoint(PREP_DIR, herg_key)
    split_method = endpoint_data.provenance.get("split_method")
    if split_method != "scaffold":
        pytest.skip(f"{herg_key} unexpectedly uses split_method={split_method!r}, not the documented case")

    report = _fake_report(herg_key)
    report.endpoint_key = herg_key
    result = build_tdc_comparison(report, endpoint_data, mars_metric_name="auroc")
    assert not result.comparable
