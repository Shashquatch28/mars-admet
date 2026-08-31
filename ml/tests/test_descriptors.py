"""Tests for Module 3 Stage 4 — RDKit 2D descriptors."""

from __future__ import annotations

import numpy as np
import pytest
from featurize.descriptors import (
    DESCRIPTOR_COUNT,
    DESCRIPTOR_NAMES,
    DESCRIPTOR_SET_SHA,
    DESCRIPTOR_VERSION,
    DescriptorConfig,
    assert_descriptor_set_matches,
    descriptor_matrix,
    descriptor_row,
    summary,
)

# --- set + ordering -----------------------------------------------------


def test_descriptor_count_is_about_200():
    assert 190 <= DESCRIPTOR_COUNT <= 230  # "~200" per blueprint; RDKit 2026.3 = 217


def test_names_are_sorted_and_unique():
    assert list(DESCRIPTOR_NAMES) == sorted(DESCRIPTOR_NAMES)
    assert len(set(DESCRIPTOR_NAMES)) == DESCRIPTOR_COUNT


def test_the_blueprint_named_descriptors_are_present():
    for n in ("MolWt", "TPSA", "MolLogP", "NumHDonors", "NumHAcceptors", "NumRotatableBonds"):
        assert n in DESCRIPTOR_NAMES


def test_descriptor_set_sha_is_stable_hash_of_the_name_list():
    import hashlib
    expected = hashlib.sha256("\n".join(DESCRIPTOR_NAMES).encode()).hexdigest()
    assert DESCRIPTOR_SET_SHA == expected


# --- values -----------------------------------------------------------


def test_aspirin_molwt_is_correct():
    r = descriptor_row("CC(=O)Oc1ccccc1C(=O)O")
    i = DESCRIPTOR_NAMES.index("MolWt")
    assert abs(r.values[i] - 180.16) < 0.1


def test_row_length_matches_count():
    r = descriptor_row("c1ccccc1O")
    assert r.values.shape == (DESCRIPTOR_COUNT,)
    assert r.ok


def test_invalid_smiles_returns_none():
    assert descriptor_row("NOT_A_SMILES") is None
    assert descriptor_row("") is None


# --- determinism + reproducibility -----------------------------------


def test_descriptor_values_are_deterministic():
    a = descriptor_row("CC(C)Cc1ccc(cc1)C(C)C(=O)O")  # ibuprofen
    b = descriptor_row("CC(C)Cc1ccc(cc1)C(C)C(=O)O")
    assert np.array_equal(a.values, b.values, equal_nan=True)


def test_column_order_is_positional_and_stable():
    """Column j always corresponds to DESCRIPTOR_NAMES[j] — a training pipeline
    can rely on the position, not just the name."""
    smis = ["CCO", "c1ccccc1", "CC(=O)O"]
    m, _mask, _dropped, _nf = descriptor_matrix(smis)
    j = DESCRIPTOR_NAMES.index("MolWt")
    per_row = [descriptor_row(s).values[j] for s in smis]
    assert np.allclose(m[:, j], per_row)


# --- batch + non-finite handling ------------------------------------


def test_batch_drops_invalid_and_keeps_dense_matrix():
    m, mask, dropped, nf = descriptor_matrix(["CCO", "NOT_A_SMILES", "c1ccccc1"])
    assert dropped == [1]
    assert m.shape == (2, DESCRIPTOR_COUNT)
    assert mask.shape == m.shape
    assert len(nf) == 2


def test_non_finite_values_are_recorded_not_silently_passed():
    """Raw matrix may contain inf/nan; the finite_mask makes it explicit rather
    than a training pipeline discovering NaNs mid-fit."""
    # a large fused-ring system is a classic Ipc-overflow trigger
    weird = "c1ccc2c(c1)c1cccc3c1c1c2cccc1cc3" * 2
    m, mask, dropped, nf = descriptor_matrix(["CCO", weird])
    if dropped == [1] or m.shape[0] < 2:
        pytest.skip("weird molecule failed to parse on this RDKit; non-finite path not exercised")
    # if any non-finite value exists, it must be reflected in BOTH mask and nf dict
    n_nonfinite = int((~mask).sum())
    total_nf_in_dicts = sum(len(d) for d in nf)
    assert n_nonfinite == total_nf_in_dicts


def test_empty_batch_is_safe():
    m, mask, dropped, nf = descriptor_matrix([])
    assert m.shape == (0, DESCRIPTOR_COUNT)
    assert mask.shape == (0, DESCRIPTOR_COUNT)
    assert dropped == []
    assert nf == []


# --- version guard --------------------------------------------------


def test_assert_descriptor_set_matches_passes_for_current():
    assert_descriptor_set_matches(DescriptorConfig())


def test_assert_descriptor_set_matches_raises_on_drift():
    stale = DescriptorConfig(descriptor_set_sha="0" * 64)
    with pytest.raises(RuntimeError):
        assert_descriptor_set_matches(stale)


def test_cache_key_encodes_version_and_set_hash():
    a = DescriptorConfig().cache_key()
    assert DESCRIPTOR_VERSION in a
    assert DESCRIPTOR_SET_SHA[:16] in a


# --- summary ------------------------------------------------------


def test_summary_reports_non_finite_columns():
    m, mask, _dropped, _nf = descriptor_matrix(["CCO", "c1ccccc1O"])
    s = summary(m, mask)
    assert s["n"] == 2
    assert s["n_descriptors"] == DESCRIPTOR_COUNT
    assert isinstance(s["non_finite_column_names"], list)
