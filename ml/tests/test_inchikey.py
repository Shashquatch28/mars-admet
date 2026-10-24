"""InChIKey for the name lookup (ml/serve/inchikey.py, frontend ADR-043).

The key is the only thing about a molecule that leaves the server for a name source, so what matters is that it is the standard
key for the molecule as written, that it keeps stereochemistry, and that something that is not a molecule is an error and never a
key.
"""

from __future__ import annotations

import re

import pytest
from serve.inchikey import INCHIKEY_SOURCE, MAX_SMILES_LENGTH, inchikey

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"
ASPIRIN_OTHER = "OC(=O)c1ccccc1OC(C)=O"
ALANINE_L = "C[C@H](N)C(=O)O"
ALANINE_D = "C[C@@H](N)C(=O)O"
SALT = "[Na+].[Cl-]"


def test_a_known_molecule_has_its_published_key():
    # aspirin, as listed by PubChem (CID 2244) and ChEMBL; L-alanine likewise (CID 5950)
    assert inchikey(ASPIRIN) == "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"
    assert inchikey(ALANINE_L) == "QNAYBMKLOCPYGJ-REOHCLBHSA-N"


def test_the_key_has_the_standard_shape():
    assert re.fullmatch(r"[A-Z]{14}-[A-Z]{10}-[A-Z]", inchikey(SALT))


def test_every_way_of_writing_a_molecule_gives_one_key():
    assert inchikey(ASPIRIN) == inchikey(ASPIRIN_OTHER)


def test_stereoisomers_get_different_keys_so_they_are_named_apart():
    assert inchikey(ALANINE_L) != inchikey(ALANINE_D)


def test_a_salt_is_keyed_as_written_not_desalted():
    assert inchikey(SALT) != inchikey("[Na+]")


def test_the_key_does_not_contain_the_smiles():
    assert ASPIRIN not in inchikey(ASPIRIN)


@pytest.mark.parametrize("bad", ["", "   ", "not a smiles ((", "C1CC", "[Xx]"])
def test_something_that_is_not_a_molecule_is_an_error_not_a_key(bad):
    with pytest.raises(ValueError):
        inchikey(bad)


def test_an_overlong_smiles_is_refused_before_it_is_parsed():
    with pytest.raises(ValueError, match="longer than"):
        inchikey("C" * (MAX_SMILES_LENGTH + 1))


def test_the_source_is_named():
    assert INCHIKEY_SOURCE == "rdkit-inchi"
