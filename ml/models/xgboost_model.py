"""
XGBoost baseline model for MARS ADMET endpoints.

Feature matrix: [RDKit 2D descriptors (217) | Morgan r2/2048 fingerprint].
XGBoost handles NaN descriptor values natively (learns a default direction).
Dropped SMILES (featurization failure) are excluded from training and returned
as NaN in predict() so callers can filter or report them.
"""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from featurize.cache import FeatureCache
from featurize.descriptors import DESCRIPTOR_COUNT, DescriptorConfig
from featurize.fingerprints import MorganConfig
from mars_contracts.endpoints import TaskType

from models.base import MARSModel

try:
    import xgboost as xgb

    _XGB_AVAILABLE = True
except ImportError:
    _XGB_AVAILABLE = False

MODEL_ID = "mars-xgboost-ecfp-desc-v1"

_DEFAULT_PARAMS: dict[str, Any] = {
    "n_estimators": 500,
    "max_depth": 6,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "n_jobs": -1,
}

_EARLY_STOPPING_ROUNDS = 50


@dataclass
class XGBoostConfig:
    morgan_config: MorganConfig = field(default_factory=MorganConfig)
    descriptor_config: DescriptorConfig = field(default_factory=DescriptorConfig)
    hyperparams: dict[str, Any] = field(default_factory=dict)


def _extract_features(
    smiles: list[str],
    cache: FeatureCache,
    *,
    morgan_config: MorganConfig,
    descriptor_config: DescriptorConfig,
) -> tuple[np.ndarray, list[int], list[int]]:
    """Build [descriptors | morgan_fp] matrix aligned to the input smiles list.

    Returns
    -------
    X : ndarray, shape (n_valid, DESCRIPTOR_COUNT + n_bits)
    valid_idx : list[int]  — input indices that were successfully featurized
    dropped_idx : list[int]  — input indices that failed featurization
    """
    n = len(smiles)
    if n == 0:
        n_bits = morgan_config.n_bits
        return np.zeros((0, DESCRIPTOR_COUNT + n_bits), dtype=np.float64), [], []

    desc_matrix, _, dropped_desc, _, _ = cache.descriptors_cached(smiles, descriptor_config)
    morgan_matrix, dropped_morgan, _ = cache.morgan_cached(smiles, morgan_config)

    dropped_desc_set = set(dropped_desc)
    dropped_morgan_set = set(dropped_morgan)

    valid_desc = [i for i in range(n) if i not in dropped_desc_set]
    valid_morgan = [i for i in range(n) if i not in dropped_morgan_set]
    valid_both_set = set(valid_desc) & set(valid_morgan)
    valid_idx = sorted(valid_both_set)
    dropped_idx = sorted(i for i in range(n) if i not in valid_both_set)

    if not valid_idx:
        return (
            np.zeros((0, DESCRIPTOR_COUNT + morgan_config.n_bits), dtype=np.float64),
            valid_idx,
            dropped_idx,
        )

    # Map original index → row in each sub-matrix
    desc_row_map = {orig: j for j, orig in enumerate(valid_desc)}
    morgan_row_map = {orig: j for j, orig in enumerate(valid_morgan)}
    desc_rows = np.array([desc_row_map[i] for i in valid_idx])
    morgan_rows = np.array([morgan_row_map[i] for i in valid_idx])

    # Replace non-finite and float32-overflowing values with nan.
    # XGBoost 3.x uses QuantileDMatrix which converts to float32 internally;
    # float64 values > float32.max (~3.4e38) become inf after that cast.
    # RDKit's Ipc descriptor can produce values >>1e38 for large molecules.
    # nan is treated as "missing" by XGBoost (learns a default split direction).
    _F32_MAX = float(np.finfo(np.float32).max)
    desc_part = desc_matrix[desc_rows].astype(np.float64)
    desc_part = np.where(
        np.isfinite(desc_part) & (np.abs(desc_part) <= _F32_MAX),
        desc_part,
        np.nan,
    )
    morgan_part = morgan_matrix[morgan_rows].astype(np.float64)

    X = np.hstack([desc_part, morgan_part])
    return X, valid_idx, dropped_idx


