"""
Tier 2 (path c) — ordinal-CDF homogenization of a mixed cluster, trained by the
UNMODIFIED stock KERMT CLI.

Each regression endpoint of a mixed cluster is re-encoded as ``M`` binary columns
``<endpoint>__gt<m>`` ("is y above threshold m?"), so the whole cluster becomes one
all-classification run that ``KermtModel`` already knows how to train. Regression
values are then decoded from the predicted survival function (running-minimum
monotonicity, ``featurize.ordinal.decode``).

Status and scheduling (maintainer, 2026-10-14): **not deferred, and not scheduled
either.** Whether Tier 2 is trained depends on the GPU-time budget left at the end of
Tier 1. This module exists so that decision is only about hours, not about writing
code under time pressure. It does not change the default order of work.

What this module does and does not establish
--------------------------------------------
* ``n_bins`` has no default. The zero-GPU discretization ceiling
  (``featurize.ordinal.discretization_ceiling_mae``, run by
  ``train/preflight_clusters.py``) is a *necessary* condition — it bounds what no
  model can beat — but it does not say 16 bins trains better than 8 or 32. It is a
  tuning-protocol axis (``train.kermt_mixed.tuning`` accepts it via a Protocol whose
  reference states the value), and the source of the value is recorded.
* Thresholds and bin representatives are fit on the **train fold only**, per seed.
* The decoded value is not calibrated and is not an interval. Classification
  columns pass through the same ``logit(clip(p))`` score definition as Tier 0, so
  their calibration is directly comparable.
* The Tier-2 gate (:func:`t2_decoded_mae_gate`) compares validation-fold MAE of the
  decoded value against a *direct* regression MAE for the same endpoint and seed.
  Which direct baseline that is (Tier-0 subgroup model, or a single-task KERMT
  regression that does not exist yet for the A&D endpoints) and how the pairs are
  aggregated are explicit arguments, not defaults.

GPU-dependent exactly where ``KermtModel`` is.
"""

from __future__ import annotations

import json
import warnings
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
from configs.experiment_config import FIXED_SEEDS, ExperimentConfig
from data.cluster_loaders import SMILES_COL, ClusterData
from data.split import five_seed_train_val_folds
from eval.cluster_calibration import calibrate_endpoints, save_calibration_outcomes
from eval.cluster_eval import ClusterSeedResult, decompose_cluster_predictions
from featurize.ordinal import (
    OrdinalCdfCodec,
    decode,
    discretization_ceiling_mae,
    encode,
    fit_ordinal_codec,
)
from mars_contracts.endpoints import TaskType
from models.kermt_model import KermtConfig, KermtModel
from tracking.experiment import ExperimentRun
from utils.seed import set_global_seed

from train.kermt_mixed.common import probability_to_logit
from train.train_kermt_cluster import _checkpoint_provenance, _label_lookup, _stack

ModelFactory = Callable[..., Any]


# ---- encoding ----------------------------------------------------------------


def fit_codecs(
    y_train: np.ndarray,
    keys: Sequence[str],
    task_types: Mapping[str, TaskType],
    *,
    n_bins: int,
    strategy: str,
) -> dict[str, OrdinalCdfCodec]:
    """One codec per regression endpoint, fit on train-fold labels only."""
    y = np.asarray(y_train, dtype=float)
    out: dict[str, OrdinalCdfCodec] = {}
    for j, key in enumerate(keys):
        if task_types[key] is TaskType.REGRESSION:
            out[key] = fit_ordinal_codec(y[:, j], n_bins=n_bins, strategy=strategy)  # type: ignore[arg-type]
    return out


@dataclass(frozen=True)
class WideLayout:
    """Where each endpoint lives in the wide binary matrix."""

    keys: tuple[str, ...]
    names: tuple[str, ...]
    slices: Mapping[str, slice]

    @property
    def n_columns(self) -> int:
        return len(self.names)


