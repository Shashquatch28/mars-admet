"""
Zero-GPU preflight for the KERMT cluster work. Run this BEFORE any lab session.

Answers the two questions that gate GPU spend, both on CPU, both from real M1
data:

1. **What does leakage-safe cluster assembly cost?** Building a shared-encoder
   cluster means removing the union of every member endpoint's test set from the
   shared train_val (see ``data.cluster_loaders``). If that sacrifices most of an
   endpoint's labels, the honest response is to narrow the cluster, not to train
   it anyway and discover the damage in the results.

2. **How many ordinal bins does Tier 2 need, and is Tier 2 even viable?**
   Discretizing a regression target puts a floor under achievable MAE that no
   model can beat. ``featurize.ordinal.discretization_ceiling_mae`` measures that
   floor exactly, with no training at all, by encoding true labels and decoding
   them straight back. Compared here against the completed XGBoost baseline MAE.

Neither check needs a GPU, the KERMT checkout, or the docker image — only
``ml/data/processed/<prep_id>/``.

Usage
-----
    cd ml && PYTHONPATH=. python train/preflight_clusters.py
    cd ml && PYTHONPATH=. python train/preflight_clusters.py --prep-dir data/processed/<id>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from configs.clusters import (
    CLUSTER_KEYS,
    all_subgroups,
    cluster_members,
    mixed_clusters,
)
from data.cluster_loaders import load_cluster
from featurize.ordinal import discretization_ceiling_mae, fit_ordinal_codec
from mars_contracts.endpoints import TaskType

# A cluster arm that throws away more than this fraction of any member's
# training labels is reported as a warning — it is a judgement call for the
# maintainer, not an automatic stop.
SACRIFICE_WARN_FRACTION = 0.20

# Tier 2 is only worth running if the pure discretization floor is small
# relative to what direct regression already achieves.
CEILING_MAX_FRACTION_OF_BASELINE = 0.25

CANDIDATE_BINS = (4, 8, 16, 32)


def _newest_prep_dir(ml_root: Path) -> Path | None:
    root = ml_root / "data" / "processed"
    if not root.exists():
        return None
    dirs = sorted(p for p in root.iterdir() if p.is_dir())
    return dirs[-1] if dirs else None


def _baseline_mae(ml_root: Path, endpoint_key: str) -> float | None:
    """Completed XGBoost 5-seed mean MAE for *endpoint_key*, if it exists."""
    path = ml_root / "runs" / "evaluations" / f"{endpoint_key}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    value = data.get("aggregated", {}).get("mae_mean")
    return float(value) if value is not None else None


def audit_split_costs(prep_dir: Path) -> dict[str, Any]:
    """ClusterSplitReport for every subgroup and every mixed cluster."""
    groups: dict[str, list[str]] = {
        key: list(spec.endpoints) for key, spec in all_subgroups().items()
    }
    # The mixed clusters are also assembled whole — that is what Tier 1 trains.
    for cluster in mixed_clusters():
        groups[cluster] = cluster_members(cluster)

    out: dict[str, Any] = {}
    for key, endpoints in sorted(groups.items()):
        try:
            cd = load_cluster(prep_dir, endpoints, cluster_key=key)
        except FileNotFoundError as exc:
            out[key] = {"status": "skipped", "reason": str(exc)}
            continue
        report = cd.split_report.to_dict()
        worst = max(report["sacrifice_fraction"].values(), default=0.0)
        report["status"] = "warn" if worst > SACRIFICE_WARN_FRACTION else "ok"
        report["worst_sacrifice_fraction"] = worst
        out[key] = report
    return out


def audit_ordinal_ceilings(prep_dir: Path, ml_root: Path) -> dict[str, Any]:
    """Discretization floor per regression endpoint, per candidate bin count."""
    from configs.clusters import endpoint_task_types

    reg_endpoints = [
        key
        for cluster in CLUSTER_KEYS
        for key, tt in endpoint_task_types(cluster_members(cluster)).items()
        if tt is TaskType.REGRESSION
    ]

    out: dict[str, Any] = {}
    for key in sorted(reg_endpoints):
        try:
            cd = load_cluster(prep_dir, [key], cluster_key=key)
        except FileNotFoundError as exc:
            out[key] = {"status": "skipped", "reason": str(exc)}
            continue

        y = cd.label_matrix("train_val")[:, 0]
        y = y[~np.isnan(y)]
        baseline = _baseline_mae(ml_root, key)

        per_bins: dict[str, Any] = {}
        recommended: int | None = None
        for n_bins in CANDIDATE_BINS:
            try:
                codec = fit_ordinal_codec(y, n_bins=n_bins)
            except ValueError as exc:
                per_bins[str(n_bins)] = {"error": str(exc)}
                continue
            ceiling = discretization_ceiling_mae(codec, y)
            entry: dict[str, Any] = {
                "n_thresholds": codec.n_thresholds,
                "ceiling_mae": ceiling,
            }
            if baseline:
                entry["fraction_of_baseline_mae"] = ceiling / baseline
                if (
                    recommended is None
                    and ceiling / baseline <= CEILING_MAX_FRACTION_OF_BASELINE
                ):
                    recommended = n_bins
            per_bins[str(n_bins)] = entry

        out[key] = {
            "status": "ok" if recommended is not None else "warn",
            "n_labels": int(y.size),
            "baseline_xgboost_mae": baseline,
            "recommended_n_bins": recommended,
            "per_bins": per_bins,
        }
    return out


def main(argv: list[str] | None = None) -> int:
    ml_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prep-dir",
        default=None,
        help="Processed M1 snapshot (default: newest under ml/data/processed/).",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Where to write the JSON report (default: ml/runs/cluster_preflight.json).",
    )
    args = parser.parse_args(argv)

    prep_dir = Path(args.prep_dir) if args.prep_dir else _newest_prep_dir(ml_root)
    if prep_dir is None or not prep_dir.exists():
        print(
            "No processed M1 data found. Run ml/data/acquire.py + prepare.py first "
            "(see ml/data/acquisition/README.md).",
            file=sys.stderr,
        )
        return 2

    print(f"prep_dir: {prep_dir}\n")

    split_costs = audit_split_costs(prep_dir)
    ordinal = audit_ordinal_ceilings(prep_dir, ml_root)

    print("=== Leakage-safe cluster assembly cost ===")
    for key, rep in split_costs.items():
        if rep.get("status") == "skipped":
            print(f"  {key:38s} SKIP  {rep['reason'][:60]}")
            continue
        worst = rep["worst_sacrifice_fraction"]
        print(
            f"  {key:38s} {rep['status'].upper():4s} "
            f"rows={rep['n_train_val_rows']:6d} "
            f"dropped={rep['n_rows_dropped_from_train_val']:5d} "
            f"worst_sacrifice={worst:6.1%}"
        )
        for ep, frac in sorted(rep["sacrifice_fraction"].items()):
            if frac > SACRIFICE_WARN_FRACTION:
                lost = rep["labels_sacrificed"][ep]
                kept = rep["labels_retained"][ep]
                print(f"      ! {ep}: lost {lost} of {lost + kept} labels ({frac:.1%})")

    print("\n=== Tier 2 ordinal discretization ceiling ===")
    for key, rep in ordinal.items():
        if rep.get("status") == "skipped":
            print(f"  {key:28s} SKIP")
            continue
        base = rep["baseline_xgboost_mae"]
        base_s = f"{base:.4f}" if base else "n/a"
        print(
            f"  {key:28s} {rep['status'].upper():4s} "
            f"n={rep['n_labels']:6d} xgb_mae={base_s:>8s} "
            f"recommended_n_bins={rep['recommended_n_bins']}"
        )
        for n_bins, entry in rep["per_bins"].items():
            if "error" in entry:
                continue
            frac = entry.get("fraction_of_baseline_mae")
            frac_s = f" ({frac:.1%} of baseline)" if frac is not None else ""
            print(f"      bins={n_bins:>3s}  ceiling_mae={entry['ceiling_mae']:.4f}{frac_s}")

    out_path = Path(args.out) if args.out else ml_root / "runs" / "cluster_preflight.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "prep_dir": str(prep_dir),
                "split_costs": split_costs,
                "ordinal_ceilings": ordinal,
                "thresholds": {
                    "sacrifice_warn_fraction": SACRIFICE_WARN_FRACTION,
                    "ceiling_max_fraction_of_baseline": CEILING_MAX_FRACTION_OF_BASELINE,
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nWrote {out_path}")

    warned = [k for k, v in split_costs.items() if v.get("status") == "warn"]
    if warned:
        print(
            "\nWARNING: these cluster arms sacrifice >"
            f"{SACRIFICE_WARN_FRACTION:.0%} of some member's labels: {warned}\n"
            "That is a maintainer judgement call, not an automatic stop — but "
            "decide it before spending GPU time."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
