"""
Module 3 Stage 2 — molecular graph representation.

Blueprint requirements this implements:

  * Atom-level features + bond-level features suitable for a GNN backbone.
  * **Chirality tags included explicitly** — this is a Module 3 §Stereochemistry
    non-negotiable (same silent-default risk as ECFP: if you don't include
    chirality in the atom features, the GNN cannot see the R/S distinction and
    the CYP2C9 endpoint pays for it).
  * Undefined stereo is **not fabricated** — the chirality tag surfaces as
    ``CHI_UNSPECIFIED`` (an explicit category), never guessed.
  * Batched.
  * Deterministic.

Format
------

We emit a portable, backbone-agnostic representation:

    MoleculeGraph:
        n_atoms:       int
        n_bonds:       int  (directed edge count, undirected * 2)
        atom_features: (n_atoms, ATOM_FEATURE_DIM) float32
        edge_index:    (2, n_bonds) int64             — PyG-style ``(source, target)``
        edge_features: (n_bonds, BOND_FEATURE_DIM) float32

Undirected bonds are expanded to two directed edges with matching bond features
(the standard convention for message-passing GNNs; also matches KERMT / GROVER
featurizer schemas that we'll pin at M2 pre-flight).

**KERMT-specific featurizer stays deferred to M2 pre-flight** — the decision
2026-08-30 KERMT entry says the graph schema gets locked to KERMT's featurizer
when it's added to ``ml/requirements.txt``. This module produces a portable
representation that (a) is a superset of typical GNN needs and (b) can be
mapped into KERMT's schema with a thin adapter without redoing the atom-walk
logic. What must NOT change under any KERMT adaptation is the chirality-tag
inclusion at the atom level and the bond-stereo inclusion at the bond level —
those are blueprint constraints, not implementation choices.

Feature schemas
---------------

Both schemas are one-hot encoded categorical variables with a trailing "other"
bin plus a small suffix of continuous features. The exact ordering is fixed
here and version-tagged (``GRAPH_FEATURE_VERSION``) so it becomes part of any
downstream cache key.

Atom features (``ATOM_FEATURE_DIM = 42``):
  * atomic number → one-hot over ATOM_NUMBERS (10 bins + 1 "other")     -> 11
  * degree → one-hot over DEGREES (6 bins + 1 "other")                  -> 7
  * formal charge → one-hot over CHARGES (5 bins + 1 "other")           -> 6
  * chirality tag → one-hot over CHIRAL_TAGS (4 bins) — CHI_UNSPECIFIED
    is a real bin, not "other" (blueprint: no fabrication)              -> 4
  * hybridization → one-hot over HYBRIDIZATIONS (5 bins + 1 "other")    -> 6
  * total num Hs → one-hot over HYDROGENS (5 bins + 1 "other")          -> 6
  * is aromatic + is in ring                                            -> 2

Bond features (``BOND_FEATURE_DIM = 10``):
  * bond type → one-hot over {SINGLE, DOUBLE, TRIPLE, AROMATIC} (4 bins)
  * is conjugated (1)
  * is in ring (1)
  * bond stereo → one-hot over {STEREONONE, STEREOZ, STEREOE, STEREOANY} (4 bins)
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import numpy as np
from rdkit import Chem, RDLogger

_LOGGER = RDLogger.logger()
_LOGGER.setLevel(RDLogger.CRITICAL)


GRAPH_FEATURE_VERSION = "mars-graph-v1"


# --- categorical vocabularies -------------------------------------------------
# Fixed once — extending them is a version bump.

ATOM_NUMBERS: tuple[int, ...] = (5, 6, 7, 8, 9, 15, 16, 17, 35, 53)  # B, C, N, O, F, P, S, Cl, Br, I
DEGREES: tuple[int, ...] = (0, 1, 2, 3, 4, 5)
CHARGES: tuple[int, ...] = (-2, -1, 0, 1, 2)
CHIRAL_TAGS: tuple[Chem.ChiralType, ...] = (
    Chem.ChiralType.CHI_UNSPECIFIED,
    Chem.ChiralType.CHI_TETRAHEDRAL_CW,
    Chem.ChiralType.CHI_TETRAHEDRAL_CCW,
    Chem.ChiralType.CHI_OTHER,
)
HYBRIDIZATIONS: tuple[Chem.HybridizationType, ...] = (
    Chem.HybridizationType.SP,
    Chem.HybridizationType.SP2,
    Chem.HybridizationType.SP3,
    Chem.HybridizationType.SP3D,
    Chem.HybridizationType.SP3D2,
)
HYDROGENS: tuple[int, ...] = (0, 1, 2, 3, 4)

BOND_TYPES: tuple[Chem.BondType, ...] = (
    Chem.BondType.SINGLE,
    Chem.BondType.DOUBLE,
    Chem.BondType.TRIPLE,
    Chem.BondType.AROMATIC,
)
BOND_STEREOS: tuple[Chem.BondStereo, ...] = (
    Chem.BondStereo.STEREONONE,
    Chem.BondStereo.STEREOZ,
    Chem.BondStereo.STEREOE,
    Chem.BondStereo.STEREOANY,
)


# One-hot bin counts (+1 "other" bin except for chirality, where CHI_UNSPECIFIED
# already captures the "no defined stereo" state).
_N_ATOM_NUM = len(ATOM_NUMBERS) + 1
_N_DEGREE = len(DEGREES) + 1
_N_CHARGE = len(CHARGES) + 1
_N_CHIRAL = len(CHIRAL_TAGS)
_N_HYB = len(HYBRIDIZATIONS) + 1
_N_HYD = len(HYDROGENS) + 1

ATOM_FEATURE_DIM = _N_ATOM_NUM + _N_DEGREE + _N_CHARGE + _N_CHIRAL + _N_HYB + _N_HYD + 2  # +aromatic +in_ring

_N_BOND_TYPE = len(BOND_TYPES)
_N_BOND_STEREO = len(BOND_STEREOS)
BOND_FEATURE_DIM = _N_BOND_TYPE + 2 + _N_BOND_STEREO  # +conjugated +in_ring


@dataclass(frozen=True)
class GraphFeaturizerConfig:
    include_chirality: bool = True  # blueprint non-negotiable; only False for ablation
    version: str = GRAPH_FEATURE_VERSION
    atom_feature_dim: int = ATOM_FEATURE_DIM
    bond_feature_dim: int = BOND_FEATURE_DIM

    def cache_key(self) -> str:
        return (
            f"{self.version}|atom={self.atom_feature_dim}|bond={self.bond_feature_dim}"
            f"|chi={int(self.include_chirality)}"
        )


@dataclass(frozen=True)
class MoleculeGraph:
    n_atoms: int
    n_bonds: int
    atom_features: np.ndarray  # (n_atoms, ATOM_FEATURE_DIM) float32
    edge_index: np.ndarray  # (2, n_bonds) int64
    edge_features: np.ndarray  # (n_bonds, BOND_FEATURE_DIM) float32
    smiles: str

    def summary(self) -> dict[str, Any]:
        return {
            "smiles": self.smiles,
            "n_atoms": self.n_atoms,
            "n_bonds": self.n_bonds,
            "atom_features_shape": list(self.atom_features.shape),
            "edge_index_shape": list(self.edge_index.shape),
            "edge_features_shape": list(self.edge_features.shape),
        }


# --- primitive helpers --------------------------------------------------------


def _one_hot(value: Any, vocab: tuple[Any, ...], with_other: bool = True) -> list[float]:
    n = len(vocab) + (1 if with_other else 0)
    out = [0.0] * n
    for i, v in enumerate(vocab):
        if v == value:
            out[i] = 1.0
            return out
    if with_other:
        out[-1] = 1.0
    return out


def _atom_features(atom: Chem.Atom, *, include_chirality: bool) -> list[float]:
    tag = atom.GetChiralTag() if include_chirality else Chem.ChiralType.CHI_UNSPECIFIED
    feats = (
        _one_hot(atom.GetAtomicNum(), ATOM_NUMBERS)
        + _one_hot(atom.GetDegree(), DEGREES)
        + _one_hot(atom.GetFormalCharge(), CHARGES)
        + _one_hot(tag, CHIRAL_TAGS, with_other=False)
        + _one_hot(atom.GetHybridization(), HYBRIDIZATIONS)
        + _one_hot(atom.GetTotalNumHs(), HYDROGENS)
        + [float(atom.GetIsAromatic()), float(atom.IsInRing())]
    )
    assert len(feats) == ATOM_FEATURE_DIM, (len(feats), ATOM_FEATURE_DIM)
    return feats


def _bond_features(bond: Chem.Bond) -> list[float]:
    feats = (
        _one_hot(bond.GetBondType(), BOND_TYPES, with_other=False)
        + [float(bond.GetIsConjugated()), float(bond.IsInRing())]
        + _one_hot(bond.GetStereo(), BOND_STEREOS, with_other=False)
    )
    assert len(feats) == BOND_FEATURE_DIM, (len(feats), BOND_FEATURE_DIM)
    return feats


# --- public API ---------------------------------------------------------------


def molecule_graph(
    smiles: str,
    config: GraphFeaturizerConfig | None = None,
) -> MoleculeGraph | None:
    """Return a :class:`MoleculeGraph` or ``None`` if the SMILES cannot be parsed.

    Assumes ``smiles`` is already standardized (see ``featurize.standardize``);
    this function does not standardize again — the aim is deterministic, cheap
    conversion from a standardized SMILES to a graph.
    """
    cfg = config or GraphFeaturizerConfig()
    if not smiles:
        return None
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None

    # Assign stereochemistry so bond E/Z + atom chirality tags are populated
    Chem.AssignStereochemistry(mol, cleanIt=True, force=True)

    n_atoms = mol.GetNumAtoms()
    atom_features = np.zeros((n_atoms, ATOM_FEATURE_DIM), dtype=np.float32)
    for idx, atom in enumerate(mol.GetAtoms()):
        atom_features[idx] = _atom_features(atom, include_chirality=cfg.include_chirality)

    n_bonds_dir = 2 * mol.GetNumBonds()
    edge_index = np.zeros((2, n_bonds_dir), dtype=np.int64)
    edge_features = np.zeros((n_bonds_dir, BOND_FEATURE_DIM), dtype=np.float32)
    for i, bond in enumerate(mol.GetBonds()):
        a = bond.GetBeginAtomIdx()
        b = bond.GetEndAtomIdx()
        f = _bond_features(bond)
        edge_index[0, 2 * i] = a
        edge_index[1, 2 * i] = b
        edge_features[2 * i] = f
        edge_index[0, 2 * i + 1] = b
        edge_index[1, 2 * i + 1] = a
        edge_features[2 * i + 1] = f

    return MoleculeGraph(
        n_atoms=n_atoms,
        n_bonds=n_bonds_dir,
        atom_features=atom_features,
        edge_index=edge_index,
        edge_features=edge_features,
        smiles=smiles,
    )


def molecule_graphs_batch(
    smiles_list: Iterable[str],
    config: GraphFeaturizerConfig | None = None,
) -> tuple[list[MoleculeGraph], list[int]]:
    """Return (graphs, dropped_indices). Same drop-invalid-and-keep-indices
    convention as ``morgan_fingerprints_batch`` so downstream callers can align
    labels/metadata."""
    cfg = config or GraphFeaturizerConfig()
    graphs: list[MoleculeGraph] = []
    dropped: list[int] = []
    for idx, smi in enumerate(smiles_list):
        g = molecule_graph(smi, cfg)
        if g is None:
            dropped.append(idx)
        else:
            graphs.append(g)
    return graphs, dropped


def chirality_bit_slice() -> tuple[int, int]:
    """Return the (start, end) index slice of the chirality bins inside the atom
    feature vector. Used by tests to prove chirality survives into the graph
    features rather than being silently zeroed."""
    start = _N_ATOM_NUM + _N_DEGREE + _N_CHARGE
    return start, start + _N_CHIRAL
