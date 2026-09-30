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
from data.dataset_registry import DATASET_SPECS
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


def _raw_snapshot_present(lock: dict, data_root: Path = DATA_ROOT) -> bool:
    """True if ANY ``raw/*/<acq_id>`` directory for the lockfile's acquisition exists.

    The lockfile is tracked, but the raw data it references is gitignored and lives
    only on the machine that ran the acquisition. "No directory for this acquisition
    at all" means the snapshot is simply not on this machine (skip). A directory that
    exists but lacks a referenced file is a damaged snapshot (must FAIL, never skip).
    """
    acq_id = lock["acquisition"]["acq_id"]
    return any((data_root / "raw").glob(f"*/{acq_id}"))


def _require_raw_snapshot(lock: dict, data_root: Path = DATA_ROOT) -> None:
    if not _raw_snapshot_present(lock, data_root):
        pytest.skip(
            f"raw-data snapshot {lock['acquisition']['acq_id']} referenced by the lockfile is not "
            f"present under {data_root / 'raw'} — the raw-file integrity checks need the acquisition's "
            "own files (run them on the machine that holds them); no other snapshot is substituted"
        )


def _check_raw_files(lock: dict, data_root: Path = DATA_ROOT) -> None:
    """Re-derive size and SHA-256 of every raw file the lockfile references."""
    for key, entry in lock["datasets"].items():
        for f in entry["raw_files"]:
            p = data_root / f["path"]
            assert p.exists(), f"{key}: missing raw file {f['path']}"
            assert p.stat().st_size == f["bytes"], f"{key}: size drift {f['path']}"
            assert sha256_file(p) == f["sha256"], f"{key}: sha256 drift {f['path']}"


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
    _require_raw_snapshot(lock)
    _check_raw_files(lock)


def test_snapshot_digest_reproduces_from_full_csv(lock):
    _require_raw_snapshot(lock)
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
    # Lockfile-only assertions: they need no raw data and always run.
    for key, entry in lock["datasets"].items():
        if not entry["in_admet_benchmark_group"]:
            assert entry["benchmark_split"] is None, key
            continue
        bs = entry["benchmark_split"]
        assert bs and "error" not in bs, f"{key}: benchmark split failed: {bs}"
    # File-level checks need the acquisition's raw snapshot.
    _require_raw_snapshot(lock)
    for key, entry in lock["datasets"].items():
        if not entry["in_admet_benchmark_group"]:
            continue
        bs = entry["benchmark_split"]
        for part in ("train_val", "test"):
            p = DATA_ROOT / bs[part]["path"]
            assert p.exists(), f"{key}: missing {part}"
            assert sha256_file(p) == bs[part]["sha256"], f"{key}: {part} sha256 drift"
            digest = canonical_rows_digest(
                _rows_from_csv(p, entry["smiles_column"], entry["label_column"])
            )
            assert digest == bs[part]["snapshot_sha256"], f"{key}: {part} digest drift"


def test_benchmark_split_partitions_the_full_set(lock):
    """
    For every benchmark-group dataset the official split must be a partition of the
    single_pred full set (train_val + test == full N).

    Pre-Option-C, PPBR_AZ was the one known exception (single_pred N != benchmark N).
    Option C (decisions.md 2026-08-30; blueprint Module 1 §4 "PPB exception") makes the
    primary PPB endpoint human-only (N=1,614) with an independent Murcko split, so
    ``ppb_binding`` is no longer in the benchmark group, has no benchmark split, and
    there is no exception any more. The registry is the authoritative declaration.
    """
    assert DATASET_SPECS["ppb_binding"].in_admet_benchmark_group is False
    assert lock["datasets"]["ppb_binding"]["in_admet_benchmark_group"] is False
    assert lock["datasets"]["ppb_binding"]["benchmark_split"] is None

    mismatches = {}
    for key, entry in lock["datasets"].items():
        bs = entry.get("benchmark_split")
        if not bs or "train_val" not in bs:
            continue
        total = bs["train_val"]["n_rows"] + bs["test"]["n_rows"]
        if total != entry["n_rows"]:
            mismatches[key] = (entry["n_rows"], total)
    assert mismatches == {}, (
        f"unexpected full-vs-benchmark N mismatches: {mismatches}"
    )


# Blueprint Module 2 row 7: PPB "1,614 (human) / 1,797 compounds pooled". Option C makes the
# human-only set the primary endpoint, so its headline N is 1,614 (decisions.md 2026-08-30).
BLUEPRINT_PPB_HUMAN_N = 1614


