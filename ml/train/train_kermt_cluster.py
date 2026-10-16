"""
Tier 0 — seed-aware training loop for a type-homogeneous KERMT subgroup.

This is **MARS-side harness and CLI code only. It introduces no new KERMT
optimization or model logic**: the training step is the existing ``KermtModel``
shelling out to KERMT's stock CLI exactly as it already does. What is here is
the plumbing around it — a shared cluster fold, a wide label matrix, temperature
calibration, and per-endpoint decomposition of the results.

Mirrors ``train.train_xgboost``'s conventions deliberately (``FIXED_SEEDS``,
``set_global_seed``, ``ExperimentRun`` as the on-disk source of truth,
``use_wandb=False`` at this library layer so ad-hoc calls stay off the
dashboard). The production entry point turns W&B on.

Per-seed data flow
------------------
::

    pool  = train_val  minus  every calibration molecule   (holdout_calibration)
    fold  = five_seed_train_val_folds(pool, seed)          -> train / val
    fit   : KermtModel.fit(train, val)                     (val selects the epoch)
    calibrate : held-out calibration split -> logits -> fit_temperature_scaler
    test  : untouched test split -> logits -> fitted scaler -> calibrated metrics

The test set is used only in the final step, only to transform and score, never
to fit or select anything. ``eval.cluster_calibration`` enforces that structurally.

EQUAL WEIGHTING ONLY. KERMT's ``run_finetune_local.py`` never forwards
``--use_mtl_loss``, so every run produced here is equal-weighted — precisely
blueprint Module 4's mandatory fixed/equal baseline arm. Kendall and GradNorm
come from the Tier-1 trainer, for pure-type clusters as well as mixed ones. See
``documentation/AIMS/decisions.md`` (2026-09-20, finding 2).

GPU-dependent: ``KermtModel.fit`` / ``predict`` / ``predict_logits`` all run KERMT
inside its container. Everything else in this module is CPU-only.
"""

from __future__ import annotations

import json
import warnings
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
from configs.clusters import SubgroupSpec
from configs.experiment_config import FIXED_SEEDS, ExperimentConfig
from data.cluster_loaders import SMILES_COL, ClusterData
from data.split import five_seed_train_val_folds
from eval.cluster_calibration import (
    calibrate_endpoints,
    save_calibration_outcomes,
)
from eval.cluster_eval import ClusterSeedResult, decompose_cluster_predictions
from mars_contracts.endpoints import TaskType
from models.kermt_model import KermtConfig, KermtModel
from tracking.experiment import ExperimentRun
from utils.seed import set_global_seed

_CHECKPOINT_LOCK = Path("ml") / "data" / "metadata" / "kermt_checkpoint.lock.json"


def _checkpoint_provenance(repo_root: Path) -> dict[str, Any]:
    """Pretrained-checkpoint identity from the tracked lockfile, if present.

    Absent on a machine without the lockfile; recorded as ``None`` rather than
    guessed, so a missing hash is visible in the run record.
    """
    path = repo_root / _CHECKPOINT_LOCK
    if not path.exists():
        return {"checkpoint_sha256": None, "checkpoint_hf_repo_sha": None, "kermt_commit": None}
    lock = json.loads(path.read_text(encoding="utf-8"))
    return {
        "checkpoint_sha256": lock["files"]["kermt_contrastive_v2.0.pt"]["sha256"],
        "checkpoint_hf_repo_sha": lock["model"].get("huggingface_repo_sha"),
        "kermt_commit": lock["model"].get("source_code_commit"),
    }


def _label_lookup(pool: Any) -> dict[str, np.ndarray]:
    """SMILES -> its row of the wide label matrix (NaN where absent)."""
    label_cols = [c for c in pool.columns if c != SMILES_COL]
    matrix = pool[label_cols].to_numpy(dtype=float)
    return dict(zip(pool[SMILES_COL].tolist(), matrix, strict=True))


def _stack(smiles: list[str], lookup: dict[str, np.ndarray]) -> np.ndarray:
    return np.stack([lookup[s] for s in smiles], axis=0)


def _as_2d(a: np.ndarray) -> np.ndarray:
    return a[:, None] if a.ndim == 1 else a


