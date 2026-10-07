// Tests against REAL service responses (src/domain/real-responses/, see its
// README for provenance). Every other fixture in this repo was written by us, so
// those only test our assumptions; these test what the API actually sends.
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Endpoint, PredictionResponse } from "../types/contracts";
import { ENDPOINT_METADATA, ML_ENDPOINTS, STUB_MODEL_ID } from "./endpoints";
import { decimalPlaces, fmtValue } from "./format";
import { reconcile } from "./reconcile";

import miss from "./real-responses/celecoxib-miss.json";
import hit from "./real-responses/celecoxib-hit.json";
import subset from "./real-responses/celecoxib-subset.json";
import stubOnly from "./real-responses/celecoxib-stub-only.json";
import invalid422 from "./real-responses/invalid-smiles-422.json";
import missingField422 from "./real-responses/missing-field-422.json";

const asResponse = (j: unknown) => j as PredictionResponse;
const MISS = asResponse(miss);
const HIT = asResponse(hit);
const SUBSET = asResponse(subset);
const STUB_ONLY = asResponse(stubOnly);

const RESPONSE_KEYS = [
  "smiles_input",
  "smiles_standardized",
  "molecule_id",
  "predictions",
  "model_version",
  "served_at",
  "cache_hit",
].sort();
const PREDICTION_KEYS = [
  "endpoint",
  "value",
  "unit",
  "confidence_low",
  "confidence_high",
  "in_domain",
  "knn_distance",
  "model_id",
  "ad_threshold",
].sort();

describe("real responses match the TS contract mirror", () => {
  for (const [name, r] of Object.entries({ MISS, HIT, SUBSET, STUB_ONLY })) {
    it(`${name}: exact key sets`, () => {
      expect(Object.keys(r).sort()).toEqual(RESPONSE_KEYS);
      for (const p of r.predictions) expect(Object.keys(p).sort()).toEqual(PREDICTION_KEYS);
    });
  }

  it("ad_threshold is the cutoff in_domain was judged against (contracts/prediction.py)", () => {
    for (const p of MISS.predictions) {
      if (p.ad_threshold === null) continue;
      expect(p.in_domain, p.endpoint).toBe(p.knn_distance <= p.ad_threshold);
    }
  });

  it("ad_threshold is null exactly where there is no applicability-domain index", () => {
    for (const p of MISS.predictions) {
      const ruleBased = ENDPOINT_METADATA[p.endpoint].taskType === "rule_based";
      expect(p.ad_threshold === null, p.endpoint).toBe(ruleBased);
    }
    for (const p of STUB_ONLY.predictions) expect(p.ad_threshold, p.endpoint).toBeNull();
  });

  it("the service sends unit: null for model rows, so nothing may depend on it", () => {
    const modelRows = MISS.predictions.filter((p) => ENDPOINT_METADATA[p.endpoint].taskType !== "rule_based");
    expect(modelRows.length).toBe(14);
    for (const p of modelRows) expect(p.unit, p.endpoint).toBeNull();
  });
});

describe("reconcile() on a full real response", () => {
  const recon = reconcile(MISS);

  it("counts 14 requested / 14 returned and excludes the rule-based SA row", () => {
    expect(recon.counts.requested).toBe(14);
    expect(recon.counts.returned).toBe(14);
    expect(recon.rows.length).toBe(15);
  });

  it("derives out_of_domain from the response, never from the value", () => {
    const expected = MISS.predictions.filter((p) => !p.in_domain && p.model_id !== STUB_MODEL_ID).map((p) => p.endpoint);
    expect(expected.length).toBeGreaterThan(0); // a real molecule really is partly out of domain
    expect(recon.counts.outOfDomain).toBe(expected.length);
    const oodRows = recon.rows.filter((r) => r.state.kind === "out_of_domain").map((r) => r.endpoint);
    expect(oodRows.sort()).toEqual([...expected].sort());
  });

  it("serves no stub rows and marks the SA row rule_based", () => {
    expect(recon.counts.stubServed).toBe(0);
    expect(recon.rows.find((r) => r.endpoint === "synthetic_accessibility")?.state.kind).toBe("rule_based");
  });
});

