import { describe, expect, it } from "vitest";
import { CSV_COLUMNS, batchFileName, batchRowFileName, buildCsv, predictFileName, type ExportMolecule } from "./exportCsv";
import { ALL_ENDPOINTS } from "./endpoints";
import { reconcile, requestedMlEndpoints } from "./reconcile";
import type { PredictionResponse } from "../types/contracts";

import miss from "./real-responses/celecoxib-miss.json";
import subset from "./real-responses/celecoxib-subset.json";
import stubOnly from "./real-responses/celecoxib-stub-only.json";

const MISS = miss as PredictionResponse;
const SUBSET = subset as PredictionResponse;
const STUB_ONLY = stubOnly as PredictionResponse;

// Minimal RFC 4180 reader so the tests check what a spreadsheet would see, not the writer's own output.
function parse(csv: string): string[][] {
  const out: string[][] = [];
  let row: string[] = [];
  let cur = "";
  let quoted = false;
  for (let i = 0; i < csv.length; i++) {
    const ch = csv[i];
    if (quoted) {
      if (ch === '"' && csv[i + 1] === '"') {
        cur += '"';
        i++;
      } else if (ch === '"') quoted = false;
      else cur += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ",") {
      row.push(cur);
      cur = "";
    } else if (ch === "\r") continue;
    else if (ch === "\n") {
      row.push(cur);
      out.push(row);
      row = [];
      cur = "";
    } else cur += ch;
  }
  return out;
}

const molecule = (response: PredictionResponse, extra: Partial<ExportMolecule> = {}): ExportMolecule => ({
  smilesInput: response.smiles_input,
  response,
  cells: reconcile(response, requestedMlEndpoints(null)).rows,
  ...extra,
});

const col = (header: string[], name: string) => header.indexOf(name);

