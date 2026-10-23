// What the Explanation section of the inspector should show, decided in one pure place (like
// conformerView and deriveRowState) so every state, including the ones that are not errors, is
// testable. ADR-031: the serving model explains; attribution is signed and never good or bad.
import type {
  Endpoint,
  EndpointPrediction,
  ExplainJobStatus,
  ExplainMethod,
  ExplainOutputSpace,
  ExplainResponse,
} from "../types/contracts";
import { DISPLAY_UNIT } from "./endpoints";
import { fmtNum } from "./format";
import { modelFamily } from "./modelFamily";
import type { EndpointRowState } from "./rowState";

// What the API said about an explanation (ADR-035): the result, a job that is queued or running, or nothing
// started. Reading never starts anything; only an explicit Start does.
export type ExplainAnswer =
  | { kind: "result"; data: ExplainResponse }
  | { kind: "job"; job: ExplainJobStatus }
  | { kind: "none" };

export type ExplainView =
  | { kind: "not_askable"; why: string } // the row has no model behind it: nothing to explain
  | { kind: "checking" } // asking the server whether this was already explained or is running
  | { kind: "idle"; cancelled: boolean; background: boolean } // can be started; `background` = takes minutes, not an instant
  | { kind: "starting" }
  | { kind: "job"; job: ExplainJobStatus; stopping: boolean } // queued or running
  | { kind: "ready"; data: ExplainResponse }
  | { kind: "mismatch"; explained: string; served: string } // an explanation of a different model than the value on screen
  | { kind: "no_model"; message: string } // 409: the service says there is no model to explain
  | { kind: "expired" } // 404: the molecule's cache entry is gone
  | { kind: "unsupported" } // 501: this API environment has no ml stack
  | { kind: "unexplainable"; message: string } // 422: this molecule cannot be explained; trying again will not help
  | { kind: "limited"; message: string } // 429: rate limit, or an explanation of yours is already running
  | { kind: "busy"; message: string } // 503: the serving model cannot explain right now, the queue is full, or the job was lost
  | { kind: "error"; message: string };

export interface ExplainInputs {
  rowState: EndpointRowState;
  prediction: EndpointPrediction | undefined;
  answer?: ExplainAnswer; // the latest thing the server said
  pending: "check" | "start" | null; // a request in flight: the first read, or a Start
  stopping?: boolean; // a Cancel was sent and the job has not reported cancelled yet
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

// A queued or running job is read again every few seconds; anything else is not (ADR-035 item 3). Reading is
// cheap and has no side effect, and it is not rate limited. The browser pauses it while the tab is hidden.
export const EXPLAIN_POLL_MS = 3000;
export function shouldPoll(a: ExplainAnswer | undefined): boolean {
  return a?.kind === "job" && (a.job.state === "queued" || a.job.state === "running");
}

// Whether there is a model behind this row to ask. The server is only read for these rows.
export function isAskable(rowState: EndpointRowState, prediction: EndpointPrediction | undefined): boolean {
  return !!prediction && !NOT_ASKABLE[rowState.kind];
}

export function explainView(i: ExplainInputs): ExplainView {
  const why = NOT_ASKABLE[i.rowState.kind];
  if (why || !i.prediction) return { kind: "not_askable", why: why ?? "There is no prediction to explain." };
  if (i.error) {
    switch (i.error.status) {
      case 404:
        return { kind: "expired" };
      case 409:
        return { kind: "no_model", message: i.error.message };
      case 422:
        return { kind: "unexplainable", message: i.error.message };
      case 429:
        return { kind: "limited", message: i.error.message };
      case 501:
        return { kind: "unsupported" };
      case 503:
        return { kind: "busy", message: i.error.message };
      default:
        return { kind: "error", message: i.error.message };
    }
  }
  const a = i.answer;
  if (a?.kind === "result") {
    // The explanation must describe the artifact that produced the value on screen. If the value was
    // answered by a fallback (a KERMT outage answered by XGBoost), say so instead of mixing the two.
    if (a.data.model_id !== i.prediction.model_id)
      return { kind: "mismatch", explained: a.data.model_id, served: i.prediction.model_id };
    return { kind: "ready", data: a.data };
  }
  if (a?.kind === "job" && (a.job.state === "queued" || a.job.state === "running"))
    return { kind: "job", job: a.job, stopping: !!i.stopping };
  if (i.pending === "start") return { kind: "starting" };
  if (i.pending === "check" && !a) return { kind: "checking" };
  return {
    kind: "idle",
    cancelled: a?.kind === "job" && a.job.state === "cancelled",
    background: modelFamily(i.prediction.model_id) === "kermt",
  };
}

// Progress in words: where the job is, never a percentage or a time left (ADR-035 item 5: the step count
// escalates 64, 128, 256 until the residual is small enough, so the end is not known in advance).
export function describeJob(job: ExplainJobStatus): { status: string; detail: string | null; elapsed: string } {
  const status =
    job.state === "queued"
      ? job.queue_position != null
        ? `Waiting in the queue, position ${job.queue_position}.`
        : "Waiting in the queue."
      : job.stage
        ? `Running: ${job.stage}.`
        : "Running.";
  const detail =
    job.state === "running" && job.seeds_total > 0
      ? `${job.seeds_done} of ${job.seeds_total} ${job.seeds_total === 1 ? "seed" : "seeds"} attributed so far.`
      : null;
  return { status, detail, elapsed: `Elapsed ${fmtDuration(job.elapsed_seconds)}.` };
}

export function fmtDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  const m = Math.floor(s / 60);
  return m === 0 ? `${s} s` : `${m} min ${String(s % 60).padStart(2, "0")} s`;
}

// Integrated Gradients is iterative. When it stopped at its largest step count without meeting its tolerance,
// the result is still returned and the parts still add up to the output; this says how much was left unplaced.
export function convergenceNote(d: ExplainResponse): string | null {
  if (d.converged !== false) return null;
  const steps = d.n_steps != null ? `${d.n_steps} steps` : "its largest number of steps";
  return `The integration did not meet its tolerance after ${steps}, so ${fmtNum(
    Math.abs(d.unmapped_total),
    3,
  )} of the output change is shown as Unplaced. The parts above still add up to the output.`;
}

// Median pairwise cosine of the per-seed atom attributions, in words. A number and what it measures; no verdict.
export function seedAgreementNote(d: ExplainResponse): string | null {
  if (d.seed_agreement == null) return null;
  return `Seed agreement ${fmtNum(d.seed_agreement, 2)}: how alike the ${d.n_seeds} seeds' atom attributions are (1 means the same pattern, 0 unrelated, below 0 opposite).`;
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
