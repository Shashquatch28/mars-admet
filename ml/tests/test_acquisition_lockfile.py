"""
Verification of a produced acquisition against its lockfile
(ml/data/metadata/datasets.lock.json).

This is an *integration* check: it re-derives every recorded hash from the raw
files on disk and asserts they match. It runs only when an acquisition has
actually been performed on this machine; otherwise it skips (so CI without the
~22 MB of raw data still passes).

Run the acquisition with:  see ml/data/acquisition/README.md
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from data.snapshot import canonical_rows_digest, sha256_file

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = REPO_ROOT / "ml" / "data"
LOCKFILE = DATA_ROOT / "metadata" / "datasets.lock.json"

EXPECTED_PRIMARY_ENDPOINTS = {
    "solubility_logs",
    "lipophilicity_logp",
    "caco2_permeability",
    "hia_absorption",
    "pgp_inhibition",
    "bbb_permeability",
    "ppb_binding",
    "cyp3a4_inhibition",
    "cyp2d6_inhibition",
    "cyp2c9_inhibition",
    "clearance_microsomal",
    "herg_cardiotoxicity",
    "ames_mutagenicity",
    "dili_liver_injury",
}


def _load_lock() -> dict:
    if not LOCKFILE.exists():
        pytest.skip(f"no acquisition lockfile at {LOCKFILE} — run acquisition first")
    return json.loads(LOCKFILE.read_text(encoding="utf-8"))


def _rows_from_csv(path: Path, smiles_col: str, label_col: str):
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            yield row[smiles_col], row[label_col]


@pytest.fixture(scope="module")
def lock() -> dict:
    return _load_lock()


def test_schema_and_acquisition_block(lock):
    assert lock["schema_version"] == 1
    acq = lock["acquisition"]
    assert acq["pytdc_version"] and acq["pytdc_version"] != "unknown"
    assert acq["acq_id"]
    assert acq["acquired_at_utc"].endswith("Z")
    assert acq["tdc_benchmark_group_dataset_names"], "benchmark group names not recorded"


def test_all_primary_endpoints_and_both_herg_present(lock):
    ds = lock["datasets"]
    primary_endpoints = {
        e["endpoint_key"] for e in ds.values() if e["variant"] == "primary"
    }
    assert primary_endpoints == EXPECTED_PRIMARY_ENDPOINTS
    assert "herg_cardiotoxicity__benchmark" in ds
    assert ds["herg_cardiotoxicity__benchmark"]["variant"] == "benchmark_alt"
    assert ds["herg_cardiotoxicity"]["tdc_name"] == "hERG_Karim"


def test_raw_files_exist_and_hashes_match(lock):
    for key, entry in lock["datasets"].items():
        for f in entry["raw_files"]:
            p = DATA_ROOT / f["path"]
            assert p.exists(), f"{key}: missing raw file {f['path']}"
            assert p.stat().st_size == f["bytes"], f"{key}: size drift {f['path']}"
            assert sha256_file(p) == f["sha256"], f"{key}: sha256 drift {f['path']}"


def test_snapshot_digest_reproduces_from_full_csv(lock):
    for key, entry in lock["datasets"].items():
        full = next(
            f for f in entry["raw_files"] if f["role"] == "full_normalized_csv"
        )
        path = DATA_ROOT / full["path"]
        digest = canonical_rows_digest(
            _rows_from_csv(path, entry["smiles_column"], entry["label_column"])
        )
        assert digest == entry["snapshot_sha256"], f"{key}: snapshot digest drift"
        assert full["n_rows"] == entry["n_rows"]


def test_benchmark_splits_present_for_group_datasets(lock):
    for key, entry in lock["datasets"].items():
        if not entry["in_admet_benchmark_group"]:
            assert entry["benchmark_split"] is None, key
            continue
        bs = entry["benchmark_split"]
        assert bs and "error" not in bs, f"{key}: benchmark split failed: {bs}"
        for part in ("train_val", "test"):
            p = DATA_ROOT / bs[part]["path"]
            assert p.exists(), f"{key}: missing {part}"
            assert sha256_file(p) == bs[part]["sha256"], f"{key}: {part} sha256 drift"
            digest = canonical_rows_digest(
                _rows_from_csv(p, entry["smiles_column"], entry["label_column"])
            )
            assert digest == bs[part]["snapshot_sha256"], f"{key}: {part} digest drift"


def test_benchmark_split_partitions_the_full_set_except_ppbr(lock):
    """
    For every benchmark-group dataset the official split should be a partition of
    the single_pred full set (train_val + test == full N). PPBR_AZ is the known
    exception (single_pred N != benchmark N) — asserted here so a regression that
    'fixes' it silently is noticed and reviewed.
    """
    mismatches = {}
    for key, entry in lock["datasets"].items():
        bs = entry.get("benchmark_split")
        if not bs or "train_val" not in bs:
            continue
        total = bs["train_val"]["n_rows"] + bs["test"]["n_rows"]
        if total != entry["n_rows"]:
            mismatches[key] = (entry["n_rows"], total)
    assert set(mismatches) == {"ppb_binding"}, (
        f"unexpected full-vs-benchmark N mismatches: {mismatches}"
    )


def test_blueprint_n_flags_recorded(lock):
    """The known sample-count deviations are recorded, not hidden."""
    ds = lock["datasets"]
    # these deviate >5% from the blueprint Module 2 headline N
    assert ds["ppb_binding"]["n_matches_blueprint_within_5pct"] is False
    # solubility / CYP series / clearance / DILI match exactly
    assert ds["solubility_logs"]["n_matches_blueprint_within_5pct"] is True
    assert ds["dili_liver_injury"]["n_matches_blueprint_within_5pct"] is True
