"""Selection-free parity check of deployed checkpoints on the calibration holdouts (toxicity__cls, seeds 0-4).

Scores, per seed, (a) the stock Tier-0 best-validation ``model.pt`` and (b) the mixed trainer's own-epoch
``model.pt`` on the hERG and AMES calibration holdouts -- molecules ``train_pool`` removes, so no arm trained or selected
on them. AUROC is computed host-side with ``eval.metrics.compute_metrics`` on raw probabilities (invariant to
temperature scaling; no calibrator is fitted or touched). Paired delta (mixed - stock) with a molecule-level paired
bootstrap percentile interval (same resample for both arms, and for all seeds in the pooled estimate).

Reads: train.csv / val.csv inputs of each run (provenance), the calibration split labels. Never reads the test split,
metrics.jsonl, or KERMT's test_result.csv. Inference only (KERMT container, GPU); nothing is trained.

    PREP_ID=<id> python -m eval.selection_free_parity --out <json> [--cache-dir <dir>] [--boot 4000]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from configs.clusters import type_homogeneous_subgroups
from data.cluster_loaders import SMILES_COL, load_cluster
from data.split import five_seed_train_val_folds
from eval.metrics import compute_metrics
from mars_contracts.endpoints import TaskType

SEEDS = (0, 1, 2, 3, 4)
MARGIN = 0.02
BOOT_SEED = 20261019


def run_dirs() -> dict[str, dict[int, Path]]:
    out: dict[str, dict[int, Path]] = {"stock": {}, "mixed": {}}
    for s in SEEDS:
        c = sorted(glob.glob(f"runs/kermt_mtsub_toxicity__cls_seed{s}_*"))
        c = [p for p in c if json.loads((Path(p) / "run.json").read_text()).get("status") == "completed"]
        assert len(c) == 1, (s, c)  # seed 4 has a second, crashed dir that is left in place and excluded here
        out["stock"][s] = Path(c[0])
        m = sorted(glob.glob(f"runs/kermt_mx_toxicity__cls_seed{s}_fixed_*"))
        assert len(m) == 1, (s, m)
        out["mixed"][s] = Path(m[0])
    return out


def provenance(cd, dirs) -> dict:
    cal_all = cd.calibration_molecules()
    pool, _ = cd.train_pool(holdout_calibration=True)
    folds = {s: (set(t), set(v)) for s, t, v in five_seed_train_val_folds(pool[SMILES_COL].tolist(), seeds=SEEDS)}
    rep = {}
    for arm in ("stock", "mixed"):
        for s in SEEDS:
            cfg = json.loads((dirs[arm][s] / "config.json").read_text())
            tr = set(pd.read_csv(dirs[arm][s] / "artifacts/kermt/input/train.csv")["smiles"])
            va = set(pd.read_csv(dirs[arm][s] / "artifacts/kermt/input/val.csv")["smiles"])
            r = {"holdout_calibration": cfg.get("holdout_calibration"), "prep_id": cfg.get("prep_id"),
                 "n_train": len(tr), "n_val": len(va),
                 "calibration_in_train": len(tr & cal_all), "calibration_in_val": len(va & cal_all),
                 "train_equals_recomputed_fold": tr == folds[s][0], "val_equals_recomputed_fold": va == folds[s][1]}
            assert r["holdout_calibration"] is True and r["calibration_in_train"] == 0 and r["calibration_in_val"] == 0, (arm, s, r)
            rep[f"{arm}_seed{s}"] = r
    return rep


def fast_auc(y: np.ndarray, p: np.ndarray) -> float:
    pos = y == 1
    n1, n0 = int(pos.sum()), int((~pos).sum())
    r = rankdata(p)
    return float((r[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--boot", type=int, default=4000)
    a = ap.parse_args()
    prep = Path("data/processed") / os.environ["PREP_ID"]
    keys = list(type_homogeneous_subgroups("toxicity")["toxicity__cls"].endpoints)
    cd = load_cluster(prep, keys, cluster_key="toxicity__cls")
    dirs = run_dirs()
    prov = provenance(cd, dirs)
    print("provenance OK: no calibration molecule in any train/val file; folds equal recomputed folds", flush=True)

    cal = cd.calibration.reset_index(drop=True)
    smiles = cal[SMILES_COL].tolist()
    cache = Path(a.cache_dir); cache.mkdir(parents=True, exist_ok=True)

    from models.kermt_mixed_model import KermtMixedModel
    from models.kermt_model import KermtModel

    probs: dict[str, np.ndarray] = {}
    for arm in ("stock", "mixed"):
        for s in SEEDS:
            f = cache / f"{arm}_seed{s}.npy"
            if f.exists():
                probs[f"{arm}{s}"] = np.load(f); continue
            if arm == "stock":
                m = KermtModel.load(dirs[arm][s] / "artifacts/model/kermt")
            else:
                m = KermtMixedModel.load(dirs[arm][s] / "artifacts/model/kermt_mixed")
            p = np.asarray(m.predict(smiles, run_dir=cache / f"work_{arm}_seed{s}"))
            assert p.shape == (len(smiles), len(keys)), p.shape
            np.save(f, p); probs[f"{arm}{s}"] = p
            print("scored", arm, s, flush=True)

    rng = np.random.default_rng(BOOT_SEED)
    res: dict = {"prep_id": os.environ["PREP_ID"], "margin": MARGIN, "n_boot": a.boot, "boot_rng_seed": BOOT_SEED,
                 "n_calibration_molecules": len(smiles), "provenance": prov, "endpoints": {}}
    for j, ep in enumerate(keys):
        lab = cal[ep].to_numpy(dtype=float); idx = np.where(~np.isnan(lab))[0]
        y = lab[idx].astype(int); n = len(idx)
        sa = {arm: {s: probs[f"{arm}{s}"][idx, j] for s in SEEDS} for arm in ("stock", "mixed")}
        full = {arm: {s: float(compute_metrics(y, sa[arm][s], TaskType.CLASSIFICATION).auroc) for s in SEEDS} for arm in sa}
        for arm in sa:
            for s in SEEDS:
                assert abs(full[arm][s] - fast_auc(y, sa[arm][s])) < 1e-9
        draws = rng.integers(0, n, size=(a.boot, n))
        D = np.empty((a.boot, len(SEEDS)))
        for b in range(a.boot):
            ii = draws[b]; yy = y[ii]
            if yy.min() == yy.max():
                D[b] = np.nan; continue
            for k, s in enumerate(SEEDS):
                D[b, k] = fast_auc(yy, sa["mixed"][s][ii]) - fast_auc(yy, sa["stock"][s][ii])
        def interval(v):
            v = v[~np.isnan(v)]
            lo, hi = np.percentile(v, [5, 95]); return float(lo), float(hi)
        per_seed = {}
        for k, s in enumerate(SEEDS):
            lo, hi = interval(D[:, k]); d = full["mixed"][s] - full["stock"][s]
            per_seed[s] = {"auroc_stock": full["stock"][s], "auroc_mixed": full["mixed"][s], "delta": d,
                           "ci90": [lo, hi], "inside_margin": bool(lo >= -MARGIN and hi <= MARGIN)}
        pd_ = float(np.mean([full["mixed"][s] - full["stock"][s] for s in SEEDS]))
        lo, hi = interval(D.mean(axis=1))
        # stock seed-to-seed spread of the same scored quantity (reference scale for the margin)
        res["endpoints"][ep] = {
            "n_scored": n, "n_pos": int(y.sum()), "n_neg": int(n - y.sum()), "per_seed": per_seed,
            "pooled": {"mean_auroc_stock": float(np.mean(list(full["stock"].values()))),
                       "mean_auroc_mixed": float(np.mean(list(full["mixed"].values()))),
                       "delta": pd_, "ci90": [lo, hi], "inside_margin": bool(lo >= -MARGIN and hi <= MARGIN)},
            "stock_seed_sd": float(np.std(list(full["stock"].values()))),
            "mixed_seed_sd": float(np.std(list(full["mixed"].values()))),
        }
        e = res["endpoints"][ep]
        print(ep, "n", n, "pooled delta %.4f ci90 [%.4f, %.4f]" % (pd_, lo, hi), flush=True)
    Path(a.out).write_text(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
