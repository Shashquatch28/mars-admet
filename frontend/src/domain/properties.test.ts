import { describe, expect, it } from "vitest";
import { PROPERTY_NOTES, PROPERTY_SOURCE, alertGroups, propertyLines } from "./properties";
import type { MoleculeProperties } from "../types/contracts";

const P: MoleculeProperties = {
  mol_weight: 381.3714,
  crippen_logp: -0.5,
  h_bond_donors: 1,
  h_bond_acceptors: 3,
  tpsa: 77.98,
  rotatable_bonds: 3,
  qed: 0.7541,
  lipinski_criteria_exceeded: 0,
  alerts: [
    { catalog: "Brenk", name: "nitro group" },
    { catalog: "PAINS", name: "ene_rhod_A(235)" },
    { catalog: "Brenk", name: "Aliphatic long chain" },
  ],
};

describe("propertyLines", () => {
  it("lists the properties in a fixed order with the screen's number format", () => {
    const lines = propertyLines(P);
    expect(lines.map((l) => l.key)).toEqual([
      "mol_weight",
      "crippen_logp",
      "h_bond_donors",
      "h_bond_acceptors",
      "tpsa",
      "rotatable_bonds",
      "qed",
      "lipinski",
    ]);
    const v = Object.fromEntries(lines.map((l) => [l.key, `${l.value}${l.unit ? ` ${l.unit}` : ""}`]));
    expect(v.mol_weight).toBe("381.37 g/mol");
    expect(v.crippen_logp).toBe("−0.50"); // a true minus, like every other number on screen
    expect(v.tpsa).toBe("78.0 Å²");
    expect(v.qed).toBe("0.75");
    expect(v.lipinski).toBe("0 of 4");
  });
  it("says 'not computed' for a QED RDKit could not produce, never a number", () => {
    expect(propertyLines({ ...P, qed: null }).find((l) => l.key === "qed")!.value).toBe("not computed");
    expect(propertyLines({ ...P, qed: undefined }).find((l) => l.key === "qed")!.value).toBe("not computed");
  });
  it("carries no state, tone or colour: only a key, a label, a value and a unit", () => {
    for (const l of propertyLines(P)) expect(Object.keys(l).sort()).toEqual(["key", "label", "unit", "value"]);
  });
});

describe("alertGroups", () => {
  it("groups by catalog, PAINS first, names sorted, and lists a catalog with no match as empty", () => {
    expect(alertGroups(P)).toEqual([
      { catalog: "PAINS", names: ["ene_rhod_A(235)"] },
      { catalog: "Brenk", names: ["Aliphatic long chain", "nitro group"] },
    ]);
    expect(alertGroups({ ...P, alerts: [] })).toEqual([
      { catalog: "PAINS", names: [] },
      { catalog: "Brenk", names: [] },
    ]);
  });
});

describe("PROPERTY_NOTES", () => {
  const text = PROPERTY_NOTES.join(" ").toLowerCase();
  it("names the source and what these values are not", () => {
    expect(PROPERTY_SOURCE).toBe("RDKit");
    expect(text).toContain("not marS predictions".toLowerCase());
    expect(text).toContain("not a prediction");
    expect(text).toContain("not toxicity");
  });
  it("uses no ranking, grading or favourability wording", () => {
    for (const word of ["good", "safe", "favourable", "favorable", "better", "pass", "fail", "acceptable", "violation", "winner", "rank"]) {
      expect(text).not.toContain(word);
    }
  });
});
