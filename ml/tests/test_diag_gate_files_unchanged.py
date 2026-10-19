"""The diagnostic re-run must not change the gate-staged trainer: every file recorded in the G3 runs' trainer_provenance.json
still hashes to the recorded value. Skipped when the runs are not on this machine."""
import glob
import hashlib
import json
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "train" / "kermt_mixed"


def test_gate_staged_files_byte_identical_to_g3_runs():
    runs = sorted(glob.glob(str(Path(__file__).resolve().parents[1] / "runs/kermt_mx_toxicity__cls_seed*_fixed_*/artifacts/kermt/trainer_provenance.json")))
    if not runs:
        pytest.skip("G3 runs not present")
    for r in runs:
        for name, digest in json.loads(Path(r).read_text())["files"].items():
            assert hashlib.sha256((SRC / name).read_bytes()).hexdigest() == digest, (r, name)
