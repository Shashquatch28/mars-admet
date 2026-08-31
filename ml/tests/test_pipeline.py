"""Tests for the batched Module 3 featurization pipeline façade."""

from __future__ import annotations

import numpy as np
from featurize.descriptors import DESCRIPTOR_COUNT
from featurize.fingerprints import morgan_fingerprint
from featurize.graph import molecule_graph
from featurize.pipeline import PIPELINE_VERSION, PipelineConfig, featurize_batch

RAW = ["CCO", "CC[O-].[Na+]", "NOT_A_SMILES", "C[C@@H](N)C(=O)O", "c1ccc(O)cc1"]


def test_standardization_runs_once_and_drops_invalid():
    b = featurize_batch(RAW)
    # "NOT_A_SMILES" (index 2) is the only reject
    assert b.kept_input_indices == [0, 1, 3, 4]
    assert b.n_input == 5
    assert len(b.standardized_smiles) == 4
    assert b.standardization_rejects.get("smiles-parse-failed") == 1


def test_every_requested_stage_output_aligns_to_standardized_smiles():
    b = featurize_batch(RAW)
    n = len(b.standardized_smiles)
    assert len(b.graphs) == n
    assert b.morgan.shape == (n, 2048)
    assert b.descriptors.shape == (n, DESCRIPTOR_COUNT)
    assert b.descriptor_finite_mask.shape == (n, DESCRIPTOR_COUNT)


def test_pipeline_matches_calling_each_stage_directly():
    b = featurize_batch(RAW)
    for i, smi in enumerate(b.standardized_smiles):
        assert np.array_equal(b.morgan[i], morgan_fingerprint(smi))
        assert np.array_equal(b.graphs[i].atom_features, molecule_graph(smi).atom_features)


def test_conformers_are_off_by_default_and_opt_in():
    default = featurize_batch(["CCO", "c1ccccc1O"])
    assert default.conformers is None

    with_conf = featurize_batch(
        ["CCO", "c1ccccc1O"],
        PipelineConfig(want_graph=False, want_morgan=False, want_descriptors=False, want_conformers=True),
    )
    assert with_conf.conformers is not None
    assert len(with_conf.conformers) == 2
    assert all(c.ok for c in with_conf.conformers)


def test_selective_stages():
    b = featurize_batch(
        ["CCO", "c1ccccc1"],
        PipelineConfig(want_graph=True, want_morgan=False, want_descriptors=False),
    )
    assert b.graphs is not None
    assert b.morgan is None
    assert b.descriptors is None
    assert "morgan_version" not in b.provenance
    assert "graph_version" in b.provenance


def test_provenance_bundle_names_every_active_stage_version():
    b = featurize_batch(["CCO"], PipelineConfig(want_conformers=True))
    p = b.provenance
    assert p["pipeline_version"] == PIPELINE_VERSION
    assert p["standardizer_version"]
    assert p["graph_version"] and p["morgan_version"] and p["descriptor_version"]
    assert p["conformer_version"]
    # cache keys present for each
    assert p["graph_cache_key"] and p["morgan_cache_key"] and p["descriptor_cache_key"]


def test_all_invalid_batch_returns_empty_but_valid_structure():
    b = featurize_batch(["NOT_A_SMILES", ""])
    assert b.standardized_smiles == []
    assert b.kept_input_indices == []
    assert b.graphs is None  # nothing to featurize
    assert b.provenance["pipeline_version"] == PIPELINE_VERSION


def test_summary_is_serialisable_and_complete():
    b = featurize_batch(RAW, PipelineConfig(want_conformers=True))
    s = b.summary()
    assert s["n_input"] == 5
    assert s["n_standardized"] == 4
    assert s["n_graphs"] == 4
    assert s["morgan_shape"] == [4, 2048]
    assert s["descriptor_shape"] == [4, DESCRIPTOR_COUNT]
    assert s["n_conformers_ok"] + s["n_conformers_failed"] == 4


def test_batch_is_deterministic():
    a = featurize_batch(RAW)
    b = featurize_batch(RAW)
    assert a.standardized_smiles == b.standardized_smiles
    assert np.array_equal(a.morgan, b.morgan)
    assert np.array_equal(a.descriptors, b.descriptors, equal_nan=True)
