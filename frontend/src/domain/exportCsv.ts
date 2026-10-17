// CSV export of what is on screen, as data and nothing more.
//
// One line per molecule x endpoint (long format), in the fixed roster order. Nothing here ranks, scores
// or marks anything: the state column says what the screen says (ok, out_of_domain, stub_served,
// not_returned, not_requested, rule_based, row_failed), reliability stays a separate column from the
// value, and every roster endpoint appears whether or not the service returned it (ADR-008).
// Numbers are written at full precision, not at the rounding the screen uses.
import { DISPLAY_UNIT } from "./endpoints";
import type { Row } from "./reconcile";
import type { PredictionResponse } from "../types/contracts";

export const CSV_COLUMNS = [
  "row",
  "smiles_input",
  "smiles_standardized",
  "molecule_id",
  "endpoint",
  "task",
  "value",
  "unit",
  "state",
  "seed_spread_low",
  "seed_spread_high",
  "heldout_error_halfwidth",
  "heldout_error_level",
  "heldout_error_n",
  "knn_distance",
  "ad_threshold",
  "model_id",
  "model_version",
  "served_at",
  "error",
] as const;

// A cell that starts with one of these is read as a formula by a spreadsheet. Text fields get a
// leading apostrophe; numbers are written as numbers and are never touched.
const FORMULA_START = /^[=+\-@\t\r]/;

function text(s: string | null | undefined): string {
  if (s == null || s === "") return "";
  const safe = FORMULA_START.test(s) ? `'${s}` : s;
  return /[",\r\n]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
}

function num(n: number | null | undefined): string {
  return n == null || !Number.isFinite(n) ? "" : String(n);
}

/** What the molecule was, for the columns that repeat on every one of its lines. */
export interface ExportMolecule {
  row?: number; // 1-based position in a Batch; absent for a single Predict
  smilesInput: string;
  response: PredictionResponse | null;
  cells: Row[];
  error?: string | null; // a Batch row that failed before inference
}

function lineFor(m: ExportMolecule, cell: Row | null): string {
  const r = m.response;
  const p = cell?.prediction;
  const hasValue = !!p && cell?.state.kind !== "not_returned" && cell?.state.kind !== "not_requested";
  const rule = cell?.state.kind === "rule_based";
  const fields: string[] = [
    m.row == null ? "" : String(m.row),
    text(m.smilesInput),
    text(r?.smiles_standardized),
    text(r?.molecule_id),
    text(cell?.endpoint),
    text(cell?.meta.taskType),
    hasValue ? num(p!.value) : "",
    cell ? text(DISPLAY_UNIT[cell.endpoint]) : "",
    cell ? text(cell.state.kind) : "row_failed",
    // The rule-based score has no spread (the service repeats the value); do not export a fake one.
    hasValue && !rule ? num(p!.confidence_low) : "",
    hasValue && !rule ? num(p!.confidence_high) : "",
    hasValue ? num(p!.heldout_error_halfwidth) : "",
    hasValue ? num(p!.heldout_error_level) : "",
    hasValue ? num(p!.heldout_error_n) : "",
    hasValue && !rule ? num(p!.knn_distance) : "",
    hasValue ? num(p!.ad_threshold) : "",
    hasValue ? text(p!.model_id) : "",
    text(r?.model_version),
    text(r?.served_at),
    text(m.error),
  ];
  return fields.join(",");
}

export function buildCsv(molecules: ExportMolecule[]): string {
  const lines = [CSV_COLUMNS.join(",")];
  for (const m of molecules) {
    if (m.error || !m.response) lines.push(lineFor(m, null)); // one line saying the row failed, not 15 empty ones
    else for (const cell of m.cells) lines.push(lineFor(m, cell));
  }
  return lines.join("\r\n") + "\r\n";
}

const day = (d: Date) => d.toISOString().slice(0, 10);

export function predictFileName(moleculeId: string | null | undefined, now = new Date()): string {
  const id = (moleculeId ?? "").replace(/[^A-Za-z0-9_-]/g, "").slice(0, 16);
  return `mars-predict${id ? `-${id}` : ""}-${day(now)}.csv`;
}

export function batchFileName(rows: number, now = new Date()): string {
  return `mars-batch-${rows}-molecules-${day(now)}.csv`;
}

export function batchRowFileName(row: number, now = new Date()): string {
  return `mars-batch-row-${row}-${day(now)}.csv`;
}
