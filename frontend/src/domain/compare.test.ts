import { describe, expect, it } from "vitest";
import {
  buildComparison,
  compareFailure,
  compareProblem,
  filledInputs,
  repeatedSlots,
} from "./compare";
import { ALL_ENDPOINTS } from "./endpoints";
import { propertyLines } from "./properties";
import type { CompareResponse, EndpointPrediction, MoleculeProperties, PredictionResponse } from "../types/contracts";
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
    const empty = buildComparison({ molecules: [] });
    expect(empty.columns).toEqual([]);
    expect(empty.groups).toEqual([]);
    expect(empty.modelVersions).toEqual([]);
    expect(empty.properties.lines.every((l) => l.cells.length === 0)).toBe(true);
  });
});

describe("computed properties across molecules (ADR-036)", () => {
  const A: MoleculeProperties = {
    mol_weight: 381.3714,
    crippen_logp: -0.5,
    h_bond_donors: 1,
    h_bond_acceptors: 3,
    tpsa: 77.98,
    rotatable_bonds: 3,
    qed: 0.7541,
    lipinski_criteria_exceeded: 0,
    alerts: [{ catalog: "PAINS", name: "ene_rhod_A(235)" }, { catalog: "Brenk", name: "nitro group" }],
  };
  const B: MoleculeProperties = {
    mol_weight: 46.07,
    crippen_logp: -0.0014,
    h_bond_donors: 1,
    h_bond_acceptors: 1,
    tpsa: 20.23,
    rotatable_bonds: 0,
    qed: null,
    lipinski_criteria_exceeded: 0,
    alerts: [],
  };
  const withProps = (p: PredictionResponse, props: MoleculeProperties | null): PredictionResponse => ({ ...p, properties: props });
  const two = buildComparison({ molecules: [withProps(asPred(hit), A), withProps(asPred(stubOnly), B)] });

  it("has one cell per molecule in every row, in Predict's row order and number format", () => {
    expect(two.properties.lines.map((l) => l.key)).toEqual(propertyLines(A).map((l) => l.key));
    for (const row of two.properties.lines) expect(row.cells).toHaveLength(2);
    for (const [i, p] of [A, B].entries()) {
      expect(two.properties.lines.map((l) => l.cells[i])).toEqual(propertyLines(p).map((l) => l.value));
    }
    expect(two.properties.lines.map((l) => l.unit)).toEqual(propertyLines(A).map((l) => l.unit));
  });
  it("keeps the alerts per molecule: a list of names, or an empty list that reads as no match", () => {
    expect(two.properties.alerts).toEqual([
      { catalog: "PAINS", cells: [["ene_rhod_A(235)"], []] },
      { catalog: "Brenk", cells: [["nitro group"], []] },
    ]);
  });
  it("marks a molecule the service sent no properties for with null in every row, and no other molecule", () => {
    const partial = buildComparison({ molecules: [withProps(asPred(hit), A), withProps(asPred(stubOnly), null)] });
    for (const row of partial.properties.lines) {
      expect(row.cells[0]).not.toBeNull();
      expect(row.cells[1]).toBeNull();
    }
    for (const row of partial.properties.alerts) {
      expect(row.cells[0]).not.toBeNull();
      expect(row.cells[1]).toBeNull();
    }
    // a response from before `properties` existed has none at all
    const old = buildComparison({ molecules: [asPred(hit), asPred(stubOnly)] });
    expect(old.properties.lines.every((l) => l.cells.every((c) => c === null))).toBe(true);
  });
  it("is a table of written values only: no number to subtract, no difference, no marker of a higher or lower value", () => {
    for (const row of two.properties.lines) {
      expect(Object.keys(row).sort()).toEqual(["cells", "key", "label", "unit"]);
      for (const c of row.cells) expect(typeof c === "string" || c === null).toBe(true);
    }
    expect(Object.keys(two.properties).sort()).toEqual(["alerts", "lines", "notes", "source"]);
    const words = JSON.stringify(two.properties).toLowerCase();
    for (const w of ["diff", "delta", "winner", "rank", "better", "worse", "higher", "lower", "best"]) expect(words).not.toContain(w);
  });
  it("does not change the roster, its flags or its counts", () => {
    const bare = buildComparison({ molecules: [asPred(hit), asPred(stubOnly)] });
    expect(two.columns).toEqual(bare.columns);
    expect(two.groups).toEqual(bare.groups);
  });
  it("labels the values as RDKit calculations, not predictions", () => {
    expect(two.properties.source).toBe("RDKit");
    expect(two.properties.notes.join(" ")).toContain("not MARS predictions");
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
