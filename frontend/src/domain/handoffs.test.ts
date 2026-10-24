// Hand-offs into Compare (Library, Batch) and the endpoint subset for Batch and Compare. The
// subset reuses ADR-028: an endpoint the user left out is NOT REQUESTED, never NOT RETURNED, in
// every molecule's column and every Batch row, read against what the run asked for.
import { describe, expect, it } from "vitest";
import { COMPARE_MAX, addToSlots, buildComparison, handoffNote } from "./compare";
import { buildBatch } from "./batch";
import { ML_ENDPOINTS } from "./endpoints";
import { endpointsForRequest, requestedMlEndpoints } from "./reconcile";
import type { BatchPredictResponse, Endpoint, PredictionResponse } from "../types/contracts";

import subset from "./real-responses/celecoxib-subset.json";

const SUBSET = subset as unknown as PredictionResponse;
const PICKED: Endpoint[] = ["solubility_logs", "herg_cardiotoxicity"];
const SENT = endpointsForRequest(PICKED);
const REQUESTED = requestedMlEndpoints(SENT);

describe("addToSlots", () => {
  it("fills the first empty slot and leaves the others as they are", () => {
    expect(addToSlots(["CCO", ""], "c1ccccc1")).toEqual({ slots: ["CCO", "c1ccccc1"], slot: 1, kind: "added" });
    expect(addToSlots(["", "CCN"], "c1ccccc1")).toEqual({ slots: ["c1ccccc1", "CCN"], slot: 0, kind: "added" });
  });
  it("opens a third slot when there are two and both are full", () => {
    expect(addToSlots(["CCO", "CCN"], "c1ccccc1")).toEqual({ slots: ["CCO", "CCN", "c1ccccc1"], slot: 2, kind: "added" });
  });
  it("replaces the last slot only when every slot is full, and says so", () => {
    const a = addToSlots(["CCO", "CCN", "CCC"], "c1ccccc1");
    expect(a).toEqual({ slots: ["CCO", "CCN", "c1ccccc1"], slot: 2, kind: "replaced" });
    expect(handoffNote(a, "Batch")).toContain(`holds ${COMPARE_MAX} molecules`);
    expect(handoffNote(a, "Batch")).toContain("Molecule 3 was replaced");
  });
  it("does not add a molecule that is already there (trimmed), and points at its slot", () => {
    const a = addToSlots(["CCO", "CCN", ""], "  CCN ");
    expect(a.kind).toBe("already");
    expect(a.slot).toBe(1);
    expect(a.slots).toEqual(["CCO", "CCN", ""]);
    expect(handoffNote(a, "Library")).toContain("Molecule 2");
  });
  it("two hand-offs in a row fill two slots", () => {
    const first = addToSlots(["", ""], "CCO");
    const second = addToSlots(first.slots, "CCN");
    expect(second.slots).toEqual(["CCO", "CCN"]);
  });
  it("never changes the slots it was given", () => {
    const slots = ["CCO", ""];
    addToSlots(slots, "CCN");
    expect(slots).toEqual(["CCO", ""]);
  });
});

describe("handoffNote", () => {
  it("names the molecule, says nothing has been run, and uses no ranking word", () => {
    const text = handoffNote({ slot: 1, kind: "added" }, "Batch");
    expect(text).toContain("Molecule 2 came from Batch");
    expect(text).toContain("Nothing has been run");
    expect(text.toLowerCase()).not.toMatch(/better|best|worse|rank|winner/);
  });
  it("says a molecule from the Library is predicted again, not read from the saved values", () => {
    expect(handoffNote({ slot: 0, kind: "added" }, "Library")).toMatch(/predicted again.*saved values are not reused/);
    expect(handoffNote({ slot: 0, kind: "added" }, "Batch")).not.toMatch(/predicted again/);
  });
});

describe("a Compare run on a subset (ADR-028)", () => {
  const cmp = buildComparison({ molecules: [SUBSET, SUBSET] }, REQUESTED);
  const rows = cmp.groups.flatMap((g) => g.rows);

  it("reads every endpoint the user left out as NOT REQUESTED in every molecule's column, and none as NOT RETURNED", () => {
    for (const r of rows) {
      const left = ML_ENDPOINTS.includes(r.endpoint) && !REQUESTED.includes(r.endpoint);
      for (const c of r.cells) {
        expect(c.state.kind === "not_requested", r.endpoint).toBe(left);
        expect(c.state.kind).not.toBe("not_returned");
      }
    }
    expect(cmp.columns.every((c) => c.flags.notReturned === 0)).toBe(true);
  });
  it("still renders the whole roster", () => {
    expect(rows.length).toBe(ML_ENDPOINTS.length + 1);
  });
  it("read as a full request would call the left-out endpoints NOT RETURNED: the request has to travel with the result", () => {
    const wrong = buildComparison({ molecules: [SUBSET, SUBSET] });
    expect(wrong.columns[0].flags.notReturned).toBe(ML_ENDPOINTS.length - PICKED.length);
  });
});

describe("a Batch run on a subset (ADR-028)", () => {
  const response: BatchPredictResponse = {
    status: "done",
    total: 2,
    completed: 2,
    results: [
      { row_index: 0, smiles_input: "CCO", ok: true, error: null, prediction: SUBSET },
      { row_index: 1, smiles_input: "not a molecule", ok: false, error: "could not parse", prediction: null },
    ],
  };
  const b = buildBatch(response, REQUESTED);

  it("marks the endpoints left out NOT REQUESTED on a returned row, and counts none of them as not returned", () => {
    const row = b.rows[0];
    const left = row.cells.filter((c) => ML_ENDPOINTS.includes(c.endpoint) && !REQUESTED.includes(c.endpoint));
    expect(left).toHaveLength(ML_ENDPOINTS.length - PICKED.length);
    for (const c of left) expect(c.state.kind).toBe("not_requested");
    expect(row.flags.notReturned).toBe(0);
    expect(b.counts.cellsNotReturned).toBe(0);
  });
  it("keeps a failed row a row, with the same NOT REQUESTED reading for the endpoints that were left out", () => {
    const failed = b.rows[1];
    expect(failed.ok).toBe(false);
    expect(failed.error).toBe("could not parse");
    expect(failed.cells.filter((c) => c.state.kind === "not_requested")).toHaveLength(ML_ENDPOINTS.length - PICKED.length);
  });
});

describe("the request a subset sends", () => {
  it("is the selection plus the rule-based score, and null when everything is selected", () => {
    expect(SENT).toEqual([...PICKED, "synthetic_accessibility"]);
    expect(endpointsForRequest(ML_ENDPOINTS)).toBeNull();
  });
});
