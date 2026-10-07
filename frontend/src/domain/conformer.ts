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
