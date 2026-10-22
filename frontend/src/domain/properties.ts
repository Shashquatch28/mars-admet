// Computed molecule properties and structural alerts as the screen and the printed report show them
// (ADR-034 item 3). Pure and tested. Everything here is a plain number or a name: nothing is coloured, scored,
// ranked or called good, safe or acceptable, and the lines carry no state. These are RDKit calculations on the
// structure, not MARS predictions; they are outside the 14-endpoint roster and its reconciliation.
import type { MoleculeProperties, StructuralAlert } from "../types/contracts";
import { fmtNum } from "./format";

export const PROPERTY_SOURCE = "RDKit";

export interface PropertyLine {
  key: string;
  label: string;
  value: string;
  unit: string;
}

/** The property table, in a fixed order. A QED RDKit could not compute reads "not computed", never a number. */
export function propertyLines(p: MoleculeProperties): PropertyLine[] {
  return [
    { key: "mol_weight", label: "Molecular weight", value: fmtNum(p.mol_weight, 2), unit: "g/mol" },
    { key: "crippen_logp", label: "logP (Wildman-Crippen)", value: fmtNum(p.crippen_logp, 2), unit: "" },
    { key: "h_bond_donors", label: "H-bond donors", value: String(p.h_bond_donors), unit: "" },
    { key: "h_bond_acceptors", label: "H-bond acceptors", value: String(p.h_bond_acceptors), unit: "" },
    { key: "tpsa", label: "Topological polar surface area", value: fmtNum(p.tpsa, 1), unit: "Å²" },
    { key: "rotatable_bonds", label: "Rotatable bonds", value: String(p.rotatable_bonds), unit: "" },
    { key: "qed", label: "QED", value: p.qed == null ? "not computed" : fmtNum(p.qed, 2), unit: "" },
    {
      key: "lipinski",
      label: "Rule-of-five limits exceeded",
      value: `${p.lipinski_criteria_exceeded} of 4`,
      unit: "",
    },
  ];
}

export interface AlertGroup {
  catalog: StructuralAlert["catalog"];
  names: string[];
}

/** The alerts grouped by catalog, PAINS first then Brenk, names sorted. A catalog with no match is still listed (empty). */
export function alertGroups(p: MoleculeProperties): AlertGroup[] {
  return (["PAINS", "Brenk"] as const).map((catalog) => ({
    catalog,
    names: p.alerts
      .filter((a) => a.catalog === catalog)
      .map((a) => a.name)
      .sort(),
  }));
}

/** Fixed text printed with the properties, on screen and in the report. Each line is something the table must not leave to the reader to assume. */
export const PROPERTY_NOTES: readonly string[] = [
  "Computed from the structure with RDKit. These are not MARS predictions: they have no model, no ensemble and no applicability domain, and they do not depend on which model answered an endpoint.",
  "MARS draws no conclusion from any of them. QED is a published desirability function of eight properties (Bickerton et al. 2012), not a MARS prediction. The rule-of-five count follows Lipinski et al. 1997 (more than 5 donors, more than 10 acceptors, weight above 500, logP above 5), using RDKit's Wildman-Crippen logP rather than CLogP.",
  "A structural alert is a substructure match, not a prediction. PAINS (Baell and Holloway 2010) concerns interference in screening assays, not toxicity, and a 2017 analysis found most compounds it flags show no interference (Capuzzi et al.). Brenk (Brenk et al. 2008) is a list of substructures compiled for screening-library design.",
];
