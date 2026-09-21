"""
Temperature-calibrate a KERMT cluster/subgroup run and score it on the test set.

This is the production call site for ``eval.calibration.fit_temperature_scaler``,
which previously had none: nothing in the KERMT path ever fit a temperature.

Data flow (the contract this module enforces)
---------------------------------------------
::

    TRAIN         training pool  -> model fitting            (not this module)
    CALIBRATE     calibration split logits + labels
                       -> diagnose_temperature_fit()  ->  TemperatureScaler
    TEST          untouched test logits
                       -> fitted scaler -> calibrated probabilities
                       -> final test metrics (raw AND calibrated)

The fit function receives **only** calibration arrays. Test arrays are read
strictly after the scaler exists, and only to transform and score. That
separation is structural (see ``_fit_from_calibration_only``) and is pinned by
``ml/tests/test_cluster_calibration.py``, including a test that changing the
test labels cannot change the fitted temperature.

What is GPU-dependent, and what is not
--------------------------------------
Everything in this file is CPU-only. The one GPU-dependent step is *producing*
the ``cal_scores`` / ``test_scores`` inputs (``KermtModel.predict_logits`` runs
KERMT inference in its container). This module never fabricates them.

Score-matrix convention
-----------------------
Both score matrices are ``(n_rows, n_targets)`` in ``endpoint_keys`` order.
**Classification columns carry logits. Regression columns carry raw predicted
values.** Regression columns are never calibrated — there is no probability to
calibrate — and never reach the fitter.

Nothing here decides that a calibration is *acceptable*. The status field
reports what happened (fitted / fitted at a search boundary / skipped and why);
whether that is good enough is a maintainer judgement, and no project document
defines a threshold for it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from mars_contracts.endpoints import TaskType

from eval.calibration import TemperatureScaler
from eval.calibration_diagnostics import (
    CalibrationFitDiagnostics,
    diagnose_temperature_fit,
)
from eval.metrics import (
    ClassificationMetrics,
    RegressionMetrics,
    aggregate_seed_metrics,
    compute_metrics,
)

CLUSTER_CALIBRATION_VERSION = "mars-cluster-calibration-v1"

STATUS_FITTED = "fitted"
STATUS_FITTED_AT_BOUNDARY = "fitted_at_boundary"
STATUS_SKIPPED_REGRESSION = "skipped_regression"
STATUS_SKIPPED_INVALID = "skipped_invalid_calibration_data"

# Every key that must be present in a persisted per-endpoint diagnostics record.
REQUIRED_RECORD_KEYS: tuple[str, ...] = (
    "endpoint_key",
    "seed",
    "n_fit_samples",
    "n_positive",
    "n_negative",
    "positive_rate",
    "temperature",
    "at_boundary",
    "optimizer_success",
    "nll_before",
    "nll_after",
    "ece_before",
    "ece_after",
    "nll_improved",
    "ece_improved",
    "train_val_positive_rate",
    "calibration_positive_rate",
    "status",
    "prep_id",
    "model_id",
    "checkpoint_sha256",
)


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _metrics_dict(m: ClassificationMetrics | RegressionMetrics | None) -> dict | None:
    return None if m is None else asdict(m)


@dataclass
class EndpointCalibrationOutcome:
    """Everything about calibrating and scoring one endpoint for one seed."""

    endpoint_key: str
    seed: int
    task_type: str
    status: str
    reason: str | None = None
    diagnostics: CalibrationFitDiagnostics | None = None
    scaler: TemperatureScaler | None = None
    train_val_positive_rate: float | None = None
    calibration_positive_rate: float | None = None
    n_calibration_labeled: int = 0
    n_test_labeled: int = 0
    test_metrics_raw: ClassificationMetrics | RegressionMetrics | None = None
    test_metrics_calibrated: ClassificationMetrics | None = None
    # In-memory only (excluded from persistence): lets tests and callers check
    # that calibration actually changed the probabilities.
    test_probs_raw: np.ndarray | None = field(default=None, repr=False)
    test_probs_calibrated: np.ndarray | None = field(default=None, repr=False)
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def temperature(self) -> float | None:
        return None if self.scaler is None else self.scaler.temperature

    def to_record(self) -> dict[str, Any]:
        """Flat, JSON-serializable record: fit diagnostics + provenance + metrics.

        Contains every field in ``REQUIRED_RECORD_KEYS``. Fields that do not
        apply (e.g. ``temperature`` for a regression endpoint) are ``None``
        rather than absent, so consumers see a stable schema.
        """
        diag = self.diagnostics.to_dict() if self.diagnostics is not None else {}
        record: dict[str, Any] = {
            "version": CLUSTER_CALIBRATION_VERSION,
            "endpoint_key": self.endpoint_key,
            "seed": self.seed,
            "task_type": self.task_type,
            "status": self.status,
            "reason": self.reason,
            "n_fit_samples": diag.get("n_fit_samples"),
            "n_positive": diag.get("n_positive"),
            "n_negative": diag.get("n_negative"),
            "positive_rate": diag.get("positive_rate"),
            "temperature": diag.get("temperature"),
            "at_boundary": diag.get("at_boundary"),
            "optimizer_success": diag.get("optimizer_success"),
            "nll_before": diag.get("nll_before"),
            "nll_after": diag.get("nll_after"),
            "ece_before": diag.get("ece_before"),
            "ece_after": diag.get("ece_after"),
            "nll_improved": diag.get("nll_improved"),
            "ece_improved": diag.get("ece_improved"),
            "train_val_positive_rate": self.train_val_positive_rate,
            "calibration_positive_rate": self.calibration_positive_rate,
            "n_calibration_labeled": self.n_calibration_labeled,
            "n_test_labeled": self.n_test_labeled,
            "test_metrics_raw": _metrics_dict(self.test_metrics_raw),
            "test_metrics_calibrated": _metrics_dict(self.test_metrics_calibrated),
        }
        for key in ("prep_id", "model_id", "checkpoint_sha256"):
            record[key] = self.provenance.get(key)
        # Any additional provenance the caller supplied is preserved verbatim.
        record["provenance"] = {
            k: v
            for k, v in self.provenance.items()
            if k not in ("prep_id", "model_id", "checkpoint_sha256")
        }
        return record


def _fit_from_calibration_only(
    cal_logits: np.ndarray,
    cal_labels: np.ndarray,
    *,
    endpoint_key: str,
    seed: int,
) -> tuple[TemperatureScaler, CalibrationFitDiagnostics]:
    """Fit a temperature scaler. Takes ONLY calibration arrays, by signature.

    Isolated in its own function so the "test data cannot influence the fit"
    property is enforced by what this function is *able to see*, not by
    discipline in its caller.
    """
    return diagnose_temperature_fit(
        cal_logits, cal_labels, endpoint_key=endpoint_key, seed=seed
    )


def _positive_rate(labels: np.ndarray) -> float | None:
    labels = labels[~np.isnan(labels)]
    return float(labels.mean()) if labels.size else None


def calibrate_endpoints(
    *,
    endpoint_keys: list[str],
    task_types: Mapping[str, TaskType],
    seed: int,
    cal_scores: np.ndarray,
    cal_labels: np.ndarray,
    test_scores: np.ndarray,
    test_labels: np.ndarray,
    train_val_positive_rates: Mapping[str, float | None] | None = None,
    provenance: Mapping[str, Any] | None = None,
) -> dict[str, EndpointCalibrationOutcome]:
    """Fit a temperature scaler per classification endpoint; score on test.

    Parameters
    ----------
    endpoint_keys:
        Column order of all four matrices.
    task_types:
        Endpoint key -> task type. Regression columns are never calibrated.
    cal_scores, cal_labels:
        ``(n_cal, T)``. Scores are logits for classification columns. Labels
        carry ``NaN`` where a molecule has no label for that endpoint.
    test_scores, test_labels:
        ``(n_test, T)`` — the untouched test rows. Used only to transform and
        score, after the scaler is fit.
    train_val_positive_rates:
        Endpoint key -> positive rate of the training pool, recorded next to the
        calibration positive rate so a prior shift between them is visible per
        run instead of rediscovered later.
    provenance:
        ``prep_id``, ``model_id``, ``checkpoint_sha256`` and anything else worth
        persisting alongside each fit.

    Raises
    ------
    ValueError
        On structurally invalid input (shape mismatch, empty arrays), or if an
        endpoint has no labelled test rows — a data-assembly bug, not a
        legitimate empty evaluation. An endpoint whose *calibration* data is
        unusable (no labels, single class) is **not** an error: it is reported
        as ``skipped_invalid_calibration_data`` with the reason.
    """
    cal_scores = np.asarray(cal_scores, dtype=float)
    cal_labels = np.asarray(cal_labels, dtype=float)
    test_scores = np.asarray(test_scores, dtype=float)
    test_labels = np.asarray(test_labels, dtype=float)
    provenance = dict(provenance or {})
    train_val_positive_rates = dict(train_val_positive_rates or {})

    n_targets = len(endpoint_keys)
    for name, arr in (
        ("cal_scores", cal_scores),
        ("cal_labels", cal_labels),
        ("test_scores", test_scores),
        ("test_labels", test_labels),
    ):
        if arr.ndim != 2:
            raise ValueError(f"{name} must be 2-D (n_rows, n_targets); got {arr.ndim}-D")
        if arr.shape[1] != n_targets:
            raise ValueError(
                f"shape mismatch: {name} has {arr.shape[1]} columns but "
                f"{n_targets} endpoint_keys were given"
            )
    if cal_scores.shape != cal_labels.shape:
        raise ValueError(
            f"shape mismatch: cal_scores {cal_scores.shape} vs cal_labels {cal_labels.shape}"
        )
    if test_scores.shape != test_labels.shape:
        raise ValueError(
            f"shape mismatch: test_scores {test_scores.shape} vs "
            f"test_labels {test_labels.shape}"
        )
    if cal_scores.shape[0] == 0:
        raise ValueError("calibration arrays are empty")
    if test_scores.shape[0] == 0:
        raise ValueError("test arrays are empty")

    outcomes: dict[str, EndpointCalibrationOutcome] = {}
    for col, key in enumerate(endpoint_keys):
        task_type = task_types[key]
        if task_type not in (TaskType.CLASSIFICATION, TaskType.REGRESSION):
            raise ValueError(f"{key}: unsupported task type {task_type!r}")

        test_mask = ~np.isnan(test_labels[:, col]) & ~np.isnan(test_scores[:, col])
        n_test = int(test_mask.sum())
        if n_test == 0:
            raise ValueError(
                f"{key}: no test rows with both a label and a score. Either the "
                "cluster table was assembled wrong or the model produced no "
                "output for this column."
            )

        outcome = EndpointCalibrationOutcome(
            endpoint_key=key,
            seed=seed,
            task_type=task_type.value,
            status=STATUS_SKIPPED_REGRESSION,
            n_test_labeled=n_test,
            train_val_positive_rate=train_val_positive_rates.get(key),
            provenance=dict(provenance),
        )
        outcomes[key] = outcome

        # ---- regression: never attempt classification calibration ----------
        if task_type is TaskType.REGRESSION:
            outcome.reason = "regression endpoint has no probability to calibrate"
            outcome.test_metrics_raw = compute_metrics(
                test_labels[test_mask, col], test_scores[test_mask, col], task_type
            )
            continue

        # ---- classification: fit on the calibration split ONLY -------------
        cal_col_labels = cal_labels[:, col]
        cal_mask = ~np.isnan(cal_col_labels) & ~np.isnan(cal_scores[:, col])
        n_cal = int(cal_mask.sum())
        outcome.n_calibration_labeled = n_cal
        outcome.calibration_positive_rate = _positive_rate(cal_col_labels[cal_mask])

        # Raw test probabilities are needed whether or not a fit succeeds, so a
        # skipped calibration still yields honest, clearly-labelled raw metrics.
        raw_probs = _sigmoid(test_scores[test_mask, col])
        outcome.test_probs_raw = raw_probs
        outcome.test_metrics_raw = compute_metrics(
            test_labels[test_mask, col], raw_probs, task_type
        )

        if n_cal == 0:
            outcome.status = STATUS_SKIPPED_INVALID
            outcome.reason = "no labelled calibration rows for this endpoint"
            continue

        try:
            scaler, diag = _fit_from_calibration_only(
                cal_scores[cal_mask, col],
                cal_col_labels[cal_mask].astype(int),
                endpoint_key=key,
                seed=seed,
            )
        except ValueError as exc:
            # fit_temperature_scaler rejects a strictly single-class calibration
            # split. Record it; do not fabricate a scaler and do not abort the
            # other endpoints in the cluster.
            outcome.status = STATUS_SKIPPED_INVALID
            outcome.reason = str(exc)
            continue

        outcome.scaler = scaler
        outcome.diagnostics = diag
        outcome.status = STATUS_FITTED_AT_BOUNDARY if diag.at_boundary else STATUS_FITTED

        # ---- test: scaler already exists; test data only transforms + scores
        cal_probs = scaler.transform_logits(test_scores[test_mask, col])
        outcome.test_probs_calibrated = cal_probs
        outcome.test_metrics_calibrated = compute_metrics(
            test_labels[test_mask, col], cal_probs, task_type
        )

    return outcomes


# ---------------------------------------------------------------------------- #
# Persistence + aggregation
# ---------------------------------------------------------------------------- #


def save_calibration_outcomes(
    outcomes: Mapping[str, EndpointCalibrationOutcome], out_dir: Path | str
) -> dict[str, dict[str, Path]]:
    """Persist each endpoint's scaler and diagnostics record.

    Layout, one directory per endpoint::

        <out_dir>/<endpoint_key>/temperature_scaler.json   (only when fitted)
        <out_dir>/<endpoint_key>/calibration_diagnostics.json

    The scaler file deliberately is **not** named ``calibrator.json``: that is
    the XGBoost registry's ``PlattCalibrator`` filename, and loading a
    ``TemperatureScaler`` there would fail on the missing ``A``/``B`` fields.
    """
    out_dir = Path(out_dir)
    written: dict[str, dict[str, Path]] = {}
    for key, outcome in outcomes.items():
        ep_dir = out_dir / key
        ep_dir.mkdir(parents=True, exist_ok=True)
        paths: dict[str, Path] = {}
        if outcome.scaler is not None:
            scaler_path = ep_dir / "temperature_scaler.json"
            outcome.scaler.save(scaler_path)
            paths["temperature_scaler"] = scaler_path
        diag_path = ep_dir / "calibration_diagnostics.json"
        diag_path.write_text(
            json.dumps(outcome.to_record(), indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        paths["diagnostics"] = diag_path
        written[key] = paths
    return written


def aggregate_test_metrics_across_seeds(
    records: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Mean ± std of the TEST metrics over seeds, raw and calibrated side by side.

    Blueprint Module 11 §2: report mean ± std across seeds, never a single-run
    point estimate. ``ClusterSeedResult.per_endpoint_metrics`` (and therefore
    ``EvaluationReport``) are validation-fold numbers; the test-set numbers live
    only in these per-seed records, so this is what a final comparison against
    the XGBoost baselines must use.

    Calibrated metrics are aggregated only over seeds where a scaler was fit, and
    ``n_calibrated_seeds`` says how many that was, so a partial calibration is
    visible rather than averaged away.
    """
    by_endpoint: dict[str, list[dict[str, Any]]] = {}
    for rec in records:
        by_endpoint.setdefault(rec["endpoint_key"], []).append(rec)

    out: dict[str, dict[str, Any]] = {}
    for key, recs in by_endpoint.items():
        is_clf = recs[0]["task_type"] == TaskType.CLASSIFICATION.value
        cls = ClassificationMetrics if is_clf else RegressionMetrics

        raw = [cls(**r["test_metrics_raw"]) for r in recs if r["test_metrics_raw"]]
        cal = [
            ClassificationMetrics(**r["test_metrics_calibrated"])
            for r in recs
            if r.get("test_metrics_calibrated")
        ]
        out[key] = {
            "task_type": recs[0]["task_type"],
            "n_seeds": len(recs),
            "n_calibrated_seeds": len(cal),
            "raw": aggregate_seed_metrics(raw) if raw else None,
            "calibrated": aggregate_seed_metrics(cal) if cal else None,
        }
    return out


