// What a screen reader is told when something finishes (WCAG 4.1.3 Status Messages). Pure and tested.
//
// One polite live region carries all of it (`app/announce.tsx`). Nothing else on the page is live: a dense grid
// that announces every change is worse than one that announces none (ACCESSIBILITY.md). So these are the only
// messages, and each says what happened in the words the screen already uses. None rates a result: a count of
// out-of-domain endpoints is a fact about reliability, not a verdict on any value.
import type { BatchPhase } from "./batchJob";
import { percentDone } from "./batchJob";

export interface PredictionCounts {
  requested: number;
  returned: number;
  outOfDomain: number;
  stubServed: number;
}

export function predictionAnnouncement(c: PredictionCounts): string {
  const parts = [`${c.returned} of ${c.requested} endpoints returned`];
  if (c.outOfDomain > 0) parts.push(`${c.outOfDomain} out of domain`);
  if (c.stubServed > 0) parts.push(`${c.stubServed} stub-served`);
  const notReturned = c.requested - c.returned;
  if (notReturned > 0) parts.push(`${notReturned} not returned`);
  return `Prediction complete. ${parts.join(", ")}.`;
}

const EXPLAIN_FAILED = new Set(["busy", "limited", "unexplainable", "error", "expired", "no_model", "unsupported"]);

/**
 * An explanation can run for minutes (ADR-040), so its start and its end are announced, and nothing in between:
 * the panel polls every few seconds and a live region that spoke each time would be noise. `prev` is the view kind
 * before this one for the same molecule and endpoint, or null. Reading a result that was already cached is silent.
 */
export function explainAnnouncement(prev: string | null, next: { kind: string }): string | null {
  if (prev === "starting" && next.kind === "job")
    return "Explanation started. It runs in the background and can take several minutes.";
  if ((prev === "starting" || prev === "job") && next.kind === "ready") return "Explanation ready.";
  if (prev === "job" && next.kind === "idle") return "Explanation cancelled.";
  if ((prev === "starting" || prev === "job") && EXPLAIN_FAILED.has(next.kind))
    return "Explanation could not be completed. The reason is in the Explanation section.";
  return null;
}

/** Progress is announced at each quarter, not on every event: the service reports every half second. */
const STEP = 25;

/**
 * The message, if any, for a change of batch phase. `null` means say nothing. A failure is not announced here:
 * its message is shown in a `role="alert"` element, which announces itself.
 */
export function batchAnnouncement(prev: BatchPhase, next: BatchPhase): string | null {
  if (next.kind === "running" && prev.kind !== "running") return "Batch started.";
  if (next.kind === "running" && prev.kind === "running") {
    const before = percentDone(prev.progress);
    const after = percentDone(next.progress);
    if (after == null) return null;
    const stepNow = Math.floor(after / STEP);
    const stepBefore = before == null ? 0 : Math.floor(before / STEP);
    // 100% is announced by the "finished" message; the quarter steps are 25, 50 and 75.
    if (stepNow > stepBefore && after < 100) return `Batch ${stepNow * STEP} percent complete.`;
    return null;
  }
  if (next.kind === "done" && prev.kind !== "done") return "Batch finished. Results are in the grid.";
  return null;
}
