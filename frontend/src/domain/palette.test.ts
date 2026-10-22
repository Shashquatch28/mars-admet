import { describe, expect, it } from "vitest";
import { clipLine, paletteCommands, type PaletteState } from "./palette";

const base: PaletteState = { usingApi: true, smiles: "CCO", endpointsSelected: 14, running: false, hasResult: false };
const byId = (s: PaletteState) => Object.fromEntries(paletteCommands(s).map((c) => [c.id, c.disabledReason]));

describe("paletteCommands", () => {
  it("lists the four real commands in a fixed order", () => {
    expect(paletteCommands(base).map((c) => c.id)).toEqual(["run", "copy_id", "export", "density"]);
  });
  it("Run is available with an API, a SMILES and endpoints", () => {
    expect(byId(base).run).toBeNull();
  });
  it("Run says why it cannot run", () => {
    expect(byId({ ...base, usingApi: false }).run).toBe("no API configured");
    expect(byId({ ...base, running: true }).run).toBe("run in progress");
    expect(byId({ ...base, smiles: "  " }).run).toBe("enter a SMILES in Predict");
    expect(byId({ ...base, endpointsSelected: 0 }).run).toBe("no endpoints selected");
  });
  it("copy and export need a real result", () => {
    expect(byId(base).copy_id).toBe("no result yet");
    expect(byId(base).export).toBe("no result yet");
    expect(byId({ ...base, hasResult: true }).copy_id).toBeNull();
    expect(byId({ ...base, hasResult: true }).export).toBeNull();
  });
  it("density is always available", () => {
    expect(byId({ ...base, usingApi: false }).density).toBeNull();
  });
});

describe("clipLine", () => {
  it("only marks a SMILES as shortened when it was", () => {
    expect(clipLine("CCO")).toBe("CCO");
    expect(clipLine("C".repeat(50))).toBe(`${"C".repeat(44)}…`);
  });
});
