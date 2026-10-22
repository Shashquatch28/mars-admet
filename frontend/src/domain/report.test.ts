import { describe, expect, it } from "vitest";
import { ALL_ENDPOINTS } from "./endpoints";
import type { ExportMolecule } from "./exportCsv";
import { FALLBACK_STATEMENT, REPORT_STATEMENTS, buildReport, reportCounts, reportTitle } from "./report";
import { reconcile, requestedMlEndpoints } from "./reconcile";
import type { PredictionResponse } from "../types/contracts";

import miss from "./real-responses/celecoxib-miss.json";
import subset from "./real-responses/celecoxib-subset.json";
import stubOnly from "./real-responses/celecoxib-stub-only.json";
import mixedJson from "./real-responses/celecoxib-mixed-real-and-stub.json";

const MISS = miss as PredictionResponse;
const SUBSET = subset as PredictionResponse;
const STUB_ONLY = stubOnly as PredictionResponse;

const molecule = (response: PredictionResponse, requested = requestedMlEndpoints(null), extra: Partial<ExportMolecule> = {}): ExportMolecule => ({
  smilesInput: response.smiles_input,
  response,
  cells: reconcile(response, requested).rows,
  ...extra,
});

const NOW = new Date("2026-10-19T12:00:00Z");
const rowsOf = (r: ReturnType<typeof buildReport>) => r.groups.flatMap((g) => g.rows);

