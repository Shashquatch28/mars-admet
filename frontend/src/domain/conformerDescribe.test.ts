import { describe, expect, it } from "vitest";
import { describeConformer } from "./conformer";
import type { ConformerResponse } from "../types/contracts";

const atom = (element: string) => ({ element, x: 0, y: 0, z: 0, partial_charge: null });
const conformer: ConformerResponse = {
  molecule_id: "m1",
  atoms: [atom("C"), atom("O"), atom("H"), atom("H")],
  bonds: [
    { atom_index_1: 0, atom_index_2: 1, order: 1 },
    { atom_index_1: 0, atom_index_2: 2, order: 1 },
    { atom_index_1: 0, atom_index_2: 3, order: 1 },
  ],
  energy_kcal_mol: 12.34,
  sdf_block: "",
};

describe("describeConformer", () => {
  it("counts heavy atoms, all atoms and bonds from the conformer itself", () => {
    const text = describeConformer(conformer, "hero", false).join(" ");
    expect(text).toContain("2 heavy atoms, 4 atoms counting hydrogens, 3 bonds");
    expect(text).toContain("12.3 kcal/mol");
  });

  it("describes the view that is drawn", () => {
    expect(describeConformer(conformer, "hero", false).join(" ")).toContain("heavy atoms only; hydrogens are hidden");
    expect(describeConformer(conformer, "analysis", false).join(" ")).toContain("every atom including hydrogens");
  });

  it("mentions attribution only when the structure carries it, and never as good or bad", () => {
    expect(describeConformer(conformer, "hero", false).join(" ")).not.toMatch(/attribution|direction/i);
    const withAttr = describeConformer(conformer, "hero", true).join(" ");
    expect(withAttr).toMatch(/direction/);
    expect(withAttr).toMatch(/not whether that is good or bad/);
  });

  it("never says anything about a prediction", () => {
    const text = describeConformer(conformer, "analysis", true).join(" ");
    expect(text).not.toMatch(/\b(safe|toxic|risk|favourable|better|worse)\b/i);
  });
});
