// Excel export (ADR-037). The workbook is written for real and opened again here, as XML, so these tests check what a
// spreadsheet would see: the same table as the CSV, typed cells, no formula cell anywhere, no rank or colour.
import { strFromU8, unzipSync } from "fflate";
import { describe, expect, it } from "vitest";
import {
  NO_RANKING_LINE,
  READ_ME_SHEET,
  RESULTS_SHEET,
  XLSX_MAX_MOLECULES,
  batchXlsxFileName,
  buildWorkbookModel,
  buildXlsxBlob,
  toXlsxCell,
  xlsxCeilingNote,
  xlsxTooLarge,
} from "./exportXlsx";
import { CSV_COLUMNS, buildCsv, buildExportRows, type ExportMolecule } from "./exportCsv";
import { REPORT_STATEMENTS } from "./report";
import { reconcile, requestedMlEndpoints } from "./reconcile";
import { ALL_ENDPOINTS } from "./endpoints";
import type { PredictionResponse } from "../types/contracts";

import miss from "./real-responses/celecoxib-miss.json";
import subset from "./real-responses/celecoxib-subset.json";
import stubOnly from "./real-responses/celecoxib-stub-only.json";

const MISS = miss as unknown as PredictionResponse;
const SUBSET = subset as unknown as PredictionResponse;
const STUB = stubOnly as unknown as PredictionResponse;

const mol = (response: PredictionResponse, extra: Partial<ExportMolecule> = {}, sent: null | string[] = null): ExportMolecule => ({
  smilesInput: response.smiles_input,
  response,
  cells: reconcile(response, requestedMlEndpoints(sent as never)).rows,
  ...extra,
});

const EVIL = '=HYPERLINK("http://x","y")';
const molecules: ExportMolecule[] = [
  mol(MISS, { row: 1 }),
  mol(SUBSET, { row: 2 }, ["solubility_logs", "herg_cardiotoxicity", "synthetic_accessibility"]),
  mol(STUB, { row: 3 }),
  { row: 4, smilesInput: EVIL, response: null, cells: [], error: "+cmd|'/c calc'!A1" },
];

async function open(ms: ExportMolecule[]) {
  const blob = await buildXlsxBlob(ms);
  const files = unzipSync(new Uint8Array(await blob.arrayBuffer()));
  const text = (name: string) => strFromU8(files[name]);
  return { files, text, blob };
}

describe("the workbook model", () => {
  const sheets = buildWorkbookModel(molecules);

  it("has the Results sheet first, with exactly the CSV's columns and lines", () => {
    expect(sheets.map((s) => s.name)).toEqual([RESULTS_SHEET, READ_ME_SHEET]);
    const results = sheets[0];
    expect(results.header).toEqual([...CSV_COLUMNS]);
    expect(results.rows).toEqual(buildExportRows(molecules));
    expect(results.rows.length).toBe(buildCsv(molecules).trim().split("\r\n").length - 1 + 0);
    for (const r of results.rows) expect(r).toHaveLength(CSV_COLUMNS.length);
  });
  it("lists every roster endpoint for a returned molecule, and one line for a failed row", () => {
    const rows = sheets[0].rows;
    const endpointCol = CSV_COLUMNS.indexOf("endpoint");
    const first = rows.filter((r) => r[0] === 1).map((r) => r[endpointCol]);
    expect(first).toEqual(ALL_ENDPOINTS);
    expect(rows.filter((r) => r[0] === 4)).toHaveLength(1);
    expect(rows.find((r) => r[0] === 4)![CSV_COLUMNS.indexOf("state")]).toBe("row_failed");
  });
  it("keeps state apart from value and reads a left-out endpoint as not_requested with an empty value", () => {
    const rows = sheets[0].rows.filter((r) => r[0] === 2);
    const value = CSV_COLUMNS.indexOf("value");
    const state = CSV_COLUMNS.indexOf("state");
    const left = rows.filter((r) => r[state] === "not_requested");
    expect(left.length).toBe(12);
    for (const r of left) expect(r[value]).toBeNull();
    expect(rows.filter((r) => r[state] === "not_returned")).toEqual([]);
  });
  it("has no rank, winner, score, flag, delta or colour column", () => {
    for (const h of sheets[0].header) expect(h).not.toMatch(/rank|winner|best|score|flag|delta|diff|colou?r|risk/i);
  });
  it("numbers are numbers at full precision and text is text", () => {
    const row = sheets[0].rows.find((r) => r[0] === 1 && r[CSV_COLUMNS.indexOf("endpoint")] === "solubility_logs")!;
    expect(typeof row[CSV_COLUMNS.indexOf("value")]).toBe("number");
    expect(row[CSV_COLUMNS.indexOf("value")]).toBe(MISS.predictions.find((p) => p.endpoint === "solubility_logs")!.value);
    expect(typeof row[CSV_COLUMNS.indexOf("smiles_input")]).toBe("string");
  });
  it("the Read me sheet defines every column and every state, and reuses the report's wording", () => {
    const rm = sheets[1].rows.map((r) => r.join(" | ")).join("\n");
    for (const c of CSV_COLUMNS) expect(rm).toContain(`${c} |`);
    for (const s of ["ok", "out_of_domain", "stub_served", "not_returned", "not_requested", "rule_based", "row_failed"]) expect(rm).toContain(`${s} |`);
    expect(rm).toContain(NO_RANKING_LINE);
    for (const stmt of REPORT_STATEMENTS.slice(0, 4)) expect(rm).toContain(stmt.replace(/\bthis report\b/g, "this file"));
    // the shared statement says what is NOT called good; everything we wrote ourselves says none of it
    const shared = new Set([NO_RANKING_LINE, ...REPORT_STATEMENTS.slice(0, 4).map((x) => x.replace(/this report/g, "this file"))]);
    const own = rm.split("\n").filter((line) => !shared.has(line)).join("\n");
    expect(own.toLowerCase()).not.toMatch(/safe|favourable|better|best|winner|good/);
  });
});