class XGBoostModel(MARSModel):
    """XGBoost classifier / regressor backed by descriptor + Morgan features."""

    def __init__(
        self,
        task_type: TaskType,
        cache: FeatureCache,
        *,
        seed: int = 0,
        xgb_config: XGBoostConfig | None = None,
    ) -> None:
        if not _XGB_AVAILABLE:
            raise ImportError("xgboost is required. Install with: pip install 'xgboost>=2.0'")
        self._task_type = task_type
        self._cache = cache
        self._seed = seed
        self._cfg = xgb_config or XGBoostConfig()
        self._model: Any = None  # XGBClassifier | XGBRegressor after fit

    @property
    def model_id(self) -> str:
        return MODEL_ID

    @property
    def task_type(self) -> TaskType:
        return self._task_type

    def _build_model(self, *, with_early_stopping: bool) -> Any:
        eval_metric = "logloss" if self._task_type == TaskType.CLASSIFICATION else "mae"
        params = {
            **_DEFAULT_PARAMS,
            **self._cfg.hyperparams,
            "random_state": self._seed,
            "eval_metric": eval_metric,
        }
        # XGBoost 3.x raises if early_stopping_rounds is set but no eval_set
        # is provided in fit() — only add it when an eval_set will be passed.
        if with_early_stopping:
            params["early_stopping_rounds"] = _EARLY_STOPPING_ROUNDS
        if self._task_type == TaskType.CLASSIFICATION:
            return xgb.XGBClassifier(**params)
        return xgb.XGBRegressor(**params)

    def fit(
        self,
        X_train: list[str],
        y_train: np.ndarray,
        *,
        X_val: list[str] | None = None,
        y_val: np.ndarray | None = None,
    ) -> None:
        feat_train, valid_train, dropped_train = _extract_features(
            list(X_train),
            self._cache,
            morgan_config=self._cfg.morgan_config,
            descriptor_config=self._cfg.descriptor_config,
        )
        if dropped_train:
            warnings.warn(
                f"XGBoostModel.fit: {len(dropped_train)} training SMILES dropped by featurizer.",
                UserWarning,
                stacklevel=2,
            )
        y_tr = np.asarray(y_train, dtype=float)[valid_train]

        eval_set = None
        if X_val is not None and y_val is not None:
            feat_val, valid_val, dropped_val = _extract_features(
                list(X_val),
                self._cache,
                morgan_config=self._cfg.morgan_config,
                descriptor_config=self._cfg.descriptor_config,
            )
            if dropped_val:
                warnings.warn(
                    f"XGBoostModel.fit: {len(dropped_val)} validation SMILES dropped by featurizer.",
                    UserWarning,
                    stacklevel=2,
                )
            y_va = np.asarray(y_val, dtype=float)[valid_val]
            eval_set = [(feat_val, y_va)]

        self._model = self._build_model(with_early_stopping=eval_set is not None)
        self._model.fit(feat_train, y_tr, eval_set=eval_set, verbose=False)

    def predict(self, X: list[str]) -> np.ndarray:
        if self._model is None:
            raise RuntimeError("Model has not been fitted. Call fit() first.")
        smiles = list(X)
        feat, valid_idx, dropped_idx = _extract_features(
            smiles,
            self._cache,
            morgan_config=self._cfg.morgan_config,
            descriptor_config=self._cfg.descriptor_config,
        )
        if dropped_idx:
            warnings.warn(
                f"XGBoostModel.predict: {len(dropped_idx)} SMILES dropped; NaN returned at those positions.",
                UserWarning,
                stacklevel=2,
            )
        if len(valid_idx) == 0:
            return np.full(len(smiles), float("nan"))

        if self._task_type == TaskType.CLASSIFICATION:
            valid_preds = self._model.predict_proba(feat)[:, 1]
        else:
            valid_preds = self._model.predict(feat)

        out = np.full(len(smiles), float("nan"))
        for new_i, orig_i in enumerate(valid_idx):
            out[orig_i] = valid_preds[new_i]
        return out

    def save(self, path: Path) -> None:
        if self._model is None:
            raise RuntimeError("Model has not been fitted.")
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        self._model.save_model(str(path / "model.json"))
        meta = {
            "model_id": self.model_id,
            "task_type": self._task_type.value,
            "seed": self._seed,
        }
        (path / "metadata.json").write_text(
            json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    @classmethod
    def load(cls, path: Path) -> XGBoostModel:
        raise TypeError(
            "XGBoostModel requires a FeatureCache to make predictions. "
            "Use XGBoostModel.load_with_cache(path, cache) instead."
        )

    @classmethod
    def load_with_cache(cls, path: Path, cache: FeatureCache) -> XGBoostModel:
        """Load a saved XGBoostModel and attach the given FeatureCache."""
        if not _XGB_AVAILABLE:
            raise ImportError("xgboost is required. Install with: pip install 'xgboost>=2.0'")
        path = Path(path)
        meta = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
        task_type = TaskType(meta["task_type"])
        seed = int(meta["seed"])
        inst = cls(task_type=task_type, cache=cache, seed=seed)
        if task_type == TaskType.CLASSIFICATION:
            inst._model = xgb.XGBClassifier()
        else:
            inst._model = xgb.XGBRegressor()
        inst._model.load_model(str(path / "model.json"))
        return inst
