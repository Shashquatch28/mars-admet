// Library: what a saved snapshot is, how it is listed and filtered, and how the account
// calls fail in words. Pure and unit-tested; the network is data/client.ts.
//
// A saved molecule or report is a FROZEN copy of a response the user already received. The
// service never recomputes it, so the screen always says which model_version produced it
// and when it was saved, and never presents it as a current prediction.
import type { PredictionResponse, SavedMoleculeResponse, SavedReportResponse } from "../types/contracts";

export interface MoleculeItem {
  kind: "molecule";
  id: string;
  title: string; // the user's label, else the standardized SMILES
  smiles: string;
  notes: string | null;
  tags: string[];
  modelVersion: string;
  savedAt: string;
  response: PredictionResponse;
}

export interface ReportItem {
  kind: "report";
  id: string;
  title: string;
  type: string;
  notes: string | null;
  tags: string[];
  savedAt: string;
  summary: ReportSummary;
  moleculeCount: number; // saved molecules this report links to
}

export type LibraryItem = MoleculeItem | ReportItem;

export interface ReportSummary {
  /** What the frozen result set was. */
  shape: "batch" | "single" | "unrecognised";
  rows: number; // molecules in the snapshot
  failedRows: number; // batch rows that failed before inference
  modelVersions: string[]; // distinct versions inside the snapshot, sorted
}

const isRecord = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);

/**
 * Read a frozen report snapshot without trusting its shape. The server stores whatever
 * result set the client sent, so a snapshot that is neither a batch nor a single prediction
 * is reported as such rather than as zero rows of something.
 */
export function summarizeSnapshot(snapshot: Record<string, unknown>): ReportSummary {
  const versions = new Set<string>();
  const note = (p: unknown) => {
    if (isRecord(p) && typeof p.model_version === "string" && p.model_version) versions.add(p.model_version);
  };

  if (Array.isArray(snapshot.results)) {
    let failed = 0;
    for (const r of snapshot.results) {
      if (!isRecord(r)) continue;
      if (r.ok === false) failed += 1;
      note(r.prediction);
    }
    return { shape: "batch", rows: snapshot.results.length, failedRows: failed, modelVersions: [...versions].sort() };
  }
  if (Array.isArray(snapshot.predictions)) {
    note(snapshot);
    return { shape: "single", rows: 1, failedRows: 0, modelVersions: [...versions].sort() };
  }
  return { shape: "unrecognised", rows: 0, failedRows: 0, modelVersions: [] };
}

export function toMoleculeItem(m: SavedMoleculeResponse): MoleculeItem {
  return {
    kind: "molecule",
    id: m.id,
    title: m.label?.trim() || m.smiles,
    smiles: m.smiles,
    notes: m.notes,
    tags: m.tags,
    modelVersion: m.model_version,
    savedAt: m.created_at,
    response: m.predictions_snapshot,
  };
}

export function toReportItem(r: SavedReportResponse): ReportItem {
  const summary = summarizeSnapshot(r.results_snapshot);
  const what = summary.shape === "batch" ? `Batch of ${summary.rows}` : summary.shape === "single" ? "Single molecule" : "Report";
  return {
    kind: "report",
    id: r.id,
    title: `${what}, ${shortDate(r.created_at)}`,
    type: r.type,
    notes: r.notes,
    tags: r.tags,
    savedAt: r.created_at,
    summary,
    moleculeCount: r.molecule_ids.length,
  };
}

/** `2026-10-18` from an ISO datetime; the original string when it is not one. */
export function shortDate(iso: string): string {
  const m = /^(\d{4}-\d{2}-\d{2})/.exec(iso);
  return m ? m[1] : iso;
}

/** Newest first. The service already sends newest first; this keeps it true after any merge. */
export function newestFirst<T extends LibraryItem>(items: T[]): T[] {
  return [...items].sort((a, b) => (a.savedAt < b.savedAt ? 1 : a.savedAt > b.savedAt ? -1 : 0));
}

/** Case-insensitive match over title, SMILES, notes and tags. Hides items; never edits one. */
export function filterLibrary<T extends LibraryItem>(items: T[], text: string): T[] {
  const q = text.trim().toLowerCase();
  if (!q) return items;
  return items.filter((it) => {
    const hay = [it.title, it.notes ?? "", ...it.tags, it.kind === "molecule" ? it.smiles : ""].join("\n").toLowerCase();
    return hay.includes(q);
  });
}

/** Words for a snapshot's provenance line: which model made it and when it was saved. */
export function provenanceLine(item: MoleculeItem): string {
  return `Saved ${shortDate(item.savedAt)} with model ${item.modelVersion || "unknown"}. A frozen copy, not a new prediction.`;
}

// --- account calls, in words ---------------------------------------------------------

/** Why deleting the account failed, in words the dialog can show. */
export function deleteAccountError(status: number, message: string): string {
  if (status === 403) return "That password is not correct. Nothing was deleted.";
  if (status === 401) return "Your session has ended, so nothing was deleted. Sign in again to delete the account.";
  if (status === 0) return "The API is unreachable, so nothing was deleted.";
  return `${message || "The request failed"}. Nothing was deleted.`;
}

/** Why a saved-item delete failed; 404 is not an error, the item is already gone. */
export function deleteItemError(status: number, message: string): string | null {
  if (status === 404) return null;
  if (status === 0) return "The API is unreachable, so nothing was deleted.";
  return `${message || "The request failed"}. Nothing was deleted.`;
}

/** What `DELETE /account` removes, as shown before the user confirms. */
export const DELETE_ACCOUNT_EFFECTS: readonly string[] = [
  "your saved molecules and saved reports",
  "your batch jobs, so their results can no longer be opened (they also expire from the service's cache after their 24-hour retention)",
  "every active session, on every device",
];
