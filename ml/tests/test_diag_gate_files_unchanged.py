"""The diagnostic re-run must not change the gate-staged trainer: every file recorded in the G3 runs' trainer_provenance.json
still hashes to the recorded value. Skipped when the runs are not on this machine."""
import glob
import hashlib
import json
import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "train" / "kermt_mixed"


def test_gate_staged_files_byte_identical_to_g3_runs():
    runs = sorted(glob.glob(str(Path(__file__).resolve().parents[1] / "runs/kermt_mx_toxicity__cls_seed*_fixed_*/artifacts/kermt/trainer_provenance.json")))
    if not runs:
        pytest.skip("G3 runs not present")
    for r in runs:
        for name, digest in json.loads(Path(r).read_text())["files"].items():
            data = (SRC / name).read_bytes()
            if name == "train_mixed.py":
                # The only permitted change since the G3 runs is the marked logging block; with exactly that block
                # removed the file must still hash to the G3 value.
                data = re.sub(rb"[ ]*# BEGIN effective-args logging.*?# END effective-args logging\n", b"", data, flags=re.S)
            assert hashlib.sha256(data).hexdigest() == digest, (r, name)
