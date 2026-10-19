// Accessibility properties that a review would otherwise have to remember (ship checklist D6, ACCESSIBILITY.md).
// Static checks over tokens.css, the CSS modules and the TSX sources, in the same spirit as cssGuard.test.ts. They do not
// replace a screen reader or the in-browser audit recorded in HANDOFF; they stop the measured properties regressing.
//
// Lives in tests/, outside the type-checked src/ tree, because it reads the filesystem.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(process.cwd(), "src");

function walk(dir: string, ext: string): string[] {
  return readdirSync(dir).flatMap((name: string) => {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) return walk(p, ext);
    return name.endsWith(ext) ? [p] : [];
  });
}
const rel = (f: string) => relative(SRC, f).replaceAll("\\", "/");
const stripComments = (css: string) => css.replace(/\/\*[\s\S]*?\*\//g, (c: string) => c.replace(/[^\n]/g, ""));

// --- colour contrast, computed from tokens.css (WCAG 1.4.3, 1.4.11) ---------------------------------------------
const tokensCss = readFileSync(join(SRC, "styles", "tokens.css"), "utf8");
const token = (name: string): string => {
  const m = tokensCss.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})\\b`));
  if (!m) throw new Error(`token --${name} not found as a hex colour`);
  return m[1];
};
type RGB = [number, number, number];
const rgb = (hex: string): RGB => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)) as RGB;
const lum = ([r, g, b]: RGB) => {
  const f = (v: number) => {
    const x = v / 255;
    return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
};
const ratio = (a: RGB, b: RGB) => {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};
const over = (c: RGB, alpha: number, bg: RGB): RGB => c.map((v, i) => Math.round(v * alpha + bg[i] * (1 - alpha))) as RGB;

const SURFACES: Record<string, RGB> = {
  void: rgb(token("surface-void")),
  chrome: rgb(token("surface-chrome")),
  panel: rgb(token("surface-panel")),
  raised: rgb(token("surface-raised")),
  overlay: rgb(token("surface-overlay")),
  "accent wash": over(rgb(token("accent")), 0.14, rgb(token("surface-panel"))),
  "caution wash": over(rgb(token("caution")), 0.1, rgb(token("surface-panel"))),
};

describe("text tokens meet WCAG AA (4.5:1) on every surface they can sit on", () => {
  const textTokens = ["text-primary", "text-secondary", "text-tertiary", "text-quiet", "accent", "caution", "error", "success"];
  it.each(textTokens)("--%s", (name) => {
    for (const [surface, bg] of Object.entries(SURFACES)) {
      expect(ratio(rgb(token(name)), bg), `--${name} on ${surface}`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("--text-disabled is below AA by design, so it is only ever used on disabled controls", () => {
    // 'Disabled' text is exempt from the contrast rule; anything else that is readable must not use it.
    const offenders: string[] = [];
    for (const file of walk(SRC, ".module.css")) {
      const css = stripComments(readFileSync(file, "utf8"));
      for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
        const [, selector, body] = m;
        if (!body.includes("var(--text-disabled)")) continue;
        if (!/:disabled|\[disabled\]|aria-disabled/.test(selector)) offenders.push(`${rel(file)}: ${selector.trim().replace(/\s+/g, " ")}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("the report's ink clears AA on its paper", () => {
    expect(ratio(rgb(token("report-ink")), rgb(token("report-paper")))).toBeGreaterThanOrEqual(7);
    expect(ratio(rgb(token("report-ink-muted")), rgb(token("report-paper")))).toBeGreaterThanOrEqual(4.5);
  });
});

// --- type size floor: 9px (ACCESSIBILITY.md) --------------------------------------------------------------------
describe("no screen text is below the 9px floor", () => {
  it("font sizes in the CSS modules", () => {
    const hits: string[] = [];
    for (const file of walk(SRC, ".module.css")) {
      const css = stripComments(readFileSync(file, "utf8"));
      // Print rules are in pt and live in the report; the floor is about screen px.
      for (const m of css.matchAll(/font-size:\s*([\d.]+)px/g)) {
        if (parseFloat(m[1]) < 9) hits.push(`${rel(file)}: font-size ${m[1]}px`);
      }
    }
    expect(hits).toEqual([]);
  });
});

// --- semantics that are easy to lose in a refactor ---------------------------------------------------------------
describe("markup guards", () => {
  const tsx = walk(SRC, ".tsx").filter((f) => !f.endsWith(".test.tsx"));

  it("an icon-only button has an accessible name", () => {
    const offenders: string[] = [];
    for (const file of tsx) {
      const src = readFileSync(file, "utf8");
      // a button whose whole content is one <svg>: there is no text to name it
      for (const m of src.matchAll(/<button\b([^>]*)>\s*<svg\b[\s\S]*?<\/svg>\s*<\/button>/g)) {
        if (!/aria-label|aria-labelledby/.test(m[1])) offenders.push(`${rel(file)}: ${m[0].slice(0, 60)}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("a clickable element that is not a native control has a role", () => {
    const offenders: string[] = [];
    for (const file of tsx) {
      const src = readFileSync(file, "utf8");
      for (const m of src.matchAll(/<(div|span|li|td|tr|p)\b([^>]*\bonClick\b[^>]*)>/g)) {
        if (!/\brole=/.test(m[2])) offenders.push(`${rel(file)}: <${m[1]} ... onClick`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("the shell provides a skip link, a <main> landmark and a page heading", () => {
    const shell = readFileSync(join(SRC, "shell", "AppShell.tsx"), "utf8");
    expect(shell).toMatch(/href="#main"/);
    expect(shell).toMatch(/<main\b[^>]*id="main"/);
    expect(readFileSync(join(SRC, "shell", "TopBar.tsx"), "utf8")).toMatch(/<h1\b/);
  });

  it("there is exactly one polite live region and it is the announcer", () => {
    const live: string[] = [];
    for (const file of tsx) {
      const src = readFileSync(file, "utf8");
      if (/aria-live=/.test(src) || /role="status"/.test(src)) live.push(rel(file));
    }
    // SaveControl's one-shot "Saved" confirmation is a status; everything else routes through the announcer.
    expect(live.sort()).toEqual(["app/announce.tsx", "components/SaveControl.tsx"]);
  });

  it("every control is at least 24 px tall (WCAG 2.5.8): the base button rule says so", () => {
    expect(tokensCss).toMatch(/button\s*\{[^}]*min-height:\s*24px/);
  });
});
