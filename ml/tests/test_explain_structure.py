"""explain.structure: placing contributions on atoms and grouping them (ADR-031). RDKit only."""

from __future__ import annotations

import numpy as np
import pytest
from explain.structure import (
    bit_environments,
    bits_to_atoms,
    fragment_scores,
    ring_systems,
)
from featurize.fingerprints import MorganConfig
from rdkit import Chem

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"


def _mol(smi: str) -> Chem.Mol:
    mol = Chem.MolFromSmiles(smi)
    assert mol is not None
    return mol


def test_every_on_bit_has_an_environment_inside_the_molecule():
    mol = _mol(ASPIRIN)
    envs = bit_environments(mol)
    assert envs, "aspirin sets some bits"
    for bit, groups in envs.items():
        assert 0 <= bit < MorganConfig().n_bits
        assert groups
        for atoms in groups:
            assert atoms and atoms <= set(range(mol.GetNumAtoms()))


def test_atom_scores_plus_unplaced_equal_the_bit_total():
    mol = _mol(ASPIRIN)
    rng = np.random.default_rng(0)
    bit_scores = rng.normal(size=MorganConfig().n_bits)
    atoms, unplaced = bits_to_atoms(mol, bit_scores)
    assert atoms.shape == (mol.GetNumAtoms(),)
    assert atoms.sum() + unplaced == pytest.approx(bit_scores.sum(), abs=1e-9)


def test_only_on_bits_reach_atoms_and_off_bits_are_unplaced():
    mol = _mol(ASPIRIN)
    on = set(bit_environments(mol))
    off_bit = next(b for b in range(MorganConfig().n_bits) if b not in on)
    scores = np.zeros(MorganConfig().n_bits)
    scores[off_bit] = 2.5
    atoms, unplaced = bits_to_atoms(mol, scores)
    assert not atoms.any()
    assert unplaced == pytest.approx(2.5)


def test_a_single_on_bit_lands_on_its_own_environment_only():
    mol = _mol("CCO")
    envs = bit_environments(mol)
    bit, groups = next(iter(envs.items()))
    scores = np.zeros(MorganConfig().n_bits)
    scores[bit] = 1.0
    atoms, unplaced = bits_to_atoms(mol, scores)
    assert unplaced == pytest.approx(0.0)
    touched = {i for i, v in enumerate(atoms) if v != 0.0}
    assert touched == set().union(*groups)
    assert atoms.sum() == pytest.approx(1.0)


def test_ring_systems_merge_fused_rings_and_keep_separate_ones_apart():
    assert len(ring_systems(_mol("c1ccc2ccccc2c1"))) == 1  # naphthalene
    assert len(ring_systems(_mol("c1ccccc1-c1ccccc1"))) == 2  # biphenyl
    assert ring_systems(_mol("CCO")) == []


def test_fragments_are_a_view_over_atoms():
    mol = _mol(ASPIRIN)
    rng = np.random.default_rng(1)
    atom_scores = rng.normal(size=mol.GetNumAtoms())
    frags = fragment_scores(mol, atom_scores)
    names = {f.name for f in frags}
    assert "ring system" in names
    assert any("carboxylic" in n.lower() for n in names)
    for f in frags:
        assert f.score == pytest.approx(atom_scores[list(f.atom_indices)].sum())
        assert list(f.atom_indices) == sorted(set(f.atom_indices))
    # sorted by absolute score, deterministic
    assert [abs(f.score) for f in frags] == sorted((abs(f.score) for f in frags), reverse=True)
    assert frags == fragment_scores(mol, atom_scores)


def test_matches_that_share_an_atom_are_one_group():
    # A CF3 matches the alkyl-halide pattern once per C-F bond; it is one group of four atoms.
    mol = _mol("FC(F)(F)c1ccccc1")
    frags = fragment_scores(mol, np.ones(mol.GetNumAtoms()))
    halides = [f for f in frags if f.name == "alkyl halides"]
    assert len(halides) == 1 and len(halides[0].atom_indices) == 4


def test_separate_groups_of_the_same_kind_stay_separate():
    mol = _mol("c1ccccc1CCc1ccccc1")
    benzene = [f for f in fragment_scores(mol, np.ones(mol.GetNumAtoms())) if f.name == "benzene rings"]
    assert len(benzene) == 2
    assert not set(benzene[0].atom_indices) & set(benzene[1].atom_indices)


@pytest.mark.parametrize("smi", ["CC(=O)Oc1ccccc1C(=O)O", "Cc1ccc(cc1)-c1cc(nn1-c1ccc(cc1)S(N)(=O)=O)C(F)(F)F", "C[C@H](N)C(=O)O"])
def test_conformer_heavy_atoms_are_in_rdkit_order(smi):
    """The 3D highlight uses an attribution's atom index as the viewer's atom index (ADR-031). That holds
    only while the served conformer lists the heavy atoms first, in the order RDKit parsed the SMILES."""
    from featurize.conformers import generate_conformer

    mol = _mol(smi)
    res = generate_conformer(smi)
    assert res.ok
    n = mol.GetNumAtoms()
    assert [a.element for a in res.atoms[:n]] == [a.GetSymbol() for a in mol.GetAtoms()]
    assert all(a.element == "H" for a in res.atoms[n:])
