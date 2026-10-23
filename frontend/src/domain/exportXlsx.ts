// Excel export of a Batch result (ADR-037): the CSV's table, written as a workbook.
//
// Same columns, same order, same lines, built by the same function (`buildExportRows`), so the two files cannot drift.
// Nothing here ranks, scores, colours or marks anything: no fill, no conditional format, no rank or winner column; `state`
// is its own column and the value cell is the same cell in every state. Numbers stay numeric cells at full precision; text is
// written as string cells, which a spreadsheet never evaluates, so no cell is a formula and the CSV's apostrophe guard is not
// needed (and would alter the data). A second sheet says in words what each column and each state means.
//
// The spreadsheet library is loaded only when someone presses the button (a dynamic import, its own chunk) and sits behind
// `writeWorkbook`, the one function that touches it, so replacing it touches one place.
import { CSV_COLUMNS, buildExportRows, type ExportCell, type ExportMolecule } from "./exportCsv";
import { REPORT_STATEMENTS } from "./report";

/** Most molecules the Excel action will write. A workbook is held whole in browser memory while it is made; the CSV has no such ceiling. */
export const XLSX_MAX_MOLECULES = 5000;

export const xlsxTooLarge = (molecules: number): boolean => molecules > XLSX_MAX_MOLECULES;

export const xlsxCeilingNote = (molecules: number): string =>
  `This run has ${molecules.toLocaleString()} molecules. The Excel file is limited to ${XLSX_MAX_MOLECULES.toLocaleString()} because the browser builds the whole workbook in memory; the CSV has no such limit and holds the same table.`;

export function batchXlsxFileName(rows: number, now = new Date()): string {
  return `mars-batch-${rows}-molecules-${now.toISOString().slice(0, 10)}.xlsx`;
}

export const RESULTS_SHEET = "Results";
export const READ_ME_SHEET = "Read me";

const COLUMN_NOTES: Record<(typeof CSV_COLUMNS)[number], string> = {
  row: "Position of the molecule in the uploaded file, starting at 1.",
  smiles_input: "The SMILES as it was uploaded.",
  smiles_standardized: "The SMILES after the service's standardization; empty for a row that failed before inference.",
  molecule_id: "The service's identifier for the standardized molecule.",
  endpoint: "The endpoint. Every endpoint in the roster has a line for every molecule, returned or not.",
  task: "regression, classification, or rule_based (a computed rule, not a model prediction).",
  value: "The value at full precision. A regression value is in `unit`; a classification value is a model score between 0 and 1, not a probability. Empty when the state is not_returned, not_requested or row_failed.",
  unit: "The unit of a regression value; empty for a classification score.",
  state: "What the screen says about this value; see the list below. It is its own column: the value is the same kind of cell in every state.",
  seed_spread_low: "Lower end of the spread across the 5 cross-validation seeds. Not a confidence interval.",
  seed_spread_high: "Upper end of the spread across the 5 cross-validation seeds. Not a confidence interval.",
  heldout_error_halfwidth: "Half-width of the endpoint's held-out error band: one number per endpoint, measured on molecules the models were not trained on. It is not a range for this molecule.",
  heldout_error_level: "The coverage level of the held-out error band.",
  heldout_error_n: "The number of held-out errors the band was measured from.",
  knn_distance: "Mean 5-nearest-neighbour Tanimoto distance from the molecule to the endpoint's training set (applicability domain).",
  ad_threshold: "The cutoff knn_distance was judged against for this endpoint; empty when the endpoint has no applicability-domain index.",
  model_id: "The model artifact that answered this value.",
  model_version: "The serving generation that produced the response.",
  served_at: "When the service produced the response (UTC).",
  error: "For a row that failed before inference, why. Empty otherwise.",
};

