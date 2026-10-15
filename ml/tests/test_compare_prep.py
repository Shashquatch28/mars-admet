"""Tests for data/compare_prep.py - read-only provenance comparison of prepared snapshots."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from data.compare_prep import (
    BYTE_IDENTICAL,
    CONTENT_IDENTICAL,
    MATERIALLY_DIFFERENT,
    UNABLE_TO_VERIFY,
    compare_fingerprints,
    fingerprint_prep,
)

_TV = "standardized_smiles,label\nCCO,1.0\nCCC,0.0\nc1ccccc1,1.0\n"
_TE = "standardized_smiles,label\nCCN,0.0\nCCCC,1.0\n"
_CA = "standardized_smiles,label\nCCO,1.0\n"


def _make_prep(root: Path, prep_id: str, *, tv: str = _TV, extra_manifest: dict | None = None,
               abs_prefix: str = "C:/laptop") -> Path:
    d = root / prep_id
    ds = d / "ames_mutagenicity"
    ds.mkdir(parents=True)
    (ds / "train_val.csv").write_text(tv, newline="")
    (ds / "test.csv").write_text(_TE, newline="")
    (ds / "calibration.csv").write_text(_CA, newline="")
    manifest = {
        "prep_id": prep_id, "acquisition_id": "acq-" + prep_id, "eda_id": "eda-" + prep_id,
        "generated_at_utc": "2026-01-01T00:00:00Z", "dedup_version": "mars-dedup-v1",
        "prep_schema_version": 1, "split_version": "mars-split-v1", "standardizer_version": "mars-standardizer-v1",
        # Absolute paths differ per machine - this is why manifests are never byte-compared.
        "datasets": {"ames_mutagenicity": {"path": f"{abs_prefix}/{prep_id}"}},
        **(extra_manifest or {}),
    }
    (d / "manifest.json").write_text(json.dumps(manifest))
    return d


def test_identical_data_with_different_ids_and_machine_paths_is_byte_identical(tmp_path):
    a = _make_prep(tmp_path / "laptop", "20260830T200000Z", abs_prefix="C:/Users/x/laptop")
    b = _make_prep(tmp_path / "ws", "20260918T090433Z", abs_prefix="/home/y/workstation")
    res = compare_fingerprints(a, b)
    assert res["overall"] == BYTE_IDENTICAL
    assert res["datasets"]["ames_mutagenicity"]["classification"] == BYTE_IDENTICAL
    # IDs are reported as expected-to-differ, not treated as a mismatch.
    assert res["ids_expected_to_differ"]["prep_id"] == ("20260830T200000Z", "20260918T090433Z")
    assert res["pipeline_version_mismatch"] == {}


def test_same_rows_different_bytes_is_content_identical_not_byte_identical(tmp_path):
    a = _make_prep(tmp_path / "a", "p1")
    reordered = "standardized_smiles,label\nc1ccccc1,1.0\nCCO,1.0\nCCC,0.0\n"  # order differs
    b = _make_prep(tmp_path / "b", "p2", tv=reordered)
    res = compare_fingerprints(a, b)
    assert res["overall"] == CONTENT_IDENTICAL
    assert "bytes differ, canonical content equal" in res["datasets"]["ames_mutagenicity"]["reasons"][0]


def test_float_formatting_differences_are_content_identical(tmp_path):
    a = _make_prep(tmp_path / "a", "p1")
    b = _make_prep(tmp_path / "b", "p2", tv=_TV.replace("1.0", "1").replace("0.0", "0"))
    assert compare_fingerprints(a, b)["overall"] == CONTENT_IDENTICAL


def test_a_changed_label_is_materially_different(tmp_path):
    a = _make_prep(tmp_path / "a", "p1")
    b = _make_prep(tmp_path / "b", "p2", tv=_TV.replace("CCC,0.0", "CCC,1.0"))
    res = compare_fingerprints(a, b)
    assert res["overall"] == MATERIALLY_DIFFERENT
    assert "content differs" in res["datasets"]["ames_mutagenicity"]["reasons"][0]


def test_a_dropped_row_is_materially_different(tmp_path):
    a = _make_prep(tmp_path / "a", "p1")
    b = _make_prep(tmp_path / "b", "p2", tv="standardized_smiles,label\nCCO,1.0\nCCC,0.0\n")
    assert compare_fingerprints(a, b)["overall"] == MATERIALLY_DIFFERENT


def test_missing_dataset_on_one_side_is_unable_to_verify_not_a_pass(tmp_path):
    a = _make_prep(tmp_path / "a", "p1")
    b = _make_prep(tmp_path / "b", "p2")
    (b / "ames_mutagenicity" / "test.csv").unlink()
    res = compare_fingerprints(a, b)
    assert res["overall"] == UNABLE_TO_VERIFY
    assert "test.csv missing on B" in res["datasets"]["ames_mutagenicity"]["reasons"][0]


def test_dataset_present_on_only_one_side_is_unable_to_verify(tmp_path):
    a = _make_prep(tmp_path / "a", "p1")
    fp_b = fingerprint_prep(_make_prep(tmp_path / "b", "p2"))
    fp_b["datasets"]["extra_endpoint"] = fp_b["datasets"]["ames_mutagenicity"]
    res = compare_fingerprints(a, fp_b)
    assert res["datasets"]["extra_endpoint"]["classification"] == UNABLE_TO_VERIFY
    assert res["overall"] == UNABLE_TO_VERIFY


def test_identical_bytes_but_a_different_pipeline_version_is_not_the_same_provenance(tmp_path):
    a = _make_prep(tmp_path / "a", "p1")
    b = _make_prep(tmp_path / "b", "p2", extra_manifest={"split_version": "mars-split-v2"})
    res = compare_fingerprints(a, b)
    assert res["overall"] == MATERIALLY_DIFFERENT
    assert res["pipeline_version_mismatch"] == {"split_version": ("mars-split-v1", "mars-split-v2")}


def test_fingerprints_can_be_compared_without_the_data(tmp_path):
    """The workstation ships a ~KB fingerprint, not the processed data."""
    fp_a = tmp_path / "a.json"
    fp_a.write_text(json.dumps(fingerprint_prep(_make_prep(tmp_path / "a", "p1"))))
    fp_b = tmp_path / "b.json"
    fp_b.write_text(json.dumps(fingerprint_prep(_make_prep(tmp_path / "b", "p2"))))
    assert compare_fingerprints(fp_a, fp_b)["overall"] == BYTE_IDENTICAL


def test_comparison_is_read_only(tmp_path):
    a = _make_prep(tmp_path / "a", "p1")
    b = _make_prep(tmp_path / "b", "p2", tv=_TV.replace("CCC,0.0", "CCC,1.0"))
    before = {p: p.read_bytes() for d in (a, b) for p in d.rglob("*") if p.is_file()}
    compare_fingerprints(a, b)
    fingerprint_prep(a)
    assert {p: p.read_bytes() for p in before} == before
    assert {p for d in (a, b) for p in d.rglob("*") if p.is_file()} == set(before)  # nothing created


def test_missing_manifest_is_reported_not_guessed(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(FileNotFoundError, match="manifest.json"):
        fingerprint_prep(tmp_path / "empty")


def test_canonical_fingerprint_matches_the_real_snapshot_when_present():
    ml = Path(__file__).resolve().parents[1]
    fp = ml / "data" / "metadata" / "prep_fingerprint.20260830T200000Z.json"
    prep = ml / "data" / "processed" / "20260830T200000Z"
    if not (fp.exists() and prep.exists()):
        pytest.skip("canonical fingerprint or snapshot not present")
    assert compare_fingerprints(fp, prep)["overall"] == BYTE_IDENTICAL
