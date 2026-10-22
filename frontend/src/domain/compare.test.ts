import { describe, expect, it } from "vitest";
import {
  buildComparison,
  compareFailure,
  compareProblem,
  filledInputs,
  repeatedSlots,
} from "./compare";
import { ALL_ENDPOINTS } from "./endpoints";
import type { CompareResponse, EndpointPrediction, PredictionResponse } from "../types/contracts";
import hit from "./real-responses/celecoxib-hit.json";
import stubOnly from "./real-responses/celecoxib-stub-only.json";

const asPred = (x: unknown) => x as PredictionResponse;
const without = (p: PredictionResponse, endpoint: string): PredictionResponse => ({
  ...p,
  predictions: p.predictions.filter((e: EndpointPrediction) => e.endpoint !== endpoint),
});

describe("input handling", () => {
  it("trims, drops blank slots and keeps order", () => {
    expect(filledInputs(["  CCO ", "", "c1ccccc1"])).toEqual(["CCO", "c1ccccc1"]);
  });
  it("needs two molecules, and says so", () => {
    expect(compareProblem(["CCO", ""])).toContain("at least 2");
    expect(compareProblem(["CCO", " ", " "])).not.toBeNull();
    expect(compareProblem(["CCO", "CCN"])).toBeNull();
    expect(compareProblem(["CCO", "CCN", "CCC"])).toBeNull();
  });
  it("flags a slot that repeats an earlier one but never a blank", () => {
    expect(repeatedSlots(["CCO", "CCN", " CCO "])).toEqual([2]);
    expect(repeatedSlots(["", "", ""])).toEqual([]);
  });
});

describe("buildComparison", () => {
  const response: CompareResponse = { molecules: [asPred(hit), asPred(stubOnly)] };
  const cmp = buildComparison(response);

  it("gives every molecule a cell on every endpoint, in the same order", () => {
    const rows = cmp.groups.flatMap((g) => g.rows);
    expect(rows.map((r) => r.endpoint).sort()).toEqual([...ALL_ENDPOINTS].sort());
    for (const r of rows) {
      expect(r.cells).toHaveLength(2);
      expect(r.cells.every((c) => c.endpoint === r.endpoint)).toBe(true);
    }
  });
  it("keeps one column per molecule with its own identity and version", () => {
    expect(cmp.columns.map((c) => c.index)).toEqual([0, 1]);
    expect(cmp.columns[0].moleculeId).toBe(asPred(hit).molecule_id);
    expect(cmp.columns[1].moleculeId).toBe(asPred(stubOnly).molecule_id);
  });
  it("marks an endpoint one molecule lacks as not returned for that molecule only", () => {
    const partial = buildComparison({
      molecules: [asPred(hit), without(asPred(stubOnly), "hia_absorption")],
    });
    const hia = partial.groups.flatMap((g) => g.rows).find((r) => r.endpoint === "hia_absorption")!;
    expect(hia.cells[0].state.kind).not.toBe("not_returned");
    expect(hia.cells[1].state.kind).toBe("not_returned");
    expect(partial.columns[1].flags.notReturned).toBeGreaterThan(0);
    expect(partial.columns[0].flags.notReturned).toBe(0);
  });
  it("counts stub-served cells per molecule", () => {
    expect(cmp.columns[1].flags.stubServed).toBeGreaterThan(0);
  });
  it("never reads per_endpoint_winner: a response that carries one builds the same comparison", () => {
    const withWinner = buildComparison({
      ...response,
      per_endpoint_winner: Object.fromEntries(ALL_ENDPOINTS.map((e) => [e, 1])) as never,
    });
    expect(withWinner).toEqual(cmp);
  });
  it("lists distinct model versions, sorted", () => {
    const mixed = buildComparison({
      molecules: [{ ...asPred(hit), model_version: "v2" }, { ...asPred(stubOnly), model_version: "v1" }],
    });
    expect(mixed.modelVersions).toEqual(["v1", "v2"]);
  });
  it("is empty rather than throwing for an empty response", () => {
    expect(buildComparison({ molecules: [] })).toEqual({ columns: [], groups: [], modelVersions: [] });
  });
});

describe("compareFailure", () => {
  it("names a rejected molecule and a rate limit, and shows the status", () => {
    expect(compareFailure(422, "Invalid SMILES").title).toBe("Molecule rejected");
    expect(compareFailure(429, "slow down").title).toBe("Rate limited");
    expect(compareFailure(500, "x").detail).toBe("500 · x");
    expect(compareFailure(0, "API unreachable").detail).toBe("API unreachable");
  });
});