const STATE_NOTES: readonly (readonly [string, string])[] = [
  ["ok", "A model returned the value and the molecule is inside that endpoint's applicability domain."],
  ["out_of_domain", "A model returned the value, but the molecule is outside the chemical space that endpoint was trained on. Treat it as unreliable rather than as a result."],
  ["stub_served", "The value is a stand-in from the service's fallback, not a trained prediction."],
  ["not_returned", "The endpoint was requested and the service returned nothing for it. The value is empty."],
  ["not_requested", "The endpoint was left out of this run. The value is empty. Nothing failed."],
  ["rule_based", "The synthetic accessibility score: computed by a rule, not predicted by a model."],
  ["row_failed", "The row failed before inference (see the error column). It has one line, not one per endpoint."],
];

// The statements the on-screen report also prints, in the same words, so what leaves the app is not worded twice. The
// first four are the ones that make sense in a file: scores are not probabilities, there is no validated direction of good,
// what spread and held-out error are, and what out of domain and stub mean.
const SHARED_STATEMENTS = REPORT_STATEMENTS.slice(0, 4).map((s) => s.replace(/\bthis report\b/g, "this file"));

export const NO_RANKING_LINE = "Nothing in this file ranks, scores or rates a molecule: it has no rank, winner, score or flag column, and the lines are in input order and roster order.";

export interface WorkbookSheet {
  name: string;
  /** Column headings, then rows of typed cells. */
  header: string[];
  rows: ExportCell[][];
  widths: number[];
}

const WIDTHS = [6, 34, 34, 18, 26, 14, 14, 10, 15, 14, 14, 14, 14, 12, 14, 12, 28, 16, 26, 30];

/** The workbook as plain data: the Results sheet is the CSV's table; the Read me sheet explains it. Pure and tested. */
export function buildWorkbookModel(molecules: ExportMolecule[]): WorkbookSheet[] {
  const readMe: ExportCell[][] = [
    ["MARS batch results"],
    [NO_RANKING_LINE],
    ...SHARED_STATEMENTS.map((s): ExportCell[] => [s]),
    [null],
    ["Column", "Meaning"],
    ...CSV_COLUMNS.map((c): ExportCell[] => [c, COLUMN_NOTES[c]]),
    [null],
    ["State", "Meaning"],
    ...STATE_NOTES.map(([k, v]): ExportCell[] => [k, v]),
  ];
  return [
    { name: RESULTS_SHEET, header: [...CSV_COLUMNS], rows: buildExportRows(molecules), widths: WIDTHS },
    { name: READ_ME_SHEET, header: [], rows: readMe, widths: [26, 120] },
  ];
}

type XlsxCell = { value: string | number; type: StringConstructor | NumberConstructor; fontWeight?: "bold" } | null;

/** A cell as the library wants it. Text is always an explicit String cell, so nothing a user uploaded can become a formula. */
export function toXlsxCell(c: ExportCell, bold = false): XlsxCell {
  if (c == null || c === "") return null;
  const style = bold ? { fontWeight: "bold" as const } : {};
  return typeof c === "number" ? { value: c, type: Number, ...style } : { value: c, type: String, ...style };
}

/** The one place the spreadsheet library is touched. Dynamic, so it is a separate chunk fetched on the first press. */
async function writeWorkbook(sheets: WorkbookSheet[]): Promise<Blob> {
  const { default: writeXlsxFile } = await import("write-excel-file/browser");
  const content = sheets.map((s) => ({
    sheet: s.name,
    data: [...(s.header.length ? [s.header.map((h) => toXlsxCell(h, true))] : []), ...s.rows.map((r) => r.map((c) => toXlsxCell(c)))],
    columns: s.widths.map((width) => ({ width })),
    ...(s.header.length ? { stickyRowsCount: 1 } : {}),
  }));
  // The library's types describe cells more loosely than the plain objects above; the shape is the documented one.
  return writeXlsxFile(content as never).toBlob();
}

/** The workbook for a Batch result. Rejects above the ceiling instead of freezing the tab. */
export async function buildXlsxBlob(molecules: ExportMolecule[]): Promise<Blob> {
  if (xlsxTooLarge(molecules.length)) throw new Error(xlsxCeilingNote(molecules.length));
  return writeWorkbook(buildWorkbookModel(molecules));
}

export const XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
