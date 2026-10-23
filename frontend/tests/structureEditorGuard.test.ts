// ADR-035: the structure editor is third-party code that is heavy and has its own theme. Three properties are easy to
// lose in a refactor and are checked here as text, in the same spirit as cssGuard.test.ts:
//   1. Ketcher is reachable only through a dynamic import(), so it never enters the main bundle;
//   2. MARS's own chrome around it (structureEditor.module.css) uses tokens, no animation, radius within 3px;
//   3. the contract and the route are untouched: the editor reads and writes the SMILES string only.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(process.cwd(), "src");
const walk = (dir: string): string[] =>
  readdirSync(dir).flatMap((n: string) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
const rel = (f: string) => relative(SRC, f).replaceAll("\\", "/");
const read = (f: string) => readFileSync(f, "utf8");
const stripComments = (s: string) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/[^\n]*/g, "$1");
// vite-env.d.ts holds a type-only module declaration for Ketcher's subpath, which is not an import.
const sources = walk(SRC).filter((f) => /\.(ts|tsx)$/.test(f) && !/\.(test|d)\.(ts|tsx)$/.test(f));

const CANVAS = "workspaces/predict/KetcherCanvas.tsx";
const PANEL = "workspaces/predict/StructureEditor.tsx";

describe("Ketcher stays out of the main bundle", () => {
  it("only KetcherCanvas imports a ketcher package, and only as a value there", () => {
    const importers = sources
      .filter((f) => /from\s+["']ketcher-(react|standalone|core)/.test(stripComments(read(f))))
      .map(rel)
      .sort();
    // StructureEditor takes a type from ketcher-core; a type import is erased and pulls no code.
    expect(importers).toEqual([CANVAS, PANEL].sort());
    const panelImports = [...stripComments(read(join(SRC, PANEL))).matchAll(/^import\s+(type\s+)?[^;]*from\s+["']ketcher-[^"']+["']/gm)];
    expect(panelImports.length).toBeGreaterThan(0);
    for (const m of panelImports) expect(m[1], `${m[0]} must be import type`).toBe("type ");
  });

  it("the canvas is loaded with React.lazy and a dynamic import, never a static one", () => {
    const panel = stripComments(read(join(SRC, PANEL)));
    expect(panel).toMatch(/lazy\(\(\)\s*=>\s*import\(["']\.\/KetcherCanvas["']\)\)/);
    expect(panel).not.toMatch(/from\s+["']\.\/KetcherCanvas["']/);
    for (const f of sources.filter((x) => rel(x) !== PANEL)) {
      expect(stripComments(read(f)), rel(f)).not.toMatch(/from\s+["'][^"']*KetcherCanvas["']/);
    }
  });

  it("Ketcher's stylesheet is imported by the lazy module only", () => {
    const withCss = sources.filter((f) => /ketcher-react\/dist\/index\.css/.test(read(f))).map(rel);
    expect(withCss).toEqual([CANVAS]);
  });
});

describe("MARS's chrome around the editor follows the design rules", () => {
  const css = stripComments(read(join(SRC, "workspaces/predict/structureEditor.module.css")));

  it("does not animate or transition", () => {
    expect(css).not.toMatch(/\b(transition|animation)\b/);
  });
  it("keeps every radius within the token scale (<= 3px)", () => {
    for (const m of css.matchAll(/border-radius:\s*([^;]+);/g)) expect(m[1].trim()).toMatch(/^var\(--radius(-sm)?\)$/);
  });
  it("uses no shadow (it is not an overlay: it sits inside <main>)", () => {
    expect(css).not.toMatch(/box-shadow/);
  });
});

describe("the editor does not touch the prediction contract", () => {
  it("talks to the session's SMILES string and nothing from the API layer", () => {
    for (const f of [PANEL, CANVAS]) {
      const code = stripComments(read(join(SRC, f)));
      expect(code, f).not.toMatch(/data\/client|fetchPrediction|types\/contracts/);
    }
    expect(stripComments(read(join(SRC, PANEL)))).toMatch(/setSmiles/);
  });
});
