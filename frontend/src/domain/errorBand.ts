// The held-out-error band (ADR-024). One half-width per regression endpoint, printed as text.
//
// What it is: `level` of the absolute errors the promoted seeds made on molecules held out of their own
// training fell within +/- halfwidth. What it is not: a range for THIS molecule, a coverage guarantee for it,
// or a reason to colour anything. It is never drawn as a bar (an interval bar needs a real axis, and there is
// none for an unbounded regression value), and it is never invented: if the service sent no complete band
// there is nothing to show.
import type { EndpointPrediction } from "../types/contracts";

export interface ErrorBand {
  halfwidth: number;
  levelPct: number; // whole percent, e.g. 90
  n: number; // pooled held-out residuals the half-width was taken over
}

export function errorBandOf(p: EndpointPrediction): ErrorBand | null {
  const { heldout_error_halfwidth: h, heldout_error_level: l, heldout_error_n: n } = p;
  if (h == null || l == null || n == null) return null;
  if (!Number.isFinite(h) || h <= 0 || !(l > 0 && l < 1) || !Number.isInteger(n) || n <= 0) return null;
  return { halfwidth: h, levelPct: Math.round(l * 100), n };
}

export function errorBandNote(b: ErrorBand): string {
  return (
    `${b.levelPct}% of the ${b.n.toLocaleString("en-US")} errors the models made on molecules held out of their own ` +
    `training fell within this. One value for the whole endpoint: not a range for this molecule, and not a ` +
    `guarantee for an out-of-domain one.`
  );
}
