"""The InChIKey of a molecule for the serving layer (frontend ADR-043).

`POST /name` looks a molecule's name up by its standard InChIKey and never sends the SMILES to the name source. The key is a
fixed 27-character hash of the structure: it identifies the structure to whoever receives it, which is why the interface says
that it is sent, but it is not the SMILES and it cannot be turned back into one without a database that already knows the
molecule.

The key is computed from the molecule exactly as written, not from a standardized or desalted form: what the user is looking
at is what is named. Stereochemistry is kept, so two stereoisomers get two keys and two names (or one name and one "none").

`inchikey` raises `ValueError` with a reason a person can read; it never returns a key it could not compute.
"""

from __future__ import annotations

import re

from rdkit import Chem
from rdkit.Chem import inchi

INCHIKEY_SOURCE = "rdkit-inchi"
MAX_SMILES_LENGTH = 1000
_KEY = re.compile(r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$")


def inchikey(smiles: str) -> str:
    """The standard InChIKey of `smiles`, or `ValueError` if it cannot be parsed or has none."""
    text = (smiles or "").strip()
    if not text:
        raise ValueError("smiles must be a non-empty string")
    if len(text) > MAX_SMILES_LENGTH:
        raise ValueError(f"smiles is longer than {MAX_SMILES_LENGTH} characters")
    mol = Chem.MolFromSmiles(text)
    if mol is None or mol.GetNumAtoms() == 0:
        raise ValueError("could not parse the SMILES")
    key = inchi.MolToInchiKey(mol)
    if not key or not _KEY.match(key):
        raise ValueError("no InChIKey can be computed for this structure")
    return key
