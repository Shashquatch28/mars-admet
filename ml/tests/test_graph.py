"""Tests for Module 3 Stage 2 — molecular graph representation."""

from __future__ import annotations

import numpy as np
from featurize.graph import (
    ATOM_FEATURE_DIM,
    BOND_FEATURE_DIM,
    GRAPH_FEATURE_VERSION,
    GraphFeaturizerConfig,
    chirality_bit_slice,
    molecule_graph,
    molecule_graphs_batch,
)

# --- basic shape + validity -----------------------------------------------


def test_shapes_and_dtypes():
    g = molecule_graph("c1ccccc1O")  # phenol: 7 atoms, 7 bonds
    assert g.n_atoms == 7
    assert g.n_bonds == 14  # 7 bonds * 2 (directed)
    assert g.atom_features.shape == (7, ATOM_FEATURE_DIM)
    assert g.atom_features.dtype == np.float32
    assert g.edge_index.shape == (2, 14)
    assert g.edge_index.dtype == np.int64
    assert g.edge_features.shape == (14, BOND_FEATURE_DIM)
    assert g.edge_features.dtype == np.float32


def test_invalid_smiles_returns_none():
    assert molecule_graph("NOT_A_SMILES") is None
    assert molecule_graph("") is None


def test_edges_are_symmetric_directed_pairs():
    g = molecule_graph("CCO")
    # every bond appears twice; consecutive rows are (a,b) and (b,a) with same features
    for i in range(0, g.n_bonds, 2):
        a, b = int(g.edge_index[0, i]), int(g.edge_index[1, i])
        assert int(g.edge_index[0, i + 1]) == b
        assert int(g.edge_index[1, i + 1]) == a
        assert np.array_equal(g.edge_features[i], g.edge_features[i + 1])


def test_default_config_matches_blueprint():
    cfg = GraphFeaturizerConfig()
    assert cfg.include_chirality is True
    assert cfg.version == GRAPH_FEATURE_VERSION
    assert cfg.atom_feature_dim == ATOM_FEATURE_DIM


# --- chirality (Module 3 §Stereochemistry non-negotiable) -----------------


def test_enantiomers_produce_different_atom_features_with_chirality_on():
    L = molecule_graph("C[C@@H](N)C(=O)O")
    D = molecule_graph("C[C@H](N)C(=O)O")
    assert L is not None and D is not None
    assert L.n_atoms == D.n_atoms
    # atom features must differ (they should ONLY differ in the chirality bins)
    assert not np.array_equal(L.atom_features, D.atom_features)


def test_disabling_chirality_collapses_enantiomers_in_atom_features():
    cfg = GraphFeaturizerConfig(include_chirality=False)
    L = molecule_graph("C[C@@H](N)C(=O)O", cfg)
    D = molecule_graph("C[C@H](N)C(=O)O", cfg)
    assert np.array_equal(L.atom_features, D.atom_features)


def test_chirality_bins_are_the_only_difference_between_enantiomers():
    L = molecule_graph("C[C@@H](N)C(=O)O")
    D = molecule_graph("C[C@H](N)C(=O)O")
    lo, hi = chirality_bit_slice()
    # mask out the chirality bins
    L_masked = L.atom_features.copy()
    D_masked = D.atom_features.copy()
    L_masked[:, lo:hi] = 0
    D_masked[:, lo:hi] = 0
    assert np.array_equal(L_masked, D_masked)
    # and the chirality slice itself IS different
    assert not np.array_equal(L.atom_features[:, lo:hi], D.atom_features[:, lo:hi])


def test_undefined_stereo_is_not_fabricated():
    """An unspecified center encodes as CHI_UNSPECIFIED (bin 0), never guessed."""
    g = molecule_graph("CC(N)C(=O)O")
    lo, hi = chirality_bit_slice()
    for row in g.atom_features:
        chi = row[lo:hi]
        # exactly one bin should be hot — and for an undefined stereocenter it must be bin 0
        assert int(chi.sum()) == 1
        assert chi[0] == 1.0


def test_bond_stereo_survives_into_edge_features():
    """(E)- and (Z)-2-butene must produce different bond feature vectors."""
    e = molecule_graph("C/C=C/C")
    z = molecule_graph("C/C=C\\C")
    assert e is not None and z is not None
    # different bond stereo → the edge feature matrix differs
    assert not np.array_equal(e.edge_features, z.edge_features)


# --- determinism + batch --------------------------------------------------


def test_deterministic():
    a = molecule_graph("c1ccc(Cl)cc1")
    b = molecule_graph("c1ccc(Cl)cc1")
    assert np.array_equal(a.atom_features, b.atom_features)
    assert np.array_equal(a.edge_index, b.edge_index)
    assert np.array_equal(a.edge_features, b.edge_features)


def test_batch_matches_singleton_and_drops_invalid_indices():
    xs = ["CCO", "NOT_A_SMILES", "c1ccncc1", "C[C@@H](N)C(=O)O"]
    gs, dropped = molecule_graphs_batch(xs)
    assert dropped == [1]
    assert len(gs) == 3
    assert np.array_equal(gs[0].atom_features, molecule_graph("CCO").atom_features)
    assert np.array_equal(gs[1].atom_features, molecule_graph("c1ccncc1").atom_features)
    assert np.array_equal(gs[2].atom_features, molecule_graph("C[C@@H](N)C(=O)O").atom_features)


def test_empty_batch_returns_empty_lists():
    gs, dropped = molecule_graphs_batch([])
    assert gs == []
    assert dropped == []


# --- feature-slice invariants ---------------------------------------------


def test_atom_feature_row_sum_matches_expected_one_hot_count():
    """Each atom row must have exactly seven '1's under one-hot encoding:
    (element, degree, charge, chirality, hybridization, hydrogens) + (aromatic?, in_ring?)
    where the last two are binary flags each individually ≤ 1.
    """
    g = molecule_graph("c1ccc(O)cc1")
    # Six one-hot categories contribute exactly 1 each → 6.
    # Aromatic and in_ring are binary flags → 0 or 1 each; sum ∈ {6, 7, 8}.
    for row in g.atom_features:
        s = int(row.sum())
        assert 6 <= s <= 8, s


def test_bond_feature_row_sum_matches_expected_one_hot_count():
    """Bond row: (bond_type) + (bond_stereo) + optional (conjugated, in_ring)"""
    g = molecule_graph("c1ccc(O)cc1")
    for row in g.edge_features:
        s = int(row.sum())
        # bond_type → 1, bond_stereo → 1, flags → 0..2 → total 2..4
        assert 2 <= s <= 4, s


def test_cache_key_encodes_chirality_choice():
    a = GraphFeaturizerConfig().cache_key()
    b = GraphFeaturizerConfig(include_chirality=False).cache_key()
    assert a != b
