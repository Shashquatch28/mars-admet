"""
Read-only provenance comparison of two prepared M1 snapshots.

Purpose: establish whether the data on the GPU workstation is the same data the
XGBoost baselines were trained and tested on, WITHOUT copying gigabytes across or
regenerating anything. Each side is reduced to a small *fingerprint* (per dataset,
per split file: a byte digest and a content digest). Fingerprints are compared.

Why not just diff ``manifest.json``: the manifest embeds absolute file paths
(``C:/Users/...`` on one machine, ``/home/...`` on another), so two manifests can
never be byte-identical even for identical data. The split files are hashed instead.

Classification per dataset (and overall = the weakest dataset):

  A  BYTE_IDENTICAL       every split file has the same SHA-256
  B  CONTENT_IDENTICAL    bytes differ (e.g. line endings, row order, float text)
                          but the canonical (smiles, label) content is the same
  C  MATERIALLY_DIFFERENT the canonical content differs
  D  UNABLE_TO_VERIFY     one side is missing, or lacks the dataset/file

This tool never writes to a processed directory and never modifies data. The only
write is the optional ``--out`` fingerprint file.

Usage
-----
    # on each machine
    python data/compare_prep.py fingerprint --prep-dir data/processed/<prep_id> --out fp.json
    # anywhere (each side may be a prep dir or a fingerprint json)
    python data/compare_prep.py compare --a fp_laptop.json --b fp_workstation.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

FINGERPRINT_VERSION = "mars-prep-fingerprint-v1"
SPLIT_FILES = ("train_val", "test", "calibration", "assignments")

BYTE_IDENTICAL = "A_BYTE_IDENTICAL"
CONTENT_IDENTICAL = "B_CONTENT_IDENTICAL_REGENERATED"
MATERIALLY_DIFFERENT = "C_MATERIALLY_DIFFERENT"
UNABLE_TO_VERIFY = "D_UNABLE_TO_VERIFY"

# Ordered weakest-last so the overall verdict is the worst dataset's.
_SEVERITY = [BYTE_IDENTICAL, CONTENT_IDENTICAL, MATERIALLY_DIFFERENT, UNABLE_TO_VERIFY]

# Version fields that must agree for two snapshots to be the same pipeline output.
_MUST_MATCH = ("dedup_version", "prep_schema_version", "split_version", "standardizer_version")
# IDs/timestamps that are expected to differ between independent preparations.
_EXPECTED_TO_DIFFER = ("prep_id", "acquisition_id", "eda_id", "generated_at_utc")


def _sha256_bytes(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_content_digest(path: Path) -> str:
    """Digest of the sorted (column values) rows, insensitive to row order and to how
    floats are printed. Compares CSV *content*, not bytes."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    cols = sorted(df.columns)
    rows: list[str] = []
    for rec in df[cols].itertuples(index=False, name=None):
        norm = []
        for v in rec:
            try:
                norm.append(repr(float(v)) if v not in ("",) and _looks_numeric(v) else v)
            except ValueError:
                norm.append(v)
        rows.append("\x1f".join(norm))
    rows.sort()
    h = hashlib.sha256()
    h.update("\x1e".join(cols).encode())
    for r in rows:
        h.update(b"\n")
        h.update(r.encode())
    return h.hexdigest()


def _looks_numeric(v: str) -> bool:
    try:
        float(v)
        return True
    except ValueError:
        return False


def fingerprint_prep(prep_dir: Path | str) -> dict[str, Any]:
    """Reduce a processed snapshot to hashes of its split files (read-only)."""
    prep_dir = Path(prep_dir)
    manifest_path = prep_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json not found in {prep_dir}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    datasets: dict[str, Any] = {}
    for ds_dir in sorted(p for p in prep_dir.iterdir() if p.is_dir()):
        entry: dict[str, Any] = {}
        for name in SPLIT_FILES:
            f = ds_dir / f"{name}.csv"
            if f.exists():
                entry[name] = {
                    "bytes_sha256": _sha256_bytes(f),
                    "content_sha256": _canonical_content_digest(f),
                    "n_rows": int(sum(1 for _ in f.open("rb")) - 1),
                }
        if entry:
            datasets[ds_dir.name] = entry

    return {
        "fingerprint_version": FINGERPRINT_VERSION,
        "prep_id": manifest.get("prep_id", prep_dir.name),
        "manifest": {
            k: manifest.get(k)
            for k in (*_MUST_MATCH, *_EXPECTED_TO_DIFFER)
            if k in manifest
        },
        "datasets": datasets,
    }


