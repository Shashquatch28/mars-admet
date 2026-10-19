"""G2 extension (Phase A, no training): stock path vs mixed path on one fixed batch each, inside the KERMT container.

Checks, in order: (1) loss, (2) two-view forward in TRAINING mode with identical RNG, (3) per-column target scaling,
(4) batch composition over one epoch, (5) LR schedule per step; plus (A2) the checkpoint-args overwrite.
Reads training/validation inputs of an existing mixed run (its ``test_placeholder`` is a copy of val); never the test set.
Writes ``/runs/g2_extension.json``. Run through ``eval/g2_extension_host.py`` (stages data + trainer, calls the container).
"""
from __future__ import annotations

import json
import math
import os
import random
import sys
from pathlib import Path

import numpy as np
import torch
from torch import nn

DATA = Path("/data")
OUT = Path("/runs")
RUN_JSON = DATA / "run.json"
SPEC = json.loads((DATA / "spec.json").read_text())
CKPT = "/ckpt"
res: dict = {}


def seed_all(s: int) -> None:
    torch.manual_seed(s); torch.cuda.manual_seed_all(s); np.random.seed(s); random.seed(s)


def diff(a, b) -> dict:
    a = np.asarray(a, dtype=np.float64); b = np.asarray(b, dtype=np.float64)
    ad = float(np.max(np.abs(a - b))) if a.size else 0.0
    return {"max_abs": ad, "max_rel": float(np.max(np.abs(a - b) / np.maximum(np.abs(b), 1e-12))) if a.size else 0.0}


def setup():
    from kermt.util.parsing import parse_args
    from kermt.util.utils import get_data, get_task_names, load_checkpoint, build_optimizer, build_lr_scheduler
    from kermt_mixed.train_mixed import finetune_argv_tail
    from kermt_mixed.scaling import ColumnScaler, from_kermt_targets, to_kermt_targets

    tail = [t.replace("/runs/data/", "/data/data/") for t in finetune_argv_tail(RUN_JSON)]
    sys.argv = ["main.py", *tail]
    args = parse_args()
    cli = {k: getattr(args, k) for k in ("dist_coff", "dropout", "bond_drop_rate", "weight_decay", "select_by_loss")}
    seed_all(args.seed)
    torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms(mode=True)
    args.task_names = get_task_names(args.data_path)
    train_data = get_data(path=args.data_path, args=args)
    args.features_dim = len(train_data.data[0].features) if train_data.data[0].features is not None else 0
    args.num_tasks = train_data.num_tasks(); args.features_size = train_data.features_size()
    val_data = get_data(path=args.separate_val_path, args=args, features_path=args.separate_val_features_path)
    args.train_data_size = len(train_data)
    model, ck_state = load_checkpoint(args.checkpoint_paths[0], current_args=args)
    post = {k: getattr(args, k) for k in cli}
    model = model.cuda()
    return dict(args=args, train=train_data, val=val_data, model=model, cli=cli, post=post, build_opt=build_optimizer,
                build_sched=build_lr_scheduler)