describe("buildReport", () => {
  it("lists every roster endpoint, returned or not, once", () => {
    const rows = rowsOf(buildReport(molecule(MISS), NOW));
    expect(rows.map((r) => r.endpoint).sort()).toEqual([...ALL_ENDPOINTS].sort());
  });

  it("prints a value in the same form in every state and keeps reliability in its own field", () => {
    for (const response of [MISS, SUBSET, STUB_ONLY]) {
      for (const row of rowsOf(buildReport(molecule(response), NOW))) {
        if (row.value !== null) expect(row.value).toMatch(/^[−]?\d+(\.\d+)?$/); // a bare number: no marker inside it
        expect(row.value ?? "").not.toMatch(/OUT|STUB|NOT/);
      }
    }
  });

  it("marks a stub value with the hatch flag and the word STUB, and nothing else", () => {
    const rows = rowsOf(buildReport(molecule(STUB_ONLY), NOW));
    const stub = rows.filter((r) => r.stateKind === "stub_served");
    expect(stub.length).toBeGreaterThan(0);
    for (const r of stub) {
      expect(r.hatch).toBe(true);
      expect(r.status).toBe("STUB");
    }
    expect(rows.filter((r) => r.stateKind !== "stub_served").every((r) => !r.hatch)).toBe(true);
  });

  it("says NOT RETURNED for what the service did not answer and NOT REQUESTED for what was left out", () => {
    const requested = requestedMlEndpoints(["solubility_logs", "bbb_permeability"]);
    const rows = rowsOf(buildReport(molecule(SUBSET, requested), NOW));
    const byState = (k: string) => rows.filter((r) => r.stateKind === k);
    // a prediction that is present is described as such whatever was requested, so only absent ones count
    const returned = new Set(SUBSET.predictions.map((p) => p.endpoint));
    const absentUnrequested = requestedMlEndpoints(null).filter((e) => !requested.includes(e) && !returned.has(e));
    expect(byState("not_requested").map((r) => r.endpoint).sort()).toEqual([...absentUnrequested].sort());
    expect(absentUnrequested.length).toBeGreaterThan(0);
    expect(byState("not_requested").every((r) => r.status === "NOT REQUESTED" && r.value === null)).toBe(true);
    for (const r of byState("not_returned")) {
      expect(r.status).toBe("NOT RETURNED");
      expect(r.value).toBeNull();
      expect(r.spread).toBeNull();
    }
  });

  it("states out of domain in words and never as a judgement on the value", () => {
    const rows = rowsOf(buildReport(molecule(MISS), NOW));
    const ood = rows.filter((r) => r.stateKind === "out_of_domain");
    for (const r of ood) {
      expect(r.status).toBe("OUT OF DOMAIN");
      expect(r.domain).toMatch(/^out of domain, 5-NN distance/);
      expect(r.value).not.toBeNull();
    }
  });

  it("prints no spread for the rule-based score and no held-out error for classification", () => {
    const rows = rowsOf(buildReport(molecule(MISS), NOW));
    for (const r of rows.filter((r) => r.task === "rule_based")) expect(r.spread).toBeNull();
    for (const r of rows.filter((r) => r.task === "classification")) expect(r.heldOutError).toBeNull();
  });

  it("prints the held-out error with what it measures, only when the service sent a complete band", () => {
    const withBand = rowsOf(buildReport(molecule(MISS), NOW)).filter((r) => r.heldOutError);
    for (const r of withBand) {
      expect(r.task).toBe("regression");
      expect(r.heldOutError).toMatch(/^±\d+(\.\d+)? \(\d+% of [\d,]+ errors\)$/);
    }
    // what the band does and does not mean is said once, in the fixed statements
    expect(buildReport(molecule(MISS), NOW).statements.join(" ")).toMatch(/not a range for this molecule/);
  });

  it("carries the provenance a reader needs to trace the numbers", () => {
    const r = buildReport(molecule(MISS), NOW);
    expect(r.moleculeId).toBe(MISS.molecule_id);
    expect(r.smilesStandardized).toBe(MISS.smiles_standardized);
    expect(r.modelVersion).toBe(MISS.model_version);
    expect(r.generatedAt).toBe("2026-10-19T12:00:00.000Z");
    expect(r.servedAt).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC$/);
  });

  it("reports a failed Batch row as a failure, with no table", () => {
    const r = buildReport({ row: 7, smilesInput: "not-a-smiles", response: null, cells: [], error: "invalid SMILES" }, NOW);
    expect(r.failure).toBe("invalid SMILES");
    expect(r.groups).toEqual([]);
    expect(r.batchRow).toBe(7);
  });

  it("always prints the statements that stop a reader assuming more than MARS can support", () => {
    const text = buildReport(molecule(MISS), NOW).statements.join(" ").toLowerCase();
    expect(text).toContain("not calibrated probabilities");
    expect(text).toContain("no validated risk threshold");
    expect(text).toContain("not return");
    expect(buildReport(molecule(MISS), NOW).statements).toEqual([...REPORT_STATEMENTS]);
  });

  it("uses no ranking or favourability wording of its own", () => {
    const r = buildReport(molecule(MISS), NOW);
    const own = [...r.statements.filter((s) => !s.includes("no value is called")), ...rowsOf(r).flatMap((x) => [x.domain, x.status ?? "", x.heldOutError ?? ""])].join(" ").toLowerCase();
    for (const word of ["favourable", "favorable", "safe", "low risk", "high risk", "winner", "rank 1", "pass", "fail"]) {
      expect(own).not.toContain(word);
    }
  });
});

describe("reportCounts", () => {
  it("reconciles requested = returned + not returned, over the ML endpoints only", () => {
    for (const response of [MISS, SUBSET, STUB_ONLY]) {
      const c = reportCounts(molecule(response).cells);
      expect(c.requested).toBe(c.returned + c.notReturned);
      expect(c.requested + c.notRequested).toBe(14);
    }
  });

  it("agrees with the screen's own counts", () => {
    const requested = requestedMlEndpoints(null);
    const recon = reconcile(MISS, requested);
    const c = reportCounts(recon.rows);
    expect(c.requested).toBe(recon.counts.requested);
    expect(c.returned).toBe(recon.counts.returned);
    expect(c.outOfDomain).toBe(recon.counts.outOfDomain);
    expect(c.stubServed).toBe(recon.counts.stubServed);
  });
});

describe("reportTitle", () => {
  it("is safe to use as a document title (the saved PDF's default name)", () => {
    const r = buildReport(molecule(MISS), NOW);
    expect(reportTitle(r)).toMatch(/^MARS prediction report [A-Za-z0-9_-]{1,16}$/);
    expect(reportTitle({ ...r, moleculeId: "../x y" })).toBe("MARS prediction report xy");
  });
});

