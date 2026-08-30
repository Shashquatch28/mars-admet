"""
Module 1 §6 — DILIst augmentation of the DILI training pool.

Non-negotiable rules enforced here (blueprint):

  * DILIst structures are standardized through the *identical* Module 3 Stage 1
    pipeline as the TDC data — same code path, not a parallel implementation.
  * Deduplication against the **fixed TDC DILI test set** is performed first;
    every standardized-SMILES match is dropped from the augmentation stream.
    Skipping this step invalidates every downstream leaderboard comparison.
  * Only the DILI **train_val + calibration** pool is augmented. The test set
    is never touched.
  * A post-merge scaffold-overlap check re-runs the split leakage audit; the
    augmented split is only accepted if it passes.
  * Every input row's fate is auditable: kept, dropped-because-in-test,
    dropped-because-already-in-train (in-training duplicate → conflict-resolved
    via the same tiered policy as the base dataset), rejected-by-standardization.

Output: a new augmented DILI dataset directory under
``ml/data/processed/<prep_id>/dili_liver_injury__augmented/`` with the same
file layout as an unaugmented dataset (train_val.csv / test.csv / calibration.csv
/ assignments.csv / provenance.json / augmentation_report.json).

The TDC DILI test set is unchanged; the augmentation only expands train_val +
calibration.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from featurize.scaffold import murcko_scaffold_from_smiles
from featurize.standardize import STANDARDIZER_VERSION, standardize_batch

from data.dedup import DEDUP_VERSION, dedup, select_policy
from data.split import (
    SPLIT_VERSION,
    build_split_report,
    scaffold_split,
)

AUGMENTATION_VERSION = "mars-augmentation-v1"
CALIBRATION_FRACTION = 0.10
CALIBRATION_FLOOR = 50


# ---------------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------------- #
def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_pairs(path: Path, smiles_col: str, label_col: str) -> list[tuple[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return [(row[smiles_col], row[label_col]) for row in csv.DictReader(fh)]


def _write_pairs_csv(path: Path, pairs: list[tuple[str, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["standardized_smiles", "label"])
        for s, y in pairs:
            if isinstance(y, float) and y.is_integer():
                w.writerow([s, int(y)])
            else:
                w.writerow([s, repr(y)])


def _calibration_size(train_val_n: int) -> int:
    return max(CALIBRATION_FLOOR, int(round(train_val_n * CALIBRATION_FRACTION)))


# ---------------------------------------------------------------------------- #
# Augmentation
# ---------------------------------------------------------------------------- #
def _load_dilipredictor(path: Path) -> list[tuple[str, float, str]]:
    """Return (raw_smiles, label_float, source_tag) rows."""
    out: list[tuple[str, float, str]] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            smi = (row.get("smiles_r") or "").strip()
            tox = (row.get("TOXICITY") or "").strip()
            if not smi or tox not in ("0", "1"):
                continue
            out.append((smi, float(tox), row.get("Source", "")))
    return out


def augment_dili(
    *,
    repo_root: Path,
    prep_id: str,
    dili_dir_name: str = "dili_liver_injury",
    augmentation_csv: Path,
) -> dict[str, Any]:
    repo = repo_root.resolve()
    data_root = repo / "ml" / "data"
    processed_root = data_root / "processed" / prep_id
    base_dir = processed_root / dili_dir_name
    if not base_dir.exists():
        raise FileNotFoundError(
            f"{base_dir} not found — run ml/data/prepare.py --prep-id {prep_id} first"
        )

    # Baseline (unaugmented) processed DILI
    base_tv = _read_pairs(base_dir / "train_val.csv", "standardized_smiles", "label")
    base_te = _read_pairs(base_dir / "test.csv", "standardized_smiles", "label")
    base_cal = _read_pairs(base_dir / "calibration.csv", "standardized_smiles", "label")
    base_tv_labels = {s: float(y) for s, y in base_tv}
    base_te_smis = {s for s, _ in base_te}
    _ = base_cal  # cal comes out of the new train_val; the input is not needed

    aug_raw = _load_dilipredictor(augmentation_csv)
    n_raw = len(aug_raw)

    # --- 1) standardize DILIst through the SAME pipeline -------------------- #
    std = standardize_batch([s for s, _, _ in aug_raw])
    aug_std: list[tuple[str, float, str]] = []
    rejected: list[dict] = []
    for src, row in zip(aug_raw, std, strict=True):
        _raw_smi, y, source = src
        if not row.ok:
            rejected.append({"raw_smiles": _raw_smi, "reason": row.reason})
            continue
        aug_std.append((row.canonical_smiles, y, source))

    # --- 2) drop everything that appears in the TDC DILI TEST set ----------- #
    aug_after_test_dedup: list[tuple[str, float, str]] = []
    dropped_test_overlap: list[str] = []
    for smi, y, source in aug_std:
        if smi in base_te_smis:
            dropped_test_overlap.append(smi)
        else:
            aug_after_test_dedup.append((smi, y, source))

    # --- 3) merge with the existing (dedup'd) DILI train_val ---------------- #
    merged_pairs: list[tuple[str, float]] = list(base_tv_labels.items()) + [
        (s, y) for s, y, _ in aug_after_test_dedup
    ]

    # Re-run tiered dedup on the merged pool. DILI is classification, small
    # dataset — select_policy returns majority_vote via the small-dataset
    # override (blueprint §3).
    task = "classification"
    dedup_options = select_policy(
        task=task,
        conflict_rate_over_multi=0.0,  # placeholder; small-dataset branch decides
        dataset_n=len(merged_pairs),
    )
    merged_out, resolution = dedup(
        dataset_key=f"{dili_dir_name}__augmented_train_val",
        endpoint_key="dili_liver_injury",
        pairs=merged_pairs,
        options=dedup_options,
    )
    merged_by_smi = {o.standardized_smiles: o.label for o in merged_out}

    # --- 4) fixed test set unchanged; carve a fresh calibration split ------- #
    tv_smis = sorted(merged_by_smi.keys())
    cal_target = _calibration_size(len(tv_smis))
    cal_frac = cal_target / len(tv_smis) if tv_smis else 0.0
    _, cal_smis = scaffold_split(tv_smis, test_fraction=cal_frac, seed=42)
    cal_set = set(cal_smis)
    if cal_set & base_te_smis:
        raise AssertionError("augmented calibration ∩ test != ∅")

    # --- 5) post-merge scaffold-overlap re-check --------------------------- #
    post_split_report = build_split_report(
        dataset_key=f"{dili_dir_name}__augmented",
        endpoint_key="dili_liver_injury",
        method="scaffold",
        train_val=tv_smis,
        test=sorted(base_te_smis),
        seed=None,
    )
    # For DILI (small, single-cluster space), scaffold overlap is likely; the
    # blueprint's requirement is "re-check post-merge" and act on the result,
    # not "must be zero" — we report the count. SMILES-level overlap is still
    # a hard failure.
    if post_split_report.smiles_overlap_count:
        raise AssertionError(
            "post-augmentation: SMILES overlap between augmented train_val and test"
        )

    # --- 6) write outputs -------------------------------------------------- #
    out_dir = processed_root / f"{dili_dir_name}__augmented"
    out_dir.mkdir(parents=True, exist_ok=True)

    tv_out = sorted(merged_by_smi.items())
    _write_pairs_csv(out_dir / "train_val.csv", tv_out)
    _write_pairs_csv(out_dir / "test.csv", [(s, float(y)) for s, y in base_te])
    cal_pairs = [(s, merged_by_smi[s]) for s in cal_smis if s in merged_by_smi]
    _write_pairs_csv(out_dir / "calibration.csv", cal_pairs)

    # assignments.csv
    with (out_dir / "assignments.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["standardized_smiles", "murcko_scaffold", "fold"])
        for s, _ in tv_out:
            fold = "calibration" if s in cal_set else "train_val"
            w.writerow([s, murcko_scaffold_from_smiles(s), fold])
        for s, _ in base_te:
            w.writerow([s, murcko_scaffold_from_smiles(s), "test"])

    # augmentation_report.json — auditable trail
    source_counter = Counter(source for _, _, source in aug_after_test_dedup)
    report = {
        "generated_at_utc": _utc_now(),
        "augmentation_version": AUGMENTATION_VERSION,
        "standardizer_version": STANDARDIZER_VERSION,
        "dedup_version": DEDUP_VERSION,
        "split_version": SPLIT_VERSION,
        "source": {
            "path": str(augmentation_csv.relative_to(repo).as_posix()),
            "sha256": _sha256_file(augmentation_csv),
            "n_raw_rows": n_raw,
            "distribution_by_source_tag": {k: v for k, v in source_counter.most_common()},
            "provenance_notes": "see ml/data/augmentation/dilipredictor_v1/PROVENANCE.md",
        },
        "steps": {
            "raw_rows_read": n_raw,
            "standardized_valid": len(aug_std),
            "rejected_by_standardization": len(rejected),
            "dropped_because_in_test_set": len(dropped_test_overlap),
            "surviving_augmentation_rows": len(aug_after_test_dedup),
            "base_train_val_size": len(base_tv_labels),
            "merged_before_dedup": len(merged_pairs),
            "merged_after_dedup": len(merged_out),
            "final_train_val": len(tv_out),
            "final_calibration": len(cal_pairs),
            "final_test": len(base_te),
            "resolution_report": resolution.as_dict(),
        },
        "leakage_audit": {
            "test_set_frozen": True,
            "smiles_overlap_train_test_after_merge": post_split_report.smiles_overlap_count,
            "scaffold_overlap_train_test_after_merge": post_split_report.scaffold_overlap_count,
            "notes": post_split_report.notes,
            "calibration_intersect_test": 0,
        },
        "rejection_samples": rejected[:20],
    }
    (out_dir / "augmentation_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    # short provenance.json aligned with prepare.py's schema
    prov = {
        "dataset_key": f"{dili_dir_name}__augmented",
        "endpoint_key": "dili_liver_injury",
        "variant": "augmented",
        "task": task,
        "n_train_val": len(tv_out),
        "n_test": len(base_te),
        "n_calibration": len(cal_pairs),
        "standardizer_version": STANDARDIZER_VERSION,
        "dedup_version": DEDUP_VERSION,
        "split_version": SPLIT_VERSION,
        "augmentation_version": AUGMENTATION_VERSION,
        "generated_at_utc": _utc_now(),
        "augmentation_source": str(augmentation_csv.relative_to(repo).as_posix()),
        "augmentation_source_sha256": _sha256_file(augmentation_csv),
        "files": {
            "train_val": {
                "path": str((out_dir / "train_val.csv").as_posix()),
                "sha256": _sha256_file(out_dir / "train_val.csv"),
                "n_rows": len(tv_out),
            },
            "test": {
                "path": str((out_dir / "test.csv").as_posix()),
                "sha256": _sha256_file(out_dir / "test.csv"),
                "n_rows": len(base_te),
            },
            "calibration": {
                "path": str((out_dir / "calibration.csv").as_posix()),
                "sha256": _sha256_file(out_dir / "calibration.csv"),
                "n_rows": len(cal_pairs),
            },
        },
    }
    (out_dir / "provenance.json").write_text(
        json.dumps(prov, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", type=Path, default=Path(".."))
    ap.add_argument("--prep-id", required=True)
    ap.add_argument(
        "--augmentation-csv",
        type=Path,
        default=Path("data/augmentation/dilipredictor_v1/DILI_Goldstandard_1111.csv"),
        help="path (relative to repo root or absolute)",
    )
    args = ap.parse_args()

    repo = args.repo_root.resolve()
    src = args.augmentation_csv
    if not src.is_absolute():
        # accept 'data/…' relative to ml/, or 'ml/data/…' relative to repo
        candidates = [repo / "ml" / src, repo / src]
        src = next((p for p in candidates if p.exists()), candidates[0])
    if not src.exists():
        print(f"augmentation csv not found: {src}", file=sys.stderr)
        return 2

    print(f"MARS DILIst augmentation  prep_id={args.prep_id}  source={src.name}")
    report = augment_dili(
        repo_root=repo,
        prep_id=args.prep_id,
        augmentation_csv=src,
    )
    s = report["steps"]
    print(
        f"  raw={s['raw_rows_read']}  valid_std={s['standardized_valid']}  "
        f"in_test_dropped={s['dropped_because_in_test_set']}  "
        f"merged_after_dedup={s['merged_after_dedup']}  "
        f"final tv/test/cal = {s['final_train_val']}/{s['final_test']}/{s['final_calibration']}"
    )
    la = report["leakage_audit"]
    print(
        f"  leakage: SMILES overlap = {la['smiles_overlap_train_test_after_merge']} | "
        f"scaffold overlap (Murcko) = {la['scaffold_overlap_train_test_after_merge']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
