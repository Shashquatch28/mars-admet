"""Tests for Murcko scaffold computation."""

from __future__ import annotations

from featurize.scaffold import murcko_scaffold_from_smiles, murcko_scaffolds_batch


def test_aspirin_scaffold_is_benzene():
    assert murcko_scaffold_from_smiles("CC(=O)Oc1ccccc1C(=O)O") == "c1ccccc1"


def test_acyclic_returns_empty_sentinel():
    assert murcko_scaffold_from_smiles("CCO") == ""
    assert murcko_scaffold_from_smiles("CCCCCCCC") == ""


def test_empty_input_returns_empty():
    assert murcko_scaffold_from_smiles("") == ""


def test_invalid_smiles_returns_empty():
    assert murcko_scaffold_from_smiles("NOT_A_SMILES") == ""


def test_batch_matches_singleton():
    xs = ["CC(=O)Oc1ccccc1C(=O)O", "CCO", "c1ccncc1"]
    assert murcko_scaffolds_batch(xs) == [murcko_scaffold_from_smiles(x) for x in xs]
