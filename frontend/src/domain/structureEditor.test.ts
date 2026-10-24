import { describe, expect, it } from "vitest";
import {
  conversionReason,
  interpretDrawn,
  obviousSmilesFault,
  shouldLoadTyped,
  statusIsProblem,
  statusText,
  webAssemblyAvailable,
  type EditorStatus,
} from "./structureEditor";

// Aspirin, in the two forms the editor and a person produce for the same molecule.
const TYPED = "CC(=O)Oc1ccccc1C(=O)O";
const INDIGO = "CC(=O)OC1C=CC=CC=1C(=O)O";

describe("interpretDrawn", () => {
  it("accepts one molecule's SMILES, trimmed", () => {
    expect(interpretDrawn(`  ${INDIGO}\n`)).toEqual({ kind: "smiles", smiles: INDIGO });
  });
  it("accepts several fragments (a salt or a mixture is one SMILES with dots)", () => {
    expect(interpretDrawn("CC(=O)[O-].[Na+]")).toEqual({ kind: "smiles", smiles: "CC(=O)[O-].[Na+]" });
  });
  it("calls an empty canvas empty, never a molecule", () => {
    expect(interpretDrawn("")).toEqual({ kind: "empty" });
    expect(interpretDrawn("  \n")).toEqual({ kind: "empty" });
  });
  it("refuses a reaction, with the reason in words", () => {
    const d = interpretDrawn("CC(=O)O.OCC>>CC(=O)OCC");
    expect(d.kind).toBe("unusable");
    if (d.kind === "unusable") expect(d.reason).toMatch(/reaction arrow/);
  });
});

describe("conversionReason", () => {
  it("keeps the first line of the editor's message, without trailing punctuation", () => {
    expect(conversionReason(new Error("Convert error!\nstack..."))).toBe("the editor reported: Convert error!.");
    expect(conversionReason("Bad structure.")).toBe("the editor reported: Bad structure.");
  });
  it("still says something when the editor said nothing", () => {
    expect(conversionReason(new Error(""))).toBe("the editor could not convert it.");
    expect(conversionReason(undefined)).toBe("the editor could not convert it.");
  });
});

describe("shouldLoadTyped: what the user typed is never redrawn over a drawing for no reason", () => {
  it("does not load an empty or blank field (the drawing is kept)", () => {
    expect(shouldLoadTyped("", null)).toBe(false);
    expect(shouldLoadTyped("   ", "CCO")).toBe(false);
  });
  it("loads text the editor did not write", () => {
    expect(shouldLoadTyped(TYPED, null)).toBe(true);
    expect(shouldLoadTyped("CCN", "CCO")).toBe(true);
  });
  it("does not load the value the editor itself wrote or last loaded", () => {
    expect(shouldLoadTyped(INDIGO, INDIGO)).toBe(false);
    expect(shouldLoadTyped(`${TYPED}\n`, TYPED)).toBe(false);
  });
});

describe("obviousSmilesFault: only mistakes that are certain", () => {
  it.each([
    TYPED,
    "c1ccccc1",
    "C1CC1C1CC1", // a ring label reused after it closed
    "C%12CCCCC%12",
    "[NH4+].[Cl-]",
    "[13CH4]",
    "CC(C)(C)c1ccc(O)cc1",
    "C[C@@H](N)C(=O)O",
    "",
  ])("finds nothing wrong with %s", (s) => expect(obviousSmilesFault(s)).toBeNull());

  it.each([
    ["C(((", /never closed/],
    ["CC(=O", /never closed/],
    ["CC)C", /no matching \(/],
    ["C1CC", /ring bond that is never closed/],
    ["C%1CC", /two digits/],
    ["[NH4+", /\[ that is never closed/],
    ["C]C", /no matching \[/],
    ["[C[C]]", /inside a bracket/],
  ])("names the mistake in %s", (s, reason) => expect(obviousSmilesFault(s)).toMatch(reason));

  it("does not count digits inside a bracket atom as ring bonds", () => {
    expect(obviousSmilesFault("[13CH3]C")).toBeNull();
    expect(obviousSmilesFault("[2H]C([2H])([2H])C")).toBeNull();
  });
});

describe("statusText: every state says, in words, what happened to the SMILES field", () => {
  const states: EditorStatus[] = [
    { kind: "idle" },
    { kind: "written" },
    { kind: "drawn" },
    { kind: "empty" },
    { kind: "unusable", reason: "it contains a reaction arrow." },
    { kind: "undrawable", reason: "it has a ( that is never closed." },
    { kind: "reported", message: "Something broke" },
  ];
  it.each(states)("$kind", (s) => {
    expect(statusText(s).length).toBeGreaterThan(20);
  });
  it("the two refusals say the typed text was kept", () => {
    expect(statusText({ kind: "empty" })).toMatch(/SMILES field was left as it was/);
    expect(statusText({ kind: "unusable", reason: "x." })).toMatch(/SMILES field was left as it was/);
    expect(statusText({ kind: "undrawable", reason: "x." })).toMatch(/canvas was left as it was/);
  });
  it("flags exactly the states that need attention, and not the empty canvas", () => {
    expect(states.filter(statusIsProblem).map((s) => s.kind)).toEqual(["unusable", "undrawable", "reported"]);
  });
  it("claims no match for a field that was only loaded onto the canvas", () => {
    expect(statusText({ kind: "drawn" })).not.toMatch(/matches/);
  });
});

describe("webAssemblyAvailable", () => {
  it("is true where WebAssembly exists and false where it does not", () => {
    expect(webAssemblyAvailable({ WebAssembly: {} })).toBe(true);
    expect(webAssemblyAvailable({})).toBe(false);
    expect(webAssemblyAvailable({ WebAssembly: null })).toBe(false);
  });
});
