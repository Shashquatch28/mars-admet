"""
Tests for ml/eval/applicability_domain.py.

Smoke tests use a small fixed set of real SMILES (RDKit featurization runs,
but no dependency on M1 processed data). Integration tests run against real
M1 data and skip cleanly if it is not present.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from eval.applicability_domain import (
    DEFAULT_K,
    ADIndex,
    build_ad_index,
    bulk_tanimoto_distance,
    query_ad,
)
from featurize.fingerprints import MorganConfig, morgan_fingerprints_batch, tanimoto_similarity

# Ethanol, benzene, aspirin, caffeine, glucose, toluene, phenol, acetone,
# propanol, butanol — small, chemically related reference pool.
_REFERENCE_SMILES = [
    "CCO",
    "c1ccccc1",
    "CC(=O)Oc1ccccc1C(=O)O",
    "Cn1c(=O)c2c(ncn2C)n(c1=O)C",
    "OCC1OC(O)C(O)C(O)C1O",
    "Cc1ccccc1",
    "Oc1ccccc1",
    "CC(C)=O",
    "CCCO",
    "CCCCO",
]

# A large, structurally unrelated steroid-like molecule — should be far from
# the small reference pool above.
_OUT_OF_DOMAIN_SMILES = "CC12CCC3C(C1CCC2O)CCC4=CC(=O)CCC34C"


# ---------------------------------------------------------------------------- #
# bulk_tanimoto_distance
# ---------------------------------------------------------------------------- #


def test_bulk_matches_pairwise():
    fps, dropped = morgan_fingerprints_batch(_REFERENCE_SMILES, MorganConfig())
    assert not dropped
    dist = bulk_tanimoto_distance(fps, fps)
    for i in range(len(_REFERENCE_SMILES)):
        for j in range(len(_REFERENCE_SMILES)):
            expected = 1.0 - tanimoto_similarity(fps[i], fps[j])
            assert dist[i, j] == pytest.approx(expected, abs=1e-9)


def test_bulk_self_distance_is_zero():
    fps, _ = morgan_fingerprints_batch(_REFERENCE_SMILES, MorganConfig())
    dist = bulk_tanimoto_distance(fps, fps)
    np.testing.assert_allclose(np.diag(dist), 0.0, atol=1e-9)


def test_bulk_distance_in_range():
    fps, _ = morgan_fingerprints_batch(_REFERENCE_SMILES, MorganConfig())
    dist = bulk_tanimoto_distance(fps, fps)
    assert np.all(dist >= 0.0)
    assert np.all(dist <= 1.0)


def test_bulk_bit_width_mismatch_raises():
    a = np.zeros((2, 2048), dtype=np.uint8)
    b = np.zeros((2, 1024), dtype=np.uint8)
    with pytest.raises(ValueError, match="Bit-width mismatch"):
        bulk_tanimoto_distance(a, b)


def test_bulk_requires_2d():
    a = np.zeros(2048, dtype=np.uint8)
    b = np.zeros((2, 2048), dtype=np.uint8)
    with pytest.raises(ValueError, match="2-D"):
        bulk_tanimoto_distance(a, b)


# ---------------------------------------------------------------------------- #
# build_ad_index
# ---------------------------------------------------------------------------- #


def test_build_ad_index_basic_properties():
    idx = build_ad_index("test_endpoint", _REFERENCE_SMILES, k=3)
    assert isinstance(idx, ADIndex)
    assert idx.k == 3
    assert idx.percentile == 90.0
    assert 0.0 <= idx.threshold <= 1.0
    assert idx.reference_fingerprints.shape[0] == len(_REFERENCE_SMILES)
    assert len(idx.reference_smiles) == len(_REFERENCE_SMILES)


def test_build_ad_index_too_few_compounds_raises():
    with pytest.raises(ValueError, match="need more than"):
        build_ad_index("test_endpoint", _REFERENCE_SMILES[:3], k=5)


def test_build_ad_index_default_k():
    idx = build_ad_index("test_endpoint", _REFERENCE_SMILES)
    assert idx.k == DEFAULT_K


# ---------------------------------------------------------------------------- #
# query_ad
# ---------------------------------------------------------------------------- #


def test_query_reference_molecule_is_in_domain():
    idx = build_ad_index("test_endpoint", _REFERENCE_SMILES, k=3)
    # Query with one of the reference molecules itself
    results = query_ad(idx, [_REFERENCE_SMILES[0]])
    assert len(results) == 1
    assert results[0].smiles == _REFERENCE_SMILES[0]
    assert results[0].in_domain


def test_query_dissimilar_molecule_flagged_out_of_domain():
    idx = build_ad_index("test_endpoint", _REFERENCE_SMILES, k=3)
    results = query_ad(idx, [_OUT_OF_DOMAIN_SMILES])
    assert len(results) == 1
    assert results[0].knn_mean_distance > idx.threshold
    assert not results[0].in_domain


def test_query_ad_distance_bounds():
    idx = build_ad_index("test_endpoint", _REFERENCE_SMILES, k=3)
    results = query_ad(idx, [_REFERENCE_SMILES[0], _OUT_OF_DOMAIN_SMILES])
    for r in results:
        assert 0.0 <= r.knn_mean_distance <= 1.0


def test_query_ad_dropped_smiles_omitted():
    idx = build_ad_index("test_endpoint", _REFERENCE_SMILES, k=3)
    results = query_ad(idx, [_REFERENCE_SMILES[0], "[2H][3He", _REFERENCE_SMILES[1]])
    # Invalid SMILES silently dropped -> only 2 results, not 3
    assert len(results) == 2
    returned_smiles = {r.smiles for r in results}
    assert returned_smiles == {_REFERENCE_SMILES[0], _REFERENCE_SMILES[1]}


def test_query_ad_empty_fingerprint_batch_returns_empty():
    idx = build_ad_index("test_endpoint", _REFERENCE_SMILES, k=3)
    results = query_ad(idx, ["not_valid_smiles!!"])
    assert results == []


def test_query_ad_bit_width_mismatch_raises():
    idx = build_ad_index("test_endpoint", _REFERENCE_SMILES, k=3)
    bad_config = MorganConfig(n_bits=1024)
    with pytest.raises(ValueError, match="does not match"):
        query_ad(idx, [_REFERENCE_SMILES[0]], morgan_config=bad_config)


# ---------------------------------------------------------------------------- #
# save / load
# ---------------------------------------------------------------------------- #


def test_save_load_roundtrip(tmp_path):
    idx = build_ad_index("test_endpoint", _REFERENCE_SMILES, k=3)
    save_dir = tmp_path / "ad_index"
    idx.save(save_dir)
    assert (save_dir / "metadata.json").exists()
    assert (save_dir / "reference_fingerprints.npy").exists()

    loaded = ADIndex.load(save_dir)
    assert loaded.endpoint_key == idx.endpoint_key
    assert loaded.k == idx.k
    assert loaded.threshold == pytest.approx(idx.threshold)
    assert loaded.reference_smiles == idx.reference_smiles
    np.testing.assert_array_equal(loaded.reference_fingerprints, idx.reference_fingerprints)

    orig_results = query_ad(idx, [_OUT_OF_DOMAIN_SMILES])
    loaded_results = query_ad(loaded, [_OUT_OF_DOMAIN_SMILES])
    assert orig_results[0].knn_mean_distance == pytest.approx(loaded_results[0].knn_mean_distance)
    assert orig_results[0].in_domain == loaded_results[0].in_domain


# ---------------------------------------------------------------------------- #
# Integration test against real M1 data
# ---------------------------------------------------------------------------- #

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "ml" / "data"


def _newest_prep_dir() -> Path | None:
    root = DATA / "processed"
    if not root.exists():
        return None
    dirs = sorted(p for p in root.iterdir() if p.is_dir())
    return dirs[-1] if dirs else None


PREP_DIR = _newest_prep_dir()


def test_integration_dili_ad_index():
    """DILI is the smallest endpoint (~1,300 compounds per blueprint) —
    good stress test for the AD index build + query path at real scale."""
    if PREP_DIR is None:
        pytest.skip("no processed outputs")
    from data.loaders import load_endpoint

    endpoint_data = load_endpoint(PREP_DIR, "dili_liver_injury")
    tv_smiles = endpoint_data.train_val["standardized_smiles"].tolist()

    idx = build_ad_index("dili_liver_injury", tv_smiles)
    assert idx.threshold > 0.0
    assert len(idx.reference_smiles) <= len(tv_smiles)

    test_smiles = endpoint_data.test["standardized_smiles"].tolist()[:50]
    results = query_ad(idx, test_smiles)
    assert len(results) > 0
    for r in results:
        assert 0.0 <= r.knn_mean_distance <= 1.0
        assert isinstance(r.in_domain, bool) or isinstance(r.in_domain, np.bool_)

    # Not every held-out test molecule should be flagged out-of-domain —
    # scaffold-split test sets are chemically related to train_val, so the
    # vast majority are expected in-domain.
    in_domain_fraction = sum(1 for r in results if r.in_domain) / len(results)
    assert in_domain_fraction > 0.5
