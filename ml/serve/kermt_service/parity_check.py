"""Check the in-process engine against predictions the stock KERMT CLI produced on the GPU.

The reference is a W&B run-record artifact (`kermt-<arm>-seed0-record:v0`, 2026-09-30 runs): its
`predictions/<split>/input/smiles.csv` went through `main.py predict` on the workstation and the
result is `predictions/<split>/out/predictions.csv`. This feeds the same SMILES to `KermtEngine`
and reports the largest absolute difference per target.

    python parity_check.py --root /models --arm metabolism__cls --seed 0 \
        --record /record --split test --n 256 [--max-abs 1e-4]

Exit status 1 if any target differs by more than --max-abs (default 1e-4: the CPU and GPU
builds are different float kernels, so bit-equality is not expected, and a drift larger than
the 4th decimal would be a real featurization or loading difference).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine import KermtEngine  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True, help="serving layout root (<arm>/seed_<n>/model.pt)")
    p.add_argument("--arm", required=True)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--record", required=True, help="downloaded run-record artifact directory")
    p.add_argument("--split", default="test", choices=["val", "calibration", "test"])
    p.add_argument("--n", type=int, default=256)
    p.add_argument("--max-abs", type=float, default=1e-4)
    args = p.parse_args(argv)

    rec = Path(args.record) / "predictions" / args.split
    smiles = pd.read_csv(rec / "input" / "smiles.csv")["smiles"].tolist()[: args.n]
    ref = pd.read_csv(rec / "out" / "predictions.csv", index_col=0).iloc[: args.n]

    engine = KermtEngine(args.root, arms=[args.arm], seeds=[args.seed])
    t0 = time.perf_counter()
    engine.load_all()
    load_s = time.perf_counter() - t0
    t0 = time.perf_counter()
    res = engine.predict(smiles)[args.arm]
    pred_s = time.perf_counter() - t0
    got = res.by_seed[args.seed]

    worst = 0.0
    for j, name in enumerate(res.target_names):
        d = np.abs(got[:, j] - ref[name].to_numpy(dtype=float))
        worst = max(worst, float(np.nanmax(d)))
        print(f"{name:28s} max|diff| {np.nanmax(d):.3e}  mean|diff| {np.nanmean(d):.3e}  nan {int(np.isnan(got[:, j]).sum())}")
    print(f"n={len(smiles)} load {load_s:.1f}s predict {pred_s:.2f}s ({1000 * pred_s / len(smiles):.1f} ms/molecule/model)")
    print("PARITY", "PASS" if worst <= args.max_abs else "FAIL", f"(worst {worst:.3e}, limit {args.max_abs:g})")
    return 0 if worst <= args.max_abs else 1


if __name__ == "__main__":
    raise SystemExit(main())
