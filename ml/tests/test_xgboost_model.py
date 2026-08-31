"""
Tests for ml/models/xgboost_model.py and ml/train/train_xgboost.py.

Smoke tests use a small fixed set of real SMILES + a tmp FeatureCache so
RDKit featurization runs but we avoid any dependency on M1 processed data.

Integration tests against real M1 data are marked and skip if no processed
outputs are found.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pytest
from featurize.cache import FeatureCache
from featurize.descriptors import DESCRIPTOR_COUNT, DescriptorConfig
from featurize.fingerprints import MorganConfig
from mars_contracts.endpoints import TaskType
from models.xgboost_model import MODEL_ID, XGBoostConfig, XGBoostModel, _extract_features

# Skip this entire module at collection time if xgboost is not installed.
pytest.importorskip("xgboost", reason="xgboost not installed in this environment")

# ---------------------------------------------------------------------------- #
# Fixtures
# ---------------------------------------------------------------------------- #

# A small set of valid SMILES: ethanol, benzene, aspirin, caffeine, glucose
_SMILES = [
    "CCO",
    "c1ccccc1",
    "CC(=O)Oc1ccccc1C(=O)O",
    "Cn1c(=O)c2c(ncn2C)n(c1=O)C",
    "OCC1OC(O)C(O)C(O)C1O",
]
_N = len(_SMILES)


@pytest.fixture(scope="module")
def cache(tmp_path_factory):
    root = tmp_path_factory.mktemp("feature_cache")
    return FeatureCache(root)


@pytest.fixture(scope="module")
def clf_model(cache):
    m = XGBoostModel(task_type=TaskType.CLASSIFICATION, cache=cache, seed=0)
    y = np.array([0, 1, 0, 1, 0], dtype=float)
    m.fit(_SMILES, y, X_val=_SMILES, y_val=y)
    return m


@pytest.fixture(scope="module")
def reg_model(cache):
    m = XGBoostModel(task_type=TaskType.REGRESSION, cache=cache, seed=0)
    y = np.array([1.0, 2.5, 0.3, 4.1, 2.2])
    m.fit(_SMILES, y, X_val=_SMILES, y_val=y)
    return m


# ---------------------------------------------------------------------------- #
# Feature extraction
# ---------------------------------------------------------------------------- #


def test_extract_features_shape(cache):
    X, valid_idx, dropped_idx = _extract_features(
        _SMILES,
        cache,
        morgan_config=MorganConfig(),
        descriptor_config=DescriptorConfig(),
    )
    expected_features = DESCRIPTOR_COUNT + MorganConfig().n_bits
    assert X.shape == (len(valid_idx), expected_features)
    assert len(valid_idx) + len(dropped_idx) == _N


def test_extract_features_all_valid(cache):
    _, valid_idx, dropped_idx = _extract_features(
        _SMILES,
        cache,
        morgan_config=MorganConfig(),
        descriptor_config=DescriptorConfig(),
    )
    assert len(dropped_idx) == 0
    assert valid_idx == list(range(_N))


def test_extract_features_empty_input(cache):
    X, valid_idx, dropped_idx = _extract_features(
        [],
        cache,
        morgan_config=MorganConfig(),
        descriptor_config=DescriptorConfig(),
    )
    assert X.shape[0] == 0
    assert valid_idx == []
    assert dropped_idx == []


def test_extract_features_no_inf(cache):
    X, valid_idx, _ = _extract_features(
        _SMILES,
        cache,
        morgan_config=MorganConfig(),
        descriptor_config=DescriptorConfig(),
    )
    # inf/-inf and float32-overflowing values must be replaced with nan so
    # XGBoost 3.x QuantileDMatrix (which casts to float32) never sees inf.
    assert not np.any(np.isinf(X)), "inf values must be converted to nan"
    f32_max = float(np.finfo(np.float32).max)
    assert not np.any(np.abs(X[np.isfinite(X)]) > f32_max), "float32-overflowing values must be nan"


# ---------------------------------------------------------------------------- #
# XGBoostModel — properties
# ---------------------------------------------------------------------------- #


def test_model_id_stable(clf_model):
    assert clf_model.model_id == MODEL_ID


def test_task_type_classification(clf_model):
    assert clf_model.task_type == TaskType.CLASSIFICATION


def test_task_type_regression(reg_model):
    assert reg_model.task_type == TaskType.REGRESSION


# ---------------------------------------------------------------------------- #
# fit() and predict()
# ---------------------------------------------------------------------------- #


def test_clf_predict_probabilities_in_range(clf_model):
    preds = clf_model.predict(_SMILES)
    valid = preds[~np.isnan(preds)]
    assert np.all(valid >= 0.0)
    assert np.all(valid <= 1.0)


def test_reg_predict_finite(reg_model):
    preds = reg_model.predict(_SMILES)
    valid = preds[~np.isnan(preds)]
    assert np.all(np.isfinite(valid))


def test_predict_length_matches_input(clf_model):
    preds = clf_model.predict(_SMILES)
    assert len(preds) == _N


def test_predict_without_fit_raises():
    m = XGBoostModel.__new__(XGBoostModel)
    m._model = None
    m._task_type = TaskType.CLASSIFICATION
    m._cache = None
    m._cfg = XGBoostConfig()
    with pytest.raises(RuntimeError, match="fit"):
        m.predict(["CCO"])


def test_fit_without_val_works(cache):
    m = XGBoostModel(task_type=TaskType.CLASSIFICATION, cache=cache, seed=1)
    y = np.array([0, 1, 0, 1, 0], dtype=float)
    m.fit(_SMILES, y)  # no val set — trains for full n_estimators, no early stopping
    preds = m.predict(_SMILES)
    assert len(preds) == _N


def test_predict_dropped_smiles_returns_nan(cache):
    # "[2H][3He" has an unclosed bracket — RDKit returns None → featurizer drops it.
    smiles_with_invalid = [_SMILES[0], "[2H][3He", _SMILES[1]]
    m = XGBoostModel(task_type=TaskType.CLASSIFICATION, cache=cache, seed=2)
    y_train = np.array([0, 1, 0, 1, 0], dtype=float)
    m.fit(_SMILES, y_train)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        preds = m.predict(smiles_with_invalid)
    assert len(preds) == 3
    assert np.isnan(preds[1])
    assert not np.isnan(preds[0])
    assert not np.isnan(preds[2])


# ---------------------------------------------------------------------------- #
# save / load_with_cache round-trip
# ---------------------------------------------------------------------------- #


def test_save_load_clf_roundtrip(clf_model, cache, tmp_path):
    save_dir = tmp_path / "clf_model"
    clf_model.save(save_dir)
    assert (save_dir / "model.json").exists()
    assert (save_dir / "metadata.json").exists()

    loaded = XGBoostModel.load_with_cache(save_dir, cache)
    orig_preds = clf_model.predict(_SMILES)
    loaded_preds = loaded.predict(_SMILES)
    np.testing.assert_allclose(orig_preds, loaded_preds, rtol=1e-5)


def test_save_load_reg_roundtrip(reg_model, cache, tmp_path):
    save_dir = tmp_path / "reg_model"
    reg_model.save(save_dir)
    loaded = XGBoostModel.load_with_cache(save_dir, cache)
    orig_preds = reg_model.predict(_SMILES)
    loaded_preds = loaded.predict(_SMILES)
    np.testing.assert_allclose(orig_preds, loaded_preds, rtol=1e-5)


def test_load_without_cache_raises():
    with pytest.raises(TypeError, match="load_with_cache"):
        XGBoostModel.load(Path("/any/path"))


def test_loaded_model_task_type_preserved(clf_model, cache, tmp_path):
    save_dir = tmp_path / "clf_check"
    clf_model.save(save_dir)
    loaded = XGBoostModel.load_with_cache(save_dir, cache)
    assert loaded.task_type == TaskType.CLASSIFICATION


# ---------------------------------------------------------------------------- #
# Integration tests against real M1 data
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
CACHE_ROOT = DATA / "cache"


@pytest.fixture(scope="module")
def real_cache():
    return FeatureCache(CACHE_ROOT)


def test_integration_clf_ames(real_cache, tmp_path):
    """Train 1 seed of AMES (classification); verify AUROC > random."""
    if PREP_DIR is None:
        pytest.skip("no processed outputs")
    from configs.experiment_config import ExperimentConfig
    from data.loaders import load_endpoint
    from train.train_xgboost import train_one_seed

    endpoint_data = load_endpoint(PREP_DIR, "ames_mutagenicity")
    config = ExperimentConfig(
        endpoint="ames_mutagenicity",
        model_family="xgboost",
        seed=0,
        prep_id=PREP_DIR.name,
    )
    result = train_one_seed(
        endpoint_data,
        config,
        real_cache,
        seed=0,
        runs_dir=tmp_path / "runs",
        repo_root=REPO,
    )
    assert result.run_id.startswith("xgb_ames_mutagenicity")
    assert result.n_train > 0
    assert result.n_val > 0
    m = result.val_metrics
    assert m.auroc_valid, "AMES should have both classes in val set"
    assert m.auroc > 0.5, f"Expected AUROC > 0.5 for AMES; got {m.auroc:.4f}"
    assert (result.model_path / "model.json").exists()


def test_integration_reg_solubility(real_cache, tmp_path):
    """Train 1 seed of solubility (regression); verify finite MAE."""
    if PREP_DIR is None:
        pytest.skip("no processed outputs")
    from configs.experiment_config import ExperimentConfig
    from data.loaders import load_endpoint
    from train.train_xgboost import train_one_seed

    endpoint_data = load_endpoint(PREP_DIR, "solubility_logs")
    config = ExperimentConfig(
        endpoint="solubility_logs",
        model_family="xgboost",
        seed=0,
        prep_id=PREP_DIR.name,
    )
    result = train_one_seed(
        endpoint_data,
        config,
        real_cache,
        seed=0,
        runs_dir=tmp_path / "runs",
        repo_root=REPO,
    )
    assert result.n_train > 0
    m = result.val_metrics
    assert np.isfinite(m.mae), f"Expected finite MAE; got {m.mae}"
    assert m.mae > 0, "MAE > 0 expected on held-out val set"


def test_integration_split_isolation_not_touched():
    """Verify test set SMILES are disjoint from train_val (M1 pre-condition)."""
    if PREP_DIR is None:
        pytest.skip("no processed outputs")
    from data.loaders import load_endpoint

    endpoint_data = load_endpoint(PREP_DIR, "ames_mutagenicity")
    test_smiles = set(endpoint_data.test["standardized_smiles"])
    tv_smiles = set(endpoint_data.train_val["standardized_smiles"])
    assert not (test_smiles & tv_smiles), "M1 split isolation violated"
