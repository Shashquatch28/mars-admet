// The first captured response in which some endpoints were served by a trained model and the rest by the stub
// (ship checklist D7: "no mixed real+stub response has ever been captured"). Captured 2026-10-19 from the real API
// container running main, with trained artifacts mounted for solubility_logs, hia_absorption and clearance_microsomal
// only, so the routing table's per-endpoint stub fallback produced the other eleven. See real-responses/README.md.
import { describe, expect, it } from "vitest";
import mixed from "./real-responses/celecoxib-mixed-real-and-stub.json";
import type { PredictionResponse } from "../types/contracts";
import { buildCsv, CSV_COLUMNS } from "./exportCsv";
import { STUB_MODEL_ID } from "./endpoints";
import { fmtValue } from "./format";
import { buildReport } from "./report";
import { reconcile, requestedMlEndpoints } from "./reconcile";

const MIXED = mixed as PredictionResponse;
const REAL = ["solubility_logs", "hia_absorption", "clearance_microsomal"];
const recon = reconcile(MIXED, requestedMlEndpoints(null));
const byEndpoint = new Map(recon.rows.map((r) => [r.endpoint, r]));

describe("a response with both trained and stub-served endpoints", () => {
  it("really is mixed: the trained model for three endpoints, the stub for eleven, the rule for SA", () => {
    const real = MIXED.predictions.filter((p) => p.model_id !== STUB_MODEL_ID && p.endpoint !== "synthetic_accessibility");
    expect(real.map((p) => p.endpoint).sort()).toEqual([...REAL].sort());
    expect(MIXED.predictions.filter((p) => p.model_id === STUB_MODEL_ID)).toHaveLength(11);
    expect(MIXED.predictions.find((p) => p.endpoint === "synthetic_accessibility")?.model_id).toBe("rdkit-sascore");
  });

  it("derives each row's state from its own model, not from the response as a whole", () => {
    for (const row of recon.rows) {
      const p = row.prediction!;
      if (p.endpoint === "synthetic_accessibility") expect(row.state.kind).toBe("rule_based");
      else if (p.model_id === STUB_MODEL_ID) expect(row.state.kind, p.endpoint).toBe("stub_served");
      else expect(["ok", "out_of_domain"], p.endpoint).toContain(row.state.kind);
    }
  });

  it("a stub row is a stub whatever its applicability-domain flag says (stub is the more basic fact)", () => {
    const stubOutOfDomain = MIXED.predictions.filter((p) => p.model_id === STUB_MODEL_ID && !p.in_domain);
    expect(stubOutOfDomain.length).toBeGreaterThan(0); // the captured response has stub rows flagged out of domain
    for (const p of stubOutOfDomain) expect(byEndpoint.get(p.endpoint)!.state.kind).toBe("stub_served");
  });

  it("counts stub-served rows once and does not count them as out of domain", () => {
    expect(recon.counts).toEqual({ requested: 14, returned: 14, outOfDomain: 0, stubServed: 11 });
  });

  it("gives stub rows no applicability-domain cutoff and no held-out error, and gives trained regression rows a band", () => {
    for (const p of MIXED.predictions.filter((x) => x.model_id === STUB_MODEL_ID)) {
      expect(p.ad_threshold, p.endpoint).toBeNull();
      expect(p.heldout_error_halfwidth ?? null, p.endpoint).toBeNull();
    }
    for (const e of ["solubility_logs", "clearance_microsomal"]) {
      expect(byEndpoint.get(e as never)!.prediction!.heldout_error_halfwidth, e).toBeGreaterThan(0);
    }
  });

  it("formats trained and stub values with the same function: one grammar for the value cell", () => {
    for (const row of recon.rows) {
      const text = fmtValue(row.prediction!, row.meta);
      expect(text, row.endpoint).toMatch(/^[−]?\d+(\.\d+)?$/);
    }
  });

  it("the printed report hatches exactly the stub values and says STUB in words", () => {
    const report = buildReport({ smilesInput: MIXED.smiles_input, response: MIXED, cells: recon.rows }, new Date("2026-10-19T00:00:00Z"));
    const rows = report.groups.flatMap((g) => g.rows);
    const stubs = rows.filter((r) => r.hatch);
    expect(stubs).toHaveLength(11);
    expect(stubs.every((r) => r.status === "STUB" && r.stateKind === "stub_served")).toBe(true);
    expect(rows.filter((r) => !r.hatch).every((r) => r.status !== "STUB")).toBe(true);
    expect(report.counts.stubServed).toBe(11);
  });

  it("the CSV marks each line's state apart from its value", () => {
    const csv = buildCsv([{ smilesInput: MIXED.smiles_input, response: MIXED, cells: recon.rows }]);
    const lines = csv.trim().split("\r\n").slice(1);
    const stateCol = CSV_COLUMNS.indexOf("state");
    const states = lines.map((l) => l.split(",")[stateCol]);
    expect(states.filter((s) => s === "stub_served")).toHaveLength(11);
    expect(states.filter((s) => s === "rule_based")).toHaveLength(1);
  });
});
