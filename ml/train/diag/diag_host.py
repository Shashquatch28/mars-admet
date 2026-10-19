"""Host driver for the DIAGNOSTIC mixed re-run (``train/diag/diag_run_mixed.py``). Not a gate; nothing here touches the G3 record.

    python -m train.diag.diag_host prepare --seed 3 --run-dir runs/diag_kermt_mx_toxicity__cls_seed3_fixed_<ts> [--cpu-smoke]
    python -m train.diag.diag_host launch  --run-dir <dir> [--resume] [-- <extra diag_run_mixed args>]

``prepare`` stages the ORIGINAL run's prepared inputs (same folds, same argv), the unmodified gate-staged trainer package, the diagnostic script
and the calibration-holdout features, and writes ``provenance.json`` (git HEAD + dirty flag, image id, sha256 of every staged and diagnostic file).
Reads no test data: the original run's ``clean_test.*`` is a copy of ``clean_val.*`` (asserted) and is only there to satisfy the argv.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

from configs.clusters import type_homogeneous_subgroups
from data.cluster_loaders import SMILES_COL, load_cluster
from models.kermt_mixed_model import stage_trainer
from models.kermt_model import _DEFAULT_KERMT_IMAGE, _ENV_KERMT_IMAGE, _kermt_repo

CKPT = Path("data/checkpoints/kermt/NV-KERMT-70M-v2/kermt_contrastive_v2.0.pt")
HOLDOUT_SRC = Path("runs/tier1_gates/selection_free/work_mixed_seed3")  # prepare_data output for the 1,626 calibration molecules


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def prepare(seed: int, run_dir: Path) -> None:
    orig = sorted(Path("runs").glob(f"kermt_mx_toxicity__cls_seed{seed}_fixed_*"))
    assert len(orig) == 1, orig
    src = orig[0] / "artifacts/kermt"
    stage = run_dir / "stage"
    (stage / "data").mkdir(parents=True); (stage / "holdout").mkdir(); (run_dir / "out").mkdir()
    for f in ("clean_train.csv", "clean_train.npz", "clean_val.csv", "clean_val.npz"):
        shutil.copy2(src / "data" / f, stage / "data" / f)
    assert (src / "data/clean_test.csv").read_bytes() == (src / "data/clean_val.csv").read_bytes(), "clean_test is not the val placeholder"
    shutil.copy2(src / "data/clean_val.csv", stage / "data/clean_test.csv"); shutil.copy2(src / "data/clean_val.npz", stage / "data/clean_test.npz")
    shutil.copy2(src / "run.json", stage / "run.json"); shutil.copy2(src / "input/_mars_trainer/spec.json", stage / "spec.json")
    # calibration holdout: the deployed-path prepared features + labels in the same row order
    pred = sorted(HOLDOUT_SRC.glob("predict_*/data"))[0]
    shutil.copy2(pred / "clean.csv", stage / "holdout/clean.csv"); shutil.copy2(pred / "clean.npz", stage / "holdout/clean.npz")
    keys = list(type_homogeneous_subgroups("toxicity")["toxicity__cls"].endpoints)
    cd = load_cluster(Path("data/processed") / os.environ["PREP_ID"], keys, cluster_key="toxicity__cls")
    cal = cd.calibration.set_index(SMILES_COL)
    smi = [l.rstrip("\n") for l in (stage / "holdout/clean.csv").read_text().splitlines()[1:]]
    assert len(smi) == len(cal) == 1626 and set(smi) == set(cal.index), "holdout rows != calibration molecules"
    np.save(stage / "holdout/labels.npy", cal.loc[smi, keys].to_numpy(dtype=float))
    staged = stage_trainer(stage / "_stage")
    shutil.copy2(Path(__file__).parent / "diag_run_mixed.py", stage / "diag_run_mixed.py")
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
    image = subprocess.run(["docker", "image", "inspect", "kermt:latest", "--format", "{{.Id}}"], capture_output=True, text=True).stdout.strip()
    prov = {"diagnostic": True, "not_part_of_G3_record": True, "seed": seed, "original_run": orig[0].name, "git_head": head,
            "git_tree_dirty": bool(dirty), "kermt_image_id": image, "gate_staged_trainer": staged,
            "diag_script_sha256": sha(Path(__file__).parent / "diag_run_mixed.py"), "diag_host_sha256": sha(Path(__file__)),
            "original_trainer_provenance": json.loads((src / "trainer_provenance.json").read_text())}
    prov["gate_staged_files_equal_original_run"] = all(staged["files"].get(k) == v for k, v in prov["original_trainer_provenance"]["files"].items())
    (run_dir / "provenance.json").write_text(json.dumps(prov, indent=2))
    print("prepared", run_dir, "gate-staged files equal original run:", prov["gate_staged_files_equal_original_run"], "dirty:", prov["git_tree_dirty"])


def launch(run_dir: Path, resume: bool, extra: list[str], cpu: bool) -> int:
    repo = _kermt_repo(); image = os.environ.get(_ENV_KERMT_IMAGE, _DEFAULT_KERMT_IMAGE)
    stage = (run_dir / "stage").resolve()
    env = os.environ.copy(); env["KERMT_REPO"] = str(repo); env["KERMT_IMAGE"] = image
    inner = ("CUBLAS_WORKSPACE_CONFIG=:4096:8 " + ("CUDA_VISIBLE_DEVICES= " if cpu else "") +
             "PYTHONPATH=/data/_stage:${PYTHONPATH:-} python -u /data/diag_run_mixed.py " + ("--resume " if resume else "") + " ".join(extra))
    argv = [str(repo / "agent/scripts/kermt_container.sh"), "run", "--data", str(stage), "--ckpt", str(CKPT.resolve()),
            "--run-dir", str((run_dir / "out").resolve()), "--", inner]
    with (run_dir / ("container_resume.log" if resume else "container.log")).open("a") as fh:
        return subprocess.run(argv, env=env, stdout=fh, stderr=subprocess.STDOUT).returncode


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare"); p.add_argument("--seed", type=int, required=True); p.add_argument("--run-dir", required=True)
    l = sub.add_parser("launch"); l.add_argument("--run-dir", required=True); l.add_argument("--resume", action="store_true")
    l.add_argument("--cpu", action="store_true"); l.add_argument("extra", nargs="*")
    a = ap.parse_args()
    if a.cmd == "prepare":
        prepare(a.seed, Path(a.run_dir))
    else:
        sys.exit(launch(Path(a.run_dir), a.resume, a.extra, a.cpu))