def wide_layout(
    keys: Sequence[str],
    task_types: Mapping[str, TaskType],
    codecs: Mapping[str, OrdinalCdfCodec],
) -> WideLayout:
    names: list[str] = []
    slices: dict[str, slice] = {}
    for key in keys:
        start = len(names)
        if task_types[key] is TaskType.REGRESSION:
            names.extend(codecs[key].column_names(key))
        else:
            names.append(key)
        slices[key] = slice(start, len(names))
    return WideLayout(tuple(keys), tuple(names), slices)


def encode_wide(
    y: np.ndarray,
    layout: WideLayout,
    task_types: Mapping[str, TaskType],
    codecs: Mapping[str, OrdinalCdfCodec],
) -> np.ndarray:
    y = np.asarray(y, dtype=float)
    out = np.full((y.shape[0], layout.n_columns), np.nan)
    for j, key in enumerate(layout.keys):
        sl = layout.slices[key]
        if task_types[key] is TaskType.REGRESSION:
            out[:, sl] = encode(codecs[key], y[:, j])
        else:
            out[:, sl] = y[:, [j]]
    return out


def decode_wide(
    p: np.ndarray,
    layout: WideLayout,
    task_types: Mapping[str, TaskType],
    codecs: Mapping[str, OrdinalCdfCodec],
) -> np.ndarray:
    """``(n, K)`` wide probabilities -> ``(n, T)``: probability or decoded scalar."""
    p = np.asarray(p, dtype=float)
    out = np.empty((p.shape[0], len(layout.keys)))
    for j, key in enumerate(layout.keys):
        sl = layout.slices[key]
        if task_types[key] is TaskType.REGRESSION:
            out[:, j] = decode(codecs[key], p[:, sl])
        else:
            out[:, j] = p[:, sl][:, 0]
    return out


def scores_for_calibration(
    p: np.ndarray,
    decoded: np.ndarray,
    layout: WideLayout,
    task_types: Mapping[str, TaskType],
) -> np.ndarray:
    """``cluster_calibration`` convention: classification logits, regression raw."""
    out = decoded.copy()
    for j, key in enumerate(layout.keys):
        if task_types[key] is TaskType.CLASSIFICATION:
            out[:, j] = probability_to_logit(p[:, layout.slices[key]][:, 0])
    return out


# ---- the run -----------------------------------------------------------------


def _default_factory(
    wide_names: Sequence[str], checkpoint: Path, seed: int, kermt_config: KermtConfig | None
) -> KermtModel:
    return KermtModel(
        TaskType.CLASSIFICATION,
        checkpoint,
        list(wide_names),
        seed=seed,
        config=kermt_config or KermtConfig(),
    )


