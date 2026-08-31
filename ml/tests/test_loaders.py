"""
Tests for ml/data/loaders.py.

Integration tests run against the real M1 processed outputs and skip cleanly
if no processed data is present on this machine.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from data.loaders import (
    EndpointData,
    list_available_endpoints,
    load_endpoint,
    load_manifest,
)
from mars_contracts.endpoints import ML_ENDPOINTS, TaskType

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "ml" / "data"


def _newest_prep_dir() -> Path | None:
    root = DATA / "processed"
    if not root.exists():
        return None
    dirs = sorted(p for p in root.iterdir() if p.is_dir())
    return dirs[-1] if dirs else None


PREP_DIR = _newest_prep_dir()


# ---------------------------------------------------------------------------- #
# Manifest
# ---------------------------------------------------------------------------- #


def test_load_manifest_structure():
    if PREP_DIR is None:
        pytest.skip("no processed outputs")
    m = load_manifest(PREP_DIR)
    assert "datasets" in m
    assert "ames_mutagenicity" in m["datasets"]
    assert "solubility_logs" in m["datasets"]


def test_load_manifest_missing_raises():
    with pytest.raises(FileNotFoundError, match="manifest.json"):
        load_manifest(Path("/nonexistent/path/xyz"))


# ---------------------------------------------------------------------------- #
# list_available_endpoints
# ---------------------------------------------------------------------------- #


def test_list_available_endpoints():
    if PREP_DIR is None:
        pytest.skip("no processed outputs")
    eps = list_available_endpoints(PREP_DIR)
    assert "ames_mutagenicity" in eps
    assert "solubility_logs" in eps
    assert "herg_cardiotoxicity" in eps
    assert "dili_liver_injury" in eps
    assert "dili_liver_injury__augmented" in eps


def test_list_available_endpoints_missing_dir_raises():
    with pytest.raises(FileNotFoundError):
        list_available_endpoints(Path("/nonexistent/path/xyz"))


# ---------------------------------------------------------------------------- #
# load_endpoint — basic structure
# ---------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def ames():
    if PREP_DIR is None:
        pytest.skip("no processed outputs")
    return load_endpoint(PREP_DIR, "ames_mutagenicity")


@pytest.fixture(scope="module")
def solubility():
    if PREP_DIR is None:
        pytest.skip("no processed outputs")
    return load_endpoint(PREP_DIR, "solubility_logs")


def test_returns_endpoint_data(ames):
    assert isinstance(ames, EndpointData)


def test_dataframes_are_pandas(ames):
    assert isinstance(ames.train_val, pd.DataFrame)
    assert isinstance(ames.test, pd.DataFrame)
    assert isinstance(ames.calibration, pd.DataFrame)


def test_required_columns_present(ames):
    for split in (ames.train_val, ames.test, ames.calibration):
        assert "standardized_smiles" in split.columns
        assert "label" in split.columns


def test_non_empty_splits(ames):
    assert len(ames.train_val) > 0
    assert len(ames.test) > 0
    assert len(ames.calibration) > 0


def test_endpoint_key_correct(ames):
    assert ames.endpoint_key == "ames_mutagenicity"


def test_dataset_key_equals_endpoint_key_for_standard_endpoint(ames):
    assert ames.dataset_key == "ames_mutagenicity"


def test_prep_id_from_dir(ames):
    assert ames.prep_id == PREP_DIR.name


# ---------------------------------------------------------------------------- #
# Task type routing
# ---------------------------------------------------------------------------- #


def test_task_type_classification(ames):
    assert ames.task_type == TaskType.CLASSIFICATION


def test_task_type_regression(solubility):
    assert solubility.task_type == TaskType.REGRESSION


# ---------------------------------------------------------------------------- #
# Split isolation — blueprint leakage audits
# ---------------------------------------------------------------------------- #


def test_no_smiles_overlap_test_train_val(ames):
    test_smiles = set(ames.test["standardized_smiles"])
    tv_smiles = set(ames.train_val["standardized_smiles"])
    overlap = test_smiles & tv_smiles
    assert not overlap, f"Test molecules found in train_val: {overlap}"


def test_no_smiles_overlap_calibration_test(ames):
    cal_smiles = set(ames.calibration["standardized_smiles"])
    test_smiles = set(ames.test["standardized_smiles"])
    overlap = cal_smiles & test_smiles
    assert not overlap, f"Calibration molecules found in test: {overlap}"


def test_calibration_subset_of_train_val(ames):
    cal_smiles = set(ames.calibration["standardized_smiles"])
    tv_smiles = set(ames.train_val["standardized_smiles"])
    not_in_tv = cal_smiles - tv_smiles
    assert not not_in_tv, f"Calibration SMILES not in train_val: {not_in_tv}"


# ---------------------------------------------------------------------------- #
# DILI augmentation variant
# ---------------------------------------------------------------------------- #


def test_unaugmented_dili():
    if PREP_DIR is None:
        pytest.skip("no processed outputs")
    data = load_endpoint(PREP_DIR, "dili_liver_injury", use_augmented_dili=False)
    assert data.dataset_key == "dili_liver_injury"
    assert data.endpoint_key == "dili_liver_injury"


def test_augmented_dili():
    if PREP_DIR is None:
        pytest.skip("no processed outputs")
    data = load_endpoint(PREP_DIR, "dili_liver_injury", use_augmented_dili=True)
    assert data.dataset_key == "dili_liver_injury__augmented"
    assert data.endpoint_key == "dili_liver_injury"
    assert data.task_type == TaskType.CLASSIFICATION


def test_augmented_dili_larger_than_base():
    if PREP_DIR is None:
        pytest.skip("no processed outputs")
    base = load_endpoint(PREP_DIR, "dili_liver_injury", use_augmented_dili=False)
    aug = load_endpoint(PREP_DIR, "dili_liver_injury", use_augmented_dili=True)
    # Augmented training pool should be larger
    assert len(aug.train_val) >= len(base.train_val)


# ---------------------------------------------------------------------------- #
# Error cases
# ---------------------------------------------------------------------------- #


def test_unknown_endpoint_key_raises():
    if PREP_DIR is None:
        pytest.skip("no processed outputs")
    with pytest.raises(ValueError, match="Unknown endpoint key"):
        load_endpoint(PREP_DIR, "not_a_real_endpoint_xyz")


def test_use_augmented_dili_on_non_dili_is_noop():
    # use_augmented_dili=True on a non-DILI endpoint is silently ignored
    if PREP_DIR is None:
        pytest.skip("no processed outputs")
    data = load_endpoint(PREP_DIR, "ames_mutagenicity", use_augmented_dili=True)
    assert data.dataset_key == "ames_mutagenicity"


# ---------------------------------------------------------------------------- #
# All 13 ML endpoints loadable
# ---------------------------------------------------------------------------- #


def test_all_ml_endpoints_loadable():
    """Smoke-test: every ML endpoint loads without error."""
    if PREP_DIR is None:
        pytest.skip("no processed outputs")
    for ep in ML_ENDPOINTS:
        data = load_endpoint(PREP_DIR, ep.value)
        assert len(data.train_val) > 0, f"{ep.value}: train_val is empty"
        assert len(data.test) > 0, f"{ep.value}: test is empty"
        assert len(data.calibration) > 0, f"{ep.value}: calibration is empty"
        assert data.endpoint_key == ep.value