describe("toXlsxCell", () => {
  it("writes text as an explicit string cell, even when it looks like a formula", () => {
    for (const t of ["=1+1", "+1", "-1", "@SUM(A1)", EVIL]) expect(toXlsxCell(t)).toEqual({ value: t, type: String });
  });
  it("writes numbers as numeric cells and empties as nothing", () => {
    expect(toXlsxCell(-1.98)).toEqual({ value: -1.98, type: Number });
    expect(toXlsxCell(null)).toBeNull();
    expect(toXlsxCell("")).toBeNull();
  });
});

describe("the written file", () => {
  it("is a real workbook with the two sheets, in order", async () => {
    const { text } = await open(molecules);
    const wb = text("xl/workbook.xml");
    expect(wb.indexOf(RESULTS_SHEET)).toBeGreaterThan(-1);
    expect(wb.indexOf(READ_ME_SHEET)).toBeGreaterThan(wb.indexOf(RESULTS_SHEET));
  });
  it("contains no formula cell, and no text that starts like a formula is stored as anything but a string", async () => {
    const { files, text } = await open(molecules);
    const sheetFiles = Object.keys(files).filter((f) => /^xl\/worksheets\/sheet\d+\.xml$/.test(f));
    expect(sheetFiles.length).toBe(2);
    for (const f of sheetFiles) expect(text(f)).not.toMatch(/<f[ >/]/);
    const results = text(sheetFiles.sort()[0]);
    // every cell is a number or a string (shared or inline); none is typed "str" (a formula result) or "e" (error)
    const types = new Set([...results.matchAll(/<c [^>]*?\bt="([a-zA-Z]+)"/g)].map((m) => m[1]));
    expect(types.size).toBeGreaterThan(0); // the pattern found cells at all
    expect([...types].some((t) => t === "s" || t === "inlineStr")).toBe(true); // text is stored as strings
    for (const t of types) expect(["s", "inlineStr", "n"]).toContain(t);
    expect(results).toMatch(/<v>-?\d+\.\d+<\/v>/); // and a value is a bare number, not a string
    // the hostile text is present as data
    const strings = files["xl/sharedStrings.xml"] ? text("xl/sharedStrings.xml") : results;
    expect(strings).toContain("HYPERLINK");
    expect(strings).toContain("calc");
  });
  it("has no fill, conditional format or drawing: nothing in the workbook colours a value", async () => {
    const { files, text } = await open(molecules);
    const names = Object.keys(files);
    expect(names.some((n) => /drawing|chart/i.test(n))).toBe(false);
    for (const n of names.filter((f) => f.startsWith("xl/worksheets/sheet"))) expect(text(n)).not.toMatch(/conditionalFormatting|dataBar|colorScale|iconSet/);
    if (files["xl/styles.xml"]) {
      const styles = text("xl/styles.xml");
      expect(styles).not.toMatch(/<fgColor|<bgColor|patternType="solid"/);
    }
  });
});

describe("the ceiling", () => {
  it("is a named number, refuses above it with a sentence, and is not a silent failure", async () => {
    expect(XLSX_MAX_MOLECULES).toBe(5000);
    expect(xlsxTooLarge(5000)).toBe(false);
    expect(xlsxTooLarge(5001)).toBe(true);
    expect(xlsxCeilingNote(7000)).toMatch(/7,000 molecules.*limited to 5,000.*CSV has no such limit/);
    const many = Array.from({ length: XLSX_MAX_MOLECULES + 1 }, (_, i) => ({ row: i + 1, smilesInput: "C", response: null, cells: [], error: "x" }));
    await expect(buildXlsxBlob(many)).rejects.toThrow(/limited to 5,000/);
  });
  it("names the file like the CSV with the extension changed", () => {
    expect(batchXlsxFileName(12, new Date("2026-10-23T10:00:00Z"))).toBe("mars-batch-12-molecules-2026-10-23.xlsx");
  });
});
