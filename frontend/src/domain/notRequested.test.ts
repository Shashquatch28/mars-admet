// NOT REQUESTED (ADR-028): the user left an endpoint out of the run. It is a different
// fact from NOT RETURNED (the service was asked and did not answer), and the roster
// still renders every row (ADR-008).
import { describe, expect, it } from "vitest";
import type { Endpoint, PredictionResponse } from "../types/contracts";
import { ALL_ENDPOINTS, ML_ENDPOINTS, endpointSelectionLabel } from "./endpoints";
import { endpointsForRequest, reconcile, requestedMlEndpoints } from "./reconcile";

import subset from "./real-responses/celecoxib-subset.json";

// A real response to a subset request (see real-responses/README.md).
const SUBSET = subset as unknown as PredictionResponse;
const SENT: Endpoint[] = ["solubility_logs", "herg_cardiotoxicity", "synthetic_accessibility"];

describe("endpointsForRequest", () => {
  it("sends no subset when everything is selected, so the request is the plain one", () => {
    expect(endpointsForRequest(ML_ENDPOINTS)).toBeNull();
  });
  it("sends the selection plus the always-requested SA score for a subset", () => {
    expect(endpointsForRequest(["solubility_logs", "herg_cardiotoxicity"])).toEqual(SENT);
  });
});

describe("requestedMlEndpoints", () => {
  it("is every ML endpoint when nothing was sent", () => {
    expect(requestedMlEndpoints(null)).toEqual(ML_ENDPOINTS);
  });
  it("drops the rule-based SA score and keeps roster order", () => {
    expect(requestedMlEndpoints(["herg_cardiotoxicity", "synthetic_accessibility", "solubility_logs"])).toEqual([
      "solubility_logs",
      "herg_cardiotoxicity",
    ]);
  });
});

describe("reconcile() on a real subset response", () => {
  const requested = requestedMlEndpoints(SENT);
  const recon = reconcile(SUBSET, requested);

  it("still renders the full 15-row roster", () => {
    expect(recon.rows.map((r) => r.endpoint)).toEqual(ALL_ENDPOINTS);
  });

  it("marks every endpoint the user left out NOT REQUESTED, and none NOT RETURNED", () => {
    const left = ML_ENDPOINTS.filter((e) => !requested.includes(e));
    expect(left.length).toBe(12);
    for (const e of left) expect(recon.rows.find((r) => r.endpoint === e)?.state.kind, e).toBe("not_requested");
    expect(recon.rows.filter((r) => r.state.kind === "not_returned")).toEqual([]);
  });

  it("reconciles the header counts over what was asked for", () => {
    expect(recon.counts.requested).toBe(2);
    expect(recon.counts.returned).toBe(2);
  });

  it("never calls the always-requested SA score NOT REQUESTED", () => {
    expect(recon.rows.find((r) => r.endpoint === "synthetic_accessibility")?.state.kind).toBe("rule_based");
  });

  it("the same response read as a full request would call those 12 rows NOT RETURNED", () => {
    // This is the distinction ADR-028 exists to keep: same data, different cause of absence.
    const asFull = reconcile(SUBSET);
    expect(asFull.rows.filter((r) => r.state.kind === "not_returned").length).toBe(12);
    expect(asFull.rows.filter((r) => r.state.kind === "not_requested").length).toBe(0);
  });
});

describe("endpointSelectionLabel", () => {
  it("reads All 14 or N of 14", () => {
    expect(endpointSelectionLabel(ML_ENDPOINTS)).toBe("All 14 endpoints");
    expect(endpointSelectionLabel(["solubility_logs", "herg_cardiotoxicity"])).toBe("2 of 14 endpoints");
    expect(endpointSelectionLabel([])).toBe("0 of 14 endpoints");
  });
});
