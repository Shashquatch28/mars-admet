"""Synthetic-accessibility rule (ml/serve/rule_based.py).

The reference anchors are properties of the Ertl & Schuffenhauer method, not of
MARS: small, simple molecules score near 1; large polycyclic natural products
with stereocentres and macrocycles score far higher. The values asserted here
are loose bands around the published behaviour, so they do not pin RDKit's
fragment table to a version.
"""

from __future__ import annotations

import math

import pytest
from serve.rule_based import SA_MODEL_ID, SA_UNIT, compute_sa_score

ETHANOL = "CCO"
ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"
# Taxol-class scaffold: many stereocentres, bridged polycycle — hard to make.
PACLITAXEL = (
    "CC1=C2C(C(=O)C3(C(CC4C(C3C(C(C2(C)C)(CC1OC(=O)C(C(C5=CC=CC=C5)NC(=O)C6=CC=CC=C6)O)O)"
    "OC(=O)C7=CC=CC=C7)(CO4)OC(=O)C)O)C)OC(=O)C"
)


def test_constants():
    assert SA_MODEL_ID == "rdkit-sascore"
    assert SA_UNIT == "SA score"


def test_simple_molecules_score_low():
    assert 1.0 <= compute_sa_score(ETHANOL) <= 2.5
    assert 1.0 <= compute_sa_score(ASPIRIN) <= 2.5  # published SA for aspirin is ~1.6


def test_complex_natural_product_scores_higher_than_simple():
    assert compute_sa_score(PACLITAXEL) > compute_sa_score(ASPIRIN) + 2.0


def test_score_is_in_documented_range_and_finite():
    for smi in (ETHANOL, ASPIRIN, PACLITAXEL):
        s = compute_sa_score(smi)
        assert math.isfinite(s)
        assert 1.0 <= s <= 10.0


def test_deterministic():
    assert compute_sa_score(ASPIRIN) == compute_sa_score(ASPIRIN)


@pytest.mark.parametrize("bad", ["", "not-a-smiles", "C(C"])
def test_unparseable_smiles_returns_none_not_a_value(bad):
    assert compute_sa_score(bad) is None
