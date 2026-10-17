// Save to library: what the user types, what is sent, and how a failure reads. Pure and
// unit-tested; the network is data/client.ts.
//
// Saving is snapshot-on-save (persistence.py): the client sends back the response it already
// holds and the service freezes it. Nothing is recomputed, so a saved entry keeps the
// model_version it was made with and is never a current prediction. The copy here says so.
import type {
  BatchPredictResponse,
  PredictionResponse,
  SaveMoleculeRequest,
  SaveReportRequest,
} from "../types/contracts";

export interface SaveInput {
  label: string;
  notes: string;
  tags: string; // comma-separated, as typed
}

export const EMPTY_SAVE_INPUT: SaveInput = { label: "", notes: "", tags: "" };

/** Split typed tags on commas: trimmed, blanks dropped, repeats (ignoring case) dropped, order kept. */
export function parseTags(text: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of text.split(",")) {
    const t = raw.trim();
    const k = t.toLowerCase();
    if (t && !seen.has(k)) {
      seen.add(k);
      out.push(t);
    }
  }
  return out;
}

const orNull = (s: string): string | null => (s.trim() ? s.trim() : null);

export function buildMoleculeRequest(prediction: PredictionResponse, input: SaveInput): SaveMoleculeRequest {
  return { prediction, label: orNull(input.label), notes: orNull(input.notes), tags: parseTags(input.tags) };
}

/**
 * A batch report freezes the whole result set in hand. `source_batch_job_id` is provenance
 * only (the interactive tier has no job, so null). `molecule_ids` stays empty: those are
 * references to separately saved molecules, which this flow does not create.
 */
export function buildBatchReportRequest(results: BatchPredictResponse, input: SaveInput): SaveReportRequest {
  return {
    type: "batch",
    source_batch_job_id: results.job_id ?? null,
    results,
    molecule_ids: [],
    notes: orNull(input.notes),
    tags: parseTags(input.tags),
  };
}

/** Identifies one prediction as the user saw it, so the same one is not saved twice by accident. */
export function moleculeKey(p: Pick<PredictionResponse, "molecule_id" | "served_at">): string {
  return `mol:${p.molecule_id}|${p.served_at}`;
}

export function reportKey(resultId: number): string {
  return `report:${resultId}`;
}

/** Words for a failed save. Every one says nothing was saved. */
export function saveError(status: number, message: string): string {
  if (status === 401) return "Your session has ended, so nothing was saved. Sign in again to save.";
  if (status === 0) return "The API is unreachable, so nothing was saved.";
  return `${message || "The request failed"}. Nothing was saved.`;
}

/** What saving does, shown before the user commits. */
export function saveNote(kind: "molecule" | "report", modelVersion: string | null, rows?: number): string {
  if (kind === "molecule") {
    const m = modelVersion ? ` with model ${modelVersion}` : "";
    return `Saves a frozen copy of these values${m}. It does not update when the model changes. Values served by the stub are saved as stub values.`;
  }
  return `Saves a frozen copy of this batch${rows != null ? ` (${rows.toLocaleString()} rows)` : ""} exactly as returned, failed rows included. It does not update when the model changes.`;
}
