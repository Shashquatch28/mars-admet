"""
Unit tests for ml/configs/experiment_config.py.
"""

from __future__ import annotations

import pytest
from configs.experiment_config import (
    FIXED_SEEDS,
    VALID_MODEL_FAMILIES,
    ExperimentConfig,
)

# ---------------------------------------------------------------------------- #
# Valid construction
# ---------------------------------------------------------------------------- #


def test_basic_xgboost_config():
    cfg = ExperimentConfig(
        endpoint="solubility_logs",
        model_family="xgboost",
        seed=0,
        prep_id="20260830T200000Z",
    )
    assert cfg.endpoint == "solubility_logs"
    assert cfg.model_family == "xgboost"
    assert cfg.seed == 0
    assert cfg.prep_id == "20260830T200000Z"
    assert cfg.use_augmented_dili is False
    assert cfg.hyperparams == {}
    assert cfg.notes == ""


def test_all_model_families_valid():
    for fam in sorted(VALID_MODEL_FAMILIES):
        cfg = ExperimentConfig(
            endpoint="ames_mutagenicity",
            model_family=fam,
            seed=0,
            prep_id="20260830T200000Z",
        )
        assert cfg.model_family == fam


def test_hyperparams_stored():
    cfg = ExperimentConfig(
        endpoint="solubility_logs",
        model_family="xgboost",
        seed=0,
        prep_id="20260830T200000Z",
        hyperparams={"n_estimators": 500, "max_depth": 6},
    )
    assert cfg.hyperparams["n_estimators"] == 500
    assert cfg.hyperparams["max_depth"] == 6


def test_notes_stored():
    cfg = ExperimentConfig(
        endpoint="ames_mutagenicity",
        model_family="kermt_single",
        seed=2,
        prep_id="20260830T200000Z",
        notes="smoke test for CI",
    )
    assert cfg.notes == "smoke test for CI"


def test_augmented_dili_flag():
    cfg = ExperimentConfig(
        endpoint="dili_liver_injury",
        model_family="kermt_single",
        seed=1,
        prep_id="20260830T200000Z",
        use_augmented_dili=True,
    )
    assert cfg.use_augmented_dili is True


def test_kermt_multitask_cluster_config():
    cfg = ExperimentConfig(
        endpoint="absorption_distribution",
        model_family="kermt_multitask",
        seed=0,
        prep_id="20260830T200000Z",
    )
    assert cfg.model_family == "kermt_multitask"
    assert cfg.endpoint == "absorption_distribution"


# ---------------------------------------------------------------------------- #
# Validation — model_family
# ---------------------------------------------------------------------------- #


def test_invalid_model_family_raises():
    with pytest.raises(ValueError, match="model_family"):
        ExperimentConfig(
            endpoint="solubility_logs",
            model_family="random_forest",
            seed=0,
            prep_id="20260830T200000Z",
        )


# ---------------------------------------------------------------------------- #
# Validation — seed
# ---------------------------------------------------------------------------- #


def test_string_seed_raises():
    with pytest.raises(TypeError, match="seed"):
        ExperimentConfig(
            endpoint="solubility_logs",
            model_family="xgboost",
            seed="0",  # type: ignore[arg-type]
            prep_id="20260830T200000Z",
        )


def test_bool_seed_raises():
    with pytest.raises(TypeError, match="seed"):
        ExperimentConfig(
            endpoint="solubility_logs",
            model_family="xgboost",
            seed=True,  # type: ignore[arg-type]
            prep_id="20260830T200000Z",
        )


def test_float_seed_raises():
    with pytest.raises(TypeError, match="seed"):
        ExperimentConfig(
            endpoint="solubility_logs",
            model_family="xgboost",
            seed=0.0,  # type: ignore[arg-type]
            prep_id="20260830T200000Z",
        )


# ---------------------------------------------------------------------------- #
# Validation — endpoint / prep_id
# ---------------------------------------------------------------------------- #


def test_empty_endpoint_raises():
    with pytest.raises(ValueError, match="endpoint"):
        ExperimentConfig(
            endpoint="",
            model_family="xgboost",
            seed=0,
            prep_id="20260830T200000Z",
        )


def test_empty_prep_id_raises():
    with pytest.raises(ValueError, match="prep_id"):
        ExperimentConfig(
            endpoint="solubility_logs",
            model_family="xgboost",
            seed=0,
            prep_id="",
        )


# ---------------------------------------------------------------------------- #
# to_tracking_config
# ---------------------------------------------------------------------------- #


def test_to_tracking_config_contains_all_fields():
    cfg = ExperimentConfig(
        endpoint="ames_mutagenicity",
        model_family="kermt_single",
        seed=2,
        prep_id="20260830T200000Z",
        notes="test run",
        hyperparams={"lr": 1e-4},
    )
    d = cfg.to_tracking_config()
    assert d["endpoint"] == "ames_mutagenicity"
    assert d["model_family"] == "kermt_single"
    assert d["seed"] == 2
    assert d["prep_id"] == "20260830T200000Z"
    assert d["notes"] == "test run"
    assert d["hyperparams"]["lr"] == pytest.approx(1e-4)


def test_to_tracking_config_is_json_serializable():
    import json

    cfg = ExperimentConfig(
        endpoint="solubility_logs",
        model_family="xgboost",
        seed=0,
        prep_id="20260830T200000Z",
        hyperparams={"n_estimators": 200},
    )
    d = cfg.to_tracking_config()
    # Must not raise
    json.dumps(d)


# ---------------------------------------------------------------------------- #
# run_name
# ---------------------------------------------------------------------------- #


def test_run_name_xgboost():
    cfg = ExperimentConfig(
        endpoint="solubility_logs",
        model_family="xgboost",
        seed=3,
        prep_id="20260830T200000Z",
    )
    assert cfg.run_name() == "xgb_solubility_logs_seed3"


def test_run_name_kermt_single():
    cfg = ExperimentConfig(
        endpoint="ames_mutagenicity",
        model_family="kermt_single",
        seed=0,
        prep_id="20260830T200000Z",
    )
    assert cfg.run_name() == "kermt_st_ames_mutagenicity_seed0"


def test_run_name_kermt_multitask():
    cfg = ExperimentConfig(
        endpoint="metabolism",
        model_family="kermt_multitask",
        seed=1,
        prep_id="20260830T200000Z",
    )
    assert cfg.run_name() == "kermt_mt_metabolism_seed1"


def test_run_name_unique_across_seeds():
    names = {
        ExperimentConfig(
            endpoint="herg_cardiotoxicity",
            model_family="xgboost",
            seed=s,
            prep_id="20260830T200000Z",
        ).run_name()
        for s in FIXED_SEEDS
    }
    assert len(names) == 5, "run_name must differ across seeds"


# ---------------------------------------------------------------------------- #
# FIXED_SEEDS constant
# ---------------------------------------------------------------------------- #


def test_fixed_seeds_count():
    assert len(FIXED_SEEDS) == 5


def test_fixed_seeds_are_ints():
    assert all(isinstance(s, int) for s in FIXED_SEEDS)


def test_fixed_seeds_unique():
    assert len(set(FIXED_SEEDS)) == 5
