"""Pre-registered analysis of the diagnostic mixed re-runs (see the session note, "Phase B pre-registration"). Written BEFORE the runs started.

For each seed: E_loss = first argmin of validation selection loss; E_stock = first argmax of mean (over the two tasks) validation AUROC;
E_final = last epoch. Holdout = the hERG/AMES calibration holdouts (n = 1,050 / 576), AUROC only, no calibrator touched.
Bootstrap: molecule-level, paired, 4,000 resamples, 90 % percentile interval, RNG seed 20261019 + seed.

H_sel (selection-rule effect), primary form: lower 90 % bound of [holdout hERG AUROC(E_stock) - AUROC(E_loss)] >= +0.01
  AND |holdout hERG AUROC(E_stock) - AUROC(original stock checkpoint)| <= 0.01 (point estimate).
  Weak form also reported: point estimate of the first difference >= 0.01.
H_impl (implementation/dynamics): for every epoch e >= E_loss, hERG holdout AUROC(e) < AUROC(original stock checkpoint) (never reaches stock),
  AND max_{e >= E_loss} AUROC(e) - AUROC(E_loss) < 0.01 (flat: no rise of 0.01 or more).
If |E_stock - E_loss| <= 1 the run is declared uninformative about selection.
Also: matched-selection paired delta (diag E_stock checkpoint minus original stock checkpoint) on hERG and AMES, same bootstrap;
reproduction of the ORIGINAL mixed run (per-epoch train loss, validation selection loss, validation AUROC).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from pathlib import Path

import numpy as np

from configs.clusters import type_homogeneous_subgroups
from data.cluster_loaders import SMILES_COL, load_cluster

N_BOOT = 4000
BOOT_BASE = 20261019


def rank_auc(y, p):
    from scipy.stats import rankdata
    pos = y == 1; n1 = int(pos.sum()); n0 = len(y) - n1
    r = rankdata(p)
    return float((r[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def paired_boot(y, pa, pb, seed):
    """AUROC(pa) - AUROC(pb) on labelled molecules; point estimate and 90 % interval."""
    ok = ~np.isnan(y); y = y[ok].astype(int); pa = pa[ok]; pb = pb[ok]; n = len(y)
    rng = np.random.default_rng(seed); d = []
    for _ in range(N_BOOT):
        i = rng.integers(0, n, n)
        if y[i].min() == y[i].max():
            continue
        d.append(rank_auc(y[i], pa[i]) - rank_auc(y[i], pb[i]))
    lo, hi = np.percentile(d, [5, 95])
    return {"delta": rank_auc(y, pa) - rank_auc(y, pb), "ci90": [float(lo), float(hi)], "n": int(n)}


def analyse(seed: int, run_dir: Path, keys, hold_order_idx) -> dict:
    rows = [json.loads(l) for l in (run_dir / "out/diag_epochs.jsonl").read_text().splitlines() if l.strip()]
    ep = [r for r in rows if r["event"] == "epoch"]
    assert [r["epoch"] for r in ep] == list(range(len(ep))), "epoch records incomplete"
    labels = np.load(run_dir / "stage/holdout/labels.npy")
    stock = np.load(f"runs/tier1_gates/selection_free/stock_seed{seed}.npy")[hold_order_idx]      # original stock checkpoint, clean.csv row order
    mixed_orig = np.load(f"runs/tier1_gates/selection_free/mixed_seed{seed}.npy")[hold_order_idx]
    P = {r["epoch"]: np.load(run_dir / f"out/epochs/holdout_probs_e{r['epoch']:02d}.npy").astype(np.float64) for r in ep}
    sel = [r["val_selection_loss"] for r in ep]; vam = [r["val_auroc_mean"] for r in ep]
    E_loss = int(np.argmin(sel)); E_stock = int(np.argmax(vam)); E_final = len(ep) - 1
    h = keys.index("herg_cardiotoxicity"); a = keys.index("ames_mutagenicity")
    yh, ya = labels[:, h], labels[:, a]
    curve_h = [float(r["holdout_auroc"][h]) for r in ep]; curve_a = [float(r["holdout_auroc"][a]) for r in ep]
    stock_h = rank_auc(yh[~np.isnan(yh)].astype(int), stock[~np.isnan(yh), h]); stock_a = rank_auc(ya[~np.isnan(ya)].astype(int), stock[~np.isnan(ya), a])
    s = BOOT_BASE + seed
    d_sel = paired_boot(yh, P[E_stock][:, h], P[E_loss][:, h], s)
    d_match_h = paired_boot(yh, P[E_stock][:, h], stock[:, h], s + 100)
    d_match_a = paired_boot(ya, P[E_stock][:, a], stock[:, a], s + 200)
    d_loss_vs_stock_h = paired_boot(yh, P[E_loss][:, h], stock[:, h], s + 300)
    d_final_vs_stock_h = paired_boot(yh, P[E_final][:, h], stock[:, h], s + 400)
    d_final_vs_stock_a = paired_boot(ya, P[E_final][:, a], stock[:, a], s + 500)
    d_loss_vs_stock_a = paired_boot(ya, P[E_loss][:, a], stock[:, a], s + 600)
    uninformative = abs(E_stock - E_loss) <= 1
    h_sel_primary = (d_sel["ci90"][0] >= 0.01) and (abs(d_match_h["delta"]) <= 0.01)
    h_sel_weak = d_sel["delta"] >= 0.01
    after = curve_h[E_loss:]
    rise = max(after) - curve_h[E_loss]
    h_impl = all(v < stock_h for v in after) and rise < 0.01
    # reproduction of the original mixed run
    orig = sorted(glob.glob(f"runs/kermt_mx_toxicity__cls_seed{seed}_fixed_*"))[0]
    orig_log = [json.loads(l) for l in open(orig + "/artifacts/kermt/logs/mixed_epochs.jsonl") if '"event": "epoch"' in l]
    repro = {"max_abs_train_loss": max(abs(o["train_loss"] - r["train_loss"]) for o, r in zip(orig_log, ep)),
             "max_abs_val_selection_loss": max(abs(o["val_selection_loss"] - r["val_selection_loss"]) for o, r in zip(orig_log, ep)),
             "epoch0_train_loss_diag_vs_original": [ep[0]["train_loss"], orig_log[0]["train_loss"]],
             "original_best_epoch": int(np.argmin([o["val_selection_loss"] for o in orig_log]))}
    return {"seed": seed, "E_loss": E_loss, "E_stock": E_stock, "E_final": E_final, "uninformative_about_selection": uninformative,
            "holdout_hERG_curve": curve_h, "holdout_AMES_curve": curve_a, "stock_original_holdout_hERG": stock_h, "stock_original_holdout_AMES": stock_a,
            "val_auroc_curve": [r["val_auroc"] for r in ep], "val_selection_loss_curve": sel, "val_auroc_mean_curve": vam,
            "H_sel": {"E_stock_minus_E_loss_hERG": d_sel, "E_stock_vs_original_stock_hERG": d_match_h, "primary_met": bool(h_sel_primary), "weak_met": bool(h_sel_weak)},
            "H_impl": {"max_rise_after_E_loss": rise, "all_epochs_from_E_loss_below_stock": bool(all(v < stock_h for v in after)), "met": bool(h_impl)},
            "matched_selection_E_stock_minus_stock": {"hERG": d_match_h, "AMES": d_match_a},
            "E_loss_minus_stock": {"hERG": d_loss_vs_stock_h, "AMES": d_loss_vs_stock_a},
            "E_final_minus_stock": {"hERG": d_final_vs_stock_h, "AMES": d_final_vs_stock_a},
            "original_mixed_checkpoint_holdout": {"hERG": rank_auc(yh[~np.isnan(yh)].astype(int), mixed_orig[~np.isnan(yh), h]),
                                                  "AMES": rank_auc(ya[~np.isnan(ya)].astype(int), mixed_orig[~np.isnan(ya), a])},
            "reproduction_of_original_run": repro}


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--run", action="append", required=True, help="seed:run_dir"); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    keys = list(type_homogeneous_subgroups("toxicity")["toxicity__cls"].endpoints)
    cd = load_cluster(Path("data/processed") / os.environ["PREP_ID"], keys, cluster_key="toxicity__cls")
    cal_smiles = cd.calibration[SMILES_COL].tolist(); pos = {s: i for i, s in enumerate(cal_smiles)}
    res = {}
    for spec in a.run:
        seed, rd = spec.split(":"); rd = Path(rd)
        clean = [l.rstrip("\n") for l in (rd / "stage/holdout/clean.csv").read_text().splitlines()[1:]]
        idx = np.array([pos[s] for s in clean])
        res[f"seed{seed}"] = analyse(int(seed), rd, keys, idx)
        r = res[f"seed{seed}"]
        print(f"seed{seed}: E_loss {r['E_loss']} E_stock {r['E_stock']} E_final {r['E_final']} uninformative={r['uninformative_about_selection']} "
              f"H_sel primary={r['H_sel']['primary_met']} weak={r['H_sel']['weak_met']} H_impl={r['H_impl']['met']}")
    Path(a.out).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
