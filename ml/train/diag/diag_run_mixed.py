"""DIAGNOSTIC entry point (not a gate, not part of the G3 record): re-run the mixed trainer on one seed with a READ-ONLY per-epoch
hook that scores the hERG/AMES calibration holdouts, saves a checkpoint every epoch, and keeps an overwritten resume checkpoint.

It wraps the UNMODIFIED, gate-staged ``kermt_mixed`` package (``fit``, ``MixedLoss``, ``stratified_batches`` ...): nothing under
``train/kermt_mixed`` is changed. The setup below is a copy of ``train_mixed.run_fit`` lines 178-290 (same call order, same seeds) because the
model has to be reachable from a closure; the closure runs from ``fit``'s ``log_fn`` (called at the very end of each epoch).

The hook: eval mode, ``torch.no_grad``, its own DataLoader/collator, and ALL RNG states (torch CPU, torch CUDA, numpy global, python ``random``)
captured before and restored after, with an assertion that they are bitwise equal afterwards. The batch composition RNG is
``default_rng([seed, epoch])`` (stateless across epochs), so resuming needs no extra generator state.

Runs inside the KERMT container (see ``train/diag/diag_host.py``). Never reads the test split.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

DATA = Path("/data")
OUT = Path("/runs")


# ----------------------------------------------------------------------------- helpers
def rng_capture() -> dict:
    return {"torch": torch.get_rng_state(), "cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else [],
            "numpy": np.random.get_state(), "python": random.getstate()}


def rng_restore(s: dict) -> None:
    torch.set_rng_state(s["torch"])
    if s["cuda"]:
        torch.cuda.set_rng_state_all(s["cuda"])
    np.random.set_state(s["numpy"]); random.setstate(s["python"])


def rng_digest(s: dict) -> str:
    h = hashlib.sha256()
    h.update(s["torch"].numpy().tobytes())
    for c in s["cuda"]:
        h.update(c.numpy().tobytes())
    n = s["numpy"]; h.update(str(n[0]).encode()); h.update(n[1].tobytes()); h.update(str(n[2:]).encode())
    h.update(repr(s["python"]).encode())
    return h.hexdigest()


def model_digest(model) -> str:
    h = hashlib.sha256()
    for k, v in sorted(model.state_dict().items()):
        h.update(k.encode()); h.update(v.detach().cpu().numpy().tobytes())
    return h.hexdigest()


def auroc(y: np.ndarray, p: np.ndarray) -> float:
    """Tie-averaged rank AUROC over the labelled entries (NaN labels dropped)."""
    ok = ~np.isnan(y); y = y[ok]; p = p[ok]
    pos = y == 1; n1 = int(pos.sum()); n0 = int((~pos).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    order = np.argsort(p, kind="mergesort"); sp = p[order]
    _, start, cnt = np.unique(sp, return_index=True, return_counts=True)
    avg = start + (cnt + 1) / 2.0                       # 1-based average rank per tie group
    ranks = np.empty(len(p)); ranks[order] = np.repeat(avg, cnt)
    return float((ranks[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x.astype(np.float64)))


# ----------------------------------------------------------------------------- main
def run(opts) -> dict:
    from kermt.data import MolCollator
    from kermt.data.torchvocab import MolVocab  # noqa: F401
    from kermt.util.parsing import parse_args
    from kermt.util.utils import (build_lr_scheduler, build_optimizer, create_logger, get_data, get_task_names,
                                  load_checkpoint, makedirs, save_checkpoint)
    from kermt_mixed.forward import combine_views, mixed_forward
    from kermt_mixed.losses import MixedLoss, MixedLossConfig
    from kermt_mixed.sampler import stratified_batches
    from kermt_mixed.scaling import ColumnScaler, from_kermt_targets, to_kermt_targets
    from kermt_mixed.trainer import TrainSettings, fit
    from kermt_mixed.train_mixed import (KermtScalerShim, _setup_seed, finetune_argv_tail, is_classification_flags,
                                          is_regression_flags, load_spec)

    spec = load_spec(DATA / "spec.json")
    names = list(spec["target_names"]); cls_flags = is_classification_flags(spec["task_types"])
    reg_flags = is_regression_flags(spec["task_types"])
    mode = spec["loss"]["mode"]; min_per_task = int(spec["min_per_task"])
    assert mode == "fixed" and min_per_task == 0, (mode, min_per_task)

    tail = [t.replace("/runs/data/", "/data/data/") for t in finetune_argv_tail(DATA / "run.json")]
    if not torch.cuda.is_available() and "--gpu" in tail:      # CPU smoke tests only: KERMT's --gpu choices come from the visible devices
        i = tail.index("--gpu"); del tail[i : i + 2]
    sys.argv = ["main.py", *tail]
    args = parse_args()
    cli = {k: getattr(args, k) for k in ("dist_coff", "dropout", "bond_drop_rate", "weight_decay")}
    if opts.epochs:
        args.epochs = opts.epochs
    _setup_seed(args.seed)
    args.save_dir = str(OUT / "kermt_ckpt")
    logger = create_logger(name="diag", save_dir=args.save_dir, quiet=False)
    info = logger.info
    init_seed = args.seed
    args.seed = init_seed + 0
    torch.manual_seed(args.seed); torch.cuda.manual_seed_all(args.seed); np.random.seed(args.seed); random.seed(args.seed)
    makedirs(args.save_dir)

    args.task_names = get_task_names(args.data_path)
    assert list(args.task_names) == names
    train_data = get_data(path=args.data_path, args=args, logger=logger)
    args.features_dim = len(train_data.data[0].features) if train_data.data[0].features is not None else 0
    args.num_tasks = train_data.num_tasks(); args.features_size = train_data.features_size()
    val_data = get_data(path=args.separate_val_path, args=args, features_path=args.separate_val_features_path, logger=logger)
    if opts.subset_train:
        train_data = type(train_data)(train_data.data[: opts.subset_train])
        val_data = type(val_data)(val_data.data[: opts.subset_val])
    features_scaler = None
    args.train_data_size = len(train_data)

    y_train = from_kermt_targets(train_data.targets())
    scaler = ColumnScaler.fit(y_train, names, reg_flags)
    y_train_scaled = scaler.transform(y_train)
    train_data.set_targets(to_kermt_targets(y_train_scaled))
    y_val_raw = from_kermt_targets(val_data.targets())
    val_data.set_targets(to_kermt_targets(scaler.transform(y_val_raw)))
    label_mask = ~np.isnan(y_train_scaled)
    kscaler = KermtScalerShim(scaler)

    model, _ = load_checkpoint(args.checkpoint_paths[0], current_args=args, logger=logger)
    effective = {k: getattr(args, k) for k in cli}
    loss_module = MixedLoss(cls_flags, MixedLossConfig(mode=mode, dist_coff=float(args.dist_coff)))
    if args.cuda:
        model = model.cuda(); loss_module = loss_module.cuda()
    optimizer = build_optimizer(model, args)
    scheduler = build_lr_scheduler(optimizer, args)

    collator = MolCollator(shared_dict={}, args=args)
    val_collator = MolCollator(shared_dict={}, args=args)

    def train_batches(epoch: int):
        batches = stratified_batches(label_mask, args.batch_size, min_per_task=min_per_task, seed=args.seed, epoch=epoch)
        loader = DataLoader(train_data, batch_sampler=batches, num_workers=0, collate_fn=collator)
        for item in loader:
            _, batch, features_batch, mask, targets = item
            yield batch, features_batch, mask, targets

    def val_batches():
        args.bond_drop_rate = 0
        loader = DataLoader(val_data, batch_size=args.batch_size, shuffle=False, num_workers=0, collate_fn=val_collator)
        for item in loader:
            _, batch, features_batch, mask, targets = item
            yield batch, features_batch, mask, targets

    # ---- holdout (read-only hook input): same prepared features the deployed predict path uses ----
    hargs = copy.copy(args)
    hargs.features_path = [str(DATA / "holdout/clean.npz")]; hargs.max_data_size = None; hargs.use_compound_names = False
    hold_data = get_data(path=str(DATA / "holdout/clean.csv"), skip_invalid_smiles=False, args=hargs)
    hold_y = np.load(DATA / "holdout/labels.npy")
    if opts.subset_holdout:
        hold_data = type(hold_data)(hold_data.data[: opts.subset_holdout]); hold_y = hold_y[: opts.subset_holdout]
    assert len(hold_data) == len(hold_y)
    hold_collator = MolCollator(shared_dict={}, args=hargs)

    def score_holdout() -> np.ndarray:
        was = model.training; model.eval(); out = []
        try:
            with torch.no_grad():
                for item in DataLoader(hold_data, batch_size=args.batch_size, shuffle=False, num_workers=0, collate_fn=hold_collator):
                    _, batch, fb, _, _ = item
                    a, b = mixed_forward(model, batch, fb)
                    out.append(combine_views(a, b, cls_flags).cpu().numpy())
        finally:
            model.train(was)
        return np.concatenate(out, axis=0)

    run_dir = OUT
    (run_dir / "epochs").mkdir(parents=True, exist_ok=True)
    jl_path = run_dir / "diag_epochs.jsonl"
    start_epoch = 0
    last_path = run_dir / "last_checkpoint.pt"
    if opts.resume and last_path.exists():
        st = torch.load(last_path, map_location="cpu", weights_only=False)
        model.load_state_dict(st["model"]); optimizer.load_state_dict(st["optimizer"]); scheduler.load_state_dict(st["scheduler"])
        torch.set_rng_state(st["rng"]["torch"])
        if st["rng"]["cuda"]:
            torch.cuda.set_rng_state_all(st["rng"]["cuda"])
        np.random.set_state(st["rng"]["numpy"]); random.setstate(st["rng"]["python"])
        start_epoch = int(st["next_epoch"])
        kept = [l for l in jl_path.read_text().splitlines() if l.strip() and (json.loads(l).get("event") != "epoch" or json.loads(l)["epoch"] < start_epoch)]
        jl_path.write_text("\n".join(kept) + "\n")
        info(f"RESUMED at epoch {start_epoch}")
    else:
        jl_path.write_text("")

    jl = jl_path.open("a", buffering=1)
    def jwrite(rec):
        jl.write(json.dumps(rec, default=float) + "\n"); jl.flush(); os.fsync(jl.fileno())
    if start_epoch == 0:
        jwrite({"event": "start", "diagnostic": True, "seed": args.seed, "epochs": args.epochs, "mode": mode, "min_per_task": min_per_task,
                "n_train": len(train_data), "n_val": len(val_data), "n_holdout": len(hold_data), "hook": not opts.no_hook,
                "cli_values": cli, "effective_values_after_load_checkpoint": effective,
                "nn_dropout_p": sorted({float(m.p) for m in model.modules() if isinstance(m, torch.nn.Dropout)}),
                "optimizer_weight_decay": [g["weight_decay"] for g in optimizer.param_groups], "lr_args": {k: getattr(args, k) for k in ("warmup_epochs", "init_lr", "max_lr", "final_lr")}})

    val_store: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    state = {"hook_s": 0.0}

    def on_val_views(epoch, a, b):
        val_store[epoch] = (a, b)

    def log_fn(rec: dict) -> None:
        if rec.get("event") != "epoch":
            return
        e = rec["epoch"]
        row = {k: rec[k] for k in ("epoch", "train_loss", "train_task_means", "val_task_means", "val_selection_loss", "lr", "n_batches", "seconds")}
        a, b = val_store.pop(e)
        pv = (sigmoid(a) + sigmoid(b)) / 2.0
        va = [auroc(y_val_raw[:, t], pv[:, t]) for t in range(len(names))]
        row["val_auroc"] = va; row["val_auroc_mean"] = float(np.nanmean(va))
        if not opts.no_hook:
            t0 = time.time()
            before = rng_capture(); d0 = rng_digest(before)
            hp = score_holdout()
            rng_restore(before)
            d1 = rng_digest(rng_capture())
            assert d0 == d1, "hook changed RNG state"
            row["holdout_auroc"] = [auroc(hold_y[:, t], hp[:, t]) for t in range(len(names))]
            row["rng_digest_before_after_hook"] = [d0, d1]
            np.save(run_dir / "epochs" / f"holdout_probs_e{e:02d}.npy", hp.astype(np.float32))
            row["hook_seconds"] = time.time() - t0
        np.savez_compressed(run_dir / "epochs" / f"val_views_e{e:02d}.npz", atom=a.astype(np.float32), bond=b.astype(np.float32))
        if not opts.no_epoch_ckpts:
            d = run_dir / "ckpt" / f"epoch_{e:02d}"; d.mkdir(parents=True, exist_ok=True)
            save_checkpoint(str(d / "model.pt"), model, kscaler, features_scaler, args)
        row["model_digest"] = model_digest(model) if opts.digests else None
        row["rng_digest_end_of_epoch"] = rng_digest(rng_capture())
        tmp = run_dir / "last_checkpoint.pt.tmp"
        torch.save({"model": model.state_dict(), "optimizer": optimizer.state_dict(), "scheduler": scheduler.state_dict(),
                    "rng": rng_capture(), "next_epoch": e + 1, "args_seed": args.seed}, tmp)
        os.replace(tmp, last_path)
        jwrite({"event": "epoch", **row})
        info(f"epoch {e} train {row['train_loss']:.6f} val_sel {row['val_selection_loss']:.6f} valAUC {va[0]:.4f}/{va[1]:.4f}"
             + (f" holdoutAUC {row['holdout_auroc'][0]:.4f}/{row['holdout_auroc'][1]:.4f}" if "holdout_auroc" in row else ""))
        if opts.stop_after is not None and e + 1 >= opts.stop_after and e + 1 < args.epochs:
            raise SystemExit(f"STOP_AFTER {opts.stop_after}")

    try:
        result = fit(model, loss_module, optimizer, scheduler, train_batches, val_batches,
                     TrainSettings(epochs=int(args.epochs), mode=mode, dist_coff=float(args.dist_coff)), cls_flags,
                     start_epoch=start_epoch, on_best=None, log_fn=log_fn, on_val_views=on_val_views)
    except SystemExit as exc:
        jl.close(); print(json.dumps({"stopped": str(exc), "next_epoch_on_disk": True})); return {"stopped": True}
    summary = {"event": "summary", "final_model_digest": model_digest(model), "final_rng_digest": rng_digest(rng_capture()),
               "best_epoch_by_val_selection_loss": result.best_epoch}
    jwrite(summary); jl.close()
    (OUT / "DONE.json").write_text(json.dumps(summary))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=0)
    ap.add_argument("--subset-train", type=int, default=0); ap.add_argument("--subset-val", type=int, default=0)
    ap.add_argument("--subset-holdout", type=int, default=0)
    ap.add_argument("--no-hook", action="store_true"); ap.add_argument("--no-epoch-ckpts", action="store_true")
    ap.add_argument("--resume", action="store_true"); ap.add_argument("--stop-after", type=int, default=None)
    ap.add_argument("--digests", action="store_true", help="record a model digest every epoch (smoke tests)")
    opts = ap.parse_args()
    torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms(mode=True)
    try:
        out = run(opts)
    except Exception:
        import traceback; traceback.print_exc(); return 1
    print(json.dumps(out, default=str)); return 0


if __name__ == "__main__":
    sys.exit(main())
