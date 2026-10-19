"""Per-epoch selection diagnostics for toxicity__cls, seeds 0-4 (validation fold only; no test data, no GPU).

Mixed arm: per-epoch hERG / AMES validation AUROC from the saved ``val_views.npz`` (re-scored exactly as the trainer does,
checked against the run's recorded validation AUROC at its own epoch), plus the trainer's validation losses.
Stock arm: ``finetune.log`` (only ``Epoch:`` and ``Saving model at epoch`` lines are parsed). The stock run does not log
per-task scores (``show_individual_scores=False``), so only the TASK-MEAN AUROC and the mean validation loss exist per epoch.

Reports the epoch each rule picks, its spread across seeds, and what share of the epoch-to-epoch variance of the task-mean
AUROC comes from hERG (covariance share, levels and first differences) -- measurable on the mixed trajectories only.

    PREP_ID=<id> python -m eval.selection_diagnostics --out <json>
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

from configs.clusters import type_homogeneous_subgroups
from data.cluster_loaders import SMILES_COL, load_cluster
from data.split import five_seed_train_val_folds
from train.kermt_mixed.posthoc import combine_views_np
from train.train_kermt_cluster import _label_lookup, _stack

EPOCH_RE = re.compile(r"^Epoch: (\d+) loss_train: ([\d.]+) loss_val: ([\d.]+) auc_val: ([\d.]+)")
SAVE_RE = re.compile(r"^Saving model at epoch (\d+) with validation score ([\d.]+)")


def parse_stock(log: Path) -> dict:
    ep, saved = {}, []
    for line in log.read_text(errors="replace").splitlines():
        m = EPOCH_RE.match(line)
        if m:
            ep[int(m[1])] = {"loss_train": float(m[2]), "loss_val": float(m[3]), "auc_val_mean": float(m[4])}
            continue
        m = SAVE_RE.match(line)
        if m:
            saved.append(int(m[1]))
    return {"epochs": ep, "saved_epoch": saved[-1]}


def share(h: np.ndarray, a: np.ndarray, diff: bool) -> float:
    if diff:
        h, a = np.diff(h), np.diff(a)
    m = (h + a) / 2
    return float(0.5 * np.cov(h, m)[0, 1] / np.var(m, ddof=1))  # Cov(h/2, m) / Var(m); hERG + AMES shares sum to 1


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True)
    args = ap.parse_args()
    keys = list(type_homogeneous_subgroups("toxicity")["toxicity__cls"].endpoints)
    cd = load_cluster(Path("data/processed") / os.environ["PREP_ID"], keys, cluster_key="toxicity__cls")
    pool, _ = cd.train_pool(holdout_calibration=True); lk = _label_lookup(pool); smiles = pool[SMILES_COL].tolist()
    out = {"seeds": {}}
    for s in range(5):
        stock_run = [p for p in sorted(glob.glob(f"runs/kermt_mtsub_toxicity__cls_seed{s}_*"))
                     if json.loads((Path(p) / "run.json").read_text()).get("status") == "completed"][0]
        st = parse_stock(Path(stock_run) / "artifacts/kermt/logs/finetune.log")
        mrun = sorted(glob.glob(f"runs/kermt_mx_toxicity__cls_seed{s}_fixed_*"))[0]
        _, _, va = five_seed_train_val_folds(smiles, seeds=(s,))[0]
        y = np.asarray(_stack(va, lk), dtype=float)
        with np.load(mrun + "/artifacts/kermt/logs/val_views.npz") as z:
            eps = sorted(int(k.split("_e")[1]) for k in z.files if k.startswith("atom_e"))
            P = {e: combine_views_np(z[f"atom_e{e:03d}"], z[f"bond_e{e:03d}"], [True, True]) for e in eps}
        auc = np.array([[roc_auc_score(y[~np.isnan(y[:, t]), t], P[e][~np.isnan(y[:, t]), t]) for t in range(2)] for e in eps])
        recs = [json.loads(l) for l in open(mrun + "/artifacts/kermt/logs/mixed_epochs.jsonl") if l.strip()]
        ev = {r["epoch"]: r for r in recs if r["event"] == "epoch"}
        summ = [r for r in recs if r["event"] == "summary"][0]
        own = int(summ["best_epoch"])
        recorded = {}
        for l in open(mrun + "/metrics.jsonl"):
            m = json.loads(l)["metrics"]
            if m.get("split") == "val": recorded[m["endpoint"]] = m["auroc"]
        chk = max(abs(auc[own, t] - recorded[keys[t]]) for t in range(2))
        assert chk < 1e-9, (s, chk)
        mean = auc.mean(axis=1)
        stock_mean = np.array([st["epochs"][e]["auc_val_mean"] for e in sorted(st["epochs"])])
        assert st["saved_epoch"] == int(np.argmax(stock_mean)), (s, "saved epoch != first argmax of logged mean AUROC")
        h, a = auc[:, 0], auc[:, 1]
        out["seeds"][s] = {
            "stock_run": stock_run, "mixed_run": mrun,
            "stock_rule_pick_stock": st["saved_epoch"],
            "mixed_own_epoch_pick": own,
            "mixed_argmax_mean_auroc_epoch": int(np.argmax(mean)),
            "mixed_argmax_ames_epoch": int(np.argmax(a)), "mixed_argmax_herg_epoch": int(np.argmax(h)),
            "mixed_per_epoch": [{"epoch": e, "herg_auroc": float(h[e]), "ames_auroc": float(a[e]), "mean_auroc": float(mean[e]),
                                 "val_selection_loss": ev[e]["val_selection_loss"], "val_task_loss": ev[e]["val_task_means"]} for e in eps],
            "stock_per_epoch": [{"epoch": e, **st["epochs"][e]} for e in sorted(st["epochs"])],
            "herg_share_of_mean_auroc_variance": {"levels_all": share(h, a, False), "levels_epoch5plus": share(h[5:], a[5:], False),
                                                  "first_diff": share(h, a, True)},
            "sd_over_epochs": {"herg": float(h[5:].std(ddof=1)), "ames": float(a[5:].std(ddof=1)), "mean": float(mean[5:].std(ddof=1))},
            "stock_mean_auroc_sd_epoch5plus": float(stock_mean[5:].std(ddof=1)),
            "val_labels": [int((~np.isnan(y[:, t])).sum()) for t in range(2)],
            "repro_check_max_abs_err": float(chk),
        }
        q = out["seeds"][s]
        print(f"seed{s}: stock-pick {q['stock_rule_pick_stock']} | mixed own {own} | mixed argmax(mean) {q['mixed_argmax_mean_auroc_epoch']} "
              f"argmax(AMES) {q['mixed_argmax_ames_epoch']} argmax(hERG) {q['mixed_argmax_herg_epoch']} | hERG var share (levels e5+) "
              f"{q['herg_share_of_mean_auroc_variance']['levels_epoch5plus']:.2f} diffs {q['herg_share_of_mean_auroc_variance']['first_diff']:.2f} "
              f"| sd e5+ hERG {q['sd_over_epochs']['herg']:.3f} AMES {q['sd_over_epochs']['ames']:.4f}", flush=True)
    for k in ("stock_rule_pick_stock", "mixed_own_epoch_pick", "mixed_argmax_mean_auroc_epoch", "mixed_argmax_ames_epoch"):
        v = [out["seeds"][s][k] for s in range(5)]
        out[f"spread_{k}"] = {"picks": v, "range": [min(v), max(v)], "sd": float(np.std(v))}
        print(k, v)
    Path(args.out).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
