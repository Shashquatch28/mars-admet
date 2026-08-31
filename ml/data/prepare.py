"""
Milestone 1 dataset preparation driver.

For each acquired dataset:
  1. read the raw benchmark split (if any) + the raw full CSV
  2. standardize both through Module 3 Stage 1
  3. dedup the full set with the EDA-gated tiered policy (§3)
  4. build the fixed train_val / test split:
       * ``benchmark_group`` datasets → adopt TDC's official split
       * ``hERG_Karim``               → deterministic Murcko scaffold split
  5. carve a scaffold-aware calibration split from train_val (Module 4)
  6. run automated leakage audits (SMILES + scaffold, incl. post-augmentation)
  7. write processed CSVs + a per-dataset provenance record

Outputs land under::

    ml/data/processed/<prep_id>/
      <dataset_key>/
        train_val.csv         standardized SMILES + label
        test.csv              standardized SMILES + label
        calibration.csv       (subset of train_val; distinct from test)
        assignments.csv       ONE row per unique standardized SMILES: fold
        resolution_report.json
        split_report.json
        provenance.json
      prepare_report.md       roll-up
      manifest.json           per-dataset paths, hashes, versions

Deterministic. Idempotent (a fresh ``prep_id`` starts a new snapshot; existing
ones are never overwritten).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from featurize.scaffold import murcko_scaffold_from_smiles
from featurize.standardize import STANDARDIZER_VERSION, standardize_batch

from data.dataset_registry import DATASET_SPECS
from data.dedup import (
    DEDUP_VERSION,
    dedup,
    load_eda_rollup,
    select_policy_from_eda,
    write_resolution_report,
)
from data.split import (
    SPLIT_VERSION,
    adopt_benchmark_split,
    assert_no_leakage,
    build_split_report,
    scaffold_split,
)

PREP_SCHEMA_VERSION = 1
CALIBRATION_FLOOR = 50
CALIBRATION_FRACTION = 0.10


# ---------------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------------- #
def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _read_csv_pairs(path: Path, smiles_col: str, label_col: str) -> list[tuple[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return [(row[smiles_col], row[label_col]) for row in csv.DictReader(fh)]


def _standardize_pairs(raw_pairs: list[tuple[str, str]]) -> list[tuple[str, float]]:
    """Standardize + parse labels; drop rows that fail either."""
    smis = [s for s, _ in raw_pairs]
    ys = [y for _, y in raw_pairs]
    std = standardize_batch(smis)
    out: list[tuple[str, float]] = []
    for row, y in zip(std, ys, strict=True):
        if not row.ok:
            continue
        try:
            y_f = float(y)
        except (TypeError, ValueError):
            continue
        if y_f != y_f:
            continue
        out.append((row.canonical_smiles, y_f))
    return out


def _write_pairs_csv(path: Path, pairs: list[tuple[str, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["standardized_smiles", "label"])
        for s, y in pairs:
            # write with repr to keep exact float; classification stored as float
            w.writerow([s, repr(y) if isinstance(y, float) and not y.is_integer() else int(y) if y.is_integer() else repr(y)])


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _calibration_size(train_val_n: int) -> int:
    return max(CALIBRATION_FLOOR, int(round(train_val_n * CALIBRATION_FRACTION)))


# ---------------------------------------------------------------------------- #
# Per-dataset preparation
# ---------------------------------------------------------------------------- #
def prepare_dataset(
    *,
    dataset_key: str,
    entry: dict,
    data_root: Path,
    eda_rollup: dict,
    out_root: Path,
    skip_split: bool = False,
) -> dict:
    """Prepare one dataset; return its manifest entry."""
    endpoint_key = entry["endpoint_key"]
    variant = entry["variant"]
    task = entry["task"]

    ds_out = out_root / dataset_key
    ds_out.mkdir(parents=True, exist_ok=True)

    # --- 1) standardize the full set + dedup -------------------------------- #
    full_rec = next(f for f in entry["raw_files"] if f["role"] == "full_normalized_csv")
    full_path = data_root / full_rec["path"]
    raw_full = _read_csv_pairs(full_path, entry["smiles_column"], entry["label_column"])
    std_full = _standardize_pairs(raw_full)
    n_full_std = len(std_full)

    options = select_policy_from_eda(dataset_key, eda_rollup)
    dedup_out, resolution = dedup(
        dataset_key=dataset_key,
        endpoint_key=endpoint_key,
        pairs=std_full,
        options=options,
    )
    write_resolution_report(ds_out / "resolution_report.json", resolution)
    dedup_by_smi = {o.standardized_smiles: o.label for o in dedup_out}

    # --- 2) split ---------------------------------------------------------- #
    if skip_split:
        (ds_out / "provenance.json").write_text(
            json.dumps(
                {
                    "dataset_key": dataset_key,
                    "endpoint_key": endpoint_key,
                    "variant": variant,
                    "task": task,
                    "note": "split intentionally skipped (see maintainer note in provenance)",
                    "n_full_raw": len(raw_full),
                    "n_full_valid": n_full_std,
                    "n_after_dedup": len(dedup_out),
                    "resolution_policy": options.policy,
                    "resolution_rationale": options.rationale,
                    "standardizer_version": STANDARDIZER_VERSION,
                    "dedup_version": DEDUP_VERSION,
                    "split_version": None,
                    "acquired_at_utc": entry["acquired_at_utc"],
                    "acq_snapshot_sha256": entry["snapshot_sha256"],
                    "generated_at_utc": _utc_now(),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return {
            "dataset_key": dataset_key,
            "endpoint_key": endpoint_key,
            "variant": variant,
            "task": task,
            "split_status": "deferred",
            "reason": "explicitly skipped by prepare invocation",
        }

    # Registry is the source of truth for split method (blueprint Module 1 §4).
    # The lockfile records what the acquisition physically wrote to disk, but
    # policy changes between the acquisition and preparation runs (e.g. Option C
    # for PPB, 2026-08-30) must be honored — so if the registry says the primary
    # endpoint does not adopt a benchmark split, we scaffold-split regardless of
    # what the lockfile has attached.
    spec = DATASET_SPECS.get(dataset_key)
    registry_says_adopt = bool(spec and spec.in_admet_benchmark_group)
    bs = entry.get("benchmark_split") if registry_says_adopt else None
    post_std_leaks: list[str] = []
    if bs and "train_val" in bs and "test" in bs:
        tv_pairs = _read_csv_pairs(data_root / bs["train_val"]["path"], entry["smiles_column"], entry["label_column"])
        te_pairs = _read_csv_pairs(data_root / bs["test"]["path"], entry["smiles_column"], entry["label_column"])
        tv_std = _standardize_pairs(tv_pairs)
        te_std = _standardize_pairs(te_pairs)
        # unique standardized SMILES sets
        tv_set = {s for s, _ in tv_std}
        te_set = {s for s, _ in te_std}
        # Post-standardization collision resolution: two raw SMILES in different
        # benchmark folds can collapse to one canonical form under our Module 3
        # Stage 1 pipeline. Blueprint Module 1: the test set is fixed. Keep the
        # compound on the test side; remove it from train_val; log every case.
        post_std_leaks = sorted(tv_set & te_set)
        tv_smis = sorted(tv_set - te_set)
        te_smis = sorted(te_set)
        _ = adopt_benchmark_split  # marker; we already have the partition
        method = "adopt_benchmark"
        seed_used = None
    else:
        # deterministic Murcko split; use seed=0 for the fixed test set
        method = "scaffold"
        seed_used = 0
        all_smis = sorted(dedup_by_smi.keys())
        tv_smis, te_smis = scaffold_split(all_smis, seed=seed_used)

    split_report = build_split_report(
        dataset_key=dataset_key,
        endpoint_key=endpoint_key,
        method=method,
        train_val=tv_smis,
        test=te_smis,
        seed=seed_used,
    )
    if post_std_leaks:
        split_report.notes.append(
            f"{len(post_std_leaks)} standardized SMILES appeared in both benchmark "
            "train_val and test after Module 3 Stage 1 standardization; removed "
            "from train_val (test set is fixed)"
        )
    # SMILES-level leakage is always a hard failure. Scaffold-level leakage is
    # a hard failure for splits WE generate; for adopted TDC benchmark splits
    # it is a finding about TDC's protocol under our stricter Murcko-post-std
    # definition — surfaced in the split report, not silently tolerated, and
    # not overridden.
    if split_report.smiles_overlap_count:
        raise AssertionError(
            f"{dataset_key}: {split_report.smiles_overlap_count} SMILES appear in "
            f"both train_val and test after post-standardization resolution"
        )
    if method == "scaffold":
        assert_no_leakage(split_report)
    elif split_report.scaffold_overlap_count:
        split_report.notes.append(
            f"{split_report.scaffold_overlap_count} non-acyclic Murcko scaffolds "
            "appear in both train_val and test in the ADOPTED TDC benchmark "
            "split (Murcko scaffolds computed on Module 3 Stage 1 standardized "
            "molecules). This is a property of TDC's own split under our "
            "standardization; retained for leaderboard comparability, surfaced "
            "here rather than silently tolerated (Module 11 self-audit)."
        )
    report_dict = split_report.as_dict()
    report_dict["post_standardization_leaks_removed_from_train_val"] = post_std_leaks
    (ds_out / "split_report.json").write_text(
        json.dumps(report_dict, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    # --- 3) join back to dedup'd labels ------------------------------------ #
    # Adopting the benchmark split can name compounds we dropped during dedup
    # (unusual, but the benchmark split was made against raw data). Take the
    # standardized label from the benchmark file for those. Log the count.
    tv_pair_labels: dict[str, float] = {}
    te_pair_labels: dict[str, float] = {}
    if method == "adopt_benchmark":
        tv_allowed = set(tv_smis)
        te_allowed = set(te_smis)
        for s, y in tv_std:
            if s in tv_allowed:
                tv_pair_labels.setdefault(s, y)
        for s, y in te_std:
            if s in te_allowed:
                te_pair_labels.setdefault(s, y)
        # prefer the dedup'd label where present (consensus / averaged / majority)
        for s in list(tv_pair_labels):
            if s in dedup_by_smi:
                tv_pair_labels[s] = dedup_by_smi[s]
        for s in list(te_pair_labels):
            if s in dedup_by_smi:
                te_pair_labels[s] = dedup_by_smi[s]
    else:
        tv_pair_labels = {s: dedup_by_smi[s] for s in tv_smis if s in dedup_by_smi}
        te_pair_labels = {s: dedup_by_smi[s] for s in te_smis if s in dedup_by_smi}

    tv_final = sorted(tv_pair_labels.items())
    te_final = sorted(te_pair_labels.items())
    _write_pairs_csv(ds_out / "train_val.csv", tv_final)
    _write_pairs_csv(ds_out / "test.csv", te_final)

    # --- 4) calibration split (scaffold-aware, deterministic) --------------- #
    tv_smis_final = [s for s, _ in tv_final]
    cal_target = _calibration_size(len(tv_smis_final))
    cal_frac = cal_target / len(tv_smis_final) if tv_smis_final else 0.0
    _, cal_smis = scaffold_split(tv_smis_final, test_fraction=cal_frac, seed=42)
    cal_report = build_split_report(
        dataset_key=dataset_key,
        endpoint_key=endpoint_key,
        method="scaffold",
        train_val=[s for s in tv_smis_final if s not in set(cal_smis)],
        test=cal_smis,
        seed=42,
    )
    assert_no_leakage(cal_report)
    # calibration must ALSO be disjoint from the test set
    if set(cal_smis) & set(te_pair_labels):
        raise AssertionError(f"{dataset_key}: calibration ∩ test != ∅")
    cal_pairs = [(s, tv_pair_labels[s]) for s in cal_smis if s in tv_pair_labels]
    _write_pairs_csv(ds_out / "calibration.csv", cal_pairs)
    (ds_out / "calibration_report.json").write_text(
        json.dumps(
            {
                **cal_report.as_dict(),
                "target_n": cal_target,
                "achieved_n": len(cal_pairs),
                "fraction_of_train_val": cal_frac,
                "rule": (
                    f"max({CALIBRATION_FLOOR}, {CALIBRATION_FRACTION:.0%} of "
                    f"train_val) — blueprint Module 4"
                ),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    # --- 5) assignments.csv ------------------------------------------------- #
    with (ds_out / "assignments.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["standardized_smiles", "murcko_scaffold", "fold"])
        cal_set = set(cal_smis)
        for s, _ in tv_final:
            fold = "calibration" if s in cal_set else "train_val"
            w.writerow([s, murcko_scaffold_from_smiles(s), fold])
        for s, _ in te_final:
            w.writerow([s, murcko_scaffold_from_smiles(s), "test"])

    prov = {
        "dataset_key": dataset_key,
        "endpoint_key": endpoint_key,
        "variant": variant,
        "task": task,
        "n_full_raw": len(raw_full),
        "n_full_valid": n_full_std,
        "n_after_dedup": len(dedup_out),
        "n_train_val": len(tv_final),
        "n_test": len(te_final),
        "n_calibration": len(cal_pairs),
        "resolution_policy": options.policy,
        "resolution_rationale": options.rationale,
        "split_method": method,
        "split_seed": seed_used,
        "standardizer_version": STANDARDIZER_VERSION,
        "dedup_version": DEDUP_VERSION,
        "split_version": SPLIT_VERSION,
        "acquired_at_utc": entry["acquired_at_utc"],
        "acq_snapshot_sha256": entry["snapshot_sha256"],
        "generated_at_utc": _utc_now(),
        "registry_notes": spec.notes if spec else "",
        "registry_says_adopt_benchmark": registry_says_adopt,
        "lockfile_had_benchmark_split": bool(entry.get("benchmark_split")),
        "files": {
            "train_val": {
                "path": str((ds_out / "train_val.csv").as_posix()),
                "sha256": _sha256_file(ds_out / "train_val.csv"),
                "n_rows": len(tv_final),
            },
            "test": {
                "path": str((ds_out / "test.csv").as_posix()),
                "sha256": _sha256_file(ds_out / "test.csv"),
                "n_rows": len(te_final),
            },
            "calibration": {
                "path": str((ds_out / "calibration.csv").as_posix()),
                "sha256": _sha256_file(ds_out / "calibration.csv"),
                "n_rows": len(cal_pairs),
            },
            "assignments": {
                "path": str((ds_out / "assignments.csv").as_posix()),
                "sha256": _sha256_file(ds_out / "assignments.csv"),
            },
        },
    }
    (ds_out / "provenance.json").write_text(
        json.dumps(prov, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "dataset_key": dataset_key,
        "endpoint_key": endpoint_key,
        "variant": variant,
        "task": task,
        "split_status": "done",
        "provenance": prov,
    }


# ---------------------------------------------------------------------------- #
# Main
# ---------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", type=Path, default=Path(".."))
    ap.add_argument("--prep-id", default=None)
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument(
        "--defer-ppb",
        action="store_true",
        default=False,
        help=(
            "Escape hatch: skip PPB processing entirely. Default: OFF. Option C "
            "(human-only primary) was locked 2026-08-30; PPB is now on the same "
            "footing as every other endpoint. The dataset_registry decides its "
            "split method (scaffold for human-only PPB)."
        ),
    )
    args = ap.parse_args()

    repo = args.repo_root.resolve()
    data_root = repo / "ml" / "data"
    lock_path = data_root / "metadata" / "datasets.lock.json"
    if not lock_path.exists():
        print("no acquisition lockfile; run ml/data/acquire.py first", file=sys.stderr)
        return 2
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    eda_rollup = load_eda_rollup(data_root)

    prep_id = args.prep_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_root = data_root / "processed" / prep_id
    out_root.mkdir(parents=True, exist_ok=True)

    keys = args.only or list(lock["datasets"].keys())
    manifest: dict[str, Any] = {
        "prep_id": prep_id,
        "generated_at_utc": _utc_now(),
        "acquisition_id": lock["acquisition"]["acq_id"],
        "eda_id": eda_rollup["eda_id"],
        "standardizer_version": STANDARDIZER_VERSION,
        "dedup_version": DEDUP_VERSION,
        "split_version": SPLIT_VERSION,
        "prep_schema_version": PREP_SCHEMA_VERSION,
        "datasets": {},
    }

    print(f"MARS prepare  prep_id={prep_id}  acq={lock['acquisition']['acq_id']}", flush=True)
    for key in keys:
        entry = lock["datasets"].get(key)
        if entry is None:
            print(f"  [{key}] not in lockfile — skipping", flush=True)
            continue
        skip_split = args.defer_ppb and key == "ppb_binding"
        if skip_split:
            print(f"  [{key}] SPLIT DEFERRED (PPB investigation — see ppbr_az_investigation.md)", flush=True)
        else:
            print(f"  [{key}] preparing...", flush=True)
        result = prepare_dataset(
            dataset_key=key,
            entry=entry,
            data_root=data_root,
            eda_rollup=eda_rollup,
            out_root=out_root,
            skip_split=skip_split,
        )
        manifest["datasets"][key] = result
        if result["split_status"] == "done":
            p = result["provenance"]
            print(
                f"      dedup: {p['n_full_valid']} -> {p['n_after_dedup']} | "
                f"split: tv={p['n_train_val']} test={p['n_test']} cal={p['n_calibration']} "
                f"({p['split_method']})",
                flush=True,
            )
    (out_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    # human summary
    lines = [
        "# MARS — M1 dataset preparation report",
        "",
        f"- **prep_id:** `{prep_id}`",
        f"- **acquisition:** `{lock['acquisition']['acq_id']}` (PyTDC {lock['acquisition']['pytdc_version']})",
        f"- **eda:** `{eda_rollup['eda_id']}`",
        f"- **versions:** standardizer=`{STANDARDIZER_VERSION}` dedup=`{DEDUP_VERSION}` split=`{SPLIT_VERSION}`",
        "",
        "| dataset | task | full N | valid | after dedup | policy | split | train_val | test | cal |",
        "|---|---|--:|--:|--:|---|---|--:|--:|--:|",
    ]
    for key, r in manifest["datasets"].items():
        if r["split_status"] != "done":
            lines.append(f"| `{key}` | {r['task']} | — | — | — | — | **deferred** | — | — | — |")
            continue
        p = r["provenance"]
        lines.append(
            f"| `{key}` | {p['task']} | {p['n_full_raw']} | {p['n_full_valid']} | "
            f"{p['n_after_dedup']} | {p['resolution_policy']} | {p['split_method']} | "
            f"{p['n_train_val']} | {p['n_test']} | {p['n_calibration']} |"
        )
    (out_root / "prepare_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {(out_root / 'manifest.json').relative_to(repo)}")
    print(f"wrote {(out_root / 'prepare_report.md').relative_to(repo)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
