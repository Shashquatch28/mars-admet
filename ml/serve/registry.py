"""Module 8 model registry — endpoint -> promoted artifact(s) on disk.

Artifact layout (`artifacts_root`, default `ml/artifacts/`):

    <endpoint_key>/
        seed_<n>/model.json, metadata.json      # one XGBoostModel per promoted seed
        ad_index/reference_fingerprints.npy, metadata.json   # Module 5 CORE k-NN AD
        calibrator.json                          # Module 4 Platt calibrator (classification only)
        error_band.json                          # held-out-error band (regression only, ADR-024)

This directory is intentionally decoupled from `ml/runs/` (ExperimentRun's
ephemeral, git-ignored per-run output) — `promote_seed_artifact` is the one
function that copies a finished run's model into the stable registry a
serving process reads from. `ml/artifacts/` is git-ignored: a checkout
without promoted artifacts has zero covered endpoints (the 2026-09-17
production sweep promoted all 14 on the development machine). `ModelRegistry`
reports coverage honestly via `available_endpoints()` rather than silently
falling back to anything fake; the API layer decides what to do when an
endpoint isn't covered (Module 8's stub predictor).
"""

from __future__ import annotations

import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from eval.applicability_domain import ADIndex, build_ad_index
from eval.calibration import PlattCalibrator, fit_platt_calibrator
from eval.error_band import ERROR_BAND_FILENAME, ErrorBand
from featurize.cache import FeatureCache
from mars_contracts.endpoints import Endpoint, TaskType
from models.xgboost_model import XGBoostModel

DEFAULT_ARTIFACTS_ROOT = Path(__file__).resolve().parents[1] / "artifacts"
DEFAULT_REVALIDATE_SECONDS = 5.0


@dataclass(frozen=True)
class EndpointCoverage:
    endpoint_key: str
    seeds: list[int]
    has_ad_index: bool
    has_calibrator: bool


def _file_stamp(path: Path) -> tuple[int, int] | None:
    """(mtime_ns, size) of a file, or None if it is absent. A re-promotion rewrites
    the file (`promote_seed_artifact` copies a fresh tree), so either value moves."""
    try:
        st = path.stat()
    except FileNotFoundError:
        return None
    return (st.st_mtime_ns, st.st_size)


class ModelRegistry:
    """Read-only view over promoted model artifacts for serving.

    This is the "routing table" the blueprint's Module 8 describes: given an
    endpoint key, resolve which trained model(s) actually exist. It never
    trains anything itself.

    Loaded models, AD indexes and calibrators are kept in memory per endpoint,
    keyed on the (mtime_ns, size) of the files they were read from, so a serving
    process pays the XGBoost deserialisation once instead of on every request
    (2026-10-18: 70 `load_model` calls were ~80% of a cold /predict). The stamp is
    re-checked at most every `revalidate_seconds` (default 5 s; 0 = on every call),
    so a re-promoted artifact is picked up within that window with no restart and
    no stale model. The window exists because a stamp check is ~20 `stat`s per
    endpoint, which on a Docker Desktop bind mount cost ~5 ms each (2026-10-18:
    ~1.3 s per molecule spent in `stat` alone). Nothing cached is ever mutated by
    callers; the returned model list is a copy.
    """

    def __init__(
        self,
        cache: FeatureCache,
        artifacts_root: Path | str | None = None,
        *,
        revalidate_seconds: float = DEFAULT_REVALIDATE_SECONDS,
    ) -> None:
        self._cache = cache
        self.artifacts_root = Path(artifacts_root) if artifacts_root else DEFAULT_ARTIFACTS_ROOT
        self._revalidate_seconds = revalidate_seconds
        self._lock = threading.RLock()
        # kind -> endpoint_key -> [stamp, value, last_checked_monotonic]
        self._memo: dict[str, dict[str, list[Any]]] = {"models": {}, "ad": {}, "calibrator": {}, "error_band": {}}

    def _memoised(self, kind: str, endpoint_key: str, stamp_fn, build) -> Any:
        with self._lock:
            hit = self._memo[kind].get(endpoint_key)
            now = time.monotonic()
            if (
                hit is not None
                and self._revalidate_seconds > 0
                and now - hit[2] < self._revalidate_seconds
            ):
                return hit[1]
            stamp = stamp_fn()
            if hit is not None and hit[0] == stamp:
                hit[2] = now
                return hit[1]
            value = build()
            self._memo[kind][endpoint_key] = [stamp, value, now]
            return value

    def clear_cache(self) -> None:
        """Drop every in-memory artifact (tests, or to release memory)."""
        with self._lock:
            for table in self._memo.values():
                table.clear()

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
        ep_dir = self._endpoint_dir(endpoint_key)

        def stamp() -> tuple:
            return tuple(
                (
                    seed,
                    _file_stamp(ep_dir / f"seed_{seed}" / "model.json"),
                    _file_stamp(ep_dir / f"seed_{seed}" / "metadata.json"),
                )
                for seed in self.coverage(endpoint_key).seeds
            )

        def build() -> list[XGBoostModel]:
            return [
                XGBoostModel.load_with_cache(ep_dir / f"seed_{seed}", self._cache, n_jobs=1)
                for seed in self.coverage(endpoint_key).seeds
            ]

        return list(self._memoised("models", endpoint_key, stamp, build))

    def load_ad_index(self, endpoint_key: str) -> ADIndex | None:
        path = self._endpoint_dir(endpoint_key) / "ad_index"

        def stamp() -> tuple:
            return (
                _file_stamp(path / "metadata.json"),
                _file_stamp(path / "reference_fingerprints.npy"),
            )

        def build() -> ADIndex | None:
            return ADIndex.load(path) if (path / "metadata.json").exists() else None

        return self._memoised("ad", endpoint_key, stamp, build)

    def load_error_band(self, endpoint_key: str) -> ErrorBand | None:
        """The endpoint's held-out-error band, or None when none was built (classification, or not yet)."""
        path = self._endpoint_dir(endpoint_key) / ERROR_BAND_FILENAME

        def build() -> ErrorBand | None:
            return ErrorBand.load(path) if path.exists() else None

        return self._memoised("error_band", endpoint_key, lambda: _file_stamp(path), build)

    def load_calibrator(self, endpoint_key: str) -> PlattCalibrator | None:
        path = self._endpoint_dir(endpoint_key) / "calibrator.json"

        def build() -> PlattCalibrator | None:
            return PlattCalibrator.load(path) if path.exists() else None

        return self._memoised("calibrator", endpoint_key, lambda: _file_stamp(path), build)


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
