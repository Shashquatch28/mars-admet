"""Host driver for ``eval/g2_extension.py`` (Phase A, no training): stages a mixed run's inputs + the trainer package and
runs the check inside the KERMT container. Usage: python -m eval.g2_extension_host <work_dir> <mixed_run_dir>"""
import json
import os
import shutil
import sys
from pathlib import Path

from models.kermt_mixed_model import stage_trainer
from models.kermt_model import _DEFAULT_KERMT_IMAGE, _ENV_KERMT_IMAGE, _kermt_repo, _run_container

work = Path(sys.argv[1]).resolve(); run = Path(sys.argv[2]).resolve()
ckpt = Path("data/checkpoints/kermt/NV-KERMT-70M-v2/kermt_contrastive_v2.0.pt").resolve()
shutil.rmtree(work, ignore_errors=True); (work / "data").mkdir(parents=True); (work / "out").mkdir()
src = run / "artifacts/kermt"
for f in ("clean_train.csv", "clean_train.npz", "clean_val.csv", "clean_val.npz"):
    shutil.copy2(src / "data" / f, work / "data" / f)
# the mixed arm's "test" files are a copy of val (test set never given to the trainer); verified, then reused as-is
assert (src / "data/clean_test.csv").read_bytes() == (src / "data/clean_val.csv").read_bytes(), "clean_test.csv is not the val placeholder"
shutil.copy2(src / "data/clean_val.csv", work / "data/clean_test.csv"); shutil.copy2(src / "data/clean_val.npz", work / "data/clean_test.npz")
shutil.copy2(src / "run.json", work / "run.json")
shutil.copy2(src / "input/_mars_trainer/spec.json", work / "spec.json")
os.link(run / "artifacts/model/kermt_mixed/model.pt", work / "mixed_model.pt")
shutil.copy2(Path(__file__).parent / "g2_extension.py", work / "g2_extension.py")
stage_trainer(work / "_stage")
repo = _kermt_repo()
image = os.environ.get(_ENV_KERMT_IMAGE, _DEFAULT_KERMT_IMAGE)
cmd = ("CUBLAS_WORKSPACE_CONFIG=:4096:8 PYTHONPATH=/data/_stage:${PYTHONPATH:-} python -u /data/g2_extension.py")
proc = _run_container(repo, image, data=work, ckpt=ckpt, run_dir=work / "out", command=cmd)
print(proc.stdout[-6000:]); print(proc.stderr[-3000:], file=sys.stderr)
sys.exit(proc.returncode)
