"""NO-GPU diagnostic for the failed G3 (toxicity__cls half). Re-picks each mixed run's epoch from its SAVED per-epoch validation views
using STOCK's rule (max over epochs of the mean-over-tasks validation AUROC; ties -> first epoch, as KERMT's `>` does), then re-runs
gates.g3_auroc_parity. Selection and scoring both use the validation fold only; the test set is never read. Does not replace the official verdict."""
import glob, json
import numpy as np
from sklearn.metrics import roc_auc_score
from data.cluster_loaders import SMILES_COL, load_cluster
from configs.clusters import type_homogeneous_subgroups
from data.split import five_seed_train_val_folds
from train.train_kermt_cluster import _label_lookup, _stack
from train.kermt_mixed import gates
from train.kermt_mixed.posthoc import combine_views_np
import os
from pathlib import Path

keys = list(type_homogeneous_subgroups("toxicity")["toxicity__cls"].endpoints)
cd = load_cluster(Path("data/processed") / os.environ["PREP_ID"], keys, cluster_key="toxicity__cls")
pool, _ = cd.train_pool(holdout_calibration=True); lk = _label_lookup(pool); smiles = pool[SMILES_COL].tolist()

def val_auroc(run):
    out = {}
    for l in open(run + "/metrics.jsonl"):
        m = json.loads(l)["metrics"]
        if m.get("split") == "val": out[m["endpoint"]] = m["auroc"]
    return out

stock_dirs = ["runs/kermt_mtsub_toxicity__cls_seed0_20260922T062623Z", "runs/kermt_mtsub_toxicity__cls_seed1_20260924T080913Z",
              "runs/kermt_mtsub_toxicity__cls_seed2_20261014T062957Z", "runs/kermt_mtsub_toxicity__cls_seed3_20261014T080552Z",
              "runs/kermt_mtsub_toxicity__cls_seed4_20261014T101513Z"]
stock = [val_auroc(d) for d in stock_dirs]
rows, own_ok = [], True
for s in range(5):
    run = sorted(glob.glob(f"runs/kermt_mx_toxicity__cls_seed{s}_fixed_*"))[-1]
    _, tr, va = five_seed_train_val_folds(smiles, seeds=(s,))[0]
    y = np.asarray(_stack(va, lk), dtype=float)
    with np.load(run + "/artifacts/kermt/logs/val_views.npz") as z:
        eps = sorted(int(k.split("_e")[1]) for k in z.files if k.startswith("atom_e"))
        P = {e: combine_views_np(z[f"atom_e{e:03d}"], z[f"bond_e{e:03d}"], [True, True]) for e in eps}
    def auc(e, t):
        ok = ~np.isnan(y[:, t]); return roc_auc_score(y[ok, t], P[e][ok, t])
    S = np.array([[auc(e, t) for t in range(2)] for e in eps])               # (E, 2)
    own = json.loads([l for l in open(run + "/artifacts/kermt/logs/mixed_epochs.jsonl") if l.strip()][-1])["best_epoch"]
    rec = val_auroc(run)
    chk = max(abs(S[own, t] - rec[keys[t]]) for t in range(2))              # reproduces the run's own reported val AUROC?
    own_ok &= chk < 1e-9
    e_stock = int(np.argmax(S.mean(axis=1)))                                # first max, like KERMT's strict >
    rows.append({"seed": s, "n_epochs": len(eps), "own_epoch": own, "stock_rule_epoch": e_stock, "repro_check_max_abs_err": chk,
                 "mixed_at_own": [S[own, 0], S[own, 1]], "mixed_at_stock_rule": [S[e_stock, 0], S[e_stock, 1]],
                 "val_labels": [int((~np.isnan(y[:, t])).sum()) for t in range(2)]})
    print(f"seed{s}: own epoch {own} -> stock-rule epoch {e_stock} | repro err {chk:.1e} | "
          f"hERG {S[own,0]:.4f}->{S[e_stock,0]:.4f} AMES {S[own,1]:.4f}->{S[e_stock,1]:.4f}")
print("\nreproduction of every run's recorded val AUROC at its own epoch:", "OK" if own_ok else "FAILED -- DO NOT TRUST")
out = {"rule": "max over epochs of mean-over-tasks val AUROC (first on ties)", "repro_ok": bool(own_ok), "seeds": rows, "endpoints": {}}
for t, k in enumerate(keys):
    a = [stock[s][k] for s in range(5)]; b = [rows[s]["mixed_at_stock_rule"][t] for s in range(5)]
    r = gates.g3_auroc_parity(a, b)
    print(f"\n{k}\n  stock: {[round(x,4) for x in a]}\n  mixed(stock rule): {[round(x,4) for x in b]}\n  {r.summary}  passed={r.passed}")
    out["endpoints"][k] = {"stock": a, "mixed_stock_rule": b, "passed": r.passed, "summary": r.summary, "evidence": r.evidence}
out["both_pass"] = all(v["passed"] for v in out["endpoints"].values())
json.dump(out, open("runs/tier1_gates/g3_posthoc_stockrule.json", "w"), indent=1)
print("\nBOTH pass under stock selection rule ->", out["both_pass"])