def aggregate_calibration_across_seeds(
    records: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Summarise per-seed records into per-endpoint stability statistics.

    Only classification endpoints that produced a fit contribute. Reports the
    seed-to-seed spread of the fitted temperature and how many seeds pinned to a
    search boundary or failed to converge. It reports; it does not judge.
    """
    by_endpoint: dict[str, list[dict[str, Any]]] = {}
    for rec in records:
        by_endpoint.setdefault(rec["endpoint_key"], []).append(rec)

    out: dict[str, dict[str, Any]] = {}
    for key, recs in by_endpoint.items():
        fitted = [r for r in recs if r.get("temperature") is not None]
        if not fitted:
            out[key] = {
                "n_seeds": len(recs),
                "n_fitted": 0,
                "statuses": sorted({r["status"] for r in recs}),
            }
            continue
        temps = np.array([r["temperature"] for r in fitted], dtype=float)
        out[key] = {
            "n_seeds": len(recs),
            "n_fitted": len(fitted),
            "temperature_mean": float(temps.mean()),
            "temperature_std": float(temps.std(ddof=1)) if len(temps) > 1 else None,
            "temperature_min": float(temps.min()),
            "temperature_max": float(temps.max()),
            "n_at_boundary": int(sum(bool(r.get("at_boundary")) for r in fitted)),
            "n_optimizer_failed": int(
                sum(not bool(r.get("optimizer_success")) for r in fitted)
            ),
            "n_nll_not_improved": int(
                sum(not bool(r.get("nll_improved")) for r in fitted)
            ),
            "n_ece_not_improved": int(
                sum(not bool(r.get("ece_improved")) for r in fitted)
            ),
            "statuses": sorted({r["status"] for r in recs}),
        }
    return out