describe("buildReport: which model answered (ADR-034 item 7)", () => {
  const ROUTED = ["bbb_permeability", "clearance_microsomal"];
  const mixed = mixedJson as PredictionResponse;

  it("prints the model family, never the raw model_id", () => {
    const rows = rowsOf(buildReport(molecule(MISS), NOW));
    const byEndpoint = Object.fromEntries(rows.map((r) => [r.endpoint, r.model]));
    expect(byEndpoint.solubility_logs).toBe("XGBoost");
    expect(byEndpoint.synthetic_accessibility).toBe("RDKit");
    expect(rows.some((r) => (r.model ?? "").includes("mars-"))).toBe(false);
  });

  it("marks a row routed to KERMT but answered by XGBoost, and only that row", () => {
    const r = buildReport(molecule(MISS), NOW, ROUTED);
    expect(rowsOf(r).filter((x) => x.fellBack).map((x) => x.endpoint).sort()).toEqual(ROUTED);
    expect(r.fallbackCount).toBe(2);
    expect(r.statements).toContain(FALLBACK_STATEMENT);
    expect(r.statements.slice(0, -1)).toEqual([...REPORT_STATEMENTS]);
  });

  it("says nothing about fallback when KERMT is off or nothing fell back", () => {
    const off = buildReport(molecule(MISS), NOW);
    expect(off.fallbackCount).toBe(0);
    expect(rowsOf(off).some((x) => x.fellBack)).toBe(false);
    expect(off.statements).toEqual([...REPORT_STATEMENTS]);
  });

  it("does not call a stub value a fallback", () => {
    const rows = rowsOf(buildReport(molecule(mixed), NOW, ROUTED));
    for (const row of rows.filter((x) => x.hatch)) {
      expect(row.model).toBe("stub");
      expect(row.fellBack).toBe(false);
    }
  });

  it("words the fallback without ranking or favourability", () => {
    const text = FALLBACK_STATEMENT.toLowerCase();
    for (const word of ["favourable", "favorable", "safe", "better", "worse", "best", "winner"]) {
      expect(text).not.toContain(word);
    }
  });
});

describe("buildReport: computed properties (ADR-034 item 3)", () => {
  const withProps = (): PredictionResponse => ({
    ...MISS,
    properties: {
      mol_weight: 381.37,
      crippen_logp: 3.51,
      h_bond_donors: 1,
      h_bond_acceptors: 3,
      tpsa: 77.98,
      rotatable_bonds: 3,
      qed: 0.75,
      lipinski_criteria_exceeded: 0,
      alerts: [{ catalog: "Brenk", name: "nitro group" }],
    },
  });

  it("carries the properties block, outside the roster and the counts", () => {
    const r = buildReport(molecule(withProps()), NOW);
    expect(r.properties?.source).toBe("RDKit");
    expect(r.properties?.lines.map((l) => l.key)).toContain("qed");
    expect(r.properties?.alerts).toEqual([
      { catalog: "PAINS", names: [] },
      { catalog: "Brenk", names: ["nitro group"] },
    ]);
    expect(rowsOf(r).map((x) => x.endpoint).sort()).toEqual([...ALL_ENDPOINTS].sort()); // the roster is unchanged
    expect(r.counts).toEqual(buildReport(molecule(MISS), NOW).counts);
  });

  it("is null when the response has none, and for a failed row", () => {
    expect(buildReport(molecule(MISS), NOW).properties).toBeNull();
    const failed = buildReport({ row: 2, smilesInput: "bad", response: withProps(), cells: [], error: "invalid SMILES" }, NOW);
    expect(failed.properties).toBeNull();
  });

  it("no longer says the service computes no drug-likeness flags", () => {
    expect(buildReport(molecule(MISS), NOW).statements.join(" ")).not.toMatch(/drug-likeness/i);
  });
});
