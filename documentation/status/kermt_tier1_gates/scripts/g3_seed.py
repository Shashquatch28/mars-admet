import sys
from pathlib import Path
import os
from configs.clusters import type_homogeneous_subgroups
from configs.experiment_config import ExperimentConfig
from data.cluster_loaders import load_cluster
from train.train_kermt_mixed import train_one_seed_mixed

seed = int(sys.argv[1])
PREP = Path("data/processed") / os.environ["PREP_ID"]
CKPT = Path("data/checkpoints/kermt/NV-KERMT-70M-v2/kermt_contrastive_v2.0.pt")
keys = list(type_homogeneous_subgroups("toxicity")["toxicity__cls"].endpoints)
cd = load_cluster(PREP, keys, cluster_key="toxicity__cls")
cfg = ExperimentConfig("toxicity__cls", "kermt_mixed", seed, cd.prep_id, notes="G3 parity, mode=fixed")
res = train_one_seed_mixed(cd, cfg, seed, checkpoint=CKPT, loss_mode="fixed", min_per_task=0,
                           hyperparameter_source="parity-gate", runs_dir=Path("runs"), use_wandb=True)
print({k: res.per_endpoint_metrics[k].auroc for k in keys}, res.run_id)