def _load_side(spec: Path | str | dict) -> dict[str, Any]:
    if isinstance(spec, dict):
        return spec
    p = Path(spec)
    if p.is_dir():
        return fingerprint_prep(p)
    return json.loads(p.read_text(encoding="utf-8"))


def _classify_dataset(a: dict | None, b: dict | None) -> tuple[str, list[str]]:
    if not a or not b:
        return UNABLE_TO_VERIFY, ["dataset missing on " + ("A" if not a else "B")]
    reasons: list[str] = []
    worst = BYTE_IDENTICAL
    for name in SPLIT_FILES:
        fa, fb = a.get(name), b.get(name)
        if fa is None and fb is None:
            continue
        if fa is None or fb is None:
            return UNABLE_TO_VERIFY, [f"{name}.csv missing on " + ("A" if fa is None else "B")]
        if fa["bytes_sha256"] == fb["bytes_sha256"]:
            continue
        if fa["content_sha256"] == fb["content_sha256"]:
            worst = CONTENT_IDENTICAL
            reasons.append(f"{name}.csv: bytes differ, canonical content equal")
        else:
            worst = MATERIALLY_DIFFERENT
            reasons.append(
                f"{name}.csv: content differs (rows {fa['n_rows']} vs {fb['n_rows']})"
            )
    return worst, reasons


def compare_fingerprints(a: Path | str | dict, b: Path | str | dict) -> dict[str, Any]:
    """Compare two snapshots. Each side is a prep dir, a fingerprint json, or a dict."""
    fa, fb = _load_side(a), _load_side(b)
    per: dict[str, Any] = {}
    for key in sorted(set(fa["datasets"]) | set(fb["datasets"])):
        cls, reasons = _classify_dataset(fa["datasets"].get(key), fb["datasets"].get(key))
        per[key] = {"classification": cls, "reasons": reasons}

    version_mismatch = {
        k: (fa["manifest"].get(k), fb["manifest"].get(k))
        for k in _MUST_MATCH
        if fa["manifest"].get(k) != fb["manifest"].get(k)
    }
    overall = BYTE_IDENTICAL
    for v in per.values():
        if _SEVERITY.index(v["classification"]) > _SEVERITY.index(overall):
            overall = v["classification"]
    if version_mismatch and overall in (BYTE_IDENTICAL, CONTENT_IDENTICAL):
        # Same bytes but a different pipeline version is not the same provenance.
        overall = MATERIALLY_DIFFERENT

    return {
        "overall": overall,
        "a_prep_id": fa.get("prep_id"),
        "b_prep_id": fb.get("prep_id"),
        "pipeline_version_mismatch": version_mismatch,
        "ids_expected_to_differ": {
            k: (fa["manifest"].get(k), fb["manifest"].get(k)) for k in _EXPECTED_TO_DIFFER
        },
        "datasets": per,
        "counts": {
            c: sum(1 for v in per.values() if v["classification"] == c) for c in _SEVERITY
        },
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fingerprint")
    f.add_argument("--prep-dir", required=True)
    f.add_argument("--out", default=None)
    c = sub.add_parser("compare")
    c.add_argument("--a", required=True)
    c.add_argument("--b", required=True)
    args = p.parse_args(argv)

    if args.cmd == "fingerprint":
        fp = fingerprint_prep(args.prep_dir)
        text = json.dumps(fp, indent=2, sort_keys=True) + "\n"
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"wrote {args.out} ({len(fp['datasets'])} datasets)")
        else:
            print(text)
        return 0

    result = compare_fingerprints(args.a, args.b)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["overall"] in (BYTE_IDENTICAL, CONTENT_IDENTICAL) else 1


if __name__ == "__main__":
    sys.exit(main())
