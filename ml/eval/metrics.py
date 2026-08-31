"""
Centralized evaluation metrics for MARS — single source of truth across all
model families (XGBoost and KERMT) so definitions never drift silently.

Classification (all classification endpoints):
  - AUROC   — area under the ROC curve
  - AUPRC   — average precision (area under the precision-recall curve)
  - Brier score
  - ECE     — Expected Calibration Error (equal-width bins)

Regression:
  - MAE     — mean absolute error

No torch dependency. All functions accept plain numpy arrays.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
from mars_contracts.endpoints import TaskType
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    mean_absolute_error,
    roc_auc_score,
)


@dataclass(frozen=True)
class ClassificationMetrics:
    auroc: float
    auprc: float
    brier_score: float
    ece: float
    n_samples: int
    n_positive: int
    auroc_valid: bool  # False when only one class is present in y_true


@dataclass(frozen=True)
class RegressionMetrics:
    mae: float
    n_samples: int


def expected_calibration_error(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    *,
    n_bins: int = 10,
) -> float:
    """Expected Calibration Error via equal-width bins over [0, 1].

    ECE = Σ_b (|B_b| / N) · |acc(B_b) − conf(B_b)|

    where B_b is the set of predictions falling in bin b, acc is the fraction
    of true positives in that bin, and conf is the mean predicted probability.
    """
    y_true = np.asarray(y_true, dtype=float)
    y_prob = np.asarray(y_prob, dtype=float)
    if len(y_true) == 0:
        raise ValueError("y_true is empty")
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n = len(y_true)
    for i in range(n_bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        mask = (y_prob >= lo) & (y_prob < hi) if i < n_bins - 1 else (y_prob >= lo) & (y_prob <= hi)
        if not mask.any():
            continue
        bin_acc = float(y_true[mask].mean())
        bin_conf = float(y_prob[mask].mean())
        ece += (mask.sum() / n) * abs(bin_acc - bin_conf)
    return float(ece)


def compute_classification_metrics(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    *,
    n_bins: int = 10,
) -> ClassificationMetrics:
    """Compute all classification metrics for one model / one seed.

    Parameters
    ----------
    y_true:
        Ground-truth binary labels {0, 1}.
    y_prob:
        Predicted positive-class probabilities in [0, 1].
    n_bins:
        Number of equal-width bins for ECE computation.
    """
    y_true = np.asarray(y_true, dtype=int)
    y_prob = np.asarray(y_prob, dtype=float)

    if len(y_true) == 0:
        raise ValueError("y_true is empty")
    if len(y_true) != len(y_prob):
        raise ValueError(
            f"Length mismatch: y_true has {len(y_true)} elements, "
            f"y_prob has {len(y_prob)}"
        )
    if not np.all((y_prob >= 0.0) & (y_prob <= 1.0)):
        raise ValueError(
            "y_prob must contain probabilities in [0, 1]; "
            "pass calibrated scores, not raw logits."
        )

    n_pos = int(y_true.sum())
    n_classes = len(np.unique(y_true))
    auroc_valid = n_classes >= 2

    if auroc_valid:
        auroc = float(roc_auc_score(y_true, y_prob))
        auprc = float(average_precision_score(y_true, y_prob))
    else:
        warnings.warn(
            f"Only {n_classes} class(es) present in y_true; "
            "AUROC and AUPRC are undefined and will be NaN.",
            UserWarning,
            stacklevel=2,
        )
        auroc = float("nan")
        auprc = float("nan")

    brier = float(brier_score_loss(y_true, y_prob))
    ece = expected_calibration_error(y_true, y_prob, n_bins=n_bins)

    return ClassificationMetrics(
        auroc=auroc,
        auprc=auprc,
        brier_score=brier,
        ece=ece,
        n_samples=len(y_true),
        n_positive=n_pos,
        auroc_valid=auroc_valid,
    )


def compute_regression_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> RegressionMetrics:
    """Compute regression metrics for one model / one seed."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    if len(y_true) == 0:
        raise ValueError("y_true is empty")
    if len(y_true) != len(y_pred):
        raise ValueError(
            f"Length mismatch: y_true has {len(y_true)} elements, "
            f"y_pred has {len(y_pred)}"
        )

    return RegressionMetrics(
        mae=float(mean_absolute_error(y_true, y_pred)),
        n_samples=len(y_true),
    )


def compute_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    task_type: TaskType,
    *,
    n_bins: int = 10,
) -> ClassificationMetrics | RegressionMetrics:
    """Dispatch to classification or regression metrics based on task type.

    Parameters
    ----------
    y_true:
        Ground-truth labels.
    y_pred:
        Predicted probabilities (classification) or values (regression).
    task_type:
        ``TaskType.CLASSIFICATION`` or ``TaskType.REGRESSION``.
    """
    if task_type == TaskType.CLASSIFICATION:
        return compute_classification_metrics(y_true, y_pred, n_bins=n_bins)
    if task_type == TaskType.REGRESSION:
        return compute_regression_metrics(y_true, y_pred)
    raise ValueError(
        f"Unsupported task_type for compute_metrics: {task_type!r}. "
        "Use TaskType.CLASSIFICATION or TaskType.REGRESSION."
    )


def aggregate_seed_metrics(
    per_seed: list[ClassificationMetrics | RegressionMetrics],
) -> dict[str, float]:
    """Compute mean ± std over 5-seed results (blueprint Module 11 §2).

    Returns a flat dict: ``{metric_mean: float, metric_std: float, ...}``.
    NaN values (e.g. from single-class folds) are excluded from the aggregate.

    Parameters
    ----------
    per_seed:
        List of metric objects, one per seed.  All elements must be the same
        type (all ClassificationMetrics or all RegressionMetrics).
    """
    if not per_seed:
        raise ValueError("per_seed list is empty")

    if isinstance(per_seed[0], ClassificationMetrics):
        keys = ["auroc", "auprc", "brier_score", "ece"]
    else:
        keys = ["mae"]

    out: dict[str, float] = {}
    for k in keys:
        vals = np.array([getattr(m, k) for m in per_seed], dtype=float)
        valid = vals[~np.isnan(vals)]
        out[f"{k}_mean"] = float(np.mean(valid)) if len(valid) > 0 else float("nan")
        out[f"{k}_std"] = float(np.std(valid, ddof=1)) if len(valid) > 1 else 0.0

    out["n_seeds"] = float(len(per_seed))
    out["n_valid_seeds"] = float(
        len([m for m in per_seed if getattr(m, "auroc_valid", True)])
    )
    return out
