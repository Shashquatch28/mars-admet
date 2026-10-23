// What the structure editor may do with the two things it connects: the SMILES text the user typed and
// the SMILES Ketcher derives from the canvas (ADR-035). Pure functions, so the rules that keep a typed
// value safe are tested without a browser or a WebAssembly build.
//
// The rule that outranks the rest: a drawing that is empty, or that cannot be turned into one SMILES,
// never overwrites what the user typed, and the panel says so in text.

export type Drawn =
  | { kind: "smiles"; smiles: string }
  | { kind: "empty" }
  | { kind: "unusable"; reason: string };

/** Interpret the string Ketcher returned for the canvas. Anything but one molecule's SMILES is refused. */
export function interpretDrawn(raw: string): Drawn {
  const smiles = raw.trim();
  if (smiles === "") return { kind: "empty" };
  // ">" only occurs in reaction SMILES ("reactants>agents>products"). MARS predicts one molecule at a time.
  if (smiles.includes(">")) {
    return { kind: "unusable", reason: "it contains a reaction arrow, and MARS predicts one molecule at a time." };
  }
  return { kind: "smiles", smiles };
}

/** A conversion error from the editor, reduced to a sentence that can follow "because". */
export function conversionReason(error: unknown): string {
  const text = error instanceof Error ? error.message : typeof error === "string" ? error : "";
  const first = text.split("\n")[0].trim().replace(/[.\s]+$/, "");
  return first ? `the editor reported: ${first}.` : "the editor could not convert it.";
}

/**
 * A mistake in typed SMILES that is certain, whatever the toolkit: an unbalanced parenthesis or bracket, or a ring
 * bond opened and never closed. Indigo, which draws the canvas, is lenient and silently drops what it cannot read
 * ("C(((" is drawn as methane), so the panel must not call such a canvas a match for the field. Everything else is
 * left to the server's standardiser, which runs on Run and rejects with its own message. Null means no certain fault.
 */
export function obviousSmilesFault(smiles: string): string | null {
  let depth = 0;
  let inBracket = false;
  const open = new Set<string>();
  const s = smiles.trim();
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (inBracket) {
      if (c === "]") inBracket = false;
      else if (c === "[") return "it has a [ inside a bracket atom.";
      continue;
    }
    if (c === "[") inBracket = true;
    else if (c === "]") return "it has a ] with no matching [.";
    else if (c === "(") depth++;
    else if (c === ")") {
      if (--depth < 0) return "it has a ) with no matching (.";
    } else if (/[0-9]/.test(c) || c === "%") {
      let label = c;
      if (c === "%") {
        label = s.slice(i, i + 3);
        i += 2;
        if (!/^%\d\d$/.test(label)) return "it has a % that is not followed by two digits.";
      }
      if (open.has(label)) open.delete(label);
      else open.add(label);
    }
  }
  if (inBracket) return "it has a [ that is never closed.";
  if (depth > 0) return "it has a ( that is never closed.";
  if (open.size > 0) return "it opens a ring bond that is never closed.";
  return null;
}

/**
 * Should text that changed in the SMILES field be loaded onto the canvas? Not when it is empty (the canvas
 * keeps the drawing), and not when it is the value the editor itself just wrote there (loading it back would
 * make Indigo redraw, and possibly re-write, the user's own drawing).
 */
export function shouldLoadTyped(typed: string, lastWrittenByEditor: string | null): boolean {
  const t = typed.trim();
  if (t === "") return false;
  return t !== (lastWrittenByEditor ?? "").trim();
}

/** The panel's status line. Always text, never colour alone, and always says what happened to the SMILES field. */
export type EditorStatus =
  | { kind: "idle" }
  | { kind: "written" }
  | { kind: "drawn" }
  | { kind: "empty" }
  | { kind: "unusable"; reason: string }
  | { kind: "undrawable"; reason: string }
  | { kind: "reported"; message: string };

export function statusText(s: EditorStatus): string {
  switch (s.kind) {
    case "idle":
      return "Draw a molecule, or type a SMILES in the field on the left. Each edit updates the other; press Run prediction when you are ready.";
    case "written":
      return "The SMILES field now matches the drawing.";
    case "drawn":
      return "The canvas shows the SMILES in the field. Run prediction checks that SMILES again on the server.";
    case "empty":
      return "The canvas is empty, so there is no SMILES to write. The SMILES field was left as it was.";
    case "unusable":
      return `This drawing cannot be turned into a SMILES: ${s.reason} The SMILES field was left as it was.`;
    case "undrawable":
      return `The SMILES in the field cannot be drawn: ${s.reason} The canvas was left as it was.`;
    case "reported":
      return `The editor reported: ${s.message}`;
  }
}

/** Does this status describe something the user needs to act on (shown with the alert treatment)? */
export function statusIsProblem(s: EditorStatus): boolean {
  return s.kind === "unusable" || s.kind === "undrawable" || s.kind === "reported";
}

/** The editor runs Indigo as WebAssembly (ADR-027). Without it the panel says so and the textarea still works. */
export function webAssemblyAvailable(host: { WebAssembly?: unknown } = globalThis as { WebAssembly?: unknown }): boolean {
  return typeof host.WebAssembly === "object" && host.WebAssembly !== null;
}
