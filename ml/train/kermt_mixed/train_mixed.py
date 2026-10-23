"""
In-container entry point for the Tier-1 mixed-type trainer.

Run (by ``models.kermt_mixed_model.KermtMixedModel``, never by hand)::

    PYTHONPATH=/data/_mars_trainer:$PYTHONPATH \\
      python -m kermt_mixed.train_mixed --mode fit \\
        --run-json /runs/run.json --spec /data/_mars_trainer/spec.json

``run.json`` is the manifest that KERMT's own ``agent/scripts/run_finetune_local.py
--dry-run`` writes. Its ``argv`` is the exact ``main.py finetune`` command stock
KERMT would have run. This module parses *that* argv with KERMT's own
``parse_args()``, so every hyperparameter, architecture field, data path and
default is derived the way stock derives it (gate G2's "same argv-derived args").
The only things this module changes are the loss, the batch composition, the
target scaling and the epoch-selection rule; each is documented where it happens.

Provenance of the KERMT calls below: ``task/train.py``, ``task/predict.py``,
``task/cross_validate.py``, ``main.py`` and ``kermt/util/utils.py`` at tag
``v2.0.0`` (commit ``e402473``), read verbatim 2026-10-14. Anything that deviates
from them is marked ``DEVIATION``. The glue that could not be exercised on a laptop
(no KERMT, no GPU) is the part gates G1 and G2 exist to validate; it is kept
small and linear on purpose.

Importing this module imports neither torch nor kermt.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from . import TRAINER_VERSION
from .metrics_hooks import JsonlLogger
from .scaling import ColumnScaler, from_kermt_targets, to_kermt_targets

CLASSIFICATION = "classification"
REGRESSION = "regression"


# --------------------------------------------------------------------------- #
# Pure helpers (no torch / kermt) — unit-tested on the laptop.
# --------------------------------------------------------------------------- #


def load_spec(path: Path | str) -> dict[str, Any]:
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in ("target_names", "task_types"):
        if key not in spec:
            raise ValueError(f"spec is missing {key!r}")
    if len(spec["target_names"]) != len(spec["task_types"]):
        raise ValueError("spec target_names / task_types length mismatch")
    bad = set(spec["task_types"]) - {CLASSIFICATION, REGRESSION}
    if bad:
        raise ValueError(f"unknown task types in spec: {sorted(bad)}")
    return spec


def finetune_argv_tail(run_json: Path | str) -> list[str]:
    """``['finetune', '--data_path', ...]`` from a ``run_finetune_local --dry-run`` manifest.

    The manifest ``argv`` is ``[python, -u, main.py, "finetune", ...]``; KERMT's
    ``parse_args()`` reads ``sys.argv[1:]``, so the tail starting at the subcommand
    is what to install after a dummy program name.
    """
    manifest = json.loads(Path(run_json).read_text(encoding="utf-8"))
    argv = manifest.get("argv")
    if not argv or "finetune" not in argv:
        raise ValueError(f"{run_json} has no finetune argv (is it a finetune dry-run manifest?)")
    return [str(a) for a in argv[argv.index("finetune") :]]


def argv_value(argv: Sequence[str], flag: str, default: str | None = None) -> str | None:
    """Value following ``flag`` in an argv list, or ``default``."""
    for i, tok in enumerate(argv):
        if tok == flag and i + 1 < len(argv):
            return str(argv[i + 1])
    return default


def is_regression_flags(task_types: Sequence[str]) -> list[bool]:
    return [t == REGRESSION for t in task_types]


def is_classification_flags(task_types: Sequence[str]) -> list[bool]:
    return [t == CLASSIFICATION for t in task_types]


def write_predictions_csv(
    path: Path | str, smiles: Sequence[str], names: Sequence[str], values: np.ndarray
) -> Path:
    """``smiles,<name>...`` — the shape ``featurize.kermt_adapter.read_predictions_csv`` reads."""
    import csv

    vals = np.asarray(values, dtype=float)
    if vals.shape != (len(smiles), len(names)):
        raise ValueError(f"values {vals.shape} != ({len(smiles)}, {len(names)})")
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["smiles", *names])
        for s, row in zip(smiles, vals, strict=True):
            w.writerow([s, *[repr(float(v)) for v in row]])
    return p


class KermtScalerShim:
    """Duck-types ``kermt.data.StandardScaler`` for ``save_checkpoint``.

    ``save_checkpoint`` stores only ``scaler.means`` / ``scaler.stds``. Classification
    columns carry ``mean=0, std=1`` so a stock-style inverse transform is the
    identity on them.
    """

    def __init__(self, scaler: ColumnScaler) -> None:
        self.means = np.asarray(scaler.means, dtype=float)
        self.stds = np.asarray(scaler.stds, dtype=float)


# --------------------------------------------------------------------------- #
# fit
# --------------------------------------------------------------------------- #


def _setup_seed(seed: int) -> None:
    """``main.py::setup`` — frozen seeds + deterministic algorithms."""
    import torch

    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    np.random.seed(seed)
    random.seed(seed)
    torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms(mode=True)


def run_fit(run_json: Path, spec: dict[str, Any]) -> dict[str, Any]:
    import torch
    from kermt.data import MolCollator
    from kermt.data.torchvocab import MolVocab  # noqa: F401  (main.py imports it for side effects)
    from kermt.util.parsing import parse_args
    from kermt.util.utils import (
        build_lr_scheduler,
        build_optimizer,
        create_logger,
        get_data,
        get_task_names,
        load_checkpoint,
        makedirs,
        save_checkpoint,
    )
    from torch.utils.data import DataLoader

    from .losses import MixedLoss, MixedLossConfig
    from .sampler import batch_stats, stratified_batches
    from .trainer import TrainSettings, fit

    names: list[str] = list(spec["target_names"])
    cls_flags = is_classification_flags(spec["task_types"])
    reg_flags = is_regression_flags(spec["task_types"])
    # No defaults: every value below is supplied by the caller (a stock argv, or a
    # tuning trial recorded under ``hyperparameter_source``). A missing key is an error.
    mode = spec["loss"]["mode"]
    min_per_task = int(spec["min_per_task"])
    gn_cfg = spec.get("gradnorm") or {}
    hp_source = spec["hyperparameter_source"]
    val_views: dict[str, np.ndarray] = {}

    # ---- args exactly as stock derives them (main.py: parse_args) -------------
    sys.argv = ["main.py", *finetune_argv_tail(run_json)]
    args = parse_args()
    _setup_seed(args.seed)
    logger = create_logger(name="train", save_dir=args.save_dir, quiet=False)
    info = logger.info

    # ---- cross_validate.py, fold 0 --------------------------------------------
    init_seed = args.seed
    save_root = args.save_dir
    args.seed = init_seed + 0
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    np.random.seed(args.seed)
    random.seed(args.seed)
    args.save_dir = os.path.join(save_root, "fold_0")
    makedirs(args.save_dir)
    save_dir = os.path.join(args.save_dir, "model_0")
    makedirs(save_dir)

    # ---- load_data (user_provided branch only) --------------------------------
    if not (args.separate_val_path and args.separate_test_path):
        raise RuntimeError(
            "mixed trainer expects prepare_data's user_provided split "
            "(--separate_val_path and --separate_test_path)"
        )
    args.task_names = get_task_names(args.data_path)
    if list(args.task_names) != names:
        raise RuntimeError(f"CSV targets {args.task_names} != spec targets {names}")
    train_data = get_data(path=args.data_path, args=args, logger=logger)
    args.features_dim = (
        len(train_data.data[0].features) if train_data.data[0].features is not None else 0
    )
    args.num_tasks = train_data.num_tasks()
    args.features_size = train_data.features_size()
    val_data = get_data(
        path=args.separate_val_path,
        args=args,
        features_path=args.separate_val_features_path,
        logger=logger,
    )
    if args.features_scaling:
        features_scaler = train_data.normalize_features(replace_nan_token=0)
        val_data.normalize_features(features_scaler)
    else:
        features_scaler = None
    args.train_data_size = len(train_data)
    info(f"train size = {len(train_data):,} | val size = {len(val_data):,} | tasks = {args.num_tasks}")

    # ---- DEVIATION: per-column scaling (regression columns only) --------------
    y_train = from_kermt_targets(train_data.targets())
    scaler = ColumnScaler.fit(y_train, names, reg_flags)
    y_train_scaled = scaler.transform(y_train)
    train_data.set_targets(to_kermt_targets(y_train_scaled))
    val_data.set_targets(
        to_kermt_targets(scaler.transform(from_kermt_targets(val_data.targets())))
    )
    label_mask = ~np.isnan(y_train_scaled)
    kscaler = KermtScalerShim(scaler)

    # ---- model / optimizer / scheduler as run_training builds them ------------
    if args.num_tasks > 1 and args.ffn_num_task_specific_layers <= 0:
        raise RuntimeError(
            "mixed trainer requires --ffn_num_task_specific_layers > 0 for more than "
            "one column: without per-task heads a regression and a classification "
            "column share one output layer and GradNorm has no shared layer"
        )
    if args.checkpoint_paths is None:
        raise RuntimeError("mixed trainer fine-tunes from a pretrain checkpoint (--checkpoint_path)")
    model, _ = load_checkpoint(args.checkpoint_paths[0], current_args=args, logger=logger)
    loss_cfg = MixedLossConfig(mode=mode, dist_coff=float(args.dist_coff))
    loss_module = MixedLoss(cls_flags, loss_cfg)
    if args.cuda:
        model = model.cuda()
        loss_module = loss_module.cuda()
    optimizer = build_optimizer(model, args)
    if loss_module.log_sigma is not None:
        # Same placement KERMT uses for its MTLLoss: task-head learning rate.
        optimizer.param_groups[1]["params"].append(loss_module.log_sigma)
    save_checkpoint(os.path.join(save_dir, "model.pt"), model, kscaler, features_scaler, args)
    scheduler = build_lr_scheduler(optimizer, args)

    # ---- batches --------------------------------------------------------------
    collator = MolCollator(shared_dict={}, args=args)
    val_collator = MolCollator(shared_dict={}, args=args)
    stats_log: list[dict[str, Any]] = []

    def train_batches(epoch: int):
        batches = stratified_batches(
            label_mask,
            args.batch_size,
            min_per_task=min_per_task,
            seed=args.seed,
            epoch=epoch,
        )
        if epoch == 0:
            stats_log.append(batch_stats(batches, label_mask))
        loader = DataLoader(
            train_data, batch_sampler=batches, num_workers=0, collate_fn=collator
        )
        for item in loader:
            _, batch, features_batch, mask, targets = item
            yield batch, features_batch, mask, targets

    def val_batches():
        # Stock's predict() sets this on the shared args before it collates; the
        # train collator reads the same attribute. Reproduced for parity (G2/G3).
        args.bond_drop_rate = 0
        loader = DataLoader(
            val_data,
            batch_size=args.batch_size,
            shuffle=False,
            num_workers=0,
            collate_fn=val_collator,
        )
        for item in loader:
            _, batch, features_batch, mask, targets = item
            yield batch, features_batch, mask, targets

    run_dir = Path(save_root).parent
    log_path = run_dir / "logs" / "mixed_epochs.jsonl"
    with JsonlLogger(log_path) as jl:
        jl.write(
            {
                "event": "start",
                "trainer_version": TRAINER_VERSION,
                "mode": mode,
                "min_per_task": min_per_task,
                "gradnorm": gn_cfg or None,
                "hyperparameter_source": hp_source,
                "targets": names,
                "task_types": spec["task_types"],
                "seed": args.seed,
                "epochs": args.epochs,
                "batch_size": args.batch_size,
                "dist_coff": float(args.dist_coff),
                # BEGIN effective-args logging (2026-10-22; logging only, strip-verified against the G3 bytes)
                # Values after load_checkpoint(current_args=args) overwrote them from the pretrain checkpoint
                # (decisions.md 2026-10-19 correction). Runs whose start event lacks this key predate it.
                "effective_checkpoint_args": {
                    "dist_coff": float(args.dist_coff),
                    "dropout": float(args.dropout),
                    "bond_drop_rate": float(args.bond_drop_rate),
                    "weight_decay": float(args.weight_decay),
                },
                # END effective-args logging
                "n_train": len(train_data),
                "n_val": len(val_data),
                "labeled_per_task": label_mask.sum(axis=0).tolist(),
                "scaler": scaler.to_dict(),
            }
        )

        def on_best(epoch: int, m: Any) -> None:
            save_checkpoint(os.path.join(save_dir, "model.pt"), m, kscaler, features_scaler, args)
            info(f"Saving model at epoch {epoch} (mixed selection loss improved)")

        result = fit(
            model,
            loss_module,
            optimizer,
            scheduler,
            train_batches,
            val_batches,
            TrainSettings(
                epochs=int(args.epochs),
                mode=mode,
                dist_coff=float(args.dist_coff),
                gradnorm_alpha=(float(gn_cfg["alpha"]) if "alpha" in gn_cfg else None),
                gradnorm_lr=(float(gn_cfg["lr"]) if "lr" in gn_cfg else None),
            ),
            cls_flags,
            on_best=on_best,
            log_fn=jl.write,
            on_val_views=lambda e, a, b: val_views.update(
                {f"atom_e{e:03d}": a.astype(np.float32), f"bond_e{e:03d}": b.astype(np.float32)}
            ),
        )
        # Every epoch's raw validation views, so any selection rule (a metric, a
        # different epoch count) can be evaluated afterwards without retraining.
        np.savez_compressed(run_dir / "logs" / "val_views.npz", **val_views)
        sigma = loss_module.log_sigma_report()
        summary = {
            "event": "summary",
            "trainer_version": TRAINER_VERSION,
            "best_epoch": result.best_epoch,
            "best_selection_loss": result.best_selection_loss,
            "log_sigma_final": (
                dict(zip(names, sigma.values(), strict=True)) if sigma is not None else None
            ),
            "batch_stats_epoch0": stats_log[0] if stats_log else None,
        }
        jl.write(summary)

    meta = {
        "trainer_version": TRAINER_VERSION,
        "target_names": names,
        "task_types": list(spec["task_types"]),
        "scaler": scaler.to_dict(),
        "loss": {"mode": mode, "dist_coff": float(args.dist_coff)},
        "min_per_task": min_per_task,
        "gradnorm": gn_cfg or None,
        "hyperparameter_source": hp_source,
        "selection": "sum_t mean validation loss on scaled targets, fixed_task weighting",
        "best_epoch": result.best_epoch,
        "bond_drop_rate_note": (
            "args.bond_drop_rate is set to 0 by the first validation pass, as in "
            "stock task.predict.predict; reproduced for parity"
        ),
    }
    (Path(save_dir) / "mixed_meta.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


# --------------------------------------------------------------------------- #
# predict
# --------------------------------------------------------------------------- #


def run_predict(
    run_json: Path,
    checkpoint: Path,
    out_dir: Path,
    spec: dict[str, Any],
) -> Path:
    """Write ``<out_dir>/predictions.csv`` (probabilities / raw units) and
    ``views.csv`` (the two heads' raw outputs, for calibration research)."""
    import torch
    from kermt.data import MolCollator
    from kermt.util.utils import get_data, load_checkpoint
    from torch.utils.data import DataLoader

    from .forward import combine_views, mixed_forward

    names: list[str] = list(spec["target_names"])
    cls_flags = is_classification_flags(spec["task_types"])

    manifest = json.loads(Path(run_json).read_text(encoding="utf-8"))
    argv = [str(a) for a in manifest["argv"]]
    data_path = argv_value(argv, "--data_path")
    features_path = argv_value(argv, "--features_path")
    batch_size = int(argv_value(argv, "--batch_size", "32") or 32)
    if data_path is None:
        raise ValueError("inference manifest argv has no --data_path")

    state = torch.load(str(checkpoint), map_location="cpu", weights_only=False)
    scaler_state = state.get("data_scaler")
    reg_flags = is_regression_flags(spec["task_types"])
    if scaler_state is None:
        # A stock classification checkpoint (KERMT stores no scaler when
        # dataset_type == 'classification'). Valid for gate G1 on a Tier-0 model;
        # not valid if any requested column is a regression column.
        if any(reg_flags):
            raise RuntimeError(
                f"{checkpoint} has no data_scaler but the spec has regression columns; "
                "not a mixed-trainer checkpoint"
            )
        scaler = ColumnScaler(
            names=tuple(names),
            is_regression=tuple(reg_flags),
            means=tuple(0.0 for _ in names),
            stds=tuple(1.0 for _ in names),
        )
    else:
        scaler = ColumnScaler(
            names=tuple(names),
            is_regression=tuple(reg_flags),
            means=tuple(float(m) for m in scaler_state["means"]),
            stds=tuple(float(s) for s in scaler_state["stds"]),
        )

    train_args = state["args"]
    train_args.features_path = [features_path] if features_path else None
    train_args.max_data_size = None
    train_args.use_compound_names = False
    train_args.bond_drop_rate = 0
    train_args.batch_size = batch_size
    cuda = bool(getattr(train_args, "cuda", False)) and torch.cuda.is_available()
    train_args.cuda = cuda

    model, _ = load_checkpoint(str(checkpoint), cuda=cuda, current_args=None)
    model.eval()
    data = get_data(path=data_path, skip_invalid_smiles=False, args=train_args)
    if getattr(train_args, "features_scaling", False) and state.get("features_scaler") is not None:
        from kermt.data import StandardScaler

        fs = state["features_scaler"]
        data.normalize_features(
            StandardScaler(fs["means"], fs["stds"], replace_nan_token=0)
        )

    collator = MolCollator(shared_dict={}, args=train_args)
    loader = DataLoader(
        data, batch_size=batch_size, shuffle=False, num_workers=0, collate_fn=collator
    )
    probs: list[np.ndarray] = []
    raw_atom: list[np.ndarray] = []
    raw_bond: list[np.ndarray] = []
    with torch.no_grad():
        for item in loader:
            _, batch, features_batch, _mask, _targets = item
            atom, bond = mixed_forward(model, batch, features_batch)
            comb = combine_views(atom, bond, cls_flags)
            probs.append(comb.cpu().numpy())
            raw_atom.append(atom.cpu().numpy())
            raw_bond.append(bond.cpu().numpy())

    comb_all = np.concatenate(probs, axis=0)
    # Regression columns come back in scaled units; classification columns are
    # probabilities and have mean 0 / std 1, so the inverse is the identity there.
    served = scaler.inverse_transform(comb_all)
    smiles = data.smiles()
    out = Path(out_dir)
    pred_path = write_predictions_csv(out / "predictions.csv", smiles, names, served)
    views = np.concatenate(
        [np.concatenate(raw_atom, axis=0), np.concatenate(raw_bond, axis=0)], axis=1
    )
    write_predictions_csv(
        out / "views.csv",
        smiles,
        [f"{n}__atom" for n in names] + [f"{n}__bond" for n in names],
        views,
    )
    return pred_path


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="MARS Tier-1 mixed-type KERMT trainer (in-container)")
    p.add_argument("--mode", choices=["fit", "predict"], required=True)
    p.add_argument("--run-json", required=True)
    p.add_argument("--spec", required=True)
    p.add_argument("--checkpoint", help="predict: finetuned mixed checkpoint (model.pt)")
    p.add_argument("--out", help="predict: output directory")
    ns = p.parse_args(argv)

    spec = load_spec(ns.spec)
    try:
        if ns.mode == "fit":
            summary = run_fit(Path(ns.run_json), spec)
            print(json.dumps({"ok": True, "summary": summary}, indent=2, default=str))
        else:
            if not ns.checkpoint or not ns.out:
                raise ValueError("--mode predict needs --checkpoint and --out")
            path = run_predict(Path(ns.run_json), Path(ns.checkpoint), Path(ns.out), spec)
            print(json.dumps({"ok": True, "predictions": str(path)}, indent=2))
    except Exception as exc:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        print(json.dumps({"ok": False, "errors": [f"{type(exc).__name__}: {exc}"]}, indent=2))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
