import { describe, expect, it } from "vitest";
import { conformerFacts, conformerMethodNote, viewNotes } from "./conformer";
import type { ConformerResponse } from "../types/contracts";

const atom = (element: string, x = 0, y = 0, z = 0) => ({ element, x, y, z, partial_charge: null });
const bond = (a: number, b: number, order = 1) => ({ atom_index_1: a, atom_index_2: b, order });

// methanol-ish: C, O and three H, one single bond between the heavy atoms
const methanol: ConformerResponse = {
  molecule_id: "m1",
  atoms: [atom("C"), atom("O", 1.4, 0, 0), atom("H", 0, 1, 0), atom("H", 0, 0, 1), atom("H", -1, 0, 0), atom("H", 1.8, 0.9, 0)],
  bonds: [bond(0, 1), bond(0, 2), bond(0, 3), bond(0, 4), bond(1, 5)],
  energy_kcal_mol: 12.34,
  sdf_block: "",
};

// benzene ring of six carbons (aromatic bonds) with six hydrogens
const benzene: ConformerResponse = {
  molecule_id: "b",
  atoms: [...Array.from({ length: 6 }, (_, i) => atom("C", Math.cos((i * Math.PI) / 3) * 1.4, Math.sin((i * Math.PI) / 3) * 1.4, 0)), ...Array.from({ length: 6 }, () => atom("H"))],
  bonds: [...Array.from({ length: 6 }, (_, i) => bond(i, (i + 1) % 6, 1.5)), ...Array.from({ length: 6 }, (_, i) => bond(i, 6 + i))],
  energy_kcal_mol: 1,
  sdf_block: "",
};

describe("conformerFacts", () => {
  it("counts atoms, bonds and the Hill formula from the conformer itself", () => {
    const f = conformerFacts(methanol);
    expect(f.heavyAtoms).toBe(2);
    expect(f.atoms).toBe(6);
    expect(f.bonds).toBe(5);
    expect(f.formula).toBe("CH4O");
    expect(f.elements).toEqual([
      { element: "C", count: 1 },
      { element: "H", count: 4 },
      { element: "O", count: 1 },
    ]);
  });

  it("finds no ring in a chain and one ring in benzene, and counts aromatic bonds", () => {
    expect(conformerFacts(methanol).rings).toBe(0);
    const b = conformerFacts(benzene);
    expect(b.rings).toBe(1);
    expect(b.aromaticBonds).toBe(6);
    expect(b.formula).toBe("C6H6");
    expect(b.bondTypes).toEqual([
      { label: "single", count: 6 },
      { label: "aromatic", count: 6 },
    ]);
  });

  it("writes a formula with no carbon alphabetically", () => {
    const water: ConformerResponse = { molecule_id: "w", atoms: [atom("O"), atom("H"), atom("H")], bonds: [bond(0, 1), bond(0, 2)], energy_kcal_mol: 0, sdf_block: "" };
    expect(conformerFacts(water).formula).toBe("H2O");
  });

  it("measures the longest heavy-atom distance, and has none for a single heavy atom", () => {
    expect(conformerFacts(methanol).longestDistance).toBeCloseTo(1.4, 5);
    const one: ConformerResponse = { molecule_id: "x", atoms: [atom("C"), atom("H")], bonds: [bond(0, 1)], energy_kcal_mol: 0, sdf_block: "" };
    expect(conformerFacts(one).longestDistance).toBeNull();
  });
});

describe("the notes", () => {
  it("state the method and the conformer's own energy", () => {
    const t = conformerMethodNote(methanol);
    expect(t).toContain("ETKDG");
    expect(t).toContain("12.3 kcal/mol");
  });

  it("describe the view that is drawn", () => {
    expect(viewNotes("hero", false).join(" ")).toContain("heavy atoms only; hydrogens are hidden");
    expect(viewNotes("analysis", false).join(" ")).toContain("every atom including hydrogens");
  });

  it("mention attribution only when the structure carries it, and never as good or bad", () => {
    expect(viewNotes("hero", false).join(" ")).not.toMatch(/attribution|direction/i);
    const withAttr = viewNotes("hero", true).join(" ");
    expect(withAttr).toMatch(/direction/);
    expect(withAttr).toMatch(/not whether that is good or bad/);
  });

  it("never say anything about a prediction's quality", () => {
    const text = [conformerMethodNote(methanol), ...viewNotes("analysis", true)].join(" ");
    expect(text).not.toMatch(/\b(safe|toxic|risk|favourable|better|worse)\b/i);
  });
});
