"""
Murcko scaffold computation for standardization-consistent identity.

Blueprint Module 1 §4 requires **Murcko scaffolds**, computed on **standardized**
molecules. This tiny module exists so every caller that needs a scaffold
(splitting, leakage checks, augmentation overlap detection, EDA scaffold-
diversity summary) uses the same code path — never re-implements it.

An empty-scaffold (acyclic) molecule maps to the fixed sentinel ``""`` so
groupby-by-scaffold behaves predictably; downstream splitters treat it as one
bucket by convention (matching the TDC benchmark-group behavior).
"""

from __future__ import annotations

from rdkit import Chem
from rdkit.Chem.Scaffolds import MurckoScaffold

_EMPTY_SCAFFOLD = ""


def murcko_scaffold_from_smiles(smiles: str) -> str:
    """Return the canonical Murcko scaffold SMILES for a standardized molecule.

    ``smiles`` MUST be the output of ``featurize.standardize.standardize`` (i.e.
    already canonical + isomeric). Acyclic inputs return ``""``.
    """
    if not smiles:
        return _EMPTY_SCAFFOLD
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return _EMPTY_SCAFFOLD
    scaffold = MurckoScaffold.GetScaffoldForMol(mol)
    if scaffold is None or scaffold.GetNumAtoms() == 0:
        return _EMPTY_SCAFFOLD
    return Chem.MolToSmiles(scaffold, isomericSmiles=False, canonical=True)


def murcko_scaffolds_batch(smiles_list: list[str]) -> list[str]:
    return [murcko_scaffold_from_smiles(s) for s in smiles_list]