describe("buildCsv", () => {
  it("writes the documented header and every roster endpoint, in roster order", () => {
    const [header, ...lines] = parse(buildCsv([molecule(MISS)]));
    expect(header).toEqual([...CSV_COLUMNS]);
    expect(lines.map((l) => l[col(header, "endpoint")])).toEqual(ALL_ENDPOINTS);
    expect(lines.every((l) => l.length === header.length)).toBe(true);
  });

  it("writes full-precision numbers and the same state words the screen uses", () => {
    const [header, ...lines] = parse(buildCsv([molecule(MISS)]));
    const sol = lines.find((l) => l[col(header, "endpoint")] === "solubility_logs")!;
    const real = MISS.predictions.find((p) => p.endpoint === "solubility_logs")!;
    expect(Number(sol[col(header, "value")])).toBe(real.value);
    expect(Number(sol[col(header, "seed_spread_low")])).toBe(real.confidence_low);
    expect(sol[col(header, "unit")]).toBe("logS");
    expect(["ok", "out_of_domain"]).toContain(sol[col(header, "state")]);
  });

  it("keeps the held-out error band on a regression line and leaves it empty elsewhere", () => {
    const withBand: PredictionResponse = {
      ...MISS,
      predictions: MISS.predictions.map((p) =>
        p.endpoint === "solubility_logs"
          ? { ...p, heldout_error_halfwidth: 1.677, heldout_error_level: 0.9, heldout_error_n: 4700 }
          : p,
      ),
    };
    const [header, ...lines] = parse(buildCsv([molecule(withBand)]));
    const sol = lines.find((l) => l[col(header, "endpoint")] === "solubility_logs")!;
    const hia = lines.find((l) => l[col(header, "endpoint")] === "hia_absorption")!;
    expect([sol[col(header, "heldout_error_halfwidth")], sol[col(header, "heldout_error_level")], sol[col(header, "heldout_error_n")]]).toEqual(["1.677", "0.9", "4700"]);
    expect(hia[col(header, "heldout_error_halfwidth")]).toBe("");
  });

  it("marks an endpoint left out of the request as not_requested, with no value, not as a failure", () => {
    const requested = requestedMlEndpoints(["solubility_logs", "synthetic_accessibility"]);
    const m: ExportMolecule = { ...molecule(SUBSET), cells: reconcile(SUBSET, requested).rows };
    const [header, ...lines] = parse(buildCsv([m]));
    const left = lines.filter((l) => l[col(header, "state")] === "not_requested");
    expect(left.length).toBeGreaterThan(0);
    expect(left.every((l) => l[col(header, "value")] === "")).toBe(true);
  });

  it("keeps a stub-served value but says so", () => {
    const [header, ...lines] = parse(buildCsv([molecule(STUB_ONLY)]));
    const stub = lines.filter((l) => l[col(header, "state")] === "stub_served");
    expect(stub.length).toBeGreaterThan(0);
    expect(stub.every((l) => l[col(header, "value")] !== "")).toBe(true);
  });

  it("exports no spread for the rule-based score, which is computed, not predicted", () => {
    const [header, ...lines] = parse(buildCsv([molecule(MISS)]));
    const sa = lines.find((l) => l[col(header, "endpoint")] === "synthetic_accessibility")!;
    expect(sa[col(header, "state")]).toBe("rule_based");
    expect(sa[col(header, "value")]).not.toBe("");
    expect([sa[col(header, "seed_spread_low")], sa[col(header, "seed_spread_high")], sa[col(header, "knn_distance")]]).toEqual(["", "", ""]);
  });

  it("writes one row_failed line for a Batch row that failed, with its error, instead of empty endpoint lines", () => {
    const failed: ExportMolecule = { row: 3, smilesInput: "not-a-smiles", response: null, cells: [], error: "Invalid SMILES, bad input" };
    const [header, ...lines] = parse(buildCsv([molecule(MISS, { row: 1 }), failed]));
    const f = lines.filter((l) => l[col(header, "row")] === "3");
    expect(f).toHaveLength(1);
    expect(f[0][col(header, "state")]).toBe("row_failed");
    expect(f[0][col(header, "error")]).toBe("Invalid SMILES, bad input");
    expect(f[0][col(header, "endpoint")]).toBe("");
  });

  it("quotes commas and quotes, and defuses a leading formula character in text fields only", () => {
    const evil: ExportMolecule = { row: 1, smilesInput: '=cmd|"x", y', response: null, cells: [], error: "a,b" };
    const [header, line] = parse(buildCsv([evil]));
    expect(line[col(header, "smiles_input")]).toBe(`'=cmd|"x", y`);
    expect(line[col(header, "error")]).toBe("a,b");
    // a negative number is a number, not a formula, and is left alone
    const neg = parse(buildCsv([molecule(MISS)]));
    const sol = neg.find((l) => l[col(neg[0], "endpoint")] === "solubility_logs")!;
    expect(sol[col(neg[0], "value")].startsWith("-")).toBe(true);
  });

  it("does not order or annotate by value: no rank, score, winner or favourability column", () => {
    expect([...CSV_COLUMNS].some((c) => /rank|winner|better|best|risk|good|safe|favour/i.test(c))).toBe(false);
  });
});

describe("file names", () => {
  const d = new Date("2026-10-18T12:00:00Z");
  it("are plain and carry the date", () => {
    expect(predictFileName("572a3bb55eb31557", d)).toBe("mars-predict-572a3bb55eb31557-2026-10-18.csv");
    expect(predictFileName(null, d)).toBe("mars-predict-2026-10-18.csv");
    expect(batchFileName(240, d)).toBe("mars-batch-240-molecules-2026-10-18.csv");
    expect(batchRowFileName(3, d)).toBe("mars-batch-row-3-2026-10-18.csv");
  });
  it("never let an id break out of the name", () => {
    expect(predictFileName("../../x y", d)).toBe("mars-predict-xy-2026-10-18.csv");
  });
});
