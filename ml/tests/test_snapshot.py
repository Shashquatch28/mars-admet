"""Unit tests for deterministic snapshot hashing (ml/data/snapshot.py)."""

from __future__ import annotations

import hashlib

from data.snapshot import (
    canonical_label,
    canonical_rows_digest,
    sha256_file,
)


def test_canonical_label_int_float_equivalence():
    assert canonical_label(1) == canonical_label(1.0) == "1"
    assert canonical_label(0) == canonical_label(0.0) == "0"
    assert canonical_label(True) == "1"
    assert canonical_label(False) == "0"


def test_canonical_label_missing_variants_collapse():
    null = "\x00null"
    assert canonical_label(None) == null
    assert canonical_label(float("nan")) == null
    assert canonical_label("nan") == null
    assert canonical_label("") == null
    assert canonical_label("  ") == null


def test_canonical_label_real_float_roundtrips():
    assert canonical_label(3.14159) == repr(3.14159)
    assert canonical_label(-2.5) == repr(-2.5)


def test_digest_is_order_independent():
    a = [("CCO", 1.0), ("c1ccccc1", 0.0), ("CC(=O)O", 1)]
    b = list(reversed(a))
    assert canonical_rows_digest(a) == canonical_rows_digest(b)


def test_digest_is_content_sensitive():
    base = [("CCO", 1.0), ("c1ccccc1", 0.0)]
    changed_label = [("CCO", 0.0), ("c1ccccc1", 0.0)]
    changed_smiles = [("CCON", 1.0), ("c1ccccc1", 0.0)]
    assert canonical_rows_digest(base) != canonical_rows_digest(changed_label)
    assert canonical_rows_digest(base) != canonical_rows_digest(changed_smiles)


def test_digest_strips_smiles_whitespace_only():
    assert canonical_rows_digest([(" CCO ", 1)]) == canonical_rows_digest([("CCO", 1)])


def test_digest_classification_label_stored_as_float_matches_int():
    as_float = [("CCO", 1.0), ("CCN", 0.0)]
    as_int = [("CCO", 1), ("CCN", 0)]
    assert canonical_rows_digest(as_float) == canonical_rows_digest(as_int)


def test_sha256_file_matches_hashlib(tmp_path):
    p = tmp_path / "x.bin"
    payload = b"mars-admet\n" * 5000  # exceed the 1 MiB chunk boundary is not needed; just multi-chunk-safe
    p.write_bytes(payload)
    assert sha256_file(p) == hashlib.sha256(payload).hexdigest()
