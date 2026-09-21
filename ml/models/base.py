"""
Abstract base class for all MARS prediction models.

Both XGBoost baselines and KERMT fine-tuned models implement this interface.
Input types differ across families (numpy arrays for XGBoost, SMILES lists or
graph tensors for KERMT), so X is typed as Any — concrete subclasses enforce
their own constraints.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import numpy as np
from mars_contracts.endpoints import TaskType


class MARSModel(ABC):
    """Common interface for all MARS endpoint models."""

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Version string identifying this model family and configuration.

        Example: ``"mars-xgboost-ecfp-v1"``, ``"mars-kermt-single-v1"``.
        Must be stable across instances with the same config so it can be used
        as a cache key and in W&B run metadata.
        """

    @property
    @abstractmethod
    def task_type(self) -> TaskType:
        """Whether this model is a classifier or regressor.

        Single-valued by design. Multi-task models expose per-target detail via
        :attr:`target_task_types` instead — widening this to a list would break
        ``eval.metrics.compute_metrics``, ``eval.evaluate``, ``serve.registry``
        and ``serve.predictor``, all of which are per-endpoint by contract.
        """

    @property
    def target_names(self) -> list[str]:
        """Names of the columns :meth:`predict` returns, in order.

        Single-task models predict one unnamed column; multi-task models
        override this with their real target list. Default keeps every existing
        single-task model working unchanged.
        """
        return [""]

    @property
    def target_task_types(self) -> dict[str, TaskType]:
        """Task type per target column.

        Defaults to ``task_type`` for every target, which is correct for any
        single-task or type-homogeneous model. Only a genuinely mixed-type model
        needs to override it.
        """
        return {name: self.task_type for name in self.target_names}

    @abstractmethod
    def fit(
        self,
        X_train: Any,
        y_train: np.ndarray,
        *,
        X_val: Any | None = None,
        y_val: np.ndarray | None = None,
    ) -> None:
        """Train the model.

        Parameters
        ----------
        X_train:
            Training features. Type depends on the concrete implementation
            (numpy array for XGBoost; SMILES list or graph tensors for KERMT).
        y_train:
            Training labels — float for regression, {0,1} for classification.
        X_val, y_val:
            Optional validation set for early stopping. Must be provided
            together or not at all.
        """

    @abstractmethod
    def predict(self, X: Any) -> np.ndarray:
        """Return predictions for X.

        Classification: probabilities in [0, 1] (positive-class probability).
        Regression: raw continuous values.

        The caller decides thresholding / post-processing.
        """

    @abstractmethod
    def save(self, path: Path) -> None:
        """Persist the fitted model to *path* (a file or directory)."""

    @classmethod
    @abstractmethod
    def load(cls, path: Path) -> MARSModel:
        """Load and return a previously saved model from *path*."""
