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
  it("says why Predict did not run under the bar that was used, and through the app's one live region", () => {
    const page = stripTs(read(join(SRC, "landing", "LandingPage.tsx")));
    // each bar renders its own note and describes the input with it
    expect(page.match(/<InputBar\b/g)?.length).toBe(2);
    expect(page.match(/\bnote=\{noteFor\(/g)?.length).toBe(2);
    expect(page).toMatch(/aria-describedby=\{`\$\{id\}-note`\}/);
    // a message is announced, not given a live region of its own (a11yGuard.test.ts allows exactly one)
    expect(page).toMatch(/useAnnounce\(\)/);
    expect(page).toMatch(/announce\(text\)/);
    expect(page).not.toMatch(/aria-live=|role="status"/);
  });
  it("shows the account state from the session the app uses, never a placeholder identity", () => {
    const page = stripTs(read(join(SRC, "landing", "LandingPage.tsx")));
    expect(page).toMatch(/useAuthSession\(\)/);
    expect(page).toMatch(/landingAccount\(/);
    expect(page).toMatch(/Account: \$\{user\.email\}/); // the address is the button's accessible name
    expect(page).toMatch(/workspaceAccess\(/);
  });
  it("hands off through the Predict session, not a second copy of the input", () => {
    const page = stripTs(read(join(SRC, "landing", "LandingPage.tsx")));
    expect(page).toMatch(/usePredictSession\(\)/);
    expect(page).toMatch(/runWith\(/);
  });
});
