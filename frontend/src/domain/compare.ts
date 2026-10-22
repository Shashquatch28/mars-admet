// Compare: two or three molecules side by side. Descriptive only (ADR-007).
//
// There is no winner, no rank, no ordering by favourability and no difference column:
// MARS has no validated direction-of-good, so "which molecule is better" is not
// expressible here, and `CompareResponse.per_endpoint_winner` is never read. Rows follow
// the fixed roster order. Every molecule runs through the SAME reconcile() as Predict, so
// every molecule has one cell per endpoint and an endpoint the service did not return is a
// marked cell, never a gap (ADR-008).
import type { CompareResponse, Endpoint } from "../types/contracts";
import { ML_ENDPOINTS, type DisplayGroup, type EndpointMeta } from "./endpoints";
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

export interface Comparison {
  columns: CompareColumn[];
  groups: CompareGroup[];
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
  return { columns, groups, modelVersions: [...versions].sort() };
}

/** Why a comparison request failed, in the same words Predict uses. */
export function compareFailure(status: number, message: string): { title: string; detail: string } {
  const title = status === 422 ? "Molecule rejected" : status === 429 ? "Rate limited" : "Request failed";
  return { title, detail: status > 0 ? `${status} · ${message}` : message };
}
