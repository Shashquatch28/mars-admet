"""
Build the held-out-error band (frontend ADR-024) for the regression endpoints KERMT serves, and write it
next to the XGBoost band as ``<artifacts>/<endpoint>/kermt_error_band.json``.

Same construction as ``build_error_bands.py``: for each seed, regenerate the scaffold partition that seed
trained on, score that seed's model on its own validation fold, pool the five folds' absolute residuals
and take the ceil((n+1)*level)-th smallest. The difference is where the models live: KERMT's 25
checkpoints run in the inference service, so each seed is scored by calling it.

KERMT's training pool is not the endpoint's ``train_val``: it is the arm's wide table with the calibration
molecules held out, folded once per arm (``train_kermt_cluster.train_one_seed``). This script rebuilds
exactly that pool, and ``--verify-val arm=path`` checks the regenerated seed-0 validation fold against the
``val.csv`` KERMT was actually handed (a W&B run-record artifact), so a changed snapshot or split cannot
slip through unnoticed.

The service must have loaded all five seeds of each arm (``KERMT_SEEDS=0,1,2,3,4``).

Usage
-----
    cd ml && PYTHONPATH=. python train/build_kermt_error_bands.py --service-url http://localhost:18100 \
        --verify-val metabolism__reg=<record>/artifacts/kermt/input/val.csv
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
from data.cluster_loaders import load_cluster
from data.split import five_seed_train_val_folds
from eval.error_band import DEFAULT_LEVEL, build_error_band
from serve.registry import KERMT_ERROR_BAND_FILENAME
from serve.routing import KERMT_ARMS, RoutingTable

DEFAULT_PREP_ID = "20260830T200000Z"  # local snapshot; KERMT trained under 20260918T090433Z (see --verify-val)
SMILES_COL = "standardized_smiles"
BATCH = 128


class _SeedModel:
    """Adapts one (arm, target, seed) in the service to the `.predict(smiles)` that `build_error_band` expects."""

    def __init__(self, http: httpx.Client, arm: str, target: str, seed: int) -> None:
        self.http, self.arm, self.target, self.seed = http, arm, target, seed

    def predict(self, smiles: list[str]) -> np.ndarray:
        out: list[float] = []
        for i in range(0, len(smiles), BATCH):
            r = self.http.post("/predict", json={"smiles": smiles[i : i + BATCH], "arms": [self.arm]})
            r.raise_for_status()
            arm = r.json()["arms"][self.arm]
            col = arm["seeds"].index(self.seed)  # raises if that seed is not loaded: the band needs every seed
            out.extend(float("nan") if row[col] is None else row[col] for row in arm["values"][self.target])
        return np.array(out, dtype=float)


def regression_arm_endpoints(routing: RoutingTable) -> list[tuple[str, str]]:
    """(arm, endpoint) for every endpoint routed to KERMT whose arm is a regression arm."""
    return [(r.kermt_arm, e) for e in sorted(routing.kermt_endpoint_set()) if (r := routing.route(e)).kermt_arm.endswith("__reg")]


def main(argv: list[str] | None = None) -> int:
    ml_root = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--service-url", required=True)
    p.add_argument("--prep-id", default=DEFAULT_PREP_ID)
    p.add_argument("--artifacts-root", default=str(ml_root / "artifacts"))
    p.add_argument("--level", type=float, default=DEFAULT_LEVEL)
    p.add_argument("--verify-val", action="append", default=[], metavar="ARM=CSV", help="seed-0 val.csv KERMT trained with")
    p.add_argument("--endpoints", nargs="*", default=None, help="subset of KERMT-served regression endpoints")
    args = p.parse_args(argv)

    prep_dir = ml_root / "data" / "processed" / args.prep_id
    if not prep_dir.exists():
        print(f"Processed snapshot not found: {prep_dir}", file=sys.stderr)
        return 2
    wanted = regression_arm_endpoints(RoutingTable.load())
    if args.endpoints:
        wanted = [(a, e) for a, e in wanted if e in args.endpoints]
    if not wanted:
        print("No KERMT-served regression endpoints to build.", file=sys.stderr)
        return 1
    expected_val = dict(item.split("=", 1) for item in args.verify_val)

    http = httpx.Client(base_url=args.service_url.rstrip("/"), timeout=600)
    status = 0
    folds_by_arm: dict[str, tuple[list, dict]] = {}
    for arm, endpoint in wanted:
        t0 = time.time()
        if arm not in folds_by_arm:
            cluster = load_cluster(prep_dir, list(KERMT_ARMS[arm]), cluster_key=arm)
            pool, _ = cluster.train_pool(holdout_calibration=True)
            folds = five_seed_train_val_folds(pool[SMILES_COL].tolist())
            folds_by_arm[arm] = (folds, {e: dict(zip(pool[SMILES_COL], pool[e].astype(float), strict=True)) for e in KERMT_ARMS[arm]})
            if arm in expected_val:
                got = set(folds[0][2])
                want = set(pd.read_csv(expected_val[arm])["smiles"])
                print(f"seed-0 validation fold for {arm}: regenerated {len(got)}, recorded {len(want)}, "
                      f"{'IDENTICAL' if got == want else 'DIFFERENT'}", flush=True)
                if got != want:
                    print(f"STOP {arm}: the regenerated folds are not the ones KERMT trained with", file=sys.stderr)
                    return 3
            else:
                print(f"warning: {arm} fold not verified against a recorded val.csv", file=sys.stderr)
        folds, labels = folds_by_arm[arm]
        models = {seed: _SeedModel(http, arm, endpoint, seed) for seed in range(5)}
        # only labelled molecules count for this endpoint (multi-task wide tables hold NaN where a task has no label)
        ep_labels = {s: v for s, v in labels[endpoint].items() if not np.isnan(v)}
        ep_folds = [(seed, tr, [s for s in va if s in ep_labels]) for seed, tr, va in folds]
        band = build_error_band(endpoint, models, ep_folds, ep_labels, level=args.level)
        band.save(Path(args.artifacts_root) / endpoint / KERMT_ERROR_BAND_FILENAME)
        print(f"OK {endpoint:24s} halfwidth={band.halfwidth:.4g} n={band.n_residuals:5d} ({time.time() - t0:.0f}s)", flush=True)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
