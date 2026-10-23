// The 2D drawing (ADR-039): plain line art in one token ink, nothing marked, and a report that says what it does and
// does not contain.
import { describe, expect, it } from "vitest";
import {
  DEPICTION_NOTE,
  STRUCTURE_STATEMENT,
  depictionFailure,
  inkSvg,
  isDrawable,
  isInk,
  svgDataUrl,
  structureMissingStatement,
} from "./depiction";
import { REPORT_STATEMENTS, buildReport } from "./report";
import { reconcile } from "./reconcile";
import { ML_ENDPOINTS } from "./endpoints";
import type { PredictionResponse } from "../types/contracts";
import miss from "./real-responses/celecoxib-miss.json";

const SVG = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 320 220'><path d='M 0 0 L 1 1' style='fill:none;stroke:#000000' /><path fill='#000000' d='M 2 2'/></svg>";
const NOW = new Date("2026-10-23T10:00:00Z");
const molecule = () => {
  const response = miss as unknown as PredictionResponse;
  return { smilesInput: "x", response, cells: reconcile(response, ML_ENDPOINTS).rows };
};

describe("inkSvg", () => {
  it("puts the one ink in the token's colour and changes nothing else", () => {
    const out = inkSvg(SVG, "rgb(168, 178, 181)");
    expect(out).not.toContain("#000000");
    expect(out.match(/rgb\(168, 178, 181\)/g)).toHaveLength(2);
    expect(out.replace(/rgb\(168, 178, 181\)/g, "#000000")).toBe(SVG);
  });
  it("accepts hex and rgb colours only, so a custom property cannot write markup into the drawing", () => {
    expect(isInk("#15191b")).toBe(true);
    expect(isInk("rgb(21, 25, 27)")).toBe(true);
    for (const bad of ["", "red", "url(#x)", "'/><script>", "#zzz", "rgb(1,2)"]) expect(isInk(bad)).toBe(false);
    expect(inkSvg(SVG, "'/><script>alert(1)</script>")).toBe(SVG);
    expect(inkSvg(SVG, "")).toBe(SVG);
  });
  it("is the same ink for every molecule: the colour is an argument, never read from a value", () => {
    expect(inkSvg(SVG, "#a8b2b5")).toBe(inkSvg(SVG, "#A8B2B5").replace(/#A8B2B5/g, "#a8b2b5"));
  });
});

describe("isDrawable", () => {
  it("takes an svg and refuses anything with active or foreign content", () => {
    expect(isDrawable(SVG)).toBe(true);
    expect(isDrawable(`  ${SVG}`)).toBe(true);
    expect(isDrawable("<html></html>")).toBe(false);
    expect(isDrawable("<svg><script>1</script></svg>")).toBe(false);
    expect(isDrawable("<svg><foreignObject/></svg>")).toBe(false);
    expect(isDrawable("<svg onload='x()'></svg>")).toBe(false);
    expect(isDrawable("")).toBe(false);
  });
});

describe("svgDataUrl", () => {
  it("is an image data URL that survives a quote or a hash in the markup", () => {
    const u = svgDataUrl(SVG);
    expect(u.startsWith("data:image/svg+xml;charset=utf-8,")).toBe(true);
    expect(decodeURIComponent(u.split(",").slice(1).join(","))).toBe(SVG);
    expect(u).not.toContain("#");
  });
});

describe("depictionFailure", () => {
  it("says in words why nothing was drawn, and never about the molecule's values", () => {
    expect(depictionFailure(501, "x")).toMatch(/no RDKit/);
    expect(depictionFailure(422, "could not parse the SMILES")).toBe("This structure could not be drawn: could not parse the SMILES.");
    expect(depictionFailure(429, "x")).toMatch(/Too many/);
    expect(depictionFailure(0, "x")).toMatch(/unreachable/);
    expect(depictionFailure(500, "x")).toContain("500");
    const all = [501, 422, 429, 0, 500].map((s) => depictionFailure(s, "m")).join(" ").toLowerCase();
    expect(all).not.toMatch(/good|safe|better|rank|risk/);
  });
});

describe("the caption and the report's statements", () => {
  it("say what a drawing is: plain, nothing marked, nothing about a prediction", () => {
    for (const t of [DEPICTION_NOTE, STRUCTURE_STATEMENT]) {
      expect(t).toMatch(/plain line art/i);
      expect(t).toMatch(/no atom or bond is marked/i);
      expect(t).toMatch(/nothing about any/);
    }
  });
  it("no longer says a 2D drawing is never included: that line is gone from the fixed statements", () => {
    expect(REPORT_STATEMENTS.join(" ")).not.toMatch(/2D structure drawing/);
  });
  it("prints the drawing statement only when a drawing is on the page", () => {
    const drawn = buildReport(molecule(), NOW, [], { kind: "drawn", svg: SVG });
    expect(drawn.structure).toEqual({ kind: "drawn", svg: SVG });
    expect(drawn.statements).toContain(STRUCTURE_STATEMENT);
    const none = buildReport(molecule(), NOW);
    expect(none.structure).toBeNull();
    expect(none.statements).toEqual([...REPORT_STATEMENTS]);
  });
  it("says what is missing and why when the service could not draw it, instead of leaving a gap", () => {
    const r = buildReport(molecule(), NOW, [], { kind: "unavailable", reason: "The service has no RDKit, so it cannot draw structures." });
    expect(r.statements).toContain(structureMissingStatement("The service has no RDKit, so it cannot draw structures."));
    expect(r.statements.join(" ")).toMatch(/Not included: a 2D structure drawing\. The service has no RDKit/);
    expect(r.statements).not.toContain(STRUCTURE_STATEMENT);
  });
  it("gives a row that failed before inference no structure and no statement about one", () => {
    const failed = buildReport({ smilesInput: "bad", response: null, cells: [], error: "could not parse" }, NOW, [], { kind: "drawn", svg: SVG });
    expect(failed.structure).toBeNull();
    expect(failed.statements).toEqual([...REPORT_STATEMENTS]);
  });
  it("changes no row, count or value of the report", () => {
    const base = buildReport(molecule(), NOW);
    const withDrawing = buildReport(molecule(), NOW, [], { kind: "drawn", svg: SVG });
    expect(withDrawing.groups).toEqual(base.groups);
    expect(withDrawing.counts).toEqual(base.counts);
  });
});
