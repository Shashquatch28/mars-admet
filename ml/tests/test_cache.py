"""Tests for the on-disk feature + conformer cache (Run 4)."""

from __future__ import annotations

import json

import numpy as np
import pytest
from featurize.cache import FeatureCache, entry_key
from featurize.conformers import ConformerConfig
from featurize.descriptors import DESCRIPTOR_COUNT
from featurize.fingerprints import MorganConfig, morgan_fingerprint
from featurize.graph import molecule_graph

SMIS = ["CCO", "c1ccccc1O", "C[C@@H](N)C(=O)O", "NOT_A_SMILES"]


@pytest.fixture()
def cache(tmp_path):
    return FeatureCache(tmp_path)


# --- deterministic keys -------------------------------------------------


def test_entry_key_is_deterministic_and_config_sensitive():
    a = entry_key("morgan", "cfgA", "CCO")
    b = entry_key("morgan", "cfgA", "CCO")
    c = entry_key("morgan", "cfgB", "CCO")
    d = entry_key("morgan", "cfgA", "CCN")
    assert a == b
    assert len({a, c, d}) == 3
    assert len(a) == 64


# --- morgan -------------------------------------------------------------


def test_morgan_first_pass_computes_second_pass_hits(cache):
    m1, drop1, st1 = cache.morgan_cached(SMIS)
    assert st1.hits == 0 and st1.computed == 3 and st1.invalid == 1
    assert drop1 == [3]

    m2, drop2, st2 = cache.morgan_cached(SMIS)
    assert st2.hits == 3 and st2.computed == 0
    assert np.array_equal(m1, m2)
    assert drop2 == [3]


def test_morgan_cached_values_match_direct_computation(cache):
    m, _drop, _st = cache.morgan_cached(SMIS)
    assert np.array_equal(m[0], morgan_fingerprint("CCO"))
    assert np.array_equal(m[1], morgan_fingerprint("c1ccccc1O"))


def test_incompatible_config_is_not_silently_reused(cache):
    cache.morgan_cached(SMIS)  # default r2/2048
    m, _drop, st = cache.morgan_cached(SMIS, MorganConfig(n_bits=1024))
    assert st.hits == 0  # different config -> different key -> full recompute
    assert m.shape[1] == 1024
    keys = list(cache.configs_seen("morgan"))
    assert len(keys) == 2  # both configs recorded, neither shadows the other


def test_config_json_records_provenance(cache):
    cache.morgan_cached(SMIS)
    meta = json.loads((cache.root / "morgan" / "_config.json").read_text())
    assert meta["stage"] == "morgan"
    assert "numpy" in meta["library_versions"]
    assert "rdkit" in meta["library_versions"]
    ck = next(iter(meta["configs_seen"]))
    assert meta["configs_seen"][ck]["n_entries"] == 3


# --- descriptors -----------------------------------------------------


def test_descriptors_cache_roundtrip(cache):
    m1, mask1, drop1, nf1, st1 = cache.descriptors_cached(SMIS)
    m2, mask2, drop2, nf2, st2 = cache.descriptors_cached(SMIS)
    assert m1.shape == (3, DESCRIPTOR_COUNT)
    assert np.array_equal(m1, m2, equal_nan=True)
    assert np.array_equal(mask1, mask2)
    assert st2.hits == 3 and st2.computed == 0
    assert drop1 == [3]


def test_descriptors_non_finite_survives_the_cache(cache):
    # if a molecule has an overflowing descriptor, the reloaded non_finite dict
    # must still name it (this only fires if the RDKit build produces one)
    weird = "c1ccc2c(c1)c1cccc3c1c1c2cccc1cc3" * 2
    m, mask, drop, nf, st = cache.descriptors_cached(["CCO", weird])
    if 1 in drop or m.shape[0] < 2:
        pytest.skip("weird molecule did not parse; non-finite path not exercised")
    # reload
    m2, mask2, drop2, nf2, st2 = cache.descriptors_cached(["CCO", weird])
    n_nf = int((~mask2).sum())
    assert n_nf == sum(len(d) for d in nf2)


# --- graph ---------------------------------------------------------


def test_graph_cache_roundtrip_preserves_arrays(cache):
    g1, d1, s1 = cache.graphs_cached(SMIS)
    g2, d2, s2 = cache.graphs_cached(SMIS)
    assert len(g1) == 3 and d1 == [3]
    assert s2.hits == 3
    for a, b in zip(g1, g2, strict=True):
        assert np.array_equal(a.atom_features, b.atom_features)
        assert np.array_equal(a.edge_index, b.edge_index)
        assert np.array_equal(a.edge_features, b.edge_features)
    assert np.array_equal(g1[0].atom_features, molecule_graph("CCO").atom_features)


def test_graph_chirality_survives_the_cache(cache):
    g, _d, _s = cache.graphs_cached(["C[C@@H](N)C(=O)O", "C[C@H](N)C(=O)O"])
    g2, _d2, _s2 = cache.graphs_cached(["C[C@@H](N)C(=O)O", "C[C@H](N)C(=O)O"])
    # enantiomers still distinguishable after a cache round-trip
    assert not np.array_equal(g2[0].atom_features, g2[1].atom_features)


# --- conformer ------------------------------------------------


def test_conformer_cache_roundtrip_is_byte_identical(cache):
    c1, s1 = cache.conformers_cached(["CCO", "c1ccccc1O", "NOT_A_SMILES"])
    c2, s2 = cache.conformers_cached(["CCO", "c1ccccc1O", "NOT_A_SMILES"])
    assert s2.hits == 3 and s2.computed == 0
    for a, b in zip(c1, c2, strict=True):
        assert a.ok == b.ok
        assert a.reason == b.reason
        assert a.force_field == b.force_field
        assert a.sdf_block == b.sdf_block
        if a.ok:
            assert abs(a.energy_kcal_mol - b.energy_kcal_mol) < 1e-9


def test_conformer_failure_is_stored_not_recomputed(cache):
    c1, _s1 = cache.conformers_cached(["NOT_A_SMILES"])
    assert not c1[0].ok
    c2, s2 = cache.conformers_cached(["NOT_A_SMILES"])
    assert s2.hits == 1 and s2.computed == 0
    assert c2[0].reason == "smiles-parse-failed"


def test_conformer_config_change_forces_recompute(cache):
    cache.conformers_cached(["CCO"], ConformerConfig(random_seed=1))
    _c, st = cache.conformers_cached(["CCO"], ConformerConfig(random_seed=2))
    assert st.hits == 0


# --- cross-stage ------------------------------------------------


def test_all_stages_share_a_root_without_collision(cache):
    cache.morgan_cached(["CCO"])
    cache.descriptors_cached(["CCO"])
    cache.graphs_cached(["CCO"])
    cache.conformers_cached(["CCO"])
    for stage in ("morgan", "descriptors", "graph", "conformer"):
        assert (cache.root / stage / "_config.json").exists()
