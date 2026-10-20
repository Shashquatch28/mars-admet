"""The pure parts of the explainer validation (ADR-029): atom removal, random control sets, alert matching,
and the two checks against stand-in explainers whose answers are known."""

from __future__ import annotations

import random

import numpy as np
import pytest
from eval.explain_validation import (
    alert_check,
    alert_matches,
    perturbation_check,
    random_connected_atoms,
    remove_atoms,
)
from rdkit import Chem


def _mol(smi):
    return Chem.MolFromSmiles(smi)


def test_remove_atoms_keeps_the_largest_piece_and_sanitizes():
    mol = _mol("CCOC(=O)c1ccccc1")
    out = remove_atoms(mol, {2})  # delete the ester oxygen: benzoyl and ethyl separate
    assert out is not None and out.GetNumAtoms() == 8  # C(=O)c1ccccc1


def test_remove_atoms_survives_cutting_through_an_aromatic_ring():
    mol = _mol("CCc1ccccc1CCO")
    out = remove_atoms(mol, {4, 5})  # two ring atoms: the ring opens, the rest stays a valid molecule
    assert out is not None and out.GetNumAtoms() >= 3


def test_remove_atoms_refuses_degenerate_requests():
    mol = _mol("CCO")
    assert remove_atoms(mol, set()) is None
    assert remove_atoms(mol, {0, 1, 2}) is None
    assert remove_atoms(mol, {0, 1}) is None  # too little left to score


def test_random_connected_atoms_are_connected_sized_and_reproducible():
    mol = _mol("c1ccc2ccccc2c1CCN")
    a = random_connected_atoms(mol, 5, random.Random(3))
    assert len(a) == 5 and a == random_connected_atoms(mol, 5, random.Random(3))
    sub = Chem.RWMol(mol)
    keep = sorted(a)
    frag = Chem.MolFragmentToSmiles(mol, atomsToUse=keep)
    assert "." not in frag  # one connected piece
    assert len(random_connected_atoms(mol, 99, random.Random(0))) == mol.GetNumAtoms()
    assert sub is not None


def test_alert_matches_finds_a_nitro_group():
    matches = alert_matches(_mol("O=[N+]([O-])c1ccccc1"))
    names = {m[1] for m in matches}
    assert any("nitro" in n.lower() for n in names)
    assert all(m[2] for m in matches)


def test_perturbation_check_rewards_an_explainer_that_matches_the_model():
    # A "model" that is the number of aromatic atoms, explained exactly (each aromatic atom +1).
    def output(smi):
        mol = Chem.MolFromSmiles(smi)
        return float(sum(a.GetIsAromatic() for a in mol.GetAtoms()))

    def explain(smi):
        mol = Chem.MolFromSmiles(smi)
        scores = np.array([1.0 if a.GetIsAromatic() else 0.0 for a in mol.GetAtoms()])
        ring = tuple(i for i, a in enumerate(mol.GetAtoms()) if a.GetIsAromatic())
        return scores, [(ring, float(scores.sum()))], output(smi)

    smiles = ["CCc1ccccc1CCO", "CC(=O)Oc1ccccc1C(=O)O", "OCc1ccccc1CCN", "CCCCc1ccccc1O"]
    res = perturbation_check(smiles, explain, output, seed=1)
    assert res.n == len(smiles)
    assert res.concordance == 1.0  # removing the ring always lowers the output, as attributed
    assert res.control_concordance <= res.concordance


def test_perturbation_check_with_no_usable_molecule_reports_nan_not_a_number():
    res = perturbation_check(["CCO"], lambda s: None, lambda s: 0.0)
    assert res.n == 0 and np.isnan(res.concordance)


def test_alert_check_separates_an_explainer_that_finds_the_alert():
    def finds_nitro(smi):
        mol = Chem.MolFromSmiles(smi)
        patt = Chem.MolFromSmarts("[N+](=O)[O-]")
        hit = set(mol.GetSubstructMatch(patt))
        return np.array([1.0 if i in hit else 0.0 for i in range(mol.GetNumAtoms())])

    smiles = ["O=[N+]([O-])c1ccccc1", "O=[N+]([O-])c1ccc(C)cc1", "CCO"]  # the last has no alert
    res = alert_check(smiles, finds_nitro, "ames_mutagenicity", seed=0)
    assert res.n_molecules == 2  # molecules without an alert are not counted
    assert res.mean_alert > res.mean_rest
    assert res.share_alert_above_rest == pytest.approx(1.0)
