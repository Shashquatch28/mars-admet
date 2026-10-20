// What the Explanation section of the inspector should show, decided in one pure place (like
// conformerView and deriveRowState) so every state, including the ones that are not errors, is
// testable. ADR-031: the serving model explains; attribution is signed and never good or bad.
import type { Endpoint, EndpointPrediction, ExplainMethod, ExplainOutputSpace, ExplainResponse } from "../types/contracts";
import { DISPLAY_UNIT } from "./endpoints";
import { fmtNum } from "./format";
import type { EndpointRowState } from "./rowState";

export type ExplainView =
  | { kind: "not_askable"; why: string } // the row has no model behind it: nothing to explain
  | { kind: "idle" } // can be asked for, has not been
  | { kind: "loading" }
  | { kind: "ready"; data: ExplainResponse }
  | { kind: "mismatch"; explained: string; served: string } // an explanation of a different model than the value on screen
  | { kind: "no_model"; message: string } // 409: the service says there is no model to explain
  | { kind: "expired" } // 404: the molecule's cache entry is gone
  | { kind: "unsupported" } // 501: this API environment has no ml stack
  | { kind: "busy"; message: string } // 503: the serving model cannot explain right now
  | { kind: "error"; message: string };

export interface ExplainInputs {
  rowState: EndpointRowState;
  prediction: EndpointPrediction | undefined;
  asked: boolean; // the user pressed Explain for this molecule + endpoint
  isPending: boolean;
  data?: ExplainResponse;
  error: { status?: number; message: string } | null;
}

// Rows without a promoted model have nothing to explain, and each says so in words (never-do #8).
const NOT_ASKABLE: Partial<Record<EndpointRowState["kind"], string>> = {
  not_requested: "This endpoint was left out of the run, so there is no prediction to explain.",
  not_returned: "The service did not return this endpoint, so there is no prediction to explain.",
  stub_served:
    "No promoted model served this endpoint: its value came from a stub, so there is no model to explain.",
  rule_based: "A rule-based score is computed, not predicted: there is no model to explain.",
};

export function explainView(i: ExplainInputs): ExplainView {
  const why = NOT_ASKABLE[i.rowState.kind];
  if (why || !i.prediction) return { kind: "not_askable", why: why ?? "There is no prediction to explain." };
  if (!i.asked) return { kind: "idle" };
  if (i.error) {
    switch (i.error.status) {
      case 404:
        return { kind: "expired" };
      case 409:
        return { kind: "no_model", message: i.error.message };
      case 501:
        return { kind: "unsupported" };
      case 503:
        return { kind: "busy", message: i.error.message };
      default:
        return { kind: "error", message: i.error.message };
    }
  }
  if (i.data) {
    // The explanation must describe the artifact that produced the value on screen. If the value was
    // answered by a fallback (a KERMT outage answered by XGBoost), say so instead of mixing the two.
    if (i.data.model_id !== i.prediction.model_id)
      return { kind: "mismatch", explained: i.data.model_id, served: i.prediction.model_id };
    return { kind: "ready", data: i.data };
  }
  return i.isPending ? { kind: "loading" } : { kind: "idle" };
}

export type Sign = "up" | "down" | "none";

// Sign is taken from the rounded number: a value that prints as 0.00 gets no glyph, so a ▲ never
// sits beside "+0.00".
export function signOf(n: number, dp = 2): Sign {
  const rounded = Number(Math.abs(n).toFixed(dp));
  if (rounded === 0) return "none";
  return n > 0 ? "up" : "down";
}

export const GLYPH: Record<Sign, string> = { up: "▲", down: "▼", none: "·" };

export function fmtSigned(n: number, dp = 2): string {
  const s = signOf(n, dp);
  const body = fmtNum(Math.abs(n), dp);
  return s === "up" ? `+${body}` : s === "down" ? `−${body}` : body;
}

export function outputSpaceLabel(space: ExplainOutputSpace, endpoint: Endpoint): string {
  if (space === "log_odds") return "log-odds";
  if (space === "score") return "score";
  return DISPLAY_UNIT[endpoint];
}

export function methodLabel(method: ExplainMethod): string {
  return method === "tree_shap" ? "TreeSHAP" : "Integrated Gradients";
}

export interface TotalRow {
  key: "base" | "structure" | "whole" | "unmapped" | "output";
  label: string;
  text: string;
  sign: Sign; // "none" for the reference and the output, which are values, not contributions
  note: string;
}

// The parts that add up to the output, in the order they add. The note says, in words, what each is.
export function totalRows(d: ExplainResponse, dp = 2): TotalRow[] {
  const unmappedNote =
    d.method === "tree_shap"
      ? "Fingerprint bits absent from this molecule, which still move the trees."
      : "Part of the output change the integration did not account for.";
  const row = (key: TotalRow["key"], label: string, n: number, contribution: boolean, note: string): TotalRow => ({
    key,
    label,
    text: contribution ? fmtSigned(n, dp) : fmtNum(n, dp),
    sign: contribution ? signOf(n, dp) : "none",
    note,
  });
  return [
    row("base", "Reference", d.base_value, false, d.baseline),
    row("structure", "Structure", d.structure_total, true, "Atoms: what the heatmap shows."),
    row("whole", "Whole-molecule", d.whole_molecule_total, true, "Descriptors of the molecule as a whole. They cannot be placed on atoms."),
    row("unmapped", "Unplaced", d.unmapped_total, true, unmappedNote),
    row("output", "Model output", d.output_value, false, "The explained value, in the units above."),
  ];
}

export interface AtomHighlight {
  index: number; // RDKit atom order of smiles_standardized; heavy atoms come first in the conformer
  sign: Sign;
  strength: number; // 0..1, |score| over the largest |score| in this molecule
}

// Strength is relative to this molecule's own largest atom attribution, so it shows where the
// structure part concentrates and nothing more. It is not comparable across molecules.
export function atomHighlights(scores: readonly number[], dp = 2): AtomHighlight[] {
  const max = scores.reduce((m, s) => Math.max(m, Math.abs(s)), 0);
  return scores.map((s, index) => ({
    index,
    sign: max === 0 ? "none" : signOf(s, dp + 2),
    strength: max === 0 ? 0 : Math.abs(s) / max,
  }));
}

export function topFragments(d: ExplainResponse, n = 8) {
  return d.fragment_attributions.slice(0, n);
}

// A fragment is identified by what it is and which atoms it covers: two groups of the same kind
// share a name, never an atom set.
export const fragmentKey = (f: { name: string; atom_indices: number[] }) => `${f.name}:${f.atom_indices.join(",")}`;

// Show one group on the structure: every atom outside it goes back to the element palette.
export function focusHighlights(all: AtomHighlight[], atoms: readonly number[]): AtomHighlight[] {
  const keep = new Set(atoms);
  return all.map((h) => (keep.has(h.index) ? h : { ...h, sign: "none", strength: 0 }));
}
