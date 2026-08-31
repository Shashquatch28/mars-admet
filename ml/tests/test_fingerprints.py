"""Tests for Module 3 Stage 3 — Morgan/ECFP fingerprints (r=2 / 2048 / chirality)."""

from __future__ import annotations

import numpy as np
import pytest
from featurize.fingerprints import (
    MORGAN_FP_VERSION,
    MorganConfig,
    morgan_fingerprint,
    morgan_fingerprints_batch,
    summary,
    tanimoto_similarity,
)

# --- shape + dtype --------------------------------------------------------


def test_fp_is_2048_bit_uint8():
    fp = morgan_fingerprint("CCO")
    assert fp.shape == (2048,)
    assert fp.dtype == np.uint8


def test_default_config_matches_blueprint():
    cfg = MorganConfig()
    assert cfg.radius == 2
    assert cfg.n_bits == 2048
    assert cfg.use_chirality is True
    assert cfg.version == MORGAN_FP_VERSION


# --- validity + invalidity --------------------------------------------------


def test_invalid_smiles_returns_none():
    assert morgan_fingerprint("NOT_A_SMILES") is None
    assert morgan_fingerprint("") is None


def test_bit_count_is_positive_for_a_real_molecule():
    fp = morgan_fingerprint("c1ccccc1O")
    assert int(fp.sum()) > 0


# --- chirality (the CYP2C9 concern from blueprint Module 3 §Stereochemistry) --


def test_enantiomers_produce_different_fingerprints_with_chirality_on():
    """L- and D-alanine must NOT hash to the same ECFP4 under useChirality=True.
    Without this fix, CYP2C9 predictions would be stereo-blind."""
    L = morgan_fingerprint("C[C@@H](N)C(=O)O")
    D = morgan_fingerprint("C[C@H](N)C(=O)O")
    assert L is not None and D is not None
    assert not np.array_equal(L, D), "enantiomer fingerprints collapsed to the same bits"


def test_disabling_chirality_collapses_enantiomers():
    """Sanity check the opposite direction — proves useChirality is what matters."""
    cfg = MorganConfig(use_chirality=False)
    L = morgan_fingerprint("C[C@@H](N)C(=O)O", cfg)
    D = morgan_fingerprint("C[C@H](N)C(=O)O", cfg)
    assert np.array_equal(L, D)


def test_undefined_stereo_still_hashes_stably_with_chirality_on():
    """Turning chirality on must NOT change the FP for a molecule with no defined
    stereocenter — it stays whatever it would have been either way."""
    with_chi = morgan_fingerprint("CC(N)C(=O)O", MorganConfig(use_chirality=True))
    without_chi = morgan_fingerprint("CC(N)C(=O)O", MorganConfig(use_chirality=False))
    assert np.array_equal(with_chi, without_chi)


# --- determinism + batch --------------------------------------------------


def test_output_is_deterministic():
    a = morgan_fingerprint("c1ccc(Cl)cc1")
    b = morgan_fingerprint("c1ccc(Cl)cc1")
    assert np.array_equal(a, b)


def test_batch_matches_singleton():
    xs = ["CCO", "c1ccccc1O", "C[C@@H](N)C(=O)O", "c1ccncc1"]
    matrix, dropped = morgan_fingerprints_batch(xs)
    assert dropped == []
    assert matrix.shape == (4, 2048)
    for i, s in enumerate(xs):
        assert np.array_equal(matrix[i], morgan_fingerprint(s))


def test_batch_drops_invalid_indices_and_keeps_matrix_dense():
    xs = ["CCO", "NOT_A_SMILES", "c1ccccc1"]
    matrix, dropped = morgan_fingerprints_batch(xs)
    assert dropped == [1]
    assert matrix.shape == (2, 2048)
    assert np.array_equal(matrix[0], morgan_fingerprint("CCO"))
    assert np.array_equal(matrix[1], morgan_fingerprint("c1ccccc1"))


def test_empty_batch_returns_zero_row_matrix_not_error():
    matrix, dropped = morgan_fingerprints_batch([])
    assert matrix.shape == (0, 2048)
    assert dropped == []


# --- Tanimoto -------------------------------------------------------------


def test_tanimoto_self_is_one():
    fp = morgan_fingerprint("c1ccc(O)cc1")
    assert tanimoto_similarity(fp, fp) == 1.0


def test_tanimoto_disjoint_bits_is_zero():
    a = np.zeros(8, dtype=np.uint8)
    b = np.zeros(8, dtype=np.uint8)
    a[:4] = 1
    b[4:] = 1
    assert tanimoto_similarity(a, b) == 0.0


def test_tanimoto_shape_mismatch_raises():
    with pytest.raises(ValueError):
        tanimoto_similarity(np.zeros(8, dtype=np.uint8), np.zeros(16, dtype=np.uint8))


def test_tanimoto_enantiomers_are_similar_but_not_identical():
    L = morgan_fingerprint("C[C@@H](N)C(=O)O")
    D = morgan_fingerprint("C[C@H](N)C(=O)O")
    t = tanimoto_similarity(L, D)
    assert 0.0 < t < 1.0  # some shared achiral substructure, but not the same molecule


# --- config / cache key ----------------------------------------------------


def test_cache_key_encodes_all_variables():
    a = MorganConfig().cache_key()
    b = MorganConfig(use_chirality=False).cache_key()
    c = MorganConfig(radius=3).cache_key()
    d = MorganConfig(n_bits=1024).cache_key()
    assert len({a, b, c, d}) == 4  # all distinct


# --- summary --------------------------------------------------------------


def test_summary_shape():
    m, _ = morgan_fingerprints_batch(["CCO", "c1ccccc1O", "c1ccncc1"])
    s = summary(m)
    assert s["n"] == 3
    assert s["n_bits"] == 2048
    assert s["mean_on_bits"] > 0
    assert s["active_bit_positions"] > 0


def test_summary_of_empty_is_safe():
    s = summary(np.zeros((0, 2048), dtype=np.uint8))
    assert s == {"n": 0, "mean_on_bits": 0.0, "active_bit_positions": 0}
