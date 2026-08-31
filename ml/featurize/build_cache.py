"""
Populate the feature cache from the M1 processed datasets.

Reads ``ml/data/processed/<prep_id>/<dataset>/{train_val,test,calibration}.csv``
(columns: ``standardized_smiles``, ``label``), collects the union of unique
standardized SMILES, and warms the requested cache stages for them.

Morgan / descriptors / graph are cheap and run over everything by default.
3D conformers are expensive and lazy (blueprint Module 3 Stage 5) — off unless
``--conformer-sample N`` is given, in which case only a deterministic N-molecule
sample is embedded (enough to smoke-test the path + get timing numbers).

Writes ``ml/data/cache/build_report.json`` with per-stage hit/miss/compute
counts and wall-clock timing.

Deterministic. Idempotent — re-running only computes cache misses.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from featurize.cache import FeatureCache


def _collect_smiles(processed_dir: Path, only: list[str] | None) -> dict[str, list[str]]:
    per_dataset: dict[str, list[str]] = {}
    for ds_dir in sorted(p for p in processed_dir.iterdir() if p.is_dir()):
        if only and ds_dir.name not in only:
            continue
        smis: set[str] = set()
        for part in ("train_val.csv", "test.csv", "calibration.csv"):
            f = ds_dir / part
            if not f.exists():
                continue
            with f.open(newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    smis.add(row["standardized_smiles"])
        if smis:
            per_dataset[ds_dir.name] = sorted(smis)
    return per_dataset


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", type=Path, default=Path(".."))
    ap.add_argument("--prep-id", default=None, help="default: newest under processed/")
    ap.add_argument("--only", nargs="*", default=None, help="subset of dataset dir names")
    ap.add_argument(
        "--stages",
        default="morgan,descriptors,graph",
        help="comma list from {morgan,descriptors,graph,conformer}",
    )
    ap.add_argument("--conformer-sample", type=int, default=0)
    args = ap.parse_args()

    repo = args.repo_root.resolve()
    processed_root = repo / "ml" / "data" / "processed"
    if args.prep_id:
        processed_dir = processed_root / args.prep_id
    else:
        dirs = sorted(p for p in processed_root.iterdir() if p.is_dir())
        if not dirs:
            print("no processed datasets; run ml/data/prepare.py first")
            return 2
        processed_dir = dirs[-1]

    stages = [s.strip() for s in args.stages.split(",") if s.strip()]
    cache = FeatureCache(repo / "ml" / "data" / "cache")
    per_dataset = _collect_smiles(processed_dir, args.only)
    all_smiles = sorted({s for lst in per_dataset.values() for s in lst})

    print(f"prep_id={processed_dir.name}  datasets={len(per_dataset)}  unique_smiles={len(all_smiles)}")
    report: dict = {
        "generated_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "prep_id": processed_dir.name,
        "n_datasets": len(per_dataset),
        "n_unique_smiles": len(all_smiles),
        "stages": {},
    }

    if "morgan" in stages:
        t = time.perf_counter()
        _m, _d, st = cache.morgan_cached(all_smiles)
        report["stages"]["morgan"] = {**vars(st), "seconds": round(time.perf_counter() - t, 1)}
        print("  morgan:", report["stages"]["morgan"])

    if "descriptors" in stages:
        t = time.perf_counter()
        _m, _mask, _d, _nf, st = cache.descriptors_cached(all_smiles)
        report["stages"]["descriptors"] = {**vars(st), "seconds": round(time.perf_counter() - t, 1)}
        print("  descriptors:", report["stages"]["descriptors"])

    if "graph" in stages:
        t = time.perf_counter()
        _g, _d, st = cache.graphs_cached(all_smiles)
        report["stages"]["graph"] = {**vars(st), "seconds": round(time.perf_counter() - t, 1)}
        print("  graph:", report["stages"]["graph"])

    if "conformer" in stages or args.conformer_sample:
        n = args.conformer_sample or 200
        # deterministic sample: every k-th SMILES
        step = max(1, len(all_smiles) // n)
        sample = all_smiles[::step][:n]
        t = time.perf_counter()
        results, st = cache.conformers_cached(sample)
        n_mmff = sum(1 for r in results if r.ok and r.force_field == "MMFF94")
        n_uff = sum(1 for r in results if r.ok and r.force_field == "UFF")
        n_fail = sum(1 for r in results if not r.ok)
        report["stages"]["conformer"] = {
            **vars(st),
            "sample_size": len(sample),
            "mmff94": n_mmff,
            "uff": n_uff,
            "failed": n_fail,
            "seconds": round(time.perf_counter() - t, 1),
        }
        print("  conformer:", report["stages"]["conformer"])

    out = repo / "ml" / "data" / "cache" / "build_report.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(repo)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
