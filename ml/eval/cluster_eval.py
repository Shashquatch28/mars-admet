"""
Decompose multi-task cluster predictions into per-endpoint results.

A cluster run produces one ``(n_samples, n_targets)`` prediction matrix, but
every downstream consumer in MARS — ``eval.metrics.compute_metrics``, the
calibrators, ``EvaluationReport``, ``ml/serve/`` — is per-endpoint and 1-D by
design. This module is the seam between the two, and it is what keeps cluster
results directly comparable with the single-task and XGBoost baselines.

Missing labels (``NaN``) are masked out per column before metrics are computed,
so an endpoint is scored only on the molecules that actually carry its label.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from mars_contracts.endpoints import TaskType

from eval.evaluate import EvaluationReport, build_evaluation_report
from eval.metrics import ClassificationMetrics, RegressionMetrics, compute_metrics


@dataclass
class ClusterSeedResult:
    """One seed of a cluster/subgroup run, carrying every member's metrics.

    The multi-task analogue of ``train.train_xgboost.SeedResult``. Kept separate
    rather than widened, because ``SeedResult`` is singular by contract
    (``val_metrics`` is one metrics object) and several consumers rely on that.
    """

    seed: int
    run_id: str
    model_path: Any
    cluster_key: str
    endpoint_keys: list[str]
    per_endpoint_metrics: dict[str, ClassificationMetrics | RegressionMetrics]
    n_train: int
    n_val: int
    per_endpoint_n_labeled: dict[str, int] = field(default_factory=dict)
    # Per-task learned log-sigma at the end of training, when the run used
    # Kendall weighting. Blueprint Module 4 makes logging this MANDATORY.
    # None means the run did not use uncertainty weighting at all.
    log_sigma_final: dict[str, float] | None = None
    wandb_url: str | None = None
    # Populated when the run calibrated and scored on the test set
    # (``eval.cluster_calibration``). Per-endpoint flat records; None means the
    # run did not calibrate, NOT that calibration failed — a failed or skipped
    # calibration still yields a record carrying its status and reason.
    calibration: dict[str, dict] | None = None
    # How many training labels the calibration holdout cost each endpoint, on
    # top of the union-test removal in ClusterData.split_report.
    labels_held_out_for_calibration: dict[str, int] | None = None


@dataclass
class _EndpointSeedShim:
    """Per-endpoint view of one cluster seed.

    ``build_evaluation_report`` only reads ``.seed``, ``.val_metrics`` and
    ``.run_id``, so this satisfies it without widening ``SeedResult`` or
    duplicating the aggregation logic.
    """

    seed: int
    val_metrics: ClassificationMetrics | RegressionMetrics
    run_id: str


def decompose_cluster_predictions(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    endpoint_keys: list[str],
    task_types: dict[str, TaskType],
    *,
    n_bins: int = 10,
) -> dict[str, ClassificationMetrics | RegressionMetrics]:
    """Score each endpoint column independently, masking its missing labels.

    Parameters
    ----------
    y_true, y_pred:
        ``(n_samples, n_targets)`` arrays in ``endpoint_keys`` column order.
        ``y_true`` carries ``NaN`` where a molecule has no label for that
        endpoint. A ``NaN`` in ``y_pred`` is also dropped (a model may decline
        to predict a column, e.g. a regression column from a logits-only path).
    task_types:
        Endpoint key -> task type, as returned by
        ``configs.clusters.endpoint_task_types``.

    Raises
    ------
    ValueError
        On shape mismatch, or if an endpoint has no labelled rows at all — that
        is a data-assembly bug, not a legitimately empty evaluation.
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    if y_true.ndim != 2 or y_pred.ndim != 2:
        raise ValueError(
            f"y_true and y_pred must be 2-D; got {y_true.ndim}-D and {y_pred.ndim}-D"
        )
    if y_true.shape != y_pred.shape:
        raise ValueError(f"shape mismatch: y_true {y_true.shape} vs y_pred {y_pred.shape}")
    if y_true.shape[1] != len(endpoint_keys):
        raise ValueError(
            f"y_true has {y_true.shape[1]} columns but {len(endpoint_keys)} "
            f"endpoint_keys were given"
        )

    out: dict[str, ClassificationMetrics | RegressionMetrics] = {}
    for col, key in enumerate(endpoint_keys):
        mask = ~np.isnan(y_true[:, col]) & ~np.isnan(y_pred[:, col])
        if not mask.any():
            raise ValueError(
                f"{key}: no rows with both a label and a prediction. Either the "
                "cluster table was assembled wrong or the model produced no "
                "output for this column."
            )
        out[key] = compute_metrics(
            y_true[mask, col],
            y_pred[mask, col],
            task_types[key],
            n_bins=n_bins,
        )
    return out


def cluster_results_to_endpoint_reports(
    results: list[ClusterSeedResult],
    *,
    cluster_key: str,
    model_family: str,
    prep_id: str,
    task_types: dict[str, TaskType],
) -> dict[str, EvaluationReport]:
    """Fan a 5-seed cluster sweep out into one ``EvaluationReport`` per endpoint.

    Each report is the same artifact shape the XGBoost baselines already produce,
    with ``cluster_key`` set so it is never mistaken for a single-task result.

    Raises
    ------
    ValueError
        If *results* is empty, seeds are duplicated, or the seeds disagree about
        which endpoints they cover (a partial sweep must be fixed, not averaged).
    """
    if not results:
        raise ValueError("results is empty")
    seeds = [r.seed for r in results]
    if len(seeds) != len(set(seeds)):
        raise ValueError(f"Duplicate seeds in results: {seeds}")

    key_sets = {tuple(r.endpoint_keys) for r in results}
    if len(key_sets) != 1:
        raise ValueError(
            f"Seeds disagree on endpoint membership: {sorted(key_sets)}. "
            "Every seed of one sweep must cover the same endpoints."
        )
    endpoint_keys = list(next(iter(key_sets)))

    reports: dict[str, EvaluationReport] = {}
    for key in endpoint_keys:
        shims = []
        for r in results:
            if key not in r.per_endpoint_metrics:
                raise ValueError(
                    f"seed {r.seed} has no metrics for endpoint {key!r}"
                )
            shims.append(
                _EndpointSeedShim(
                    seed=r.seed,
                    val_metrics=r.per_endpoint_metrics[key],
                    run_id=r.run_id,
                )
            )
        report = build_evaluation_report(
            shims,  # type: ignore[arg-type]  # structural: seed/val_metrics/run_id
            endpoint_key=key,
            model_family=model_family,
            prep_id=prep_id,
            task_type=task_types[key],
        )
        report.cluster_key = cluster_key
        reports[key] = report
    return reports