def main() -> None:
    from kermt.data import MolCollator
    from kermt.util.utils import get_loss_func
    from kermt_mixed.forward import mixed_forward
    from kermt_mixed.losses import MixedLoss, MixedLossConfig
    from kermt_mixed.sampler import batch_stats, stratified_batches
    from kermt_mixed.scaling import ColumnScaler, from_kermt_targets, to_kermt_targets
    from kermt_mixed.train_mixed import is_classification_flags

    S = setup(); args, model, train, val = S["args"], S["model"], S["train"], S["val"]
    cls = is_classification_flags(SPEC["task_types"])
    names = SPEC["target_names"]

    # ---------------- A2: checkpoint args and the overwrite --------------------------------
    ck = torch.load(CKPT, map_location="cpu", weights_only=False)
    ckargs = vars(ck["args"])
    opt = S["build_opt"](model, args)
    drop_p = sorted({float(m.p) for m in model.modules() if isinstance(m, nn.Dropout)})
    res["A2"] = {
        "checkpoint_saved_args": {k: ckargs.get(k) for k in ("dist_coff", "dropout", "bond_drop_rate", "weight_decay", "select_by_loss")},
        "cli_values_from_dry_run_argv": S["cli"],
        "args_after_load_checkpoint_(stock_and_mixed_both_call_it_before_loss/optimizer/collator)": S["post"],
        "nn.Dropout_p_values_in_built_model": drop_p,
        "optimizer_weight_decay_per_group": [g["weight_decay"] for g in opt.param_groups],
        "get_model_args_includes": [k for k in ("dist_coff", "dropout", "bond_drop_rate", "weight_decay", "select_by_loss")
                                    if k in __import__("kermt.util.utils", fromlist=["x"]).get_model_args()],
    }
    print("A2", json.dumps(res["A2"], indent=1), flush=True)

    # fixed batch: first batch of the mixed sampler, epoch 0
    y_tr = from_kermt_targets(train.targets()); label_mask = ~np.isnan(y_tr)
    batches = stratified_batches(label_mask, args.batch_size, min_per_task=0, seed=args.seed, epoch=0)
    idx0 = batches[0].tolist()

    def collate(idxs, seed):
        seed_all(seed)
        return MolCollator(shared_dict={}, args=args)([train[i] for i in idxs])

    # ---------------- 1. loss -------------------------------------------------------------
    stock_loss = get_loss_func(args, model)               # KermtFinetuneTask.get_loss_func(args): dist_coff bound after load_checkpoint
    mixed = MixedLoss(cls, MixedLossConfig(mode="fixed", dist_coff=float(args.dist_coff))).cuda()
    TOL1 = 1e-6
    cases = {}
    g = torch.Generator().manual_seed(11)
    def run_case(name, atom, bond, mask, targets0):
        atom = atom.clone().requires_grad_(True); bond = bond.clone().requires_grad_(True)
        el_s = stock_loss((atom, bond), targets0) * torch.ones_like(targets0) * mask
        tot_s = el_s.sum() / mask.sum()
        gs = torch.autograd.grad(tot_s, [atom, bond])
        atom2 = atom.detach().clone().requires_grad_(True); bond2 = bond.detach().clone().requires_grad_(True)
        out = mixed(atom2, bond2, targets0, mask)               # convention A: stock-style (0-filled targets + mask tensor)
        gm = torch.autograd.grad(out.total, [atom2, bond2])
        tnan = targets0.clone(); tnan[mask == 0] = float("nan")  # convention B: NaN where unlabeled + the same mask
        out_nan = MixedLoss(cls, MixedLossConfig(mode="fixed", dist_coff=float(args.dist_coff))).cuda()(atom.detach(), bond.detach(), tnan, mask)
        elm = mixed.element_loss(atom.detach(), bond.detach(), targets0) * mask
        cases[name] = {
            "total_stock": float(tot_s), "total_mixed_A_zero_filled": float(out.total), "total_mixed_B_nan_filled": float(out_nan.total),
            "total_diff_A": diff(tot_s.detach().cpu(), out.total.detach().cpu()), "total_diff_B": diff(tot_s.detach().cpu(), out_nan.total.detach().cpu()),
            "per_element_diff": diff(el_s.detach().cpu(), elm.detach().cpu()),
            "grad_wrt_logits_diff": max(diff(a.cpu(), b.cpu())["max_abs"] for a, b in zip(gs, gm)),
            "finite_B": bool(torch.isfinite(out_nan.total)),
        }
    B, T = 32, len(cls)
    for nm, p in (("random_mask_p=(0.7,0.27)", (0.7, 0.27)), ("dense_mask", (1.0, 1.0)), ("one_task_empty", (0.7, 0.0))):
        atom = (torch.randn(B, T, generator=g) * 3).cuda(); bond = (torch.randn(B, T, generator=g) * 3).cuda()
        mask = torch.stack([(torch.rand(B, generator=g) < pp).float() for pp in p], 1).cuda()
        if mask.sum() == 0: mask[0, 0] = 1
        tg = (torch.rand(B, T, generator=g) < 0.5).float().cuda() * mask
        run_case(nm, atom, bond, mask, tg)
    # real batch: collator-produced (mask, targets) and real train-mode logits
    _, bt, fb, mk, tg = collate(idx0, 5)
    model.train(); seed_all(5)
    with torch.no_grad():
        a_r, b_r = model(bt, fb)
    run_case("real_batch_train_mode_logits", a_r.detach(), b_r.detach(), mk.cuda(), tg.cuda())
    # data layer: None-vs-NaN convention across the whole train and val folds
    def mask_check(ds):
        y = from_kermt_targets(ds.targets()); raw_nan = any(v is not None and (isinstance(v, float) and math.isnan(v)) for row in ds.targets() for v in row)
        coll = MolCollator(shared_dict={}, args=args)
        mism = 0
        for s in range(0, len(ds), 256):
            _, _, _, m, _ = coll([ds[i] for i in range(s, min(s + 256, len(ds)))])
            mism += int((m.numpy() != (~np.isnan(y[s:s + 256])).astype(np.float32)).sum())
        return {"mask_vs_label_matrix_mismatches": mism, "nan_floats_in_kermt_targets": bool(raw_nan)}
    args.bond_drop_rate_backup = args.bond_drop_rate
    res["1_loss"] = {"tolerance": TOL1, "effective_dist_coff": float(args.dist_coff), "cases": cases,
                     "data_layer_mask_convention": {"train": mask_check(train), "val": mask_check(val)},
                     "pass": all(c["total_diff_A"]["max_rel"] < TOL1 and c["total_diff_B"]["max_rel"] < TOL1 and c["per_element_diff"]["max_abs"] < TOL1
                                 and c["grad_wrt_logits_diff"] < TOL1 for c in cases.values())}
    print("1_loss pass", res["1_loss"]["pass"], flush=True)

    # ---------------- 2. two-view forward, TRAINING mode, identical RNG ---------------------
    TOL2 = 1e-5
    model.train()
    def stock_fwd(seed):
        _, bt, fb, _, _ = collate(idx0, seed)
        with torch.no_grad():
            a, b = model(bt, fb)
        return a.cpu().numpy(), b.cpu().numpy()
    def mixed_fwd(seed):
        _, bt, fb, _, _ = collate(idx0, seed)
        with torch.no_grad():
            a, b = mixed_forward(model, bt, fb)
        return a.cpu().numpy(), b.cpu().numpy()
    sa, sb = stock_fwd(123); ma, mb = mixed_fwd(123)
    sa2, sb2 = stock_fwd(124)
    args.bond_drop_rate = args.bond_drop_rate_backup
    res["2_forward_train_mode"] = {
        "tolerance": TOL2, "atom_view": diff(ma, sa), "bond_view": diff(mb, sb),
        "control_different_seed_stock_vs_stock_atom": diff(sa2, sa),   # >> tolerance iff dropout/bond-drop are really active
        "model_is_training": bool(model.training), "effective_dropout_p": drop_p, "effective_bond_drop_rate": float(args.bond_drop_rate),
    }
    res["2_forward_train_mode"]["pass"] = max(res["2_forward_train_mode"]["atom_view"]["max_abs"], res["2_forward_train_mode"]["bond_view"]["max_abs"]) < TOL2
    print("2 fwd", res["2_forward_train_mode"], flush=True)

    # ---------------- 3. per-column scaling -------------------------------------------------
    reg = [not c for c in cls]
    sc = ColumnScaler.fit(y_tr, names, reg)
    y_va = from_kermt_targets(val.targets())
    ident = lambda y: bool(np.array_equal(np.nan_to_num(sc.transform(y), nan=-9), np.nan_to_num(y, nan=-9)))
    st = torch.load("/data/mixed_model.pt", map_location="cpu", weights_only=False)
    res["3_scaling"] = {
        "fitted_means": list(sc.means), "fitted_stds": list(sc.stds), "is_regression": reg,
        "transform_is_identity_train": ident(y_tr), "transform_is_identity_val": ident(y_va),
        "inverse_is_identity_on_probabilities": bool(np.array_equal(sc.inverse_transform(np.linspace(0, 1, 11)[:, None].repeat(len(names), 1)), np.linspace(0, 1, 11)[:, None].repeat(len(names), 1))),
        "saved_mixed_checkpoint_data_scaler": {k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in (st.get("data_scaler") or {}).items()},
        "stock_path": "classification => scaler None in KERMT (load_data builds a StandardScaler only for dataset_type=='regression'); predict() skips inverse_transform when scaler is None",
        "mixed_predict_path": "run_predict applies ColumnScaler.inverse_transform to all columns; mean=0,std=1 => identity for classification",
    }
    res["3_scaling"]["pass"] = (res["3_scaling"]["transform_is_identity_train"] and res["3_scaling"]["transform_is_identity_val"]
                                and all(m == 0 for m in sc.means) and all(s_ == 1 for s_ in sc.stds))
    print("3 scaling", res["3_scaling"]["pass"], flush=True)

    # ---------------- 4. batch composition over epochs --------------------------------------
    from torch.utils.data import DataLoader
    n = len(train)
    # stock: DataLoader(shuffle=True) built exactly as run_training builds it, after the same RNG history (seed -> load_checkpoint)
    seed_all(args.seed)
    S2 = setup()  # re-runs seed -> get_data -> load_checkpoint exactly like a stock launch; leaves torch RNG where stock has it
    pos_of = {id(d): i for i, d in enumerate(S2["train"].data)}
    ldr = DataLoader(S2["train"], batch_size=args.batch_size, shuffle=True, num_workers=0, collate_fn=lambda b: [pos_of[id(d)] for d in b])
    E = 5
    stock_ep = [[np.array(b) for b in ldr] for _ in range(E)]
    mixed_ep = [stratified_batches(label_mask, args.batch_size, min_per_task=0, seed=args.seed, epoch=e) for e in range(E)]
    def summarize(ep):
        out = []
        for batches_ in ep:
            allidx = np.concatenate(batches_)
            sizes = [len(b) for b in batches_]
            st_ = batch_stats(batches_, label_mask)
            out.append({"n_batches": len(batches_), "covers_each_row_exactly_once": bool(len(allidx) == n and len(set(allidx.tolist())) == n),
                        "first_batch_size": sizes[0], "last_batch_size": sizes[-1], "size_min": min(sizes), "size_max": max(sizes),
                        "per_task_label_mean": st_["per_task_mean"], "per_task_label_min": st_["per_task_min"],
                        "batches_with_zero_labels_per_task": st_["batches_with_zero_labels_per_task"]})
        return out
    ss, ms = summarize(stock_ep), summarize(mixed_ep)
    same_order_e0 = bool(all(np.array_equal(a, b) for a, b in zip(stock_ep[0], mixed_ep[0])))
    # how different are the permutations: fraction of rows at the same position
    sp = np.concatenate(stock_ep[0]); mp = np.concatenate(mixed_ep[0])
    res["4_batches"] = {"n_train": n, "batch_size": args.batch_size, "epochs_compared": E, "molecule_order_identical_epoch0": same_order_e0,
                        "fraction_of_positions_equal_epoch0": float((sp == mp).mean()),
                        "stock_loader": "torch DataLoader(shuffle=True), RandomSampler on the global torch RNG, stream continues across epochs",
                        "mixed_loader": "numpy default_rng([seed, epoch]).permutation, chunked; DataLoader(batch_sampler=...)",
                        "stock": ss, "mixed": ms}
    ok = all(x["covers_each_row_exactly_once"] for x in ss + ms) and all((x["n_batches"], x["last_batch_size"], x["size_max"]) == (ss[0]["n_batches"], ss[0]["last_batch_size"], ss[0]["size_max"]) for x in ss + ms)
    res["4_batches"]["coverage_sizes_and_last_batch_match"] = bool(ok)
    print("4 batches order_identical", same_order_e0, "coverage/sizes match", ok, flush=True)

    # ---------------- 5. LR schedule per step ----------------------------------------------
    steps = (n // args.batch_size) + (1 if n % args.batch_size else 0)  # batches per epoch (400)
    def lr_trace(arm: str):
        S3 = setup(); m3 = S3["model"]; a3 = S3["args"]
        o = S3["build_opt"](m3, a3); sch = S3["build_sched"](o, a3)
        tr = [[g["lr"] for g in o.param_groups]]   # lr before the first optimizer step
        for e in range(3):
            for _ in range(steps):
                o.step()                              # stock: optimizer.step() then `if isinstance(scheduler, NoamLR): scheduler.step()`
                sch.step()                            # mixed: optimizer.step() then `if scheduler is not None: scheduler.step()`
                tr.append([g["lr"] for g in o.param_groups])
        return np.array(tr)
    ts = lr_trace("stock"); tm = lr_trace("mixed")
    ep_end = lambda t, e: t[(e + 1) * steps].tolist()
    res["5_lr"] = {
        "args": {k: getattr(args, k) for k in ("warmup_epochs", "init_lr", "max_lr", "final_lr", "epochs", "fine_tune_coff", "batch_size", "train_data_size")},
        "steps_per_epoch_used_by_NoamLR": args.train_data_size // args.batch_size, "batches_per_epoch_actual": steps,
        "stepping": "both arms: scheduler.step() once per batch, after optimizer.step()",
        "per_step_trace_max_abs_diff": float(np.max(np.abs(ts - tm))), "n_steps_traced": int(ts.shape[0] - 1),
        "lr_at_step": {str(k): ts[k].tolist() for k in (0, 1, 399, 400, 401, 800, 1199, 1200)},
        "lr_end_of_epoch_0_1_2": [ep_end(ts, e) for e in range(3)],
    }
    res["5_lr"]["pass"] = res["5_lr"]["per_step_trace_max_abs_diff"] == 0.0
    np.save(OUT / "lr_trace_first3_epochs.npy", ts)
    (OUT / "g2_extension.json").write_text(json.dumps(res, indent=1, default=str))
    print("DONE", {k: v.get("pass") for k, v in res.items() if isinstance(v, dict) and "pass" in v}, flush=True)


if __name__ == "__main__":
    main()
