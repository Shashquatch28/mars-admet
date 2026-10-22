// ADR-032: nothing on screen is invented. The app renders what the service returned and nothing else, so the
// sample data that used to back the no-API "design prototype" mode lives only in tests, and no control is a
// stand-in that does nothing. Reads the filesystem, so it lives in tests/ (see cssGuard.test.ts).
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

// Runtime source: everything under src except tests and the test-only folders.
const runtime = walk(SRC).filter((f) => {
  const r = rel(f);
  return (
    /\.(ts|tsx)$/.test(r) &&
    !/\.test\.(ts|tsx)$/.test(r) &&
    !r.startsWith("testSupport/") &&
    !r.includes("real-responses/")
  );
});

describe("no invented data in the app", () => {
  it("runtime code never imports test fixtures or captured responses", () => {
    const offenders = runtime
      .filter((f) => /from\s+["'][^"']*(testSupport|real-responses|\/fixtures)["']/.test(stripComments(read(f))))
      .map(rel);
    expect(offenders).toEqual([]);
  });

  it("no sample molecule, fixture id or prototype wording survives in runtime code", () => {
    const banned = [/celecoxib/i, /aspirin/i, /caffeine/i, /a3f2c81d/, /design prototype/i, /\bisSample\b/, /makeBatchFixture/, /FIXTURE_RESPONSE/];
    const hits: string[] = [];
    for (const f of runtime) {
      const code = stripComments(read(f));
      for (const re of banned) if (re.test(code)) hits.push(`${rel(f)}: ${re}`);
    }
    expect(hits).toEqual([]);
  });

  it("no development note is printed in the interface", () => {
    const shell = read(join(SRC, "shell", "CommandPalette.tsx"));
    expect(shell).not.toMatch(/transform-origin/);
  });
});

describe("no stand-in controls", () => {
  it("every <button> does something: an onClick, a disabled state or a submit type", () => {
    const offenders: string[] = [];
    for (const f of runtime.filter((x) => x.endsWith(".tsx"))) {
      const code = stripComments(read(f));
      for (const m of code.matchAll(/<button\b/g)) {
        // the opening tag ends at the first ">" that is not the arrow in "=>"
        const rest = code.slice(m.index!);
        const end = rest.search(/[^=]>/);
        const tag = rest.slice(0, end + 2);
        if (!/onClick|disabled|type="submit"/.test(tag)) offenders.push(`${rel(f)}: ${tag.replace(/\s+/g, " ").slice(0, 80)}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});