describe("reconcile() on a subset response", () => {
  const recon = reconcile(SUBSET);

  it("keeps the full roster: omitted endpoints become NOT RETURNED rows, not gaps", () => {
    expect(recon.rows.length).toBe(15);
    const returned: Endpoint[] = ["solubility_logs", "herg_cardiotoxicity"];
    expect(recon.counts.requested).toBe(14);
    expect(recon.counts.returned).toBe(returned.length);
    for (const e of ML_ENDPOINTS) {
      const row = recon.rows.find((r) => r.endpoint === e)!;
      expect(row.state.kind === "not_returned", e).toBe(!returned.includes(e));
    }
  });
});

describe("reconcile() on a stub-only service", () => {
  const recon = reconcile(STUB_ONLY);

  it("marks every row stub-served and reports the SA score as not returned", () => {
    expect(recon.counts).toEqual({ requested: 14, returned: 14, outOfDomain: 0, stubServed: 14 });
    expect(recon.rows.find((r) => r.endpoint === "synthetic_accessibility")?.state.kind).toBe("not_returned");
  });
});

describe("cache hit vs miss", () => {
  it("a hit carries the original served_at and identical predictions", () => {
    expect(MISS.cache_hit).toBe(false);
    expect(HIT.cache_hit).toBe(true);
    expect(HIT.served_at).toBe(MISS.served_at);
    expect(HIT.predictions).toEqual(MISS.predictions);
  });
});

describe("formatting real values", () => {
  it("prints % bound at 1 dp even though the service sends no unit", () => {
    const ppb = MISS.predictions.find((p) => p.endpoint === "ppb_binding")!;
    expect(ppb.unit).toBeNull();
    expect(decimalPlaces("ppb_binding")).toBe(1);
    expect(fmtValue(ppb, ENDPOINT_METADATA.ppb_binding)).toMatch(/^\d+\.\d$/);
  });

  it("prints other regression endpoints at 2 dp", () => {
    const sol = MISS.predictions.find((p) => p.endpoint === "solubility_logs")!;
    expect(fmtValue(sol, ENDPOINT_METADATA.solubility_logs)).toMatch(/^[−\d]\d*\.\d{2}$/);
  });
});

describe("client error mapping, using the real error bodies", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  async function client(fetchImpl: () => Promise<Response>) {
    vi.stubEnv("VITE_API_BASE", "/api");
    vi.stubGlobal("fetch", vi.fn(fetchImpl));
    vi.resetModules();
    return import("../data/client");
  }
  const json = (status: number, body: unknown) => () =>
    Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

  it("422 with a string detail (invalid SMILES) keeps the service's message", async () => {
    const { fetchPrediction } = await client(json(422, invalid422));
    await expect(fetchPrediction("x")).rejects.toMatchObject({ status: 422, message: invalid422.detail });
  });

  it("422 with a validation-error list becomes readable text, not [object Object]", async () => {
    const { fetchPrediction } = await client(json(422, missingField422));
    await expect(fetchPrediction("x")).rejects.toMatchObject({ status: 422, message: "Field required" });
  });

  it("a non-JSON error body (proxy 502) falls back to the status text", async () => {
    const { fetchPrediction } = await client(() =>
      Promise.resolve(new Response("bad gateway", { status: 502, statusText: "Bad Gateway" })),
    );
    await expect(fetchPrediction("x")).rejects.toMatchObject({ status: 502, message: "Bad Gateway" });
  });

  it("an unreachable API becomes status 0 'API unreachable'", async () => {
    const { fetchPrediction, fetchHealth } = await client(() => Promise.reject(new TypeError("Failed to fetch")));
    await expect(fetchPrediction("x")).rejects.toMatchObject({ status: 0, message: "API unreachable" });
    await expect(fetchHealth()).rejects.toMatchObject({ status: 0 });
  });

  it("a successful call returns the response, measured latency and what was submitted", async () => {
    const { fetchPrediction, fetchHealth } = await client(json(200, miss));
    const out = await fetchPrediction("  raw input  ".trim());
    expect(out.response).toEqual(MISS);
    expect(out.submitted).toBe("raw input");
    expect(out.latencyMs).toBeGreaterThanOrEqual(0);
    await expect(fetchHealth()).resolves.toBe(true);
  });
});
