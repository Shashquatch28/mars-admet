"""A2 follow-up (inside the KERMT container): for EVERY name in kermt.util.utils.get_model_args(), the value the CLI argv gives,
the value saved in the pretrain checkpoint, and the value in force after load_checkpoint(current_args=args). Inference-free, no training."""
import json, sys
from pathlib import Path
import torch
sys.path.insert(0, "/data/_stage")
from kermt.util.parsing import parse_args
from kermt.util.utils import get_model_args, load_checkpoint
from kermt_mixed.train_mixed import finetune_argv_tail
tail = [t.replace("/runs/data/", "/data/data/") for t in finetune_argv_tail("/data/run.json")]
sys.argv = ["main.py", *tail]
args = parse_args()
names = get_model_args()
cli = {k: getattr(args, k, "<absent>") for k in names}
ck = vars(torch.load("/ckpt", map_location="cpu", weights_only=False)["args"])
saved = {k: ck.get(k, "<absent in checkpoint>") for k in names}
from kermt.util.utils import get_data
args.task_names = ["herg_cardiotoxicity", "ames_mutagenicity"]
tr = get_data(path=args.data_path, args=args)
args.features_dim = len(tr.data[0].features) if tr.data[0].features is not None else 0
args.num_tasks = tr.num_tasks(); args.features_size = tr.features_size(); args.train_data_size = len(tr)
model, _ = load_checkpoint(args.checkpoint_paths[0], current_args=args)
post = {k: getattr(args, k, "<absent>") for k in names}
rows = {k: {"cli": cli[k], "checkpoint": saved[k], "after_load": post[k], "overwritten": cli[k] != post[k]} for k in names}
Path("/runs/a2_all_model_args.json").write_text(json.dumps(rows, indent=1, default=str))
print(json.dumps({k: v for k, v in rows.items() if v["overwritten"]}, indent=1, default=str))
print("n names", len(names), "overwritten:", [k for k, v in rows.items() if v["overwritten"]])
