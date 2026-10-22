"""Computed molecule properties and structural alerts (ml/serve/properties.py, ml/serve/alerts.py).

The reference values are properties of the RDKit definitions and the published methods, asserted as loose bands
so they do not pin a RDKit release. The point is the contract: deterministic numbers, a rule-of-five count that
follows its four published limits, alerts reported as distinct (catalog, name) pairs, and None, never a made-up
value, for a molecule that cannot be parsed.
"""

from __future__ import annotations

import math

import pytest
from rdkit import Chem
from serve.alerts import ALERT_CATALOGS, alert_matches, distinct_alerts
from serve.properties import PROPERTIES_SOURCE, compute_properties

CELECOXIB = "Cc1ccc(-c2cc(C(F)(F)F)nn2-c2ccc(S(N)(=O)=O)cc2)cc1"
ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"
PACLITAXEL = (
    "CC1=C2C(C(=O)C3(C(CC4C(C3C(C(C2(C)C)(CC1OC(=O)C(C(C5=CC=CC=C5)NC(=O)C6=CC=CC=C6)O)O)"
    "OC(=O)C7=CC=CC=C7)(CO4)OC(=O)C)O)C)OC(=O)C"
)
RHODANINE = "S=C1SC(=Cc2ccccc2)C(=O)N1"  # a classic PAINS "ene_rhod"
NITROBENZENE = "c1ccccc1[N+](=O)[O-]"  # a Brenk "nitro group"


def test_source_label():
    assert PROPERTIES_SOURCE == "rdkit"


def test_celecoxib_values_sit_in_the_expected_bands():
    p = compute_properties(CELECOXIB)
    assert p is not None
    assert p.mol_weight == pytest.approx(381.4, abs=0.2)
    assert p.h_bond_donors == 1  # the sulfonamide NH2 counts once in RDKit's definition
    assert p.h_bond_acceptors == 3
    assert 70 < p.tpsa < 85
    assert 3.0 < p.crippen_logp < 4.2
    assert p.rotatable_bonds == 3
    assert p.qed is not None and 0.6 < p.qed < 0.9
    assert p.lipinski_criteria_exceeded == 0


def test_rule_of_five_count_follows_the_four_published_limits():
    big = compute_properties(PACLITAXEL)
    assert big is not None
    # paclitaxel: weight above 500 and more than 10 acceptors at least
    assert big.mol_weight > 500 and big.h_bond_acceptors > 10
    assert 2 <= big.lipinski_criteria_exceeded <= 4
    small = compute_properties(ASPIRIN)
    assert small is not None and small.lipinski_criteria_exceeded == 0


def test_every_value_is_finite_and_in_its_documented_range():
    for smi in (CELECOXIB, ASPIRIN, PACLITAXEL, "CCO", "C"):
        p = compute_properties(smi)
        assert p is not None
        for v in (p.mol_weight, p.crippen_logp, p.tpsa):
            assert math.isfinite(v)
        assert p.tpsa >= 0 and p.mol_weight > 0
        assert 0 <= p.lipinski_criteria_exceeded <= 4
        assert p.qed is None or 0.0 <= p.qed <= 1.0


def test_unparseable_input_is_none_not_a_made_up_value():
    assert compute_properties("") is None
    assert compute_properties("not-a-smiles") is None


def test_alerts_are_distinct_catalog_and_name_pairs():
    pains = compute_properties(RHODANINE)
    assert pains is not None
    assert any(c == "PAINS" for c, _ in pains.alerts)
    brenk = compute_properties(NITROBENZENE)
    assert brenk is not None
    assert any(c == "Brenk" for c, _ in brenk.alerts)
    for p in (pains, brenk):
        assert len(set(p.alerts)) == len(p.alerts)  # each alert once
        assert all(c in ALERT_CATALOGS and name for c, name in p.alerts)
    assert compute_properties(ASPIRIN).alerts == tuple(distinct_alerts(Chem.MolFromSmiles(ASPIRIN)))


def test_alert_matches_keeps_the_shape_the_explainability_validation_reads():
    mol = Chem.MolFromSmiles(RHODANINE)
    matches = alert_matches(mol)
    assert matches
    for catalog, description, atoms in matches:
        assert catalog in ALERT_CATALOGS
        assert isinstance(description, str) and description
        assert atoms and all(0 <= a < mol.GetNumAtoms() for a in atoms)


def test_results_are_deterministic():
    assert compute_properties(CELECOXIB) == compute_properties(CELECOXIB)
