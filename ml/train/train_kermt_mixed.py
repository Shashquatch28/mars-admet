"""
Tier 1 — seed-aware training of a MIXED classification/regression KERMT cluster.

The mixed-type counterpart of ``train.train_kermt_cluster`` (Tier 0). Same
per-seed data flow, same shared fold, same calibration discipline; what differs is
the model (``KermtMixedModel``: one run, one forward pass per molecule, per-column
type-correct loss) and that the loss-weighting arm is a first-class input recorded
in the run name (``variant``) and the run config.

::

    pool  = train_val  minus  every calibration molecule     (holdout_calibration)
    fold  = five_seed_train_val_folds(pool, seed)            -> train / val
    fit   : KermtMixedModel.fit(train, val)                  (val selects the epoch)
    calibrate : calibration split -> logits (classification columns only)
    test  : untouched test split -> scaler -> calibrated metrics

Regression columns are never calibrated and never pass through a sigmoid.

Never reports a result as stock-KERMT / Tier 0: ``model_family`` must be
``kermt_mixed`` and the arm is in the run name, so a Tier-1 number cannot be
mistaken for a Tier-0 one in a results table (decisions.md 2026-09-20).

GPU-dependent exactly where ``KermtMixedModel`` is. Everything else is CPU.
"""

from __future__ import annotations

import json
import warnings
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
from configs.experiment_config import FIXED_SEEDS, ExperimentConfig
from data.cluster_loaders import SMILES_COL, ClusterData
from data.split import five_seed_train_val_folds
from eval.cluster_calibration import calibrate_endpoints, save_calibration_outcomes
from eval.cluster_eval import ClusterSeedResult, decompose_cluster_predictions
from models.kermt_mixed_model import KermtMixedModel
from models.kermt_model import KermtConfig
from tracking.experiment import ExperimentRun
from utils.seed import set_global_seed

from train.kermt_mixed.common import MODES
from train.train_kermt_cluster import _as_2d, _checkpoint_provenance, _label_lookup, _stack

ModelFactory = Callable[..., Any]


def _default_factory(
    cluster_data: ClusterData,
    checkpoint: Path,
    seed: int,
    kermt_config: KermtConfig | None,
    loss_mode: str,
    min_per_task: int,
    hyperparameter_source: str,
    gradnorm_alpha: float | None,
    gradnorm_lr: float | None,
) -> KermtMixedModel:
    return KermtMixedModel(
        {k: cluster_data.task_types[k] for k in cluster_data.endpoint_keys},
        checkpoint,
        loss_mode=loss_mode,
        min_per_task=min_per_task,
        hyperparameter_source=hyperparameter_source,
        gradnorm_alpha=gradnorm_alpha,
        gradnorm_lr=gradnorm_lr,
        seed=seed,
        config=kermt_config or KermtConfig(),
    )


