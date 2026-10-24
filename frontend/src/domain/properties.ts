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

/** The fixed rows of the property table: label, unit and how one molecule's value is written. One list serves Predict, the report and Compare. */
const PROPERTY_SPEC: readonly { key: string; label: string; unit: string; format: (p: MoleculeProperties) => string }[] = [
  { key: "mol_weight", label: "Molecular weight", unit: "g/mol", format: (p) => fmtNum(p.mol_weight, 2) },
  { key: "crippen_logp", label: "logP (Wildman-Crippen)", unit: "", format: (p) => fmtNum(p.crippen_logp, 2) },
  { key: "h_bond_donors", label: "H-bond donors", unit: "", format: (p) => String(p.h_bond_donors) },
  { key: "h_bond_acceptors", label: "H-bond acceptors", unit: "", format: (p) => String(p.h_bond_acceptors) },
  { key: "tpsa", label: "Topological polar surface area", unit: "Å²", format: (p) => fmtNum(p.tpsa, 1) },
  { key: "rotatable_bonds", label: "Rotatable bonds", unit: "", format: (p) => String(p.rotatable_bonds) },
  { key: "qed", label: "QED", unit: "", format: (p) => (p.qed == null ? "not computed" : fmtNum(p.qed, 2)) },
  { key: "lipinski", label: "Rule-of-five limits exceeded", unit: "", format: (p) => `${p.lipinski_criteria_exceeded} of 4` },
];

/** The property table, in a fixed order. A QED RDKit could not compute reads "not computed", never a number. */
export function propertyLines(p: MoleculeProperties): PropertyLine[] {
  return PROPERTY_SPEC.map((s) => ({ key: s.key, label: s.label, value: s.format(p), unit: s.unit }));
}

/** One row of a side-by-side property table: a label, a unit and one written value per molecule (null where the service sent no properties). */
export interface PropertyRowAcross {
  key: string;
  label: string;
  unit: string;
  cells: (string | null)[];
}

/** The property table across several molecules, same rows and same number format as `propertyLines`, in the same order. */
export function propertyRowsAcross(all: readonly (MoleculeProperties | null | undefined)[]): PropertyRowAcross[] {
  return PROPERTY_SPEC.map((s) => ({
    key: s.key,
    label: s.label,
    unit: s.unit,
    cells: all.map((p) => (p ? s.format(p) : null)),
  }));
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

export interface AlertRowAcross {
  catalog: StructuralAlert["catalog"];
  /** One list of matched names per molecule: [] is "no match", null is "the service sent no properties". */
  cells: (string[] | null)[];
}

/** The alerts across several molecules, PAINS then Brenk, names sorted within a cell. */
export function alertRowsAcross(all: readonly (MoleculeProperties | null | undefined)[]): AlertRowAcross[] {
  const groups = all.map((p) => (p ? alertGroups(p) : null));
  return (["PAINS", "Brenk"] as const).map((catalog) => ({
    catalog,
    cells: groups.map((g) => (g ? (g.find((x) => x.catalog === catalog)?.names ?? []) : null)),
  }));
}

/** Fixed text printed with the properties, on screen and in the report. Each line is something the table must not leave to the reader to assume. */
export const PROPERTY_NOTES: readonly string[] = [
  "Computed from the structure with RDKit. These are not MARS predictions: they have no model, no ensemble and no applicability domain, and they do not depend on which model answered an endpoint.",
  "MARS draws no conclusion from any of them. QED is a published desirability function of eight properties (Bickerton et al. 2012), not a MARS prediction. The rule-of-five count follows Lipinski et al. 1997 (more than 5 donors, more than 10 acceptors, weight above 500, logP above 5), using RDKit's Wildman-Crippen logP rather than CLogP.",
  "A structural alert is a substructure match, not a prediction. PAINS (Baell and Holloway 2010) concerns interference in screening assays, not toxicity, and a 2017 analysis found most compounds it flags show no interference (Capuzzi et al.). Brenk (Brenk et al. 2008) is a list of substructures compiled for screening-library design.",
];
