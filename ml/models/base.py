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
        """Whether this model is a classifier or regressor."""

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
