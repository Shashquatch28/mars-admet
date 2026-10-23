// The AGENTS.md "Never do these" list, as far as it can be checked from source (ship checklist D7). The value-colouring,
// stub-hatch and roster rules are also pinned by the domain tests and were audited in a browser; this file covers the
// ones a future change could break without touching a test: props that would let a caller imply a judgement, intervals
// on an invented axis, motion, shadows, rounded corners, gradients, fonts and a light theme.
//
// Lives in tests/ because it reads the filesystem (see cssGuard.test.ts).
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(process.cwd(), "src");
const walk = (dir: string, ext: string): string[] =>
  readdirSync(dir).flatMap((n: string) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? walk(p, ext) : n.endsWith(ext) ? [p] : [];
  });
const rel = (f: string) => relative(SRC, f).replaceAll("\\", "/");
const noComments = (s: string) => s.replace(/\/\*[\s\S]*?\*\//g, (c: string) => c.replace(/[^\n]/g, ""));
const read = (f: string) => readFileSync(f, "utf8");
const cssModules = walk(SRC, ".module.css");
const tokens = noComments(read(join(SRC, "styles", "tokens.css")));

describe("#2: EndpointRow cannot be told how to look", () => {
  it("has no variant, tone, severity, status or highlight prop", () => {
    const src = read(join(SRC, "workspaces", "predict", "EndpointRow.tsx"));
    const props = src.slice(src.indexOf("export interface EndpointRowProps"), src.indexOf("}", src.indexOf("export interface EndpointRowProps")));
    for (const banned of ["variant", "tone", "severity", "status", "highlight"]) {
      expect(props, banned).not.toMatch(new RegExp(`\\b${banned}\\??:`));
    }
  });
});

describe("#3: Compare names no winner", () => {
  it("per_endpoint_winner is declared in the contract mirror and read nowhere else", () => {
    const readers = walk(SRC, ".ts")
      .concat(walk(SRC, ".tsx"))
      .filter((f) => !f.endsWith(".test.ts") && !f.endsWith(".test.tsx") && !rel(f).startsWith("types/"))
      // comments may say it is never read; code may not read it
      .filter((f) => read(f).replace(/\/\/[^\n]*/g, "").replace(/\/\*[\s\S]*?\*\//g, "").includes("per_endpoint_winner"))
      .map(rel);
    expect(readers).toEqual([]);
  });
});

describe("#4: no interval bar on an invented axis", () => {
  it.each(["IntervalTrack", "ADGauge"])("%s requires an explicit domain with no default", (name) => {
    const src = read(join(SRC, "components", "dataviz", `${name}.tsx`));
    expect(src, "domain must be a required prop").toMatch(/\bdomain:\s*readonly\s*\[number,\s*number\]|\bdomain:\s*\[number,\s*number\]|\bdomain:\s*Domain/);
    expect(src, "domain must have no default").not.toMatch(/\bdomain\s*=\s*[\[A-Z]/);
    expect(src).not.toMatch(/\bdomain\?:/);
  });
});

describe("#7: nothing counts, enters, draws itself or shimmers", () => {
  it("the only @keyframes in the app belong to the AD-gauge marker settle (ADR-013)", () => {
    const withKeyframes = cssModules.filter((f) => /@keyframes/.test(noComments(read(f)))).map(rel);
    expect(withKeyframes.filter((f) => !f.startsWith("components/dataviz/"))).toEqual([]);
  });

  it("no animation property outside the dataviz components", () => {
    const offenders: string[] = [];
    for (const f of cssModules.filter((m) => !rel(m).startsWith("components/dataviz/"))) {
      for (const m of noComments(read(f)).matchAll(/(^|[;{\s])animation(-name)?\s*:\s*([^;]+);/g)) {
        if (!/^\s*none\s*$/.test(m[3])) offenders.push(`${rel(f)}: animation: ${m[3].trim()}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("no transition on layout or transform: a workspace or a row never slides in", () => {
    const offenders: string[] = [];
    for (const f of cssModules) {
      for (const m of noComments(read(f)).matchAll(/transition(-property)?\s*:\s*([^;]+);/g)) {
        // the AD-gauge marker settling into place is the one sanctioned crossing (ADR-013)
        const gaugeMarker = rel(f) === "components/dataviz/dataviz.module.css" && /^\s*left\s/.test(m[2]);
        if (!gaugeMarker && /\b(all|transform|height|width|top|left|opacity|max-height|margin|padding)\b/.test(m[2])) offenders.push(`${rel(f)}: ${m[0].trim()}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("there is no skeleton shimmer", () => {
    for (const f of cssModules) expect(noComments(read(f)), rel(f)).not.toMatch(/shimmer|skeleton/i);
  });
});

describe("#9: the visual identity", () => {
  it("radius is at most 3px (a pill or circle, 50% or 999px, is for round marks only)", () => {
    const offenders: string[] = [];
    for (const f of cssModules) {
      for (const m of noComments(read(f)).matchAll(/border-radius\s*:\s*([^;]+);/g)) {
        for (const v of m[1].matchAll(/(-?[\d.]+)px/g)) if (parseFloat(v[1]) > 3 && parseFloat(v[1]) < 999) offenders.push(`${rel(f)}: ${m[0].trim()}`);
        if (/\d+(\.\d+)?(rem|em)/.test(m[1])) offenders.push(`${rel(f)}: ${m[0].trim()}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("a drop shadow appears only on a real overlay (--shadow-overlay); inset highlights are fine", () => {
    const offenders: string[] = [];
    for (const f of cssModules) {
      for (const m of noComments(read(f)).matchAll(/box-shadow\s*:\s*([^;]+);/g)) {
        const v = m[1].trim();
        if (v === "none" || /^var\(--shadow-overlay\)$/.test(v)) continue;
        // every layer must be inset or a token highlight
        const layers = v.split(/,(?![^()]*\))/).map((l) => l.trim());
        if (!layers.every((l) => /^inset\b/.test(l) || /^var\(--highlight-[a-z-]+\)$/.test(l))) offenders.push(`${rel(f)}: ${m[0].trim()}`);
      }
    }
    expect(offenders).toEqual([]);
    expect(noComments(read(join(SRC, "styles", "tokens.css")))).toMatch(/--shadow-overlay:/);
  });

  it("no gradient in a component, except a structural dashed-edge pattern drawn in tokens only (ADR-028)", () => {
    const offenders: string[] = [];
    for (const f of cssModules) {
      for (const m of noComments(read(f)).matchAll(/((?:repeating-)?(?:linear|radial|conic)-gradient)\(([^;]*)\)\s*;/g)) {
        const patternOnly = m[1] === "repeating-linear-gradient" && !/#[0-9a-f]{3,8}|rgba?\(/i.test(m[2]);
        if (!patternOnly) offenders.push(`${rel(f)}: ${m[0].slice(0, 80)}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("the palette and every overlay open instantly: no animation in the shell", () => {
    expect(noComments(read(join(SRC, "shell", "shell.module.css")))).not.toMatch(/@keyframes|animation\s*:/);
  });

  it("no gradient in the tokens is purple or violet", () => {
    for (const m of tokens.matchAll(/(repeating-)?(linear|radial|conic)-gradient\([^;]*\)/g)) {
      for (const c of m[0].matchAll(/rgba?\((\d+),\s*(\d+),\s*(\d+)/g)) {
        const [r, g, b] = [+c[1], +c[2], +c[3]];
        const violet = b > r && b > g && r > g; // blue-dominant with red above green: purple / violet family
        expect(violet, m[0]).toBe(false);
      }
    }
  });

  it("the type is IBM Plex; Inter, Roboto and system-ui are not used", () => {
    const sources = [...cssModules, join(SRC, "styles", "tokens.css"), join(process.cwd(), "index.html")];
    for (const f of sources) {
      const text = noComments(read(f));
      expect(text, f).not.toMatch(/font-family[^;]*\b(Inter|Roboto)\b/i);
      expect(text, f).not.toMatch(/font-family[^;]*system-ui/i);
    }
    expect(tokens).toMatch(/--sans:\s*"IBM Plex Sans"/);
    expect(tokens).toMatch(/--mono:\s*"IBM Plex Mono"/);
  });

  it("dark is the only theme: no light scheme and no prefers-color-scheme rule outside the print report", () => {
    expect(tokens).toMatch(/color-scheme:\s*dark/);
    for (const f of [...cssModules, join(SRC, "styles", "tokens.css")]) {
      expect(noComments(read(f)), rel(f)).not.toMatch(/prefers-color-scheme/);
    }
    // the light treatment exists only as --report-* tokens used inside @media print (ADR-004, ADR-029)
    const reportCss = noComments(read(join(SRC, "components", "report", "report.module.css")));
    expect(reportCss).toMatch(/@media print/);
    for (const f of cssModules.filter((m) => !rel(m).startsWith("components/report/"))) {
      expect(noComments(read(f)), rel(f)).not.toMatch(/var\(--report-/);
    }
  });
});

describe("#1: the structure drawing is not coloured, marked or sized by anything about a molecule (ADR-039)", () => {
  const code = (f: string) => read(join(SRC, f)).replace(/\/\/[^\n]*/g, "").replace(/\/\*[\s\S]*?\*\//g, "");
  it("StructureDepiction takes a SMILES and a token name, and no prop that could carry a value, a highlight or a judgement", () => {
    const src = code("components/StructureDepiction.tsx");
    const props = src.slice(src.indexOf("export function StructureDepiction"), src.indexOf("const q = useDepiction"));
    for (const banned of ["highlight", "atoms", "bonds", "value", "prediction", "endpoint", "state", "tone", "variant", "severity", "status", "score"]) {
      expect(props, banned).not.toMatch(new RegExp(`\b${banned}\??:`));
    }
    expect(props).toMatch(/smiles:/);
  });
  it("the client never writes a colour into the drawing except through the one token-ink replacement", () => {
    const src = code("domain/depiction.ts");
    expect(src.match(/\.replace\(\/#/g)?.length ?? 0).toBe(1); // the one ink, nothing else is rewritten
    expect(src).not.toMatch(/highlight|atomColou?r|bondColou?r/i);
  });
  it("the service-side drawing options mark nothing", () => {
    const py = readFileSync(join(process.cwd(), "..", "ml", "serve", "depiction.py"), "utf8");
    expect(py).toMatch(/useBWAtomPalette\(\)/);
    expect(py).toMatch(/clearBackground = False/);
    expect(py).not.toMatch(/highlightAtoms|highlightBonds|highlightAtomColors|setHighlight|addAtomIndices = True/);
    expect(py).toMatch(/DrawMolecule\(mol\)/); // no highlight arguments
  });
});
