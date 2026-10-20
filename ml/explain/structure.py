"""Putting attribution on a molecule's structure (Module 6, ADR-031). RDKit only.

Two pieces both explainers share:

* `bits_to_atoms` places the contribution of Morgan fingerprint bits on atoms.
* `fragment_scores` sums atom attributions over named functional groups and ring systems.

Neither invents signal. A bit's contribution is split equally over the atom environments that set
it, and each environment's share equally over the atoms inside it, so the atom total equals the
total of the bits that could be placed. A bit RDKit cannot place is returned, not dropped.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from featurize.fingerprints import MorganConfig, _make_generator
from rdkit import Chem, RDConfig
from rdkit.Chem import rdFingerprintGenerator

RING_SYSTEM_SMARTS = "[ring system]"  # not a SMARTS: a ring system is defined by the ring graph, not a pattern


@dataclass(frozen=True)
class FragmentScore:
    name: str
    smarts: str
    atom_indices: tuple[int, ...]
    score: float


def _environment_atoms(mol: Chem.Mol, center: int, radius: int) -> set[int]:
    """Atoms inside the radius-`radius` Morgan environment around `center` (just the centre at radius 0)."""
    if radius == 0:
        return {center}
    bond_ids = Chem.FindAtomEnvironmentOfRadiusN(mol, radius, center)
    atoms: set[int] = set()
    for b in bond_ids:
        bond = mol.GetBondWithIdx(b)
        atoms.add(bond.GetBeginAtomIdx())
        atoms.add(bond.GetEndAtomIdx())
    return atoms or {center}


def bit_environments(mol: Chem.Mol, config: MorganConfig | None = None) -> dict[int, list[set[int]]]:
    """For every ON bit of the molecule's Morgan fingerprint: the atom set of each environment that set it.

    Uses the same generator the models were trained with (`featurize.fingerprints._make_generator`),
    so the bit indices are the model's feature indices.
    """
    cfg = config or MorganConfig()
    gen = _make_generator(cfg)
    out = rdFingerprintGenerator.AdditionalOutput()
    out.AllocateBitInfoMap()
    gen.GetFingerprint(mol, additionalOutput=out)
    return {
        int(bit): [_environment_atoms(mol, int(center), int(radius)) for center, radius in envs]
        for bit, envs in out.GetBitInfoMap().items()
    }


def bits_to_atoms(
    mol: Chem.Mol, bit_scores: np.ndarray, config: MorganConfig | None = None
) -> tuple[np.ndarray, float]:
    """Place per-bit contributions on atoms.

    `bit_scores[b]` is the contribution of fingerprint bit `b`. Only ON bits of this molecule are
    placed; the contribution of a bit that is OFF (a split on its absence still moves a tree) is
    not a property of any atom and is returned as the second value, together with any ON bit that
    has no recorded environment. Returns (atom_scores, unplaced_total); their sum is `bit_scores.sum()`.
    """
    envs_by_bit = bit_environments(mol, config)
    atom_scores = np.zeros(mol.GetNumAtoms(), dtype=np.float64)
    placed = 0.0
    for bit, envs in envs_by_bit.items():
        score = float(bit_scores[bit])
        if not envs:
            continue
        share = score / len(envs)
        for atoms in envs:
            per_atom = share / len(atoms)
            for a in atoms:
                atom_scores[a] += per_atom
        placed += score
    return atom_scores, float(bit_scores.sum()) - placed


def ring_systems(mol: Chem.Mol) -> list[tuple[int, ...]]:
    """Fused/spiro ring systems: rings that share an atom are merged. Sorted atom indices."""
    systems: list[set[int]] = []
    for ring in mol.GetRingInfo().AtomRings():
        merged = set(ring)
        rest = []
        for s in systems:
            if s & merged:
                merged |= s
            else:
                rest.append(s)
        systems = [*rest, merged]
    return sorted(tuple(sorted(s)) for s in systems)


@lru_cache(maxsize=1)
def _catalogue() -> tuple[tuple[str, str, Chem.Mol], ...]:
    """RDKit's own functional-group patterns (`rdkit.Chem.Fragments`), with their descriptions as names."""
    path = Path(RDConfig.RDDataDir) / "FragmentDescriptors.csv"
    out = []
    with path.open(encoding="utf-8", newline="") as fh:
        rows = (r for r in fh if r.strip() and not r.startswith("#"))
        for row in csv.reader(rows, delimiter="\t"):
            if len(row) < 3:
                continue
            _code, desc, smarts = row[0], row[1], row[2]
            patt = Chem.MolFromSmarts(smarts)
            if patt is None:
                continue
            name = desc.removeprefix("Number of ").strip().replace("acide", "acid")  # RDKit typo in two descriptions
            out.append((name, smarts, patt))
    return tuple(out)


def _merge_overlapping(groups: list[set[int]]) -> list[set[int]]:
    """Merge atom sets that share an atom (a CF3 matches once per C-F bond; it is one group)."""
    merged: list[set[int]] = []
    for g in groups:
        g = set(g)
        rest = []
        for m in merged:
            if m & g:
                g |= m
            else:
                rest.append(m)
        merged = [*rest, g]
    return merged


def fragment_scores(mol: Chem.Mol, atom_scores: np.ndarray) -> list[FragmentScore]:
    """Sum atom attributions over each matched functional group and each ring system.

    Matches of one pattern that share an atom are one group (a CF3 is one alkyl-halide group, not
    three). Separate groups of the same kind stay separate. Groups of different kinds overlap (an
    amide carbonyl is also a carbonyl), so these scores are a view over atoms and do not add up; the
    atoms do. Sorted by absolute score, ties by name, so the output is deterministic.
    """
    found: list[FragmentScore] = []
    for name, smarts, patt in _catalogue():
        for atoms_set in _merge_overlapping([set(m) for m in mol.GetSubstructMatches(patt)]):
            atoms = tuple(sorted(atoms_set))
            found.append(FragmentScore(name, smarts, atoms, float(atom_scores[list(atoms)].sum())))
    for atoms in ring_systems(mol):
        found.append(FragmentScore("ring system", RING_SYSTEM_SMARTS, atoms, float(atom_scores[list(atoms)].sum())))
    return sorted(found, key=lambda f: (-abs(f.score), f.name, f.atom_indices))
