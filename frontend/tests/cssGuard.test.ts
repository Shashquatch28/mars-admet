// AGENTS.md: "No raw hex in a component — reference a CSS custom property". ESLint
// does not read .module.css, so without this nothing enforced it (HANDOFF §3.4).
// Colour literals belong in src/styles/tokens.css and nowhere else; a component
// that needs a new colour adds a token first.
//
// Lives in tests/, outside the type-checked src/ tree, because it reads the
// filesystem and the project carries no @types/node. Vitest does not type-check.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(process.cwd(), "src");

function cssModules(dir: string): string[] {
  return readdirSync(dir).flatMap((name: string) => {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) return cssModules(p);
    return name.endsWith(".module.css") ? [p] : [];
  });
}

// hex colours, and rgb()/rgba()/hsl()/hsla() literals
const COLOUR_LITERAL = /#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\(/;

describe("component CSS uses tokens, not colour literals", () => {
  const files = cssModules(SRC);

  it("finds the CSS modules it is meant to guard", () => {
    expect(files.length).toBeGreaterThan(0);
  });

  it.each(files.map((f: string) => [relative(SRC, f).replaceAll("\\", "/"), f]))("%s", (_name, file) => {
    // comments may mention hex; blank them but keep line numbers
    const css = readFileSync(file, "utf8").replace(/\/\*[\s\S]*?\*\//g, (c: string) => c.replace(/[^\n]/g, ""));
    const hits = css
      .split("\n")
      .map((text: string, i: number) => ({ line: i + 1, text: text.trim() }))
      .filter(({ text }: { text: string }) => COLOUR_LITERAL.test(text));
    expect(hits).toEqual([]);
  });
});
