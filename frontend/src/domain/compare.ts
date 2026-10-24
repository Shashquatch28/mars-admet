// Compare: two or three molecules side by side. Descriptive only (ADR-007).
//
// There is no winner, no rank, no ordering by favourability and no difference column:
// MARS has no validated direction-of-good, so "which molecule is better" is not
// expressible here, and `CompareResponse.per_endpoint_winner` is never read. Rows follow
// the fixed roster order. The computed properties (RDKit, not predictions) follow the roster as plain values, one
// column per molecule: "diff" in the blueprint is the reader's comparison of those columns, never a computed
// difference, because a difference invites ranking (ADR-036). Every molecule runs through the SAME reconcile() as Predict, so
// every molecule has one cell per endpoint and an endpoint the service did not return is a
// marked cell, never a gap (ADR-008).
import type { CompareResponse, Endpoint } from "../types/contracts";
import { ML_ENDPOINTS, type DisplayGroup, type EndpointMeta } from "./endpoints";
import {
  PROPERTY_NOTES,
  PROPERTY_SOURCE,
  alertRowsAcross,
  propertyRowsAcross,
  type AlertRowAcross,
  type PropertyRowAcross,
} from "./properties";
import { reconcile, type Row } from "./reconcile";

export const COMPARE_MIN = 2;
export const COMPARE_MAX = 3;

/** The filled slots, trimmed and in order. A blank third slot is simply not part of the request. */
export function filledInputs(slots: string[]): string[] {
  return slots.map((s) => s.trim()).filter(Boolean);
}

/** Why a comparison cannot be run yet, in words; null when it can. */
export function compareProblem(slots: string[]): string | null {
  const filled = filledInputs(slots);
  if (filled.length < COMPARE_MIN) return `Enter at least ${COMPARE_MIN} molecules to compare.`;
  if (filled.length > COMPARE_MAX) return `Compare takes at most ${COMPARE_MAX} molecules.`;
  return null;
}

/** Slots that hold the same string as an earlier slot (a comparison of a molecule with itself). */
export function repeatedSlots(slots: string[]): number[] {
  const seen = new Set<string>();
  const out: number[] = [];
  slots.forEach((s, i) => {
    const t = s.trim();
    if (!t) return;
    if (seen.has(t)) out.push(i);
    seen.add(t);
  });
  return out;
}

export interface SlotAddition {
  slots: string[];
  /** The slot (0-based) the molecule is now in. */
  slot: number;
  /** `already`: it was in a slot, nothing changed. `replaced`: every slot was full, so the last one was overwritten. */
  kind: "added" | "already" | "replaced";
}

/**
 * Put a molecule handed over from another workspace into Compare: the molecule's own slot if it is already there, else the first
 * empty slot, else a third slot if only two exist, else it replaces the last slot (Compare holds at most COMPARE_MAX, and a
 * hand-off must never silently change the first molecules the user chose; the caller says what was replaced).
 */
export function addToSlots(slots: string[], smiles: string): SlotAddition {
  const s = smiles.trim();
  const existing = slots.findIndex((x) => x.trim() === s);
  if (existing >= 0) return { slots, slot: existing, kind: "already" };
  const empty = slots.findIndex((x) => x.trim() === "");
  if (empty >= 0) return { slots: slots.map((x, i) => (i === empty ? s : x)), slot: empty, kind: "added" };
  if (slots.length < COMPARE_MAX) return { slots: [...slots, s], slot: slots.length, kind: "added" };
  const last = slots.length - 1;
  return { slots: slots.map((x, i) => (i === last ? s : x)), slot: last, kind: "replaced" };
}

