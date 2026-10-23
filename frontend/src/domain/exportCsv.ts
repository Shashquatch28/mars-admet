// CSV export of what is on screen, as data and nothing more.
//
// One line per molecule x endpoint (long format), in the fixed roster order. Nothing here ranks, scores
// or marks anything: the state column says what the screen says (ok, out_of_domain, stub_served,
// not_returned, not_requested, rule_based, row_failed), reliability stays a separate column from the
// value, and every roster endpoint appears whether or not the service returned it (ADR-008).
// Numbers are written at full precision, not at the rounding the screen uses.
//
// The table is built once (`buildExportRows`, typed cells) and written twice: here as CSV, and by exportXlsx.ts
// as an Excel workbook (ADR-037), so the two files cannot drift apart.
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

/** One cell of the export table: text, a number at full precision, or null for an empty cell. */
export type ExportCell = string | number | null;

// A cell that starts with one of these is read as a formula by a spreadsheet that opens a CSV. Text fields get a
// leading apostrophe there; numbers are written as numbers and are never touched. (A workbook writes text as
// string cells, which are never evaluated, so it needs no such guard and adds none.)
const FORMULA_START = /^[=+\-@\t\r]/;

function csvText(s: string): string {
  const safe = FORMULA_START.test(s) ? `'${s}` : s;
  return /[",\r\n]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
}

function csvCell(c: ExportCell): string {
  if (c == null || c === "") return "";
  return typeof c === "number" ? String(c) : csvText(c);
}

function text(s: string | null | undefined): ExportCell {
  return s == null || s === "" ? null : s;
}

function num(n: number | null | undefined): ExportCell {
  return n == null || !Number.isFinite(n) ? null : n;
}

/** What the molecule was, for the columns that repeat on every one of its lines. */
export interface ExportMolecule {
  row?: number; // 1-based position in a Batch; absent for a single Predict
  smilesInput: string;
  response: PredictionResponse | null;
  cells: Row[];
  error?: string | null; // a Batch row that failed before inference
}

function rowFor(m: ExportMolecule, cell: Row | null): ExportCell[] {
  const r = m.response;
  const p = cell?.prediction;
  const hasValue = !!p && cell?.state.kind !== "not_returned" && cell?.state.kind !== "not_requested";
  const rule = cell?.state.kind === "rule_based";
  return [
    m.row ?? null,
    text(m.smilesInput),
    text(r?.smiles_standardized),
    text(r?.molecule_id),
    text(cell?.endpoint),
    text(cell?.meta.taskType),
    hasValue ? num(p!.value) : null,
    cell ? text(DISPLAY_UNIT[cell.endpoint]) : null,
    cell ? text(cell.state.kind) : "row_failed",
    // The rule-based score has no spread (the service repeats the value); do not export a fake one.
    hasValue && !rule ? num(p!.confidence_low) : null,
    hasValue && !rule ? num(p!.confidence_high) : null,
    hasValue ? num(p!.heldout_error_halfwidth) : null,
    hasValue ? num(p!.heldout_error_level) : null,
    hasValue ? num(p!.heldout_error_n) : null,
    hasValue && !rule ? num(p!.knn_distance) : null,
    hasValue ? num(p!.ad_threshold) : null,
    hasValue ? text(p!.model_id) : null,
    text(r?.model_version),
    text(r?.served_at),
    text(m.error),
  ];
}

/**
 * The data rows (no header) of the export, one per molecule x endpoint in roster order. A row that failed before inference is one
 * line saying so, not 15 empty ones. Every row has exactly `CSV_COLUMNS.length` cells.
 */
export function buildExportRows(molecules: ExportMolecule[]): ExportCell[][] {
  const out: ExportCell[][] = [];
  for (const m of molecules) {
    if (m.error || !m.response) out.push(rowFor(m, null));
    else for (const cell of m.cells) out.push(rowFor(m, cell));
  }
  return out;
}

export function buildCsv(molecules: ExportMolecule[]): string {
  const lines = [CSV_COLUMNS.join(","), ...buildExportRows(molecules).map((r) => r.map(csvCell).join(","))];
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