def train_one_seed_ordinal(
    cluster_data: ClusterData,
    config: ExperimentConfig,
    seed: int,
    *,
    checkpoint: Path,
    n_bins: int,
    strategy: str,
    hyperparameter_source: str,
    kermt_config: KermtConfig | None = None,
    runs_dir: Path | str | None = None,
    repo_root: Path | str | None = None,
    use_wandb: bool = False,
    holdout_calibration: bool = True,
    calibrate: bool = True,
    model_factory: ModelFactory | None = None,
) -> ClusterSeedResult:
    """Train one mixed cluster as an all-classification ordinal run for one seed."""
    if config.model_family != "kermt_ordinal":
        raise ValueError(
            f"config.model_family={config.model_family!r}; Tier 2 runs only as "
            "'kermt_ordinal' so it can never be filed under another tier"
        )
    if calibrate and not holdout_calibration:
        raise ValueError("calibrate=True requires holdout_calibration=True")
    if not hyperparameter_source:
        raise ValueError("hyperparameter_source must name where n_bins/strategy came from")
    keys = list(cluster_data.endpoint_keys)
    types = cluster_data.task_types
    if not any(types[k] is TaskType.REGRESSION for k in keys):
        raise ValueError("no regression endpoint: nothing to homogenize (use Tier 0)")

    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[2]
    repo_root = Path(repo_root)
    set_global_seed(seed)

    pool, labels_held_out = cluster_data.train_pool(holdout_calibration=holdout_calibration)
    pool_smiles = pool[SMILES_COL].tolist()
    _, train_smiles, val_smiles = five_seed_train_val_folds(pool_smiles, seeds=(seed,))[0]
    lookup = _label_lookup(pool)
    y_train, y_val = _stack(train_smiles, lookup), _stack(val_smiles, lookup)

    codecs = fit_codecs(y_train, keys, types, n_bins=n_bins, strategy=strategy)
    layout = wide_layout(keys, types, codecs)
    ceilings = {
        k: discretization_ceiling_mae(codecs[k], y_train[:, keys.index(k)]) for k in codecs
    }

    seed_config = replace(config, seed=seed, variant=f"bins{n_bins}")
    tracking_config = seed_config.to_tracking_config()
    tracking_config.update(
        {
            "cluster_split_report": cluster_data.split_report.to_dict(),
            "n_bins": n_bins,
            "strategy": strategy,
            "hyperparameter_source": hyperparameter_source,
            "wide_columns": layout.n_columns,
            "discretization_ceiling_mae_train": ceilings,
            "holdout_calibration": holdout_calibration,
            "labels_held_out_for_calibration": labels_held_out,
            "calibrate": calibrate,
            "task_types": {k: types[k].value for k in keys},
            "loss_weighting": "equal",
        }
    )
    provenance: dict[str, Any] = {
        "prep_id": config.prep_id,
        "model_id": None,
        **_checkpoint_provenance(repo_root),
    }
    run = ExperimentRun(
        name=seed_config.run_name(), repo_root=repo_root, config=tracking_config, runs_dir=runs_dir
    )
    run.start(
        run_tags={
            "endpoint": config.endpoint,
            "model_family": config.model_family,
            "seed": seed,
            "prep_id": config.prep_id,
            "n_bins": n_bins,
            "n_targets": layout.n_columns,
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

    factory = model_factory or _default_factory
    model = factory(layout.names, checkpoint, seed, kermt_config)
    provenance["model_id"] = model.model_id

    codec_dir = run.artifact_path("ordinal")
    codec_dir.mkdir(parents=True, exist_ok=True)
    (codec_dir / "codecs.json").write_text(
        json.dumps({k: c.to_dict() for k, c in codecs.items()}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    work_dir = run.artifact_path("kermt")
    model.fit(
        train_smiles,
        encode_wide(y_train, layout, types, codecs),
        X_val=val_smiles,
        y_val=encode_wide(y_val, layout, types, codecs),
        run_dir=work_dir,
    )

    p_val = np.asarray(model.predict(val_smiles, run_dir=work_dir), dtype=float)
    decoded_val = decode_wide(p_val, layout, types, codecs)
    per_endpoint = decompose_cluster_predictions(y_val, decoded_val, keys, types)
    for key, m in per_endpoint.items():
        row: dict[str, Any] = {"split": "val", "seed": seed, "endpoint": key, "n_bins": n_bins}
        for attr in m.__dataclass_fields__:
            row[attr] = getattr(m, attr)
        run.log_metrics(row)
        if wandb_logger is not None:
            wandb_logger.log({f"{key}/{k}": v for k, v in row.items()})

    calibration_records: dict[str, dict] | None = None
    if calibrate:
        cal_smiles, test_smiles = cluster_data.smiles("calibration"), cluster_data.smiles("test")
        p_cal = np.asarray(model.predict(cal_smiles, run_dir=work_dir), dtype=float)
        p_test = np.asarray(model.predict(test_smiles, run_dir=work_dir), dtype=float)
        outcomes = calibrate_endpoints(
            endpoint_keys=keys,
            task_types=types,
            seed=seed,
            cal_scores=scores_for_calibration(
                p_cal, decode_wide(p_cal, layout, types, codecs), layout, types
            ),
            cal_labels=cluster_data.calibration[keys].to_numpy(dtype=float),
            test_scores=scores_for_calibration(
                p_test, decode_wide(p_test, layout, types, codecs), layout, types
            ),
            test_labels=cluster_data.test[keys].to_numpy(dtype=float),
            train_val_positive_rates=cluster_data.positive_rates("train_val"),
            provenance=provenance,
        )
        save_calibration_outcomes(outcomes, run.artifact_path("calibration"))
        calibration_records = {k: o.to_record() for k, o in outcomes.items()}
        for record in calibration_records.values():
            run.log_metrics({"split": "calibration+test", "cluster": config.endpoint, **record})

    model_path = run.artifact_path("model") / "kermt_ordinal"
    model.save(model_path)
    run.finish("completed")
    wandb_url = None
    if wandb_logger is not None:
        wandb_url = getattr(wandb_logger._run, "url", None)
        wandb_logger.finish()

    return ClusterSeedResult(
        seed=seed,
        run_id=run.run_id,
        model_path=model_path,
        cluster_key=config.endpoint,
        endpoint_keys=keys,
        per_endpoint_metrics=per_endpoint,
        n_train=len(train_smiles),
        n_val=len(val_smiles),
        per_endpoint_n_labeled={
            k: int(np.sum(~np.isnan(y_train[:, i]))) for i, k in enumerate(keys)
        },
        log_sigma_final=None,
        wandb_url=wandb_url,
        calibration=calibration_records,
        labels_held_out_for_calibration=labels_held_out,
    )


def train_ordinal_all_seeds(
    cluster_data: ClusterData,
    config: ExperimentConfig,
    *,
    checkpoint: Path,
    n_bins: int,
    strategy: str,
    hyperparameter_source: str,
    **kwargs: Any,
) -> list[ClusterSeedResult]:
    return [
        train_one_seed_ordinal(
            cluster_data, config, seed, checkpoint=checkpoint, n_bins=n_bins, strategy=strategy,
            hyperparameter_source=hyperparameter_source, **kwargs,
        )
        for seed in FIXED_SEEDS
    ]


# ---- the Tier-2 gate -----------------------------------------------------------


@dataclass
class T2GateResult:
    passed: bool
    summary: str
    ratios: dict[str, list[float]]


def t2_decoded_mae_gate(
    decoded_val_mae: Mapping[str, Sequence[float]],
    direct_val_mae: Mapping[str, Sequence[float]],
    *,
    rel_tol: float,
    aggregation: str,
) -> T2GateResult:
    """Validation-fold decoded MAE vs a direct regression MAE, per endpoint and seed.

    ``rel_tol`` (the frozen 2026-09-20 wording says 0.15) and ``aggregation``
    (``"all_pairs"``: every endpoint-seed pair within tolerance; ``"mean_per_endpoint"``:
    each endpoint's mean ratio within tolerance) are required arguments. The original
    text says "within 15% ... for the same endpoint and seed" without saying how pairs
    are aggregated; that is for the maintainer to fix, not for this function to assume.
    """
    if aggregation not in ("all_pairs", "mean_per_endpoint"):
        raise ValueError("aggregation must be 'all_pairs' or 'mean_per_endpoint'")
    if set(decoded_val_mae) != set(direct_val_mae):
        raise ValueError("decoded and direct results must cover the same endpoints")
    ratios: dict[str, list[float]] = {}
    for k in decoded_val_mae:
        d, b = np.asarray(decoded_val_mae[k], float), np.asarray(direct_val_mae[k], float)
        if d.shape != b.shape or d.size == 0:
            raise ValueError(f"{k}: need paired per-seed values of equal length")
        ratios[k] = [float(x) for x in d / b]
    if aggregation == "all_pairs":
        passed = all(r <= 1.0 + rel_tol for rs in ratios.values() for r in rs)
    else:
        passed = all(float(np.mean(rs)) <= 1.0 + rel_tol for rs in ratios.values())
    worst = max(max(rs) for rs in ratios.values())
    return T2GateResult(
        passed,
        f"worst decoded/direct MAE ratio {worst:.3f} (tolerance {1.0 + rel_tol:.3f}, "
        f"aggregation={aggregation})",
        ratios,
    )


__all__ = [
    "T2GateResult",
    "WideLayout",
    "decode_wide",
    "encode_wide",
    "fit_codecs",
    "scores_for_calibration",
    "t2_decoded_mae_gate",
    "train_one_seed_ordinal",
    "train_ordinal_all_seeds",
    "wide_layout",
]
