// What the structure panel should show, decided in one pure place (like rowState
// for endpoints) so every state, including the "normal" 404, is testable.
import type { ConformerResponse } from "../types/contracts";
import { fmtNum } from "./format";

export type ConformerView =
  | { kind: "idle" } // no molecule yet
  | { kind: "loading" }
  | { kind: "ready"; caption: string }
  | { kind: "unavailable" } // 404: unknown or expired id — a normal state
  | { kind: "unsupported" } // 501: this API environment has no RDKit
  | { kind: "error"; message: string };

export interface ConformerQueryLike {
  moleculeId: string | null | undefined;
  isPending: boolean;
  data?: ConformerResponse;
  error: { status?: number; message: string } | null;
}

// The service's own description of how the conformer was made (conformer.py):
// ETKDG embedding, MMFF94-optimised. The energy is the returned conformer's.
export function conformerCaption(c: ConformerResponse): string {
  return `ETKDG · MMFF94 · ${fmtNum(c.energy_kcal_mol, 1)} kcal/mol`;
}

export function conformerView(q: ConformerQueryLike): ConformerView {
  if (!q.moleculeId) return { kind: "idle" };
  if (q.error) {
    if (q.error.status === 404) return { kind: "unavailable" };
    if (q.error.status === 501) return { kind: "unsupported" };
    return { kind: "error", message: q.error.message };
  }
  if (q.data) return { kind: "ready", caption: conformerCaption(q.data) };
  return q.isPending ? { kind: "loading" } : { kind: "idle" };
}

export interface ConformerFacts {
  heavyAtoms: number;
  atoms: number; // counting hydrogens
  bonds: number;
  /** Independent rings: bonds - atoms + connected pieces. Hydrogens add one atom and one bond each, so they cancel. */
  rings: number;
  aromaticBonds: number;
  /** Hill order: carbon, hydrogen, then the rest alphabetically; with no carbon, everything alphabetically. */
  formula: string;
  /** Element counts in the same order as the formula. */
  elements: { element: string; count: number }[];
  /** Bonds by type, fixed order, only the types present. */
  bondTypes: { label: string; count: number }[];
  /** The longest distance between two heavy atoms in this conformer, in angstrom; null for fewer than two. */
  longestDistance: number | null;
}

const BOND_LABEL: [number, string][] = [
  [1, "single"],
  [2, "double"],
  [3, "triple"],
  [1.5, "aromatic"],
];

/**
 * Plain counts read off the conformer itself: nothing here is predicted, looked up or scored, so every figure can be
 * checked against the drawing. The service's own MMFF94 energy is shown separately and is not a property of the molecule.
 */
export function conformerFacts(c: ConformerResponse): ConformerFacts {
  const counts = new Map<string, number>();
  for (const a of c.atoms) counts.set(a.element, (counts.get(a.element) ?? 0) + 1);
  const hill = (a: string, b: string) => {
    const rank = (e: string) => (counts.has("C") ? (e === "C" ? 0 : e === "H" ? 1 : 2) : 2);
    return rank(a) - rank(b) || a.localeCompare(b);
  };
  const elements = [...counts.keys()].sort(hill).map((element) => ({ element, count: counts.get(element) as number }));
  const formula = elements.map((e) => (e.count === 1 ? e.element : `${e.element}${e.count}`)).join("");

  // connected pieces by union-find over the bond list
  const parent = c.atoms.map((_, i) => i);
  const find = (x: number): number => (parent[x] === x ? x : (parent[x] = find(parent[x])));
  for (const b of c.bonds) parent[find(b.atom_index_1)] = find(b.atom_index_2);
  const pieces = new Set(c.atoms.map((_, i) => find(i))).size;

  const heavy = c.atoms.filter((a) => a.element !== "H");
  let longest: number | null = null;
  for (let i = 0; i < heavy.length; i++) {
    for (let j = i + 1; j < heavy.length; j++) {
      const d = Math.hypot(heavy[i].x - heavy[j].x, heavy[i].y - heavy[j].y, heavy[i].z - heavy[j].z);
      if (longest === null || d > longest) longest = d;
    }
  }
  return {
    heavyAtoms: heavy.length,
    atoms: c.atoms.length,
    bonds: c.bonds.length,
    rings: Math.max(0, c.bonds.length - c.atoms.length + pieces),
    aromaticBonds: c.bonds.filter((b) => b.order === 1.5).length,
    formula,
    elements,
    bondTypes: BOND_LABEL.map(([order, label]) => ({ label, count: c.bonds.filter((b) => b.order === order).length })).filter((t) => t.count > 0),
    longestDistance: longest,
  };
}

/** How the conformer was made, in one sentence, and what its energy is and is not. */
export function conformerMethodNote(c: ConformerResponse): string {
  return `Embedded with ETKDG and minimised with MMFF94; ${fmtNum(c.energy_kcal_mol, 1)} kcal/mol is that conformer's own force-field energy. It is one low-energy shape, not the shape the molecule takes in a protein or in solution, and force-field energies cannot be compared between different molecules.`;
}

/** What the current view draws and how to use it (no claim about any prediction). */
export function viewNotes(mode: "hero" | "analysis", withAttribution: boolean): string[] {
  const lines = [
    mode === "hero"
      ? "Hero view: ball-and-stick, heavy atoms only; hydrogens are hidden."
      : "Analysis view: every atom including hydrogens, drawn as sticks; atoms are not labelled.",
    "Atom colours are the element palette (grey carbon, amber for every other element). They name the element and mean nothing about any prediction.",
  ];
  if (withAttribution) {
    lines.push(
      "Atoms the explanation gave a direction are coloured by that direction and sized by its strength; the rest keep the element palette. The sign says which way an atom pushed the output, not whether that is good or bad.",
    );
  }
  lines.push(
    "Drag to rotate and scroll to zoom. The conformer is generated on demand and kept with the prediction cache, so it expires with it; run the molecule again to regenerate it.",
  );
  return lines;
}
