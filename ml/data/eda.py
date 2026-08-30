"""
MARS M1 EDA — the lightweight per-dataset audit that gates dedup / split /
augmentation decisions (blueprint Module 1 §3, Module 3 §Stereochemistry).

Purpose: for every acquired dataset, answer the questions Module 1 needs to
decide policy *from data* rather than assumption:

  * dataset size (raw / after standardization)
  * SMILES validity rate (per rejection reason)
  * duplicate rate at standardized-molecule identity
  * conflict rate (same molecule, different labels)
  * class balance (classification) / target distribution (regression)
  * stereo-defined ratio (blueprint Module 3 §Stereochemistry — CYP2C9/3A4/2D6,
    Caco2, Pgp, BBB flagged)
  * scaffold diversity (unique Murcko scaffolds / molecule; largest bucket)

Reads the acquisition lockfile + the raw CSVs on disk. Writes one JSON per
dataset + a top-level roll-up JSON + a human-readable Markdown summary under
``ml/data/eda/<eda_id>/``. Deterministic.

Not a script only — the core is a library ``run_eda(specs, data_root)`` that
returns per-dataset dicts, callable from tests.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from featurize.scaffold import murcko_scaffolds_batch
from featurize.standardize import STANDARDIZER_VERSION, rejection_summary, standardize_batch

# Endpoints whose stereochemistry deserves particular attention per blueprint
# Module 3 §Stereochemistry.
STEREO_FLAGGED_ENDPOINTS = frozenset(
    {
        "cyp2c9_inhibition",
        "cyp3a4_inhibition",
        "cyp2d6_inhibition",
        "caco2_permeability",
        "pgp_inhibition",
        "bbb_permeability",
    }
)


@dataclass(frozen=True)
class DatasetEDA:
    dataset_key: str
    endpoint_key: str
    variant: str
    task: str
    tdc_name: str
    stats: dict[str, Any]


def _load_lock(data_root: Path) -> dict:
    lock = data_root / "metadata" / "datasets.lock.json"
    return json.loads(lock.read_text(encoding="utf-8"))


def _load_csv_rows(path: Path, smiles_col: str, label_col: str) -> tuple[list[str], list[str]]:
    smis: list[str] = []
    ys: list[str] = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            smis.append(row[smiles_col])
            ys.append(row[label_col])
    return smis, ys


def _classification_conflict(labels: list[float]) -> bool:
    """Any two different labels → conflict (0 vs 1)."""
    return len(set(labels)) > 1


def _regression_conflict(labels: list[float], rel_tol: float = 0.05, abs_tol: float = 1e-6) -> bool:
    """Regression conflict if the label range exceeds max(|mean|*rel_tol, abs_tol).

    This is a *lightweight* signal for EDA (real conflict resolution is
    done downstream in dedup with the blueprint's tiered logic); it just
    labels a group as conflicting-or-not so the per-endpoint conflict rate
    can be computed.
    """
    lo, hi = min(labels), max(labels)
    mean_abs = sum(abs(x) for x in labels) / len(labels)
    tol = max(abs_tol, rel_tol * mean_abs)
    return (hi - lo) > tol


def _target_stats(labels: list[float]) -> dict[str, float]:
    labels = sorted(labels)
    n = len(labels)
    mean = sum(labels) / n
    var = sum((x - mean) ** 2 for x in labels) / n
    return {
        "n": n,
        "min": labels[0],
        "p25": labels[n // 4],
        "median": labels[n // 2],
        "p75": labels[(3 * n) // 4],
        "max": labels[-1],
        "mean": mean,
        "std": var**0.5,
    }


def _class_balance(labels: list[float]) -> dict[str, Any]:
    counts = Counter(int(x) for x in labels)
    total = sum(counts.values())
    return {
        "counts": {str(k): v for k, v in sorted(counts.items())},
        "positive_fraction": counts.get(1, 0) / total if total else None,
    }


def _analyze(
    *,
    dataset_key: str,
    endpoint_key: str,
    variant: str,
    task: str,
    tdc_name: str,
    raw_smiles: list[str],
    raw_labels: list[str],
) -> DatasetEDA:
    # Standardize the whole dataset (batched, per blueprint Module 3 non-negotiable)
    std = standardize_batch(raw_smiles)
    rej = rejection_summary(std)
    n_raw = len(raw_smiles)
    n_ok = rej.get("ok", 0)

    # Standardized dataset with parsed labels
    ok_pairs: list[tuple[str, float, bool]] = []
    parse_failures = 0
    for row, y in zip(std, raw_labels, strict=True):
        if not row.ok:
            continue
        try:
            y_f = float(y)
        except (TypeError, ValueError):
            parse_failures += 1
            continue
        if y_f != y_f:  # NaN
            parse_failures += 1
            continue
        ok_pairs.append((row.canonical_smiles, y_f, row.had_defined_stereo))

    # Stereo-defined ratio (over standardized valid molecules)
    stereo_defined = sum(1 for _, _, s in ok_pairs if s)
    stereo_ratio = (stereo_defined / len(ok_pairs)) if ok_pairs else 0.0

    # Duplicates + conflicts at standardized identity
    by_smi: dict[str, list[float]] = defaultdict(list)
    for smi, y, _ in ok_pairs:
        by_smi[smi].append(y)
    n_unique = len(by_smi)
    n_multi = sum(1 for ys in by_smi.values() if len(ys) > 1)
    conflict_fn = _classification_conflict if task == "classification" else _regression_conflict
    n_conflict = sum(1 for ys in by_smi.values() if len(ys) > 1 and conflict_fn(ys))

    # Class balance / target dist
    labels_flat = [y for _, y, _ in ok_pairs]
    if task == "classification":
        distribution = _class_balance(labels_flat)
    else:
        distribution = _target_stats(labels_flat) if labels_flat else {}

    # Scaffold diversity — computed on unique standardized SMILES
    unique_smis = sorted(by_smi.keys())
    scaffs = murcko_scaffolds_batch(unique_smis)
    scaff_counter = Counter(scaffs)
    top_scaffold_share = (
        max(scaff_counter.values()) / len(scaffs) if scaffs else 0.0
    )
    empty_scaffold_share = scaff_counter.get("", 0) / len(scaffs) if scaffs else 0.0
    scaffold_ratio = len(scaff_counter) / len(scaffs) if scaffs else 0.0

    stats = {
        "n_raw_rows": n_raw,
        "n_valid_after_standardization": n_ok,
        "validity_rate": n_ok / n_raw if n_raw else 0.0,
        "n_label_parse_failures": parse_failures,
        "rejection_reasons": {k: v for k, v in rej.items() if k != "ok"},
        "n_unique_standardized_molecules": n_unique,
        "duplicate_rate_at_standardized_identity": (
            (len(ok_pairs) - n_unique) / len(ok_pairs) if ok_pairs else 0.0
        ),
        "molecules_with_multiple_measurements": n_multi,
        "molecules_with_conflicting_labels": n_conflict,
        "conflict_rate_over_multi_measurement_molecules": (
            n_conflict / n_multi if n_multi else 0.0
        ),
        "conflict_rate_over_all_unique_molecules": (
            n_conflict / n_unique if n_unique else 0.0
        ),
        "stereo_defined_count": stereo_defined,
        "stereo_defined_ratio": stereo_ratio,
        "distribution": distribution,
        "scaffold_diversity": {
            "n_unique_scaffolds": len(scaff_counter),
            "scaffolds_per_molecule": scaffold_ratio,
            "top_scaffold_share": top_scaffold_share,
            "acyclic_share": empty_scaffold_share,
        },
        "stereo_flagged_by_blueprint": endpoint_key in STEREO_FLAGGED_ENDPOINTS,
    }

    return DatasetEDA(
        dataset_key=dataset_key,
        endpoint_key=endpoint_key,
        variant=variant,
        task=task,
        tdc_name=tdc_name,
        stats=stats,
    )


def run_eda(data_root: Path) -> tuple[dict, list[DatasetEDA]]:
    """Return (lockfile-dict, per-dataset EDA results). No side effects."""
    lock = _load_lock(data_root)
    results: list[DatasetEDA] = []
    for key, entry in lock["datasets"].items():
        # Use the persisted full CSV (the same file the snapshot digest is
        # computed over); that is the acquired dataset's "raw" for EDA.
        full_rec = next(
            f for f in entry["raw_files"] if f["role"] == "full_normalized_csv"
        )
        path = data_root / full_rec["path"]
        smis, ys = _load_csv_rows(path, entry["smiles_column"], entry["label_column"])
        results.append(
            _analyze(
                dataset_key=key,
                endpoint_key=entry["endpoint_key"],
                variant=entry["variant"],
                task=entry["task"],
                tdc_name=entry["tdc_name"],
                raw_smiles=smis,
                raw_labels=ys,
            )
        )
    return lock, results


def _write_reports(
    out_dir: Path,
    lock: dict,
    results: list[DatasetEDA],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "per_dataset").mkdir(exist_ok=True)
    for r in results:
        (out_dir / "per_dataset" / f"{r.dataset_key}.json").write_text(
            json.dumps(
                {
                    "dataset_key": r.dataset_key,
                    "endpoint_key": r.endpoint_key,
                    "variant": r.variant,
                    "task": r.task,
                    "tdc_name": r.tdc_name,
                    "stats": r.stats,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    rollup = {
        "eda_id": out_dir.name,
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "standardizer_version": STANDARDIZER_VERSION,
        "acquisition_id": lock["acquisition"]["acq_id"],
        "pytdc_version": lock["acquisition"]["pytdc_version"],
        "datasets": [
            {
                "dataset_key": r.dataset_key,
                "endpoint_key": r.endpoint_key,
                "variant": r.variant,
                "task": r.task,
                "tdc_name": r.tdc_name,
                **{
                    k: r.stats[k]
                    for k in (
                        "n_raw_rows",
                        "n_valid_after_standardization",
                        "validity_rate",
                        "n_unique_standardized_molecules",
                        "duplicate_rate_at_standardized_identity",
                        "molecules_with_multiple_measurements",
                        "molecules_with_conflicting_labels",
                        "conflict_rate_over_multi_measurement_molecules",
                        "stereo_defined_ratio",
                        "stereo_flagged_by_blueprint",
                    )
                },
                "scaffold_diversity": r.stats["scaffold_diversity"],
            }
            for r in results
        ],
    }
    (out_dir / "rollup.json").write_text(
        json.dumps(rollup, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_markdown(out_dir / "eda_report.md", rollup, results)


def _write_markdown(path: Path, rollup: dict, results: list[DatasetEDA]) -> None:
    lines = [
        "# MARS — M1 EDA report",
        "",
        f"- **eda_id:** `{rollup['eda_id']}`",
        f"- **generated:** {rollup['generated_at_utc']}",
        f"- **standardizer:** `{rollup['standardizer_version']}`",
        f"- **acquisition:** `{rollup['acquisition_id']}` (PyTDC {rollup['pytdc_version']})",
        "",
        "Every dataset in the acquisition lockfile was standardized with the "
        "Module 3 Stage 1 pipeline. Numbers below are computed over standardized "
        "molecules with parseable labels.",
        "",
        "| dataset | task | raw | valid | valid% | uniq mol | dup% | multi-meas | conflicts | conflict%(of multi) | stereo-def% | uniq scaff | top scaff% |",
        "|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|",
    ]
    for r in results:
        s = r.stats
        d = s["scaffold_diversity"]
        lines.append(
            "| `{k}` ({v}) | {task} | {raw} | {ok} | {vr:.1%} | {uniq} | "
            "{dup:.1%} | {mm} | {conf} | {cr:.1%} | {sd:.1%} | {ns} | {ts:.1%} |".format(
                k=r.dataset_key,
                v=r.variant,
                task=r.task,
                raw=s["n_raw_rows"],
                ok=s["n_valid_after_standardization"],
                vr=s["validity_rate"],
                uniq=s["n_unique_standardized_molecules"],
                dup=s["duplicate_rate_at_standardized_identity"],
                mm=s["molecules_with_multiple_measurements"],
                conf=s["molecules_with_conflicting_labels"],
                cr=s["conflict_rate_over_multi_measurement_molecules"],
                sd=s["stereo_defined_ratio"],
                ns=d["n_unique_scaffolds"],
                ts=d["top_scaffold_share"],
            )
        )
    lines += [
        "",
        "## Per-endpoint distributions",
        "",
    ]
    for r in results:
        s = r.stats
        lines.append(f"### `{r.dataset_key}` ({r.variant}, {r.task})")
        if r.task == "classification":
            cb = s["distribution"]
            lines.append(
                f"- class balance: counts={cb.get('counts')} | positive fraction "
                f"{cb.get('positive_fraction'):.1%}"
                if cb.get("positive_fraction") is not None else "- (no valid labels)"
            )
        else:
            d = s["distribution"]
            if d:
                lines.append(
                    f"- Y: n={d['n']} min={d['min']:.3g} p25={d['p25']:.3g} "
                    f"med={d['median']:.3g} p75={d['p75']:.3g} max={d['max']:.3g} "
                    f"mean={d['mean']:.3g} std={d['std']:.3g}"
                )
        if s["rejection_reasons"]:
            lines.append(f"- rejections: {s['rejection_reasons']}")
        if s["stereo_flagged_by_blueprint"]:
            lines.append(
                f"- **stereo-flagged endpoint (Module 3):** stereo-defined ratio "
                f"= {s['stereo_defined_ratio']:.1%}"
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--eda-id", default=None)
    args = ap.parse_args()

    repo = args.repo_root.resolve()
    data_root = repo / "ml" / "data"
    if not (data_root / "metadata" / "datasets.lock.json").exists():
        print("no acquisition lockfile; run ml/data/acquire.py first", file=sys.stderr)
        return 2

    eda_id = args.eda_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = data_root / "eda" / eda_id

    print(f"MARS EDA  eda_id={eda_id}  standardizer={STANDARDIZER_VERSION}", flush=True)
    lock, results = run_eda(data_root)
    for r in results:
        s = r.stats
        print(
            f"  [{r.dataset_key:32}] N={s['n_raw_rows']:>6}  "
            f"valid={s['validity_rate']:.1%}  "
            f"uniq={s['n_unique_standardized_molecules']:>6}  "
            f"dup={s['duplicate_rate_at_standardized_identity']:.1%}  "
            f"conflict%={s['conflict_rate_over_multi_measurement_molecules']:.1%}  "
            f"stereo%={s['stereo_defined_ratio']:.1%}",
            flush=True,
        )
    _write_reports(out, lock, results)
    print(f"wrote {out.relative_to(repo)}/rollup.json + eda_report.md + per_dataset/*.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
