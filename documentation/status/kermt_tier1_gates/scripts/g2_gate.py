# G2 one-epoch loss parity — lab_session_tier1.md §4 "G2" with the §0.5 preamble. Stock values only.
import os
from pathlib import Path
PREP = Path("data/processed") / os.environ["PREP_ID"]
CKPT = Path("data/checkpoints/kermt/NV-KERMT-70M-v2/kermt_contrastive_v2.0.pt")
RUNS = Path("runs")
W = RUNS / "tier1_gates"; W.mkdir(parents=True, exist_ok=True)

from configs.clusters import type_homogeneous_subgroups
from data.cluster_loaders import load_cluster, SMILES_COL
from data.split import five_seed_train_val_folds
from mars_contracts.endpoints import TaskType
from models.kermt_model import KermtModel, KermtConfig
from models.kermt_mixed_model import KermtMixedModel
from train.kermt_mixed import gates
from train.kermt_mixed.metrics_hooks import read_jsonl
from train.train_kermt_cluster import _label_lookup, _stack

keys = list(type_homogeneous_subgroups("toxicity")["toxicity__cls"].endpoints)
cd = load_cluster(PREP, keys, cluster_key="toxicity__cls")

pool, _ = cd.train_pool(holdout_calibration=True)
_, tr, va = five_seed_train_val_folds(pool[SMILES_COL].tolist(), seeds=(0,))[0]
lk = _label_lookup(pool)
ytr, yva = _stack(tr, lk), _stack(va, lk)
cfg = KermtConfig(epochs=1)
print(f"fold: n_train={len(tr)} n_val={len(va)}", flush=True)

KermtModel(TaskType.CLASSIFICATION, CKPT, keys, seed=0, config=cfg).fit(
    tr, ytr, X_val=va, y_val=yva, run_dir=W / "g2_stock")
print("g2 stock run done", flush=True)

KermtMixedModel({k: TaskType.CLASSIFICATION for k in keys}, CKPT, seed=0, config=cfg,
                loss_mode="fixed", min_per_task=0, hyperparameter_source="parity-gate").fit(
    tr, ytr, X_val=va, y_val=yva, run_dir=W / "g2_mixed")
print("g2 mixed run done", flush=True)

stock_log = (W / "g2_stock" / "logs" / "finetune.log").read_text()
mixed_ep0 = next(r for r in read_jsonl(W / "g2_mixed" / "logs" / "mixed_epochs.jsonl")
                 if r.get("event") == "epoch" and r["epoch"] == 0)["train_loss"]
print("G2_RESULT:", gates.g2_loss_parity(stock_log, mixed_ep0), flush=True)