/** What a hand-off did, in words, for the status line of Compare. */
export function handoffNote(a: Pick<SlotAddition, "slot" | "kind">, source: string): string {
  const n = a.slot + 1;
  // A saved molecule is a frozen copy; Compare sends only the SMILES, so what it shows is a new prediction.
  const again = source === "Library" ? " It is predicted again with the current model; the saved values are not reused." : "";
  if (a.kind === "already") return `The molecule you sent from ${source} is already in Compare as Molecule ${n}; nothing was added.`;
  if (a.kind === "replaced")
    return `Compare holds ${COMPARE_MAX} molecules and all were filled, so Molecule ${n} was replaced by the molecule you sent from ${source}. Nothing has been run.${again}`;
  return `Molecule ${n} came from ${source}. Nothing has been run: press Run comparison.${again}`;
}

export interface CompareColumn {
  index: number;
  smilesInput: string;
  smilesStandardized: string;
  moleculeId: string;
  modelVersion: string;
  /** Counted over ML cells only; the rule-based SA score is shown but never counted. */
  flags: { outOfDomain: number; stubServed: number; notReturned: number };
}

export interface CompareRow {
  endpoint: Endpoint;
  meta: EndpointMeta;
  /** One cell per molecule, in column order. The same Row type Predict uses. */
  cells: Row[];
}

export interface CompareGroup {
  group: DisplayGroup;
  label: string;
  rows: CompareRow[];
}

/**
 * The computed properties of every molecule, side by side (ADR-036). Plain values in Predict's grammar: one column per
 * molecule, the same rows in the same order as Predict, no difference column, no highlight of a lower or higher value.
 * A molecule the service sent no properties for has a null cell in every row, never an empty one.
 */
export interface CompareProperties {
  source: string;
  lines: PropertyRowAcross[];
  alerts: AlertRowAcross[];
  notes: readonly string[];
}

export interface Comparison {
  columns: CompareColumn[];
  groups: CompareGroup[];
  properties: CompareProperties;
  /** Distinct model versions across the molecules; more than one is worth saying out loud. */
  modelVersions: string[];
}

export function buildComparison(response: CompareResponse, requested: Endpoint[] = ML_ENDPOINTS): Comparison {
  const recons = response.molecules.map((m) => reconcile(m, requested));

  const columns: CompareColumn[] = response.molecules.map((m, index) => {
    const ml = recons[index].rows.filter((r) => r.meta.taskType !== "rule_based");
    return {
      index,
      smilesInput: m.smiles_input,
      smilesStandardized: m.smiles_standardized,
      moleculeId: m.molecule_id,
      modelVersion: m.model_version,
      flags: {
        outOfDomain: ml.filter((r) => r.state.kind === "out_of_domain").length,
        stubServed: ml.filter((r) => r.state.kind === "stub_served").length,
        notReturned: ml.filter((r) => r.state.kind === "not_returned").length,
      },
    };
  });

  // Group structure and row order come from the roster, which is the same for every molecule.
  const byEndpoint = recons.map((rc) => new Map<Endpoint, Row>(rc.rows.map((r) => [r.endpoint, r])));
  const groups: CompareGroup[] = (recons[0]?.groups ?? []).map((g) => ({
    group: g.group,
    label: g.label,
    rows: g.rows.map((row) => ({
      endpoint: row.endpoint,
      meta: row.meta,
      cells: byEndpoint.map((m) => m.get(row.endpoint) as Row),
    })),
  }));

  const versions = new Set(response.molecules.map((m) => m.model_version).filter(Boolean));
  const props = response.molecules.map((m) => m.properties);
  const properties: CompareProperties = {
    source: PROPERTY_SOURCE,
    lines: propertyRowsAcross(props),
    alerts: alertRowsAcross(props),
    notes: PROPERTY_NOTES,
  };
  return { columns, groups, properties, modelVersions: [...versions].sort() };
}

/** Why a comparison request failed, in the same words Predict uses. */
export function compareFailure(status: number, message: string): { title: string; detail: string } {
  const title = status === 422 ? "Molecule rejected" : status === 429 ? "Rate limited" : "Request failed";
  return { title, detail: status > 0 ? `${status} · ${message}` : message };
}
