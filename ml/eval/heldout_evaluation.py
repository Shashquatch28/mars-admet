"""
Held-out TEST-set evaluation of the promoted XGBoost artifacts.

Why this exists
---------------
The 70-run XGBoost sweep reports 5-seed **validation-fold** metrics
(``ml/runs/evaluations/*.json``; per-seed ``n_samples`` equals the val-fold size).
Blueprint Module 4/11 pick the winner on the held-out scaffold-split *test* set,
and the KERMT harness now reports test metrics, so the two were not comparable.
This module closes that gap **without retraining anything**.

Three kinds of numbers, kept distinct on purpose
------------------------------------------------
* **validation**  - the existing ``runs/evaluations/*.json``. Untouched. Echoed
  into each report only as a clearly-labelled reference.
* **calibration** - metrics on the calibration split. The served Platt
  calibrator was *fit* on that split, so these are in-sample for the calibrator
  and informational only.
* **test**        - the untouched test split. Loaded, predicted on, scored.
  Nothing is ever fit, selected or tuned on it.

Calibrator caveat (established from the code, verified empirically here)
-----------------------------------------------------------------------
``serve.registry.promote_seed_artifact`` writes ONE ``calibrator.json`` per
endpoint and overwrites it on every seed, so the file on disk was fit on the
model of the **last promoted seed only**. Applying it to another seed's raw
probabilities uses a calibrator that was not fit on that model. This module
therefore (a) re-derives, in memory and from the calibration split only, which
seed's model reproduces the served calibrator, and (b) marks every per-seed
calibrated result ``calibrator_is_seed_matched``. Nothing is written back.

If any promoted artifact cannot be evaluated, ``EvaluationBlocked`` is raised
with the reason. Validation metrics are never substituted.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from configs.experiment_config import FIXED_SEEDS
from mars_contracts.endpoints import TaskType

from eval.calibration import PlattCalibrator, fit_platt_calibrator
from eval.metrics import (
    ClassificationMetrics,
    RegressionMetrics,
    aggregate_seed_metrics,
    compute_metrics,
)

HELDOUT_EVALUATION_VERSION = "mars-heldout-evaluation-v1"
SPLIT_LABEL = "test"

# A seed "reproduces" the served calibrator if refitting on its own calibration-split
# predictions gives the same (A, B). Platt fitting is deterministic, so this is tight.
_CALIBRATOR_MATCH_TOL = 1e-6


class EvaluationBlocked(RuntimeError):
    """An endpoint cannot be test-evaluated from its promoted artifacts.

    Carries a machine-readable ``reason``. Callers must record and report it;
    they must NOT fall back to validation metrics.
    """

    def __init__(self, endpoint_key: str, reason: str) -> None:
        super().__init__(f"{endpoint_key}: {reason}")
        self.endpoint_key = endpoint_key
        self.reason = reason


def sha256_file(path: Path | str) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_tree(root: Path | str) -> str:
    """Deterministic digest of every file under *root* (relative path + content)."""
    root = Path(root)
    h = hashlib.sha256()
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        h.update(str(p.relative_to(root)).replace("\\", "/").encode())
        h.update(sha256_file(p).encode())
    return h.hexdigest()


@dataclass
class SeedTestResult:
    seed: int
    model_dir: str
    model_sha256: str
    n_test: int
    n_scored: int
    n_dropped: int
    test_metrics_raw: dict[str, Any]
    test_metrics_calibrated: dict[str, Any] | None = None
    # Whether the served calibrator was actually fit on THIS seed's model.
    calibrator_is_seed_matched: bool | None = None
    # In-sample for the calibrator (it was fit on this split): informational only.
    calibration_split_metrics_raw: dict[str, Any] | None = None
    calibration_split_metrics_calibrated: dict[str, Any] | None = None


@dataclass
class HeldOutEvaluationReport:
    """Durable 5-seed held-out test evaluation for one endpoint (XGBoost)."""


    endpoint_key: str
    prep_id: str
    task_type: str
    dataset_key: str
    test_set_sha256: str | None
    n_test: int
    seeds: list[int]
    per_seed: list[dict[str, Any]]
    aggregated_test_raw: dict[str, float]
    aggregated_test_calibrated: dict[str, float] | None
    calibrator: dict[str, Any] | None
    validation_reference: dict[str, Any] | None = None
    split: str = SPLIT_LABEL
    model_family: str = "xgboost"
    version: str = HELDOUT_EVALUATION_VERSION
    notes: list[str] = field(default_factory=list)

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> HeldOutEvaluationReport:
        return cls(**json.loads(Path(path).read_text(encoding="utf-8")))


def _metrics_dict(m: ClassificationMetrics | RegressionMetrics) -> dict[str, Any]:
    return asdict(m)


def _scored(y: np.ndarray, preds: np.ndarray) -> tuple[np.ndarray, np.ndarray, int]:
    mask = ~np.isnan(preds)
    return y[mask], preds[mask], int((~mask).sum())


def _refit_platt_in_memory(raw_probs: np.ndarray, y: np.ndarray) -> PlattCalibrator | None:
    """Refit Platt on CALIBRATION-split predictions, in memory. Never saved."""
    y_s, p_s, _ = _scored(y, raw_probs)
    if len(np.unique(y_s.astype(int))) < 2:
        return None
    return fit_platt_calibrator(p_s, y_s)


def evaluate_endpoint_on_test(
    endpoint_data: Any,
    *,
    endpoint_key: str,
    artifacts_root: Path | str,
    cache: Any,
    prep_id: str,
    seeds: tuple[int, ...] = FIXED_SEEDS,
    test_csv_path: Path | str | None = None,
    verify_calibrator_seed: bool = True,
    validation_report_path: Path | str | None = None,
    model_loader: Any = None,
) -> HeldOutEvaluationReport:
    """Score the promoted seed models of one endpoint on its held-out test split.

    Parameters
    ----------
    endpoint_data:
        ``EndpointData`` from ``data.loaders.load_endpoint`` - the canonical
        splits. Only ``.test`` is scored; ``.calibration`` is used solely to
        verify which seed the served calibrator came from.
    artifacts_root:
        ``ml/artifacts``. Read-only here.
    model_loader:
        ``(seed_dir, cache) -> model``; defaults to
        ``XGBoostModel.load_with_cache``. Injectable so tests need no featurizer.

    Raises
    ------
    EvaluationBlocked
        If a seed's model files are missing, or the test split is empty.
    """
    if model_loader is None:
        from models.xgboost_model import XGBoostModel

        model_loader = XGBoostModel.load_with_cache

    task_type = endpoint_data.task_type
    if task_type not in (TaskType.CLASSIFICATION, TaskType.REGRESSION):
        raise EvaluationBlocked(endpoint_key, f"unsupported task type {task_type!r}")

    ep_dir = Path(artifacts_root) / endpoint_key
    if not ep_dir.is_dir():
        raise EvaluationBlocked(endpoint_key, f"no promoted artifacts at {ep_dir}")

    test_smiles = endpoint_data.test["standardized_smiles"].tolist()
    y_test = endpoint_data.test["label"].astype(float).to_numpy()
    if len(test_smiles) == 0:
        raise EvaluationBlocked(endpoint_key, "test split is empty")

    is_clf = task_type == TaskType.CLASSIFICATION
    calibrator_path = ep_dir / "calibrator.json"
    calibrator = PlattCalibrator.load(calibrator_path) if is_clf and calibrator_path.exists() else None
    if is_clf and calibrator is None:
        raise EvaluationBlocked(
            endpoint_key, "classification endpoint has no served calibrator.json"
        )

    cal_smiles = endpoint_data.calibration["standardized_smiles"].tolist()
    y_cal = endpoint_data.calibration["label"].astype(float).to_numpy()

    per_seed: list[SeedTestResult] = []
    matched_seeds: list[int] = []
    for seed in seeds:
        seed_dir = ep_dir / f"seed_{seed}"
        model_json = seed_dir / "model.json"
        if not (seed_dir / "metadata.json").exists() or not model_json.exists():
            raise EvaluationBlocked(
                endpoint_key,
                f"seed {seed} artifact incomplete (need metadata.json + model.json in "
                f"{seed_dir}); not substituting validation metrics",
            )
        model = model_loader(seed_dir, cache)

        preds = np.asarray(model.predict(test_smiles), dtype=float)
        y_s, p_s, n_dropped = _scored(y_test, preds)
        if len(y_s) == 0:
            raise EvaluationBlocked(endpoint_key, f"seed {seed}: no test molecule could be scored")

        raw = compute_metrics(y_s, p_s, task_type)
        cal_m = None
        cal_split_raw = cal_split_cal = None
        seed_matched: bool | None = None

        if is_clf:
            assert calibrator is not None
            cal_m = compute_metrics(y_s, calibrator.transform(p_s), task_type)

            cal_preds = np.asarray(model.predict(cal_smiles), dtype=float)
            yc, pc, _ = _scored(y_cal, cal_preds)
            if len(yc):
                cal_split_raw = _metrics_dict(compute_metrics(yc, pc, task_type))
                cal_split_cal = _metrics_dict(
                    compute_metrics(yc, calibrator.transform(pc), task_type)
                )
            if verify_calibrator_seed:
                refit = _refit_platt_in_memory(cal_preds, y_cal)
                seed_matched = bool(
                    refit is not None
                    and abs(refit.A - calibrator.A) < _CALIBRATOR_MATCH_TOL
                    and abs(refit.B - calibrator.B) < _CALIBRATOR_MATCH_TOL
                )
                if seed_matched:
                    matched_seeds.append(seed)

        per_seed.append(
            SeedTestResult(
                seed=seed,
                model_dir=str(seed_dir),
                model_sha256=sha256_file(model_json),
                n_test=len(test_smiles),
                n_scored=len(y_s),
                n_dropped=n_dropped,
                test_metrics_raw=_metrics_dict(raw),
                test_metrics_calibrated=None if cal_m is None else _metrics_dict(cal_m),
                calibrator_is_seed_matched=seed_matched,
                calibration_split_metrics_raw=cal_split_raw,
                calibration_split_metrics_calibrated=cal_split_cal,
            )
        )

    cls = ClassificationMetrics if is_clf else RegressionMetrics
    agg_raw = aggregate_seed_metrics([cls(**s.test_metrics_raw) for s in per_seed])
    agg_cal = (
        aggregate_seed_metrics([ClassificationMetrics(**s.test_metrics_calibrated) for s in per_seed])
        if is_clf
        else None
    )

    calibrator_info: dict[str, Any] | None = None
    notes: list[str] = []
    if calibrator is not None:
        calibrator_info = {
            "path": str(calibrator_path),
            "sha256": sha256_file(calibrator_path),
            "A": calibrator.A,
            "B": calibrator.B,
            "n_fit_samples": calibrator.n_fit_samples,
            "version": calibrator.version,
            "fit_on": "calibration split of the last-promoted seed's model "
            "(serve.registry.promote_seed_artifact overwrites one file per endpoint)",
            "seeds_reproducing_served_calibrator": matched_seeds if verify_calibrator_seed else None,
            "verified": bool(verify_calibrator_seed),
        }
        if verify_calibrator_seed and not matched_seeds:
            notes.append(
                "No seed's calibration-split predictions reproduce the served calibrator; "
                "its provenance could not be confirmed."
            )
        unmatched = [s.seed for s in per_seed if s.calibrator_is_seed_matched is False]
        if unmatched:
            notes.append(
                f"Calibrated metrics for seeds {unmatched} apply a calibrator that was NOT fit "
                "on those seeds' models. Raw metrics are the like-for-like per-seed numbers."
            )

    validation_ref = None
    if validation_report_path is not None and Path(validation_report_path).exists():
        v = json.loads(Path(validation_report_path).read_text(encoding="utf-8"))
        validation_ref = {
            "split": "validation",
            "source": str(validation_report_path),
            "aggregated": v.get("aggregated"),
            "note": "5-seed VALIDATION-fold metrics from the production sweep; "
            "NOT test-set numbers.",
        }

    return HeldOutEvaluationReport(
        endpoint_key=endpoint_key,
        prep_id=prep_id,
        task_type=task_type.value,
        dataset_key=endpoint_data.dataset_key,
        test_set_sha256=sha256_file(test_csv_path) if test_csv_path else None,
        n_test=len(test_smiles),
        seeds=[s.seed for s in per_seed],
        per_seed=[asdict(s) for s in per_seed],
        aggregated_test_raw=agg_raw,
        aggregated_test_calibrated=agg_cal,
        calibrator=calibrator_info,
        validation_reference=validation_ref,
        notes=notes,
    )
