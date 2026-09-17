"""Module 8 model registry — endpoint -> promoted artifact(s) on disk.

Artifact layout (`artifacts_root`, default `ml/artifacts/`):

    <endpoint_key>/
        seed_<n>/model.json, metadata.json      # one XGBoostModel per promoted seed
        ad_index/reference_fingerprints.npy, metadata.json   # Module 5 CORE k-NN AD
        calibrator.json                          # Module 4 Platt calibrator (classification only)

This directory is intentionally decoupled from `ml/runs/` (ExperimentRun's
ephemeral, git-ignored per-run output) — `promote_seed_artifact` is the one
function that copies a finished run's model into the stable registry a
serving process reads from. As of 2026-09-16, MARS has never run its
production 70-run XGBoost sweep (14 endpoints x 5 seeds) and KERMT does not
exist — so most endpoints have zero promoted artifacts. `ModelRegistry`
reports this honestly via `available_endpoints()` rather than silently
falling back to anything fake; the API layer decides what to do when an
endpoint isn't covered (Module 8's stub predictor).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from eval.applicability_domain import ADIndex, build_ad_index
from eval.calibration import PlattCalibrator, fit_platt_calibrator
from featurize.cache import FeatureCache
from mars_contracts.endpoints import Endpoint, TaskType
from models.xgboost_model import XGBoostModel

DEFAULT_ARTIFACTS_ROOT = Path(__file__).resolve().parents[1] / "artifacts"


@dataclass(frozen=True)
class EndpointCoverage:
    endpoint_key: str
    seeds: list[int]
    has_ad_index: bool
    has_calibrator: bool


class ModelRegistry:
    """Read-only view over promoted model artifacts for serving.

    This is the "routing table" the blueprint's Module 8 describes: given an
    endpoint key, resolve which trained model(s) actually exist. It never
    trains anything itself.
    """

    def __init__(self, cache: FeatureCache, artifacts_root: Path | str | None = None) -> None:
        self._cache = cache
        self.artifacts_root = Path(artifacts_root) if artifacts_root else DEFAULT_ARTIFACTS_ROOT

    def _endpoint_dir(self, endpoint_key: str) -> Path:
        return self.artifacts_root / endpoint_key

    def coverage(self, endpoint_key: str) -> EndpointCoverage:
        ep_dir = self._endpoint_dir(endpoint_key)
        seeds: list[int] = []
        if ep_dir.exists():
            for child in sorted(ep_dir.iterdir()):
                if child.is_dir() and child.name.startswith("seed_"):
                    try:
                        seeds.append(int(child.name.removeprefix("seed_")))
                    except ValueError:
                        continue
        return EndpointCoverage(
            endpoint_key=endpoint_key,
            seeds=sorted(seeds),
            has_ad_index=(ep_dir / "ad_index" / "metadata.json").exists(),
            has_calibrator=(ep_dir / "calibrator.json").exists(),
        )

    def available_endpoints(self) -> list[str]:
        """Endpoint keys with at least one promoted seed model."""
        if not self.artifacts_root.exists():
            return []
        out = []
        for child in sorted(self.artifacts_root.iterdir()):
            if child.is_dir() and self.coverage(child.name).seeds:
                out.append(child.name)
        return out

    def load_models(self, endpoint_key: str) -> list[XGBoostModel]:
        cov = self.coverage(endpoint_key)
        ep_dir = self._endpoint_dir(endpoint_key)
        return [
            XGBoostModel.load_with_cache(ep_dir / f"seed_{seed}", self._cache)
            for seed in cov.seeds
        ]

    def load_ad_index(self, endpoint_key: str) -> ADIndex | None:
        path = self._endpoint_dir(endpoint_key) / "ad_index"
        if not (path / "metadata.json").exists():
            return None
        return ADIndex.load(path)

    def load_calibrator(self, endpoint_key: str) -> PlattCalibrator | None:
        path = self._endpoint_dir(endpoint_key) / "calibrator.json"
        if not path.exists():
            return None
        return PlattCalibrator.load(path)


def promote_seed_artifact(
    endpoint_key: str,
    seed: int,
    run_model_dir: Path,
    endpoint_data,  # EndpointData, avoiding a hard import cycle in the type hint
    cache: FeatureCache,
    *,
    artifacts_root: Path | str | None = None,
) -> Path:
    """Copy a finished training run's model into the stable registry, and
    (re)build its AD index + calibrator from the same endpoint_data.

    This is the one write path into `artifacts_root` — everything else in
    this module is read-only. Calling this twice for the same
    (endpoint_key, seed) overwrites the previous promotion (idempotent).
    """
    root = Path(artifacts_root) if artifacts_root else DEFAULT_ARTIFACTS_ROOT
    ep_dir = root / endpoint_key
    seed_dir = ep_dir / f"seed_{seed}"
    if seed_dir.exists():
        shutil.rmtree(seed_dir)
    shutil.copytree(run_model_dir, seed_dir)

    # AD index: built from this seed's train fold (train_val minus the held-out
    # val fold would be more precise per-seed, but the blueprint's AD index is
    # defined over "the endpoint's training set" as a whole — train_val here).
    tv_smiles = endpoint_data.train_val["standardized_smiles"].tolist()
    ad_index = build_ad_index(endpoint_key, tv_smiles)
    ad_index.save(ep_dir / "ad_index")

    # Calibrator: classification only, fit on the calibration split — NEVER
    # train_val or test (Module 4's non-negotiable rule).
    endpoint = Endpoint(endpoint_key)
    from mars_contracts.endpoints import ENDPOINT_METADATA

    if ENDPOINT_METADATA[endpoint]["task_type"] == TaskType.CLASSIFICATION:
        model = XGBoostModel.load_with_cache(seed_dir, cache)
        cal_smiles = endpoint_data.calibration["standardized_smiles"].tolist()
        cal_labels = endpoint_data.calibration["label"].astype(float).to_numpy()
        raw_probs = model.predict(cal_smiles)
        valid = ~np.isnan(raw_probs)
        calibrator = fit_platt_calibrator(raw_probs[valid], cal_labels[valid])
        calibrator.save(ep_dir / "calibrator.json")

    return seed_dir


__all__ = [
    "DEFAULT_ARTIFACTS_ROOT",
    "EndpointCoverage",
    "ModelRegistry",
    "promote_seed_artifact",
]