def train_one_seed_mixed(
    cluster_data: ClusterData,
    config: ExperimentConfig,
    seed: int,
    *,
    checkpoint: Path,
    loss_mode: str,
    min_per_task: int,
    hyperparameter_source: str,
    gradnorm_alpha: float | None = None,
    gradnorm_lr: float | None = None,
    kermt_config: KermtConfig | None = None,
    runs_dir: Path | str | None = None,
    repo_root: Path | str | None = None,
    use_wandb: bool = False,
    holdout_calibration: bool = True,
    calibrate: bool = True,
    model_factory: ModelFactory | None = None,
) -> ClusterSeedResult:
    """Fine-tune one mixed cluster for one seed under one weighting arm.

    ``config.endpoint`` is the cluster key (``"metabolism"``,
    ``"absorption_distribution"``) and ``config.model_family`` must be
    ``"kermt_mixed"``. ``config.variant`` is set to ``loss_mode`` so the three
    arms of one cluster never share a run name.

    ``loss_mode``, ``min_per_task`` and ``hyperparameter_source`` have no defaults:
    the arm is the experimental factor, and the other values are decided by a
    pre-registered tuning protocol (``train.kermt_mixed.tuning``) or are explicitly
    the stock/parity values. For a tuning trial pass ``calibrate=False``: the test
    split is then never read (``calibrate_endpoints`` is its only consumer here).
    """
    if config.model_family != "kermt_mixed":
        raise ValueError(
            f"config.model_family={config.model_family!r}; the mixed trainer runs only "
            "as 'kermt_mixed' so its results cannot be filed under a Tier-0 family"
        )
    if loss_mode not in MODES:
        raise ValueError(f"loss_mode must be one of {MODES}, got {loss_mode!r}")
    if calibrate and not holdout_calibration:
        raise ValueError(
            "calibrate=True requires holdout_calibration=True: otherwise the "
            "temperature scaler would be fit on molecules the model trained on "
            "or was selected against."
        )
    types = set(cluster_data.task_types.values())
    if len(cluster_data.endpoint_keys) < 2:
        raise ValueError("a mixed run needs a multi-endpoint cluster")
    if len(types) < 2 and loss_mode in ("kendall", "gradnorm"):
        warnings.warn(
            "pure-type cluster under a learned weighting: this is the G3/ablation "
            "configuration, not a mixed result",
            UserWarning,
            stacklevel=2,
        )

    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[2]
    repo_root = Path(repo_root)
    set_global_seed(seed)

    keys = list(cluster_data.endpoint_keys)
    pool, labels_held_out = cluster_data.train_pool(holdout_calibration=holdout_calibration)

    pool_smiles = pool[SMILES_COL].tolist()
    _, train_smiles, val_smiles = five_seed_train_val_folds(pool_smiles, seeds=(seed,))[0]
    lookup = _label_lookup(pool)
    y_train = _stack(train_smiles, lookup)
    y_val = _stack(val_smiles, lookup)

    seed_config = replace(config, seed=seed, variant=loss_mode)
    tracking_config = seed_config.to_tracking_config()
    tracking_config["cluster_split_report"] = cluster_data.split_report.to_dict()
    tracking_config["loss_weighting"] = loss_mode
    tracking_config["min_per_task"] = min_per_task
    tracking_config["gradnorm"] = (
        {"alpha": gradnorm_alpha, "lr": gradnorm_lr} if loss_mode == "gradnorm" else None
    )
    tracking_config["hyperparameter_source"] = hyperparameter_source
    tracking_config["holdout_calibration"] = holdout_calibration
    tracking_config["labels_held_out_for_calibration"] = labels_held_out
    tracking_config["calibrate"] = calibrate
    tracking_config["task_types"] = {k: cluster_data.task_types[k].value for k in keys}
    provenance: dict[str, Any] = {
        "prep_id": config.prep_id,
        "model_id": None,
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
            "variant": loss_mode,
            "seed": seed,
            "prep_id": config.prep_id,
            "cluster": config.endpoint,
            "n_targets": len(keys),
        }
    )

    wandb_logger = None
    if use_wandb:
        try:
            from tracking.wandb_logger import WandbLogger

            wandb_logger = WandbLogger(
                run_id=run.run_id, config=tracking_config, provenance=run.provenance
            )
        except Exception as exc:
            warnings.warn(f"W&B logging disabled for run {run.run_id}: {exc}", UserWarning, stacklevel=2)
            wandb_logger = None

    factory = model_factory or _default_factory
    model = factory(
        cluster_data, checkpoint, seed, kermt_config, loss_mode, min_per_task,
        hyperparameter_source, gradnorm_alpha, gradnorm_lr,
    )
    provenance["model_id"] = model.model_id

    work_dir = run.artifact_path("kermt")
    model.fit(train_smiles, y_train, X_val=val_smiles, y_val=y_val, run_dir=work_dir)

    preds = _as_2d(model.predict(val_smiles, run_dir=work_dir))
    per_endpoint_metrics = decompose_cluster_predictions(y_val, preds, keys, cluster_data.task_types)
    for key, metrics in per_endpoint_metrics.items():
        row: dict[str, Any] = {
            "split": "val",
            "seed": seed,
            "endpoint": key,
            "cluster": config.endpoint,
            "variant": loss_mode,
        }
        for attr in metrics.__dataclass_fields__:
            row[attr] = getattr(metrics, attr)
        run.log_metrics(row)
        if wandb_logger is not None:
            wandb_logger.log({f"{key}/{k}": v for k, v in row.items()})

    calibration_records: dict[str, dict] | None = None
    if calibrate:
        cal_smiles = cluster_data.smiles("calibration")
        test_smiles = cluster_data.smiles("test")
        cal_labels = cluster_data.calibration[keys].to_numpy(dtype=float)
        test_labels = cluster_data.test[keys].to_numpy(dtype=float)
        # One inference pass each; classification columns come back as logits,
        # regression columns as raw values (the calibrate_endpoints convention).
        cal_scores = _as_2d(model.predict_logits(cal_smiles, run_dir=work_dir))
        test_scores = _as_2d(model.predict_logits(test_smiles, run_dir=work_dir))
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
        for record in calibration_records.values():
            run.log_metrics({"split": "calibration+test", "cluster": config.endpoint, **record})

    model_path = run.artifact_path("model") / "kermt_mixed"
    model.save(model_path)

    log_sigma: dict[str, float] | None = None
    summary = getattr(model, "fit_summary", None) or {}
    if summary.get("log_sigma_final"):
        log_sigma = {k: float(v) for k, v in summary["log_sigma_final"].items()}
    run.log_metrics(
        {
            "split": "fit_summary",
            "variant": loss_mode,
            "best_epoch": summary.get("best_epoch"),
            "best_selection_loss": summary.get("best_selection_loss"),
            "log_sigma_final": log_sigma,
        }
    )
    (run.artifact_path("model") / "fit_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    run.finish("completed")

    wandb_url: str | None = None
    if wandb_logger is not None:
        wandb_url = getattr(wandb_logger._run, "url", None)
        wandb_logger.finish()

    return ClusterSeedResult(
        seed=seed,
        run_id=run.run_id,
        model_path=model_path,
        cluster_key=config.endpoint,
        endpoint_keys=keys,
        per_endpoint_metrics=per_endpoint_metrics,
        n_train=len(train_smiles),
        n_val=len(val_smiles),
        per_endpoint_n_labeled={
            key: int(np.sum(~np.isnan(y_train[:, i]))) for i, key in enumerate(keys)
        },
        log_sigma_final=log_sigma,
        wandb_url=wandb_url,
        calibration=calibration_records,
        labels_held_out_for_calibration=labels_held_out,
    )


def train_mixed_all_seeds(
    cluster_data: ClusterData,
    config: ExperimentConfig,
    *,
    checkpoint: Path,
    loss_mode: str,
    min_per_task: int,
    hyperparameter_source: str,
    **kwargs: Any,
) -> list[ClusterSeedResult]:
    """All ``FIXED_SEEDS`` for one cluster under one arm; one result per seed."""
    return [
        train_one_seed_mixed(
            cluster_data, config, seed, checkpoint=checkpoint, loss_mode=loss_mode,
            min_per_task=min_per_task, hyperparameter_source=hyperparameter_source, **kwargs
        )
        for seed in FIXED_SEEDS
    ]


__all__ = ["train_mixed_all_seeds", "train_one_seed_mixed"]
