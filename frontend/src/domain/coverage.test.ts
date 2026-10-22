import { describe, expect, it } from "vitest";
import { buildBatch } from "./batch";
import { COVERAGE_NOTES, buildCoverage, fmtObserved } from "./coverage";
import { ML_ENDPOINTS } from "./endpoints";
import { makeBatchFixture } from "../testSupport/batchFixture";
import type { BatchPredictResponse, Endpoint, EndpointPrediction, PredictionResponse } from "../types/contracts";

const XGB = "mars-xgboost-ecfp-desc-v1";
const KERMT = "mars-kermt-single-v1";

const p = (endpoint: Endpoint, value: number, model_id: string, in_domain = true): EndpointPrediction => ({
  endpoint,
  value,
  unit: null,
  confidence_low: value - 0.1,
  confidence_high: value + 0.1,
  in_domain,
  knn_distance: 0.3,
  ad_threshold: 0.6,
  model_id,
});

const molecule = (id: string, predictions: EndpointPrediction[]): PredictionResponse => ({
  smiles_input: id,
  smiles_standardized: id,
  molecule_id: id,
  predictions,
  model_version: "v0.2.0-dev+kermt.test",
  served_at: "2026-10-22T00:00:00Z",
  cache_hit: false,
});

const response = (...rows: (PredictionResponse | string)[]): BatchPredictResponse => ({
  job_id: null,
  status: "done",
  total: rows.length,
  completed: rows.length,
  results: rows.map((r, i) =>
    typeof r === "string"
      ? { row_index: i, smiles_input: r, ok: false, error: "invalid SMILES", prediction: null }
      : { row_index: i, smiles_input: r.smiles_input, ok: true, error: null, prediction: r },
  ),
});

const A = molecule("A", [
  p("solubility_logs", -3, XGB),
  p("bbb_permeability", 0.8, KERMT),
  p("clearance_microsomal", 10, XGB),
  p("hia_absorption", 0.9, "stub-v0"),
]);
const B = molecule("B", [p("solubility_logs", -1, XGB, false), p("bbb_permeability", 0.4, XGB)]);
const C = molecule("C", [p("solubility_logs", -2, XGB), p("bbb_permeability", 0.6, KERMT)]);
const RUN = response(A, B, C, "bad");
const row = (cov: ReturnType<typeof buildCoverage>, e: Endpoint) => cov.rows.find((r) => r.endpoint === e)!;

describe("buildCoverage", () => {
  const cov = buildCoverage(buildBatch(RUN).rows, ["bbb_permeability", "clearance_microsomal"]);

  it("has one row per ML endpoint in roster order and leaves the rule-based score out", () => {
    expect(cov.rows.map((r) => r.endpoint)).toEqual(ML_ENDPOINTS);
    expect(cov.rows.some((r) => r.endpoint === "synthetic_accessibility")).toBe(false);
  });

  it("counts only molecules that returned a result and says how many failed", () => {
    expect(cov.molecules).toBe(3);
    expect(cov.failedRows).toBe(1);
    expect(row(cov, "solubility_logs").requested).toBe(3);
  });

  it("counts returned, not returned and out of domain", () => {
    const sol = row(cov, "solubility_logs");
    expect([sol.returned, sol.notReturned, sol.outOfDomain]).toEqual([3, 0, 1]);
    const clr = row(cov, "clearance_microsomal");
    expect([clr.requested, clr.returned, clr.notReturned]).toEqual([3, 1, 2]);
    expect(row(cov, "ames_mutagenicity").notReturned).toBe(3);
  });

  it("counts a stub value as stub-served only: no family, not out of domain, not in the range", () => {
    const hia = row(cov, "hia_absorption");
    expect([hia.returned, hia.stubServed, hia.xgboost, hia.kermt, hia.fellBack, hia.other]).toEqual([1, 1, 0, 0, 0, 0]);
    expect(hia.notReturned).toBe(2);
    expect(hia.observed).toBeNull();
  });

  it("keeps a fallback apart from both XGBoost and KERMT", () => {
    const bbb = row(cov, "bbb_permeability");
    expect([bbb.kermt, bbb.fellBack, bbb.xgboost]).toEqual([2, 1, 0]);
    // the same data with KERMT off: the XGBoost row is just an XGBoost row
    const off = row(buildCoverage(buildBatch(RUN).rows, []), "bbb_permeability");
    expect([off.kermt, off.fellBack, off.xgboost]).toEqual([2, 0, 1]);
    // every returned non-stub value is in exactly one family column
    for (const r of cov.rows) expect(r.xgboost + r.kermt + r.fellBack + r.other).toBe(r.returned - r.stubServed);
  });

  it("gives min, median and max for regression endpoints only", () => {
    expect(row(cov, "solubility_logs").observed).toEqual({ min: -3, median: -2, max: -1 });
    expect(row(cov, "bbb_permeability").observed).toBeNull(); // classification scores have no range here
    expect(row(cov, "clearance_microsomal").observed).toEqual({ min: 10, median: 10, max: 10 });
  });

  it("takes the mean of the two middle values for an even count", () => {
    const two = buildCoverage(buildBatch(response(A, B)).rows);
    expect(row(two, "solubility_logs").observed).toEqual({ min: -3, median: -2, max: -1 });
  });

  it("does not count an endpoint the request left out", () => {
    // the service answered only what was asked, as it does for a subset request
    const onlySol = response(molecule("A", [p("solubility_logs", -3, XGB)]), molecule("B", [p("solubility_logs", -1, XGB)]));
    const cov1 = buildCoverage(buildBatch(onlySol, ["solubility_logs"]).rows);
    expect(row(cov1, "bbb_permeability").requested).toBe(0);
    expect(row(cov1, "bbb_permeability").returned).toBe(0);
    expect(row(cov1, "solubility_logs").requested).toBe(2);
  });

  it("reconciles on a large fixture: requested = returned + not returned, and ranges are ordered", () => {
    const big = buildCoverage(buildBatch(makeBatchFixture(240)).rows, ["bbb_permeability"]);
    for (const r of big.rows) {
      expect(r.requested).toBe(r.returned + r.notReturned);
      expect(r.stubServed + r.xgboost + r.kermt + r.fellBack + r.other).toBe(r.returned);
      expect(r.outOfDomain).toBeLessThanOrEqual(r.returned);
      if (r.observed) {
        expect(r.observed.min).toBeLessThanOrEqual(r.observed.median);
        expect(r.observed.median).toBeLessThanOrEqual(r.observed.max);
      }
    }
    expect(big.molecules + big.failedRows).toBe(240);
  });

  it("prints a range at the decimals the screen uses and a true minus", () => {
    expect(fmtObserved("solubility_logs", { min: -3, median: -2.004, max: -1 })).toBe("−3.00 · −2.00 · −1.00");
    expect(fmtObserved("ppb_binding", { min: 55.04, median: 90, max: 99.5 })).toBe("55.0 · 90.0 · 99.5");
  });
});

describe("COVERAGE_NOTES", () => {
  it("uses no ranking, flagging or favourability wording", () => {
    const text = COVERAGE_NOTES.join(" ").toLowerCase();
    for (const word of ["outlier", "favourable", "favorable", "safe", "best", "worst", "rank", "winner", "anomal", "unusual"]) {
      expect(text).not.toContain(word);
    }
  });
  it("says what the range is and is not", () => {
    const text = COVERAGE_NOTES.join(" ");
    expect(text).toMatch(/this batch only/);
    expect(text).toMatch(/no direction of good/);
  });
});
