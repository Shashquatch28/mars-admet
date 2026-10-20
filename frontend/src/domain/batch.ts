// Batch triage domain layer. Three jobs, all pure and unit-testable:
//
//  1. Turn a BatchPredictResponse into a matrix of molecules × the full endpoint
//     roster. Every row runs through the SAME reconcile() the Predict workspace
//     uses, so ADR-008 holds here too: a molecule always has one cell per
//     endpoint, and an endpoint the service did not return is a marked cell,
//     never a gap in the row.
//  2. Sort. Only two kinds exist: input order, and a RAW numeric sort on one
//     endpoint. There is no favourability sort and no ranking (AGENTS.md #3) —
//     MARS has no direction-of-good, so "best first" is not expressible.
//  3. Filter, by text or by reliability state. Filtering hides rows the user
//     asked to hide; it never hides a cell inside a visible row.
import type {
  BatchPredictResponse,
  Endpoint,
  PredictionResponse,
} from "../types/contracts";
import { ML_ENDPOINTS } from "./endpoints";
import { reconcile, type Row } from "./reconcile";

// A cell is exactly a Predict row: same endpoint, same derived state, same
// reliability channel. Reusing the type is deliberate — it is what keeps the two
// workspaces one product rather than two dashboards.
export type BatchCell = Row;

export interface BatchRow {
  rowIndex: number;
  smilesInput: string;
  ok: boolean;
  error: string | null;
  moleculeId: string | null;
  response: PredictionResponse | null;
  cells: BatchCell[];
  flags: { outOfDomain: number; stubServed: number; notReturned: number };
}

export interface BatchSummary {
  rows: BatchRow[];
  status: BatchPredictResponse["status"];
  total: number;
  completed: number;
  counts: {
    molecules: number;
    failedRows: number;
    rowsWithOod: number;
    rowsWithStub: number;
    cellsNotReturned: number;
  };
}

/** An empty response for a molecule that failed before inference ran. */
function failedResponse(smiles: string): PredictionResponse {
  return {
    smiles_input: smiles,
    smiles_standardized: "",
    molecule_id: "",
    predictions: [],
    model_version: "",
    served_at: "",
    cache_hit: false,
  };
}

export function buildBatch(
  response: BatchPredictResponse,
  requested: Endpoint[] = ML_ENDPOINTS,
): BatchSummary {
  const results = response.results ?? [];

  const rows: BatchRow[] = results.map((r) => {
    const pred = r.ok && r.prediction ? r.prediction : failedResponse(r.smiles_input);
    const cells = reconcile(pred, requested).rows;

    // Flags count ML cells only — the rule-based SA score is shown but never
    // counted, because it is computed rather than predicted (Q1/Q2).
    const ml = cells.filter((c) => c.meta.taskType !== "rule_based");
    return {
      rowIndex: r.row_index,
      smilesInput: r.smiles_input,
      ok: r.ok,
      error: r.error ?? null,
      moleculeId: r.ok && r.prediction ? r.prediction.molecule_id : null,
      response: r.ok && r.prediction ? r.prediction : null,
      cells,
      flags: {
        outOfDomain: ml.filter((c) => c.state.kind === "out_of_domain").length,
        stubServed: ml.filter((c) => c.state.kind === "stub_served").length,
        notReturned: ml.filter((c) => c.state.kind === "not_returned").length,
      },
    };
  });

  const ok = rows.filter((r) => r.ok);
  return {
    rows,
    status: response.status,
    total: response.total,
    completed: response.completed,
    counts: {
      molecules: rows.length,
      failedRows: rows.filter((r) => !r.ok).length,
      rowsWithOod: ok.filter((r) => r.flags.outOfDomain > 0).length,
      rowsWithStub: ok.filter((r) => r.flags.stubServed > 0).length,
      cellsNotReturned: ok.reduce((n, r) => n + r.flags.notReturned, 0),
    },
  };
}

// --- sorting -----------------------------------------------------------------

export type SortSpec =
  | { kind: "input" }
  | { kind: "raw"; endpoint: Endpoint; dir: "asc" | "desc" };

function valueFor(row: BatchRow, endpoint: Endpoint): number | null {
  const cell = row.cells.find((c) => c.endpoint === endpoint);
  if (!cell?.prediction) return null;
  return cell.prediction.value;
}

/**
 * A raw numeric sort on one endpoint's value. Explicitly NOT a ranking: the
 * direction is the user's, the UI labels it "raw", and nothing is marked best.
 *
 * Rows with no value for that endpoint (not returned, or a failed row) always
 * sort last in both directions. Ordering a missing value as though it were a
 * number — low in asc, high in desc — would invent data.
 */
export function sortRows(rows: BatchRow[], spec: SortSpec): BatchRow[] {
  if (spec.kind === "input") return [...rows].sort((a, b) => a.rowIndex - b.rowIndex);
  const sign = spec.dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const va = valueFor(a, spec.endpoint);
    const vb = valueFor(b, spec.endpoint);
    if (va == null && vb == null) return a.rowIndex - b.rowIndex;
    if (va == null) return 1;
    if (vb == null) return -1;
    if (va === vb) return a.rowIndex - b.rowIndex;
    return (va - vb) * sign;
  });
}

// --- filtering ---------------------------------------------------------------

export interface FilterSpec {
  text: string;
  onlyOod: boolean;
  onlyStub: boolean;
  onlyFailed: boolean;
}

export const NO_FILTER: FilterSpec = { text: "", onlyOod: false, onlyStub: false, onlyFailed: false };

export function filterRows(rows: BatchRow[], spec: FilterSpec): BatchRow[] {
  const q = spec.text.trim().toLowerCase();
  return rows.filter((r) => {
    if (spec.onlyFailed && r.ok) return false;
    if (spec.onlyOod && r.flags.outOfDomain === 0) return false;
    if (spec.onlyStub && r.flags.stubServed === 0) return false;
    if (q) {
      const hay = `${r.smilesInput} ${r.moleculeId ?? ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

export function isFiltered(spec: FilterSpec): boolean {
  return !!spec.text.trim() || spec.onlyOod || spec.onlyStub || spec.onlyFailed;
}
