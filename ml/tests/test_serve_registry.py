"""Integration tests for ml/serve/ against a real, locally-trained artifact.

Trains one real XGBoost seed on the smallest endpoint (HIA, 578 compounds)
into a temp runs dir, promotes it into a temp artifacts registry, and
verifies the registry + predictor produce real, non-fabricated predictions.
This is the "locally trained artifact" verification tier described in the
M3 execution rules — distinct from (and not a substitute for) the production
70-run sweep, which has not been executed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from configs.experiment_config import ExperimentConfig
from data.loaders import load_endpoint
from featurize.cache import FeatureCache
from serve.predictor import predict_endpoint, predict_endpoints
from serve.registry import ModelRegistry, promote_seed_artifact
from train.train_xgboost import train_one_seed

PREP_ID = "20260830T200000Z"
ENDPOINT = "hia_absorption"


def _prep_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "processed" / PREP_ID


@pytest.fixture(scope="module")
def promoted_registry(tmp_path_factory):
    prep_dir = _prep_dir()
    if not prep_dir.exists():
        pytest.skip(f"M1 processed data not found at {prep_dir}")

    endpoint_data = load_endpoint(prep_dir, ENDPOINT)
    cache = FeatureCache(Path(__file__).resolve().parents[1] / "data" / "cache")
    config = ExperimentConfig(endpoint=ENDPOINT, model_family="xgboost", seed=0, prep_id=PREP_ID)

    runs_dir = tmp_path_factory.mktemp("runs")
    result = train_one_seed(endpoint_data, config, cache, seed=0, runs_dir=runs_dir)

    artifacts_root = tmp_path_factory.mktemp("artifacts")
    promote_seed_artifact(
        ENDPOINT, seed=0, run_model_dir=result.model_path,
        endpoint_data=endpoint_data, cache=cache, artifacts_root=artifacts_root,
    )

    registry = ModelRegistry(cache, artifacts_root=artifacts_root)
    return registry, endpoint_data


def test_coverage_reflects_promoted_seed(promoted_registry):
    registry, _ = promoted_registry
    cov = registry.coverage(ENDPOINT)
    assert cov.seeds == [0]
    assert cov.has_ad_index
    assert cov.has_calibrator  # HIA is classification


def test_available_endpoints_lists_only_promoted(promoted_registry):
    registry, _ = promoted_registry
    assert registry.available_endpoints() == [ENDPOINT]


def test_uncovered_endpoint_returns_none(promoted_registry):
    registry, _ = promoted_registry
    result = predict_endpoint(registry, "solubility_logs", "CCO")
    assert result is None


def test_covered_endpoint_returns_real_prediction(promoted_registry):
    registry, endpoint_data = promoted_registry
    smiles = endpoint_data.test["standardized_smiles"].iloc[0]
    result = predict_endpoint(registry, ENDPOINT, smiles)
    assert result is not None
    assert 0.0 <= result.value <= 1.0  # classification probability
    assert result.confidence_low <= result.value <= result.confidence_high
    assert result.n_seeds == 1
    assert result.model_id == "mars-xgboost-ecfp-desc-v1"
    assert not np.isnan(result.knn_distance)


def test_predict_endpoints_mixes_covered_and_uncovered(promoted_registry):
    registry, endpoint_data = promoted_registry
    smiles = endpoint_data.test["standardized_smiles"].iloc[0]
    out = predict_endpoints(registry, smiles, [ENDPOINT, "solubility_logs"])
    assert out[ENDPOINT] is not None
    assert out["solubility_logs"] is None


def test_calibration_never_touches_train_val_or_test(promoted_registry):
    """The Platt calibrator promoted alongside the model must be fit only on
    the calibration split — assert it exists and was built with the right
    sample count rather than accidentally the full train_val pool."""
    registry, endpoint_data = promoted_registry
    calibrator = registry.load_calibrator(ENDPOINT)
    assert calibrator is not None
    assert calibrator.n_fit_samples <= len(endpoint_data.calibration)
    assert calibrator.n_fit_samples < len(endpoint_data.train_val)
