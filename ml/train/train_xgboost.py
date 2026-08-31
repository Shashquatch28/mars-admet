"""
Seed-aware XGBoost training loop for one MARS endpoint.

One call to train_one_seed() produces one experiment run (one seed, one endpoint).
train_xgboost_all_seeds() loops over all 5 seeds and returns a list of results.

The test set inside EndpointData is NEVER touched here.  Calibration split
molecules are present in train_val (by design) and will appear in either the
train or val fold — this is correct; they are used only for Platt calibration
in Run 2a, not for model selection.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from configs.experiment_config import FIXED_SEEDS, ExperimentConfig
from data.loaders import EndpointData
from data.split import five_seed_train_val_folds
from eval.metrics import aggregate_seed_metrics, compute_metrics
from featurize.cache import FeatureCache
from models.xgboost_model import XGBoostConfig, XGBoostModel
from tracking.experiment import ExperimentRun
from utils.seed import set_global_seed


@dataclass
class SeedResult:
    seed: int
    val_metrics: Any  # ClassificationMetrics | RegressionMetrics
    model_path: Path
    run_id: str
    n_train: int
    n_val: int
    n_dropped_train: int
    n_dropped_val: int
    best_iteration: int | None


def train_one_seed(
    endpoint_data: EndpointData,
    config: ExperimentConfig,
    cache: FeatureCache,
    seed: int,
    *,
    runs_dir: Path | str | None = None,
    repo_root: Path | str | None = None,
) -> SeedResult:
    """Train XGBoost for one seed; log to ExperimentRun; return SeedResult.

    Parameters
    ----------
    endpoint_data:
        Loaded M1 splits from load_endpoint(). Test set is NOT used.
    config:
        ExperimentConfig with model_family="xgboost" and correct endpoint/prep_id.
    cache:
        FeatureCache instance pointing to the on-disk cache root.
    seed:
        Integer seed for this run (typically from FIXED_SEEDS).
    runs_dir:
        Override for the ExperimentRun runs directory (default: ml/runs/).
    repo_root:
        Override for the repo root (default: two dirs up from this file).
    """
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[2]
    repo_root = Path(repo_root)

    set_global_seed(seed)

    # Build one specific fold for this seed by calling five_seed_train_val_folds
    # and extracting the matching seed entry.
    tv_smiles = endpoint_data.train_val["standardized_smiles"].tolist()
    smiles_to_label: dict[str, float] = dict(
        zip(
            endpoint_data.train_val["standardized_smiles"],
            endpoint_data.train_val["label"].astype(float),
            strict=False,
        )
    )

    folds = five_seed_train_val_folds(tv_smiles, seeds=(seed,))
    _, train_smiles, val_smiles = folds[0]

    y_train = np.array([smiles_to_label[s] for s in train_smiles])
    y_val = np.array([smiles_to_label[s] for s in val_smiles])

    # Override the config seed field with the current seed so the run name is correct.
    from dataclasses import replace as _replace

    seed_config = _replace(config, seed=seed)
    run_name = seed_config.run_name()
    tracking_config = seed_config.to_tracking_config()

    xgb_config = XGBoostConfig(
        hyperparams=config.hyperparams,
    )
    model = XGBoostModel(
        task_type=endpoint_data.task_type,
        cache=cache,
        seed=seed,
        xgb_config=xgb_config,
    )

    run = ExperimentRun(
        name=run_name,
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
        }
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        model.fit(train_smiles, y_train, X_val=val_smiles, y_val=y_val)

    n_dropped_train = sum(
        1
        for w in caught
        if "training SMILES dropped" in str(w.message)
    )
    n_dropped_val = sum(
        1
        for w in caught
        if "validation SMILES dropped" in str(w.message)
    )

    preds = model.predict(val_smiles)
    valid_mask = ~np.isnan(preds)
    y_val_valid = y_val[valid_mask]
    preds_valid = preds[valid_mask]

    val_metrics = compute_metrics(y_val_valid, preds_valid, endpoint_data.task_type)

    metrics_dict: dict[str, Any] = {"split": "val", "seed": seed}
    for attr in val_metrics.__dataclass_fields__:
        metrics_dict[attr] = getattr(val_metrics, attr)
    run.log_metrics(metrics_dict)

    model_path = run.artifact_path("model") / "xgboost"
    model.save(model_path)

    best_iter: int | None = None
    try:
        best_iter = int(model._model.best_iteration)
    except (AttributeError, TypeError):
        pass

    run.finish("completed")

    return SeedResult(
        seed=seed,
        val_metrics=val_metrics,
        model_path=model_path,
        run_id=run.run_id,
        n_train=len(train_smiles),
        n_val=len(val_smiles),
        n_dropped_train=n_dropped_train,
        n_dropped_val=n_dropped_val,
        best_iteration=best_iter,
    )


def train_xgboost_all_seeds(
    endpoint_data: EndpointData,
    config: ExperimentConfig,
    cache: FeatureCache,
    *,
    runs_dir: Path | str | None = None,
    repo_root: Path | str | None = None,
) -> list[SeedResult]:
    """Train XGBoost for all FIXED_SEEDS; return one SeedResult per seed."""
    results: list[SeedResult] = []
    for seed in FIXED_SEEDS:
        result = train_one_seed(
            endpoint_data,
            config,
            cache,
            seed,
            runs_dir=runs_dir,
            repo_root=repo_root,
        )
        results.append(result)
    return results


def aggregate_results(results: list[SeedResult]) -> dict[str, Any]:
    """Compute mean ± std over 5-seed val metrics."""
    per_seed = [r.val_metrics for r in results]
    return aggregate_seed_metrics(per_seed)
