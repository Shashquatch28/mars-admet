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

/**
 * What the enlarged structure pane says it is showing, in plain sentences (one pure place, so each claim is testable and
 * none can drift from what the viewer draws). Every sentence describes the drawing or how the conformer was made; none
 * says anything about a prediction.
 */
export function describeConformer(c: ConformerResponse, mode: "hero" | "analysis", withAttribution: boolean): string[] {
  const total = c.atoms.length;
  const heavy = c.atoms.filter((a) => a.element !== "H").length;
  const lines = [
    `One 3D conformer of the standardized molecule: ${heavy} heavy atoms, ${total} atoms counting hydrogens, ${c.bonds.length} bonds.`,
    `It was embedded with ETKDG and minimised with MMFF94; ${fmtNum(c.energy_kcal_mol, 1)} kcal/mol is that conformer's own force-field energy. It is one low-energy shape, not the shape the molecule takes in a protein or in solution, and force-field energies cannot be compared between different molecules.`,
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
