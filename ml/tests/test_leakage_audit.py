"""
Tests for ml/eval/leakage_audit.py.

Each check is verified both on clean data (must pass) and on deliberately
corrupted synthetic data (must fail) — proving the checks actually detect
violations rather than trivially passing on anything.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from data.loaders import EndpointData
from eval.calibration import PlattCalibrator
from eval.leakage_audit import (
    LeakageAuditReport,
    assert_no_leakage,
    check_ad_index_disjoint_from_test,
    check_calibration_disjoint_from_test,
    check_calibration_subset_of_train_val,
    check_calibrator_fit_sample_count,
    check_no_duplicate_smiles_within_test,
    check_no_duplicate_smiles_within_train_val,
    check_seed_fold_scaffold_isolation,
    check_seed_folds_cover_train_val,
    check_test_disjoint_from_train_val_scaffolds,
    check_test_disjoint_from_train_val_smiles,
    run_leakage_audit,
)
from mars_contracts.endpoints import TaskType

# 20 chemically diverse real SMILES so scaffold splitting has something to work with.
_POOL = [
    "CCO", "c1ccccc1", "CC(=O)Oc1ccccc1C(=O)O", "Cn1c(=O)c2c(ncn2C)n(c1=O)C",
    "OCC1OC(O)C(O)C(O)C1O", "Cc1ccccc1", "Oc1ccccc1", "CC(C)=O", "CCCO", "CCCCO",
    "CCCCCO", "CCCCCCO", "c1ccc2ccccc2c1", "c1ccc2[nH]ccc2c1", "CCN(CC)CC",
    "CC(C)(C)O", "c1ccncc1", "c1ccoc1", "c1ccsc1", "CC(=O)N",
]


def _make_endpoint_data(
    *,
    train_val_smiles: list[str],
    test_smiles: list[str],
    calibration_smiles: list[str],
    endpoint_key: str = "synthetic_endpoint",
) -> EndpointData:
    def _df(smiles: list[str]) -> pd.DataFrame:
        return pd.DataFrame({"standardized_smiles": smiles, "label": [i % 2 for i in range(len(smiles))]})

    return EndpointData(
        endpoint_key=endpoint_key,
        dataset_key=endpoint_key,
        task_type=TaskType.CLASSIFICATION,
        prep_id="test-prep",
        train_val=_df(train_val_smiles),
        test=_df(test_smiles),
        calibration=_df(calibration_smiles),
        provenance={},
    )


def _clean_endpoint_data() -> EndpointData:
    train_val = _POOL[:14]
    test = _POOL[14:]
    calibration = _POOL[:3]  # subset of train_val
    return _make_endpoint_data(train_val_smiles=train_val, test_smiles=test, calibration_smiles=calibration)


# ---------------------------------------------------------------------------- #
# 1-2: test vs train_val (SMILES + scaffold)
# ---------------------------------------------------------------------------- #


def test_check_test_disjoint_smiles_passes_on_clean_data():
    ep = _clean_endpoint_data()
    result = check_test_disjoint_from_train_val_smiles(ep)
    assert result.passed


def test_check_test_disjoint_smiles_fails_on_injected_leak():
    ep = _make_endpoint_data(
        train_val_smiles=_POOL[:10],
        test_smiles=[_POOL[0], *_POOL[10:15]],  # _POOL[0] leaked from train_val
        calibration_smiles=_POOL[1:3],
    )
    result = check_test_disjoint_from_train_val_smiles(ep)
    assert not result.passed
    assert "1 overlapping" in result.detail


def test_check_test_disjoint_scaffolds_passes_on_clean_data():
    ep = _clean_endpoint_data()
    result = check_test_disjoint_from_train_val_scaffolds(ep)
    assert result.passed


def test_check_test_disjoint_scaffolds_fails_on_injected_leak():
    # _POOL[1] = benzene (a real ring scaffold, not the allowed acyclic "" bucket)
    # in both train_val and test -> non-acyclic scaffold overlap.
    ep = _make_endpoint_data(
        train_val_smiles=_POOL[:10],
        test_smiles=[_POOL[1], *_POOL[10:15]],
        calibration_smiles=[_POOL[2], _POOL[3]],
    )
    result = check_test_disjoint_from_train_val_scaffolds(ep)
    assert not result.passed


# ---------------------------------------------------------------------------- #
# 3-4: calibration isolation
# ---------------------------------------------------------------------------- #


def test_check_calibration_subset_passes_on_clean_data():
    ep = _clean_endpoint_data()
    result = check_calibration_subset_of_train_val(ep)
    assert result.passed


def test_check_calibration_subset_fails_when_calibration_has_foreign_smiles():
    ep = _make_endpoint_data(
        train_val_smiles=_POOL[:10],
        test_smiles=_POOL[10:15],
        calibration_smiles=[_POOL[15]],  # not in train_val at all
    )
    result = check_calibration_subset_of_train_val(ep)
    assert not result.passed


def test_check_calibration_disjoint_from_test_passes_on_clean_data():
    ep = _clean_endpoint_data()
    result = check_calibration_disjoint_from_test(ep)
    assert result.passed


def test_check_calibration_disjoint_from_test_fails_on_overlap():
    ep = _make_endpoint_data(
        train_val_smiles=_POOL[:10],
        test_smiles=[_POOL[0], *_POOL[10:15]],
        calibration_smiles=[_POOL[0]],  # same molecule as the leaked test one
    )
    result = check_calibration_disjoint_from_test(ep)
    assert not result.passed


# ---------------------------------------------------------------------------- #
# 5-6: internal duplicates
# ---------------------------------------------------------------------------- #


def test_check_no_duplicates_train_val_passes_on_clean_data():
    ep = _clean_endpoint_data()
    assert check_no_duplicate_smiles_within_train_val(ep).passed


def test_check_no_duplicates_train_val_fails_on_dupe():
    ep = _make_endpoint_data(
        train_val_smiles=[_POOL[0], _POOL[0], *_POOL[1:10]],
        test_smiles=_POOL[10:15],
        calibration_smiles=_POOL[1:3],
    )
    result = check_no_duplicate_smiles_within_train_val(ep)
    assert not result.passed
    assert "1 duplicate" in result.detail


def test_check_no_duplicates_test_passes_on_clean_data():
    ep = _clean_endpoint_data()
    assert check_no_duplicate_smiles_within_test(ep).passed


def test_check_no_duplicates_test_fails_on_dupe():
    ep = _make_endpoint_data(
        train_val_smiles=_POOL[:10],
        test_smiles=[_POOL[10], _POOL[10], *_POOL[11:15]],
        calibration_smiles=_POOL[1:3],
    )
    result = check_no_duplicate_smiles_within_test(ep)
    assert not result.passed


# ---------------------------------------------------------------------------- #
# 7-8: per-seed CV fold checks
# ---------------------------------------------------------------------------- #


def test_check_seed_fold_scaffold_isolation_passes():
    ep = _clean_endpoint_data()
    result = check_seed_fold_scaffold_isolation(ep)
    assert result.passed
    assert "5 seeds" in result.detail


def test_check_seed_folds_cover_train_val_passes():
    ep = _clean_endpoint_data()
    result = check_seed_folds_cover_train_val(ep)
    assert result.passed


# ---------------------------------------------------------------------------- #
# 9: AD index isolation (optional check)
# ---------------------------------------------------------------------------- #


def test_check_ad_index_disjoint_from_test_passes_on_clean_index():
    from eval.applicability_domain import build_ad_index

    ep = _clean_endpoint_data()
    idx = build_ad_index("synthetic_endpoint", ep.train_val["standardized_smiles"].tolist(), k=3)
    result = check_ad_index_disjoint_from_test(ep, idx)
    assert result.passed


def test_check_ad_index_disjoint_from_test_fails_on_leaked_reference():
    from eval.applicability_domain import build_ad_index

    ep = _clean_endpoint_data()
    idx = build_ad_index("synthetic_endpoint", ep.train_val["standardized_smiles"].tolist(), k=3)
    # Corrupt the index: inject a test-set SMILES into its reference set.
    leaked_smiles = ep.test["standardized_smiles"].iloc[0]
    idx.reference_smiles = [*idx.reference_smiles, leaked_smiles]
    result = check_ad_index_disjoint_from_test(ep, idx)
    assert not result.passed


# ---------------------------------------------------------------------------- #
# 10: calibrator fit-sample-count isolation (optional check)
# ---------------------------------------------------------------------------- #


def test_check_calibrator_fit_sample_count_passes_within_bounds():
    ep = _clean_endpoint_data()  # calibration has 3 rows
    cal = PlattCalibrator(A=1.0, B=0.0, n_fit_samples=3)
    result = check_calibrator_fit_sample_count(ep, cal)
    assert result.passed


def test_check_calibrator_fit_sample_count_fails_when_exceeding_split():
    ep = _clean_endpoint_data()  # calibration has 3 rows
    cal = PlattCalibrator(A=1.0, B=0.0, n_fit_samples=999)  # impossible without leakage
    result = check_calibrator_fit_sample_count(ep, cal)
    assert not result.passed
    assert "EXCEEDS" in result.detail


# ---------------------------------------------------------------------------- #
# Orchestrator + assert_no_leakage
# ---------------------------------------------------------------------------- #


def test_run_leakage_audit_default_checks_only():
    ep = _clean_endpoint_data()
    report = run_leakage_audit(ep)
    assert isinstance(report, LeakageAuditReport)
    assert len(report.checks) == 8  # 6 split checks + 2 fold checks, no optional artifacts
    assert report.all_passed


def test_run_leakage_audit_with_optional_artifacts():
    from eval.applicability_domain import build_ad_index

    ep = _clean_endpoint_data()
    idx = build_ad_index("synthetic_endpoint", ep.train_val["standardized_smiles"].tolist(), k=3)
    cal = PlattCalibrator(A=1.0, B=0.0, n_fit_samples=3)
    report = run_leakage_audit(ep, ad_index=idx, calibrator=cal)
    assert len(report.checks) == 10
    assert report.all_passed


def test_assert_no_leakage_passes_silently_on_clean_report():
    ep = _clean_endpoint_data()
    report = run_leakage_audit(ep)
    assert_no_leakage(report)  # must not raise


def test_assert_no_leakage_raises_with_failure_detail():
    ep = _make_endpoint_data(
        train_val_smiles=_POOL[:10],
        test_smiles=[_POOL[0], *_POOL[10:15]],
        calibration_smiles=_POOL[1:3],
    )
    report = run_leakage_audit(ep)
    assert not report.all_passed
    with pytest.raises(AssertionError, match="leakage check"):
        assert_no_leakage(report)


# ---------------------------------------------------------------------------- #
# Integration: real M1 AMES data must pass every default check
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


def test_integration_real_ames_data_passes_all_default_checks():
    if PREP_DIR is None:
        pytest.skip("no processed outputs")
    from data.loaders import load_endpoint

    endpoint_data = load_endpoint(PREP_DIR, "ames_mutagenicity")
    report = run_leakage_audit(endpoint_data)
    assert_no_leakage(report)  # must not raise on real, already-audited M1 data