def train_one_seed(
    cluster_data: ClusterData,
    subgroup: SubgroupSpec,
    config: ExperimentConfig,
    seed: int,
    *,
    checkpoint: Path,
    kermt_config: KermtConfig | None = None,
    runs_dir: Path | str | None = None,
    repo_root: Path | str | None = None,
    use_wandb: bool = False,
    holdout_calibration: bool = True,
    calibrate: bool = True,
) -> ClusterSeedResult:
    """Fine-tune one type-homogeneous subgroup for one seed, then calibrate + test.

    Parameters
    ----------
    cluster_data:
        Leakage-safe wide splits from ``data.cluster_loaders.load_cluster``,
        loaded with exactly ``subgroup.endpoints``.
    subgroup:
        The subgroup being trained. Its ``task_type`` is what reaches KERMT's
        ``--dataset_type``; its homogeneity is what makes that legitimate.
    config:
        ``ExperimentConfig`` whose ``endpoint`` is the subgroup key and whose
        ``model_family`` matches ``subgroup.model_family``.
    checkpoint:
        Path to the pretrained ``kermt_contrastive_v2.0.pt``.
    holdout_calibration:
        Remove every calibration molecule from the training pool (so from both
        the train and the validation fold). Default ``True``. See
        ``ClusterData.train_pool`` for why. Costs some training labels — the
        cost is recorded on the result, never hidden.
    calibrate:
        Fit a temperature scaler per classification endpoint on the calibration
        split and score the untouched test set (raw and calibrated). Default
        ``True``. Requires ``holdout_calibration`` — see below.

    Raises
    ------
    ValueError
        If *cluster_data* and *subgroup* disagree on membership; if *config* is
        not set up for this subgroup; or if ``calibrate`` is requested without
        ``holdout_calibration``. That last combination would fit the calibrator
        on molecules the model trained on or was selected against, producing a
        calibration that looks fine and means nothing.
    """
    if list(cluster_data.endpoint_keys) != list(subgroup.endpoints):
        raise ValueError(
            f"cluster_data covers {cluster_data.endpoint_keys} but subgroup "
            f"{subgroup.key!r} is {list(subgroup.endpoints)}. Load the cluster with "
            "exactly the subgroup's endpoints, in order."
        )
    if config.model_family != subgroup.model_family:
        raise ValueError(
            f"config.model_family={config.model_family!r} but subgroup "
            f"{subgroup.key!r} must run as {subgroup.model_family!r}. "
            "A single-task subgroup reported as multi-task would fabricate a "
            "multi-task result out of a single-task run."
        )
    if calibrate and not holdout_calibration:
        raise ValueError(
            "calibrate=True requires holdout_calibration=True: otherwise the "
            "temperature scaler would be fit on molecules the model trained on "
            "or was selected against."
        )

    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[2]
    repo_root = Path(repo_root)

    set_global_seed(seed)

    pool, labels_held_out = cluster_data.train_pool(holdout_calibration=holdout_calibration)

    # ONE shared fold for every task in the subgroup. Per-task folds would put a
    # molecule in task A's train and task B's val, leaking through the encoder.
    pool_smiles = pool[SMILES_COL].tolist()
    _, train_smiles, val_smiles = five_seed_train_val_folds(pool_smiles, seeds=(seed,))[0]

    lookup = _label_lookup(pool)
    y_train = _stack(train_smiles, lookup)
    y_val = _stack(val_smiles, lookup)

    seed_config = replace(config, seed=seed)
    tracking_config = seed_config.to_tracking_config()
    # The split report is provenance: it records what the leakage fix cost.
    tracking_config["cluster_split_report"] = cluster_data.split_report.to_dict()
    tracking_config["loss_weighting"] = "equal"
    tracking_config["holdout_calibration"] = holdout_calibration
    tracking_config["labels_held_out_for_calibration"] = labels_held_out
    tracking_config["calibrate"] = calibrate
    provenance = {
        "prep_id": config.prep_id,
        "model_id": None,  # filled once the model exists
        **_checkpoint_provenance(repo_root),
    }

    run = ExperimentRun(
        name=seed_config.run_name(),
        repo_root=repo_root,
        config=tracking_config,
        runs_dir=runs_dir,
    )
    run.start(
        run_tags={
            "endpoint": config.endpoint,
            "model_family": config.model_family,
            "seed": seed,
            "prep_id": config.prep_id,
            "cluster": subgroup.cluster,
            "n_targets": len(subgroup.endpoints),
        }
    )

    wandb_logger = None
    if use_wandb:
        try:
            from tracking.wandb_logger import WandbLogger

            wandb_logger = WandbLogger(
                run_id=run.run_id,
                config=tracking_config,
                provenance=run.provenance,
            )
        except Exception as exc:
            warnings.warn(
                f"W&B logging disabled for run {run.run_id}: {exc}",
                UserWarning,
                stacklevel=2,
            )
            wandb_logger = None

    model = KermtModel(
        subgroup.task_type,
        checkpoint,
        list(subgroup.endpoints),
        seed=seed,
        config=kermt_config or KermtConfig(),
    )
    provenance["model_id"] = model.model_id

    # KermtModel's single-task contract is 1-D labels and 1-D predictions;
    # everything downstream of here is uniformly 2-D.
    single = len(subgroup.endpoints) == 1
    work_dir = run.artifact_path("kermt")
    model.fit(
        train_smiles,
        y_train[:, 0] if single else y_train,
        X_val=val_smiles,
        y_val=y_val[:, 0] if single else y_val,
        run_dir=work_dir,
    )

    preds = _as_2d(model.predict(val_smiles, run_dir=work_dir))

    per_endpoint_metrics = decompose_cluster_predictions(
        y_val, preds, list(subgroup.endpoints), cluster_data.task_types
    )

    for key, metrics in per_endpoint_metrics.items():
        metrics_dict: dict[str, Any] = {
            "split": "val",
            "seed": seed,
            "endpoint": key,
            "subgroup": subgroup.key,
        }
        for attr in metrics.__dataclass_fields__:
            metrics_dict[attr] = getattr(metrics, attr)
        run.log_metrics(metrics_dict)
        if wandb_logger is not None:
            wandb_logger.log({f"{key}/{k}": v for k, v in metrics_dict.items()})

    # ---- calibrate on the held-out calibration split; score the test set ------
    calibration_records: dict[str, dict] | None = None
    if calibrate:
        keys = list(subgroup.endpoints)
        cal_smiles = cluster_data.smiles("calibration")
        test_smiles = cluster_data.smiles("test")
        cal_labels = cluster_data.calibration[keys].to_numpy(dtype=float)
        test_labels = cluster_data.test[keys].to_numpy(dtype=float)

        if subgroup.task_type is TaskType.CLASSIFICATION:
            # GPU-dependent: KERMT inference in its container.
            cal_scores = _as_2d(model.predict_logits(cal_smiles, run_dir=work_dir))
            test_scores = _as_2d(model.predict_logits(test_smiles, run_dir=work_dir))
        else:
            # Regression is never calibrated, so calibration rows need no
            # inference; the test predictions are still needed for scoring.
            cal_scores = np.full(cal_labels.shape, np.nan)
            test_scores = _as_2d(model.predict(test_smiles, run_dir=work_dir))

        outcomes = calibrate_endpoints(
            endpoint_keys=keys,
            task_types=cluster_data.task_types,
            seed=seed,
            cal_scores=cal_scores,
            cal_labels=cal_labels,
            test_scores=test_scores,
            test_labels=test_labels,
            train_val_positive_rates=cluster_data.positive_rates("train_val"),
            provenance=provenance,
        )
        save_calibration_outcomes(outcomes, run.artifact_path("calibration"))
        calibration_records = {k: o.to_record() for k, o in outcomes.items()}

        for key, record in calibration_records.items():
            log_record = {"split": "calibration+test", "subgroup": subgroup.key, **record}
            run.log_metrics(log_record)
            if wandb_logger is not None:
                flat = {
                    f"{key}/{k}": v
                    for k, v in record.items()
                    if isinstance(v, (int, float, bool)) and v is not None
                }
                wandb_logger.log(flat)

    model_path = run.artifact_path("model") / "kermt"
    model.save(model_path)
    run.finish("completed")

    wandb_url: str | None = None
    if wandb_logger is not None:
        wandb_url = getattr(wandb_logger._run, "url", None)
        wandb_logger.finish()

    return ClusterSeedResult(
        seed=seed,
        run_id=run.run_id,
        model_path=model_path,
        cluster_key=subgroup.key,
        endpoint_keys=list(subgroup.endpoints),
        per_endpoint_metrics=per_endpoint_metrics,
        n_train=len(train_smiles),
        n_val=len(val_smiles),
        per_endpoint_n_labeled={
            key: int(np.sum(~np.isnan(y_train[:, i])))
            for i, key in enumerate(subgroup.endpoints)
        },
        # Stock CLI cannot enable MTLLoss, so there is no learned log-sigma to
        # report. None here means "equal weighting", not "not logged".
        log_sigma_final=None,
        wandb_url=wandb_url,
        calibration=calibration_records,
        labels_held_out_for_calibration=labels_held_out,
    )


def train_subgroup_all_seeds(
    cluster_data: ClusterData,
    subgroup: SubgroupSpec,
    config: ExperimentConfig,
    *,
    checkpoint: Path,
    kermt_config: KermtConfig | None = None,
    runs_dir: Path | str | None = None,
    repo_root: Path | str | None = None,
    use_wandb: bool = False,
    holdout_calibration: bool = True,
    calibrate: bool = True,
) -> list[ClusterSeedResult]:
    """Train all ``FIXED_SEEDS`` for one subgroup; one result per seed."""
    return [
        train_one_seed(
            cluster_data,
            subgroup,
            config,
            seed,
            checkpoint=checkpoint,
            kermt_config=kermt_config,
            runs_dir=runs_dir,
            repo_root=repo_root,
            use_wandb=use_wandb,
            holdout_calibration=holdout_calibration,
            calibrate=calibrate,
        )
        for seed in FIXED_SEEDS
    ]


__all__ = ["SMILES_COL", "train_one_seed", "train_subgroup_all_seeds"]
