"""Computed molecule properties and structural alerts for the serving layer (frontend ADR-034 item 3).

Deterministic RDKit calculations on an already-standardized SMILES. They are not model predictions: no
training set, no ensemble, no applicability domain, nothing that depends on which model served a row, so a
KERMT outage changes nothing here. They are reported as plain numbers and a count; whether a value is good or
bad for a molecule is not a thing MARS knows, and nothing here says so.

* Molecular weight, Crippen logP, H-bond donors and acceptors, TPSA, rotatable bonds: RDKit definitions. The
  logP is Wildman-Crippen, not the CLogP Lipinski used, so the rule-of-five count below is "criteria exceeded
  with RDKit's numbers".
* `lipinski_criteria_exceeded`: how many of the four rule-of-five limits are passed (Lipinski et al. 1997, Adv.
  Drug Deliv. Rev. 23:3): more than 5 donors, more than 10 acceptors, weight above 500, logP above 5. Zero to four.
* QED: the quantitative estimate of drug-likeness, a published desirability function of eight properties
  (Bickerton et al. 2012, Nat. Chem. 4:90), RDKit's `QED.qed`. It is not a MARS prediction. None if RDKit
  cannot compute it for the molecule.
* Alerts: PAINS and Brenk substructure matches (`serve.alerts`).

`compute_properties` returns None for a molecule RDKit cannot parse, never a made-up value.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from rdkit import Chem
from rdkit.Chem import QED, Crippen, Descriptors, Lipinski, rdMolDescriptors

from serve.alerts import distinct_alerts

PROPERTIES_SOURCE = "rdkit"


@dataclass(frozen=True)
class MolProperties:
    mol_weight: float
    crippen_logp: float
    h_bond_donors: int
    h_bond_acceptors: int
    tpsa: float
    rotatable_bonds: int
    qed: float | None
    lipinski_criteria_exceeded: int
    alerts: tuple[tuple[str, str], ...]  # (catalog, alert name)


def _qed(mol: Chem.Mol) -> float | None:
    try:
        value = QED.qed(mol)
    except Exception:
        return None
    return float(value) if math.isfinite(value) else None


def compute_properties(smiles_standardized: str) -> MolProperties | None:
    """Properties of an already-standardized SMILES, or None if it cannot be parsed."""
    mol = Chem.MolFromSmiles(smiles_standardized)
    if mol is None or mol.GetNumAtoms() == 0:  # "" parses to a valid zero-atom mol
        return None
    weight = float(Descriptors.MolWt(mol))
    logp = float(Crippen.MolLogP(mol))
    donors = int(Lipinski.NumHDonors(mol))
    acceptors = int(Lipinski.NumHAcceptors(mol))
    exceeded = int(donors > 5) + int(acceptors > 10) + int(weight > 500) + int(logp > 5)
    return MolProperties(
        mol_weight=weight,
        crippen_logp=logp,
        h_bond_donors=donors,
        h_bond_acceptors=acceptors,
        tpsa=float(rdMolDescriptors.CalcTPSA(mol)),
        rotatable_bonds=int(Lipinski.NumRotatableBonds(mol)),
        qed=_qed(mol),
        lipinski_criteria_exceeded=exceeded,
        alerts=tuple(distinct_alerts(mol)),
    )
