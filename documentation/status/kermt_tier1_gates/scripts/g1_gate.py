# G1 forward/inference parity — lab_session_tier1.md §3 with the §0.5 preamble. Stock values only.
import os
from pathlib import Path
PREP = Path("data/processed") / os.environ["PREP_ID"]
CKPT = Path("data/checkpoints/kermt/NV-KERMT-70M-v2/kermt_contrastive_v2.0.pt")
RUNS = Path("runs")
W = RUNS / "tier1_gates"; W.mkdir(parents=True, exist_ok=True)
_c = sorted(RUNS.glob("kermt_mtsub_toxicity__cls_seed0_*/artifacts/model/kermt"))
MODEL_DIR = _c[-1]
print("MODEL_DIR:", MODEL_DIR, flush=True)

from configs.clusters import type_homogeneous_subgroups
from data.cluster_loaders import load_cluster
from mars_contracts.endpoints import TaskType
from models.kermt_model import KermtModel
from models.kermt_mixed_model import KermtMixedModel
from train.kermt_mixed import gates
from train.kermt_mixed.train_mixed import write_predictions_csv

keys = list(type_homogeneous_subgroups("toxicity")["toxicity__cls"].endpoints)
cd = load_cluster(PREP, keys, cluster_key="toxicity__cls")
smi = cd.smiles("test")[:64]                       # fixed: first 64 test molecules
print("keys:", keys, "n_smiles:", len(smi), flush=True)

stock = KermtModel.load(MODEL_DIR)
p_stock = stock.predict(smi, run_dir=W / "g1_stock")
print("stock predict done", flush=True)

mixed = KermtMixedModel.from_finetuned(            # inference only: no training settings involved
    MODEL_DIR / "model.pt", {k: TaskType.CLASSIFICATION for k in keys}, CKPT, work_dir=W / "g1_mixed")
p_mixed = mixed.predict(smi)
print("mixed predict done", flush=True)

write_predictions_csv(W / "g1_stock.csv", smi, keys, p_stock)
write_predictions_csv(W / "g1_mixed.csv", smi, keys, p_mixed)
print("G1_RESULT:", gates.g1_forward_parity(W / "g1_stock.csv", W / "g1_mixed.csv"), flush=True)