def test_blueprint_n_flags_recorded(lock):
    """The sample-count flags are recorded truthfully and agree with the registry.

    Pre-Option-C this asserted that ppb_binding deviated >5% from the blueprint headline N
    (benchmark pool vs human subset). Under Option C the primary PPB set is the human-only
    1,614-compound set, which *matches* the blueprint, so the flag is True. The check is
    re-derived from the registry's ``approx_n`` with the acquisition code's own tolerance
    (``max(1, round(0.05 * approx_n))``) instead of trusting the recorded flag.
    """
    ds = lock["datasets"]

    ppb = ds["ppb_binding"]
    assert DATASET_SPECS["ppb_binding"].approx_n == BLUEPRINT_PPB_HUMAN_N
    assert ppb["n_rows"] == BLUEPRINT_PPB_HUMAN_N
    assert ppb["n_matches_blueprint_within_5pct"] is True

    # solubility / CYP series / clearance / DILI match exactly
    assert ds["solubility_logs"]["n_matches_blueprint_within_5pct"] is True
    assert ds["dili_liver_injury"]["n_matches_blueprint_within_5pct"] is True

    # Every recorded flag must equal the value re-derived from the registry, so a real
    # deviation can never be hidden behind a stale True/False.
    for key, entry in ds.items():
        approx = DATASET_SPECS[key].approx_n
        expected = approx is not None and abs(entry["n_rows"] - approx) <= max(1, round(0.05 * approx))
        assert entry["n_matches_blueprint_within_5pct"] is expected, (
            f"{key}: recorded flag {entry['n_matches_blueprint_within_5pct']} != re-derived {expected}"
        )


# ---------------------------------------------------------------------------- #
# Environment vs integrity: explicit behaviour of the raw-snapshot guard
# ---------------------------------------------------------------------------- #


def _fake_lock(acq_id: str, path: str, data: bytes, *, sha: str | None = None) -> dict:
    import hashlib

    return {
        "acquisition": {"acq_id": acq_id},
        "datasets": {
            "demo": {
                "raw_files": [
                    {
                        "path": path,
                        "bytes": len(data),
                        "sha256": sha or hashlib.sha256(data).hexdigest(),
                    }
                ]
            }
        },
    }


def test_missing_referenced_snapshot_is_skipped_with_a_reason(tmp_path):
    """No raw/*/<acq_id> directory anywhere -> the machine simply lacks the snapshot -> SKIP."""
    lock = _fake_lock("ACQ1", "raw/DEMO/ACQ1/demo.csv", b"x")
    (tmp_path / "raw" / "DEMO" / "OTHER_ACQ").mkdir(parents=True)  # a different snapshot is not a substitute
    with pytest.raises(pytest.skip.Exception, match="ACQ1.*not present"):
        _require_raw_snapshot(lock, tmp_path)


def test_present_snapshot_with_wrong_digest_fails(tmp_path):
    """Snapshot present but content drifted -> integrity check must FAIL, never skip."""
    lock = _fake_lock("ACQ1", "raw/DEMO/ACQ1/demo.csv", b"good", sha="0" * 64)
    f = tmp_path / "raw" / "DEMO" / "ACQ1" / "demo.csv"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"good")
    _require_raw_snapshot(lock, tmp_path)  # does not skip
    with pytest.raises(AssertionError, match="sha256 drift"):
        _check_raw_files(lock, tmp_path)


def test_partial_snapshot_missing_a_referenced_file_fails_not_skips(tmp_path):
    """The acquisition directory exists but a referenced file is gone -> damaged snapshot -> FAIL."""
    lock = _fake_lock("ACQ1", "raw/DEMO/ACQ1/demo.csv", b"good")
    (tmp_path / "raw" / "DEMO" / "ACQ1").mkdir(parents=True)  # directory, but no demo.csv
    _require_raw_snapshot(lock, tmp_path)  # does not skip
    with pytest.raises(AssertionError, match="missing raw file"):
        _check_raw_files(lock, tmp_path)


def test_present_snapshot_with_correct_digest_passes(tmp_path):
    lock = _fake_lock("ACQ1", "raw/DEMO/ACQ1/demo.csv", b"good")
    f = tmp_path / "raw" / "DEMO" / "ACQ1" / "demo.csv"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"good")
    _require_raw_snapshot(lock, tmp_path)
    _check_raw_files(lock, tmp_path)
