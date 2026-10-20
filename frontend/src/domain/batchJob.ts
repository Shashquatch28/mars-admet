// The upload-and-progress side of Batch: what a file must look like before it is sent,
// how the server's progress stream is read, and the one derived phase the workspace
// shows. Pure and unit-tested; the network lives in data/client.ts.
//
// The service has two tiers (API_ROUTES.md): up to 100 molecules come back in the
// POST response itself (job_id null, status "done"); more are queued, and the browser
// follows GET /batch/progress/{job_id} (server-sent events) and then fetches
// GET /batch/results/{job_id}.
import type { BatchPredictResponse } from "../types/contracts";

export const BATCH_MAX_MOLECULES = 50_000; // service cap (settings.batch_size_cap), for the copy only
export const BATCH_INTERACTIVE_MAX = 100; // service default (settings.batch_interactive_threshold), for the copy only

export type JobStatus = "queued" | "running" | "done" | "failed" | "unknown";

/** One `data:` event of GET /batch/progress/{job_id} (BatchJobStatus-shaped). */
export interface JobProgress {
  job_id: string;
  status: JobStatus;
  total?: number;
  completed?: number;
}

const ACCEPTED = [".csv", ".sdf"] as const;

/** Why a file cannot be sent, or null when it can. Checked before any request. */
export function validateUpload(file: { name: string; size: number }): string | null {
  const name = file.name.toLowerCase();
  if (!ACCEPTED.some((ext) => name.endsWith(ext))) {
    return `${file.name} is not a .csv or .sdf file. Batch reads a CSV with a SMILES column, or an SDF.`;
  }
  if (file.size === 0) return `${file.name} is empty.`;
  return null;
}

/**
 * Split a streamed `text/event-stream` buffer into complete JSON events plus the
 * unfinished remainder. The service writes `data: {json}\n\n`, but a chunk boundary can
 * fall anywhere, so the caller keeps `rest` and prepends it to the next chunk. A
 * malformed event is dropped rather than guessed at.
 */
export function parseProgressEvents(buffer: string): { events: JobProgress[]; rest: string } {
  const normalized = buffer.replace(/\r\n/g, "\n");
  const parts = normalized.split("\n\n");
  const rest = parts.pop() ?? "";
  const events: JobProgress[] = [];
  for (const block of parts) {
    const data = block
      .split("\n")
      .filter((l) => l.startsWith("data:"))
      .map((l) => l.slice(5).trimStart())
      .join("\n");
    if (!data) continue;
    try {
      const parsed = JSON.parse(data) as Partial<JobProgress>;
      if (typeof parsed.job_id === "string" && typeof parsed.status === "string") {
        events.push(parsed as JobProgress);
      }
    } catch {
      /* not JSON: ignore the block */
    }
  }
  return { events, rest };
}

/** Whole-number percent for a progress bar; null until the total is known. */
export function percentDone(p: Pick<JobProgress, "total" | "completed"> | null): number | null {
  if (!p || !p.total || p.total <= 0) return null;
  const done = Math.min(Math.max(p.completed ?? 0, 0), p.total);
  return Math.floor((done / p.total) * 100);
}

export type BatchPhase =
  | { kind: "idle" }
  | { kind: "uploading"; fileName: string }
  | { kind: "running"; jobId: string; progress: JobProgress | null }
  | { kind: "fetching"; jobId: string }
  | { kind: "done" }
  | { kind: "failed"; message: string };

/** Words for the status line under the upload controls. */
export function phaseLabel(phase: BatchPhase): string {
  switch (phase.kind) {
    case "idle":
      return "No batch run yet";
    case "uploading":
      return `Uploading ${phase.fileName}`;
    case "running": {
      const p = phase.progress;
      if (!p || !p.total) return "Queued, waiting for the first progress report";
      const pct = percentDone(p);
      return `${p.status === "queued" ? "Queued" : "Running"}: ${p.completed ?? 0} of ${p.total} molecules (${pct}%)`;
    }
    case "fetching":
      return "Finished, fetching results";
    case "done":
      return "Done";
    case "failed":
      return phase.message;
  }
}

/**
 * What the final progress event means. `unknown` is the service saying it has no
 * progress record: the job is not found or its record expired, so there is nothing to
 * fetch and the result must not be shown as though it were complete.
 */
export function settleProgress(last: JobProgress | null): { ok: true } | { ok: false; message: string } {
  if (!last) return { ok: false, message: "The progress stream ended without a report." };
  if (last.status === "done") return { ok: true };
  if (last.status === "failed") return { ok: false, message: "The batch job failed on the server." };
  if (last.status === "unknown") {
    return { ok: false, message: "The server has no record of this job; it may have expired." };
  }
  return { ok: false, message: "The progress stream ended before the job finished." };
}

/** The result as a plain "how many rows" fact for the header, without implying quality. */
export function describeResult(r: BatchPredictResponse): string {
  const n = r.results?.length ?? 0;
  const tier = r.job_id ? "queued job" : "interactive";
  return `${n} of ${r.total} rows returned (${tier})`;
}
