// ADR-046: the landing page has its own front-door type scale, and it stays on the landing page. Everywhere else
// the 26px ceiling holds. Also pins what the landing may and may not do with a molecule: it reads the service for
// its example (nothing is written into the page, ADR-032) and it never decides a row's state itself.
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
const stripTs = (s: string) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/[^\n]*/g, "$1");
const read = (f: string) => readFileSync(f, "utf8");

describe("the front-door type scale stays on the landing page (ADR-046)", () => {
  it("no CSS module outside src/landing sets a font-size above the 26px ceiling", () => {
    const offenders: string[] = [];
    for (const f of walk(SRC, ".module.css").filter((m) => !rel(m).startsWith("landing/"))) {
      for (const m of noComments(read(f)).matchAll(/font-size:\s*([\d.]+)px/g)) {
        if (parseFloat(m[1]) > 26) offenders.push(`${rel(f)}: font-size ${m[1]}px`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("the landing never sizes a predicted value above 26px", () => {
    const css = noComments(read(join(SRC, "landing", "landing.module.css")));
    for (const sel of ["sVal", "sideVal"]) {
      const body = css.match(new RegExp(`\\.${sel}\\s*\\{([^}]*)\\}`))?.[1] ?? "";
      const size = body.match(/font-size:\s*([\d.]+)px/)?.[1];
      expect(size, sel).toBeDefined();
      expect(parseFloat(size as string), sel).toBeLessThanOrEqual(26);
    }
  });
});

describe("the landing page shows only what the service returned", () => {
  const landing = walk(join(SRC, "landing"), ".tsx");
  it("decides no row state: it reads reconcile and the data-viz components, never deriveRowState", () => {
    for (const f of landing) expect(stripTs(read(f)), rel(f)).not.toMatch(/deriveRowState|reliabilityOf/);
  });
  it("writes no predicted value into the page", () => {
    // a numeric literal next to an endpoint key would be an invented value
    for (const f of landing) {
      expect(stripTs(read(f)), rel(f)).not.toMatch(/(solubility_logs|herg_cardiotoxicity|bbb_permeability)[^\n]{0,40}\d\.\d/);
    }
  });
  it("hands off through the Predict session, not a second copy of the input", () => {
    const page = stripTs(read(join(SRC, "landing", "LandingPage.tsx")));
    expect(page).toMatch(/usePredictSession\(\)/);
    expect(page).toMatch(/runWith\(/);
  });
});
