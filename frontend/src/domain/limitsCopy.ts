// The sentences that state the service's policy numbers. They are built from `GET /limits`
// (ADR-034 item 8) and never from constants, so they cannot drift from what the service enforces.
// Before the service has answered, or when it is unreachable, the numbers are left out and
// the sentence says less; it never guesses one.
import type { LimitsResponse } from "../types/contracts";

const n = (v: number) => v.toLocaleString("en-US");
const hours = (h: number) => `${n(h)} ${h === 1 ? "hour" : "hours"}`;

/** The note under the Batch upload controls. */
export function batchUploadNote(limits: LimitsResponse | undefined): string {
  if (!limits) {
    return "The service states its batch limits once it answers. Each batch belongs to your account.";
  }
  return (
    `Up to ${n(limits.batch_interactive_threshold)} molecules are returned directly. Larger files, up to ` +
    `${n(limits.batch_size_cap)}, run as a queued job with live progress. The results of a queued job are kept for ` +
    `${hours(limits.batch_result_retention_hours)}; smaller batches are not stored. Each batch belongs to your account.`
  );
}

/** Why Batch needs an account (the sign-in state's explanation). */
export function batchGateWhy(limits: LimitsResponse | undefined): string {
  const size = limits ? `a file of up to ${n(limits.batch_size_cap)} molecules` : "a file of molecules";
  return `Batch takes ${size} and runs it with live progress. Each batch belongs to the account that uploaded it, which is how MARS knows whose results they are.`;
}

/** Shown when fetching a queued job's results answers 410. */
export function expiredResultsMessage(limits: LimitsResponse | undefined): string {
  const kept = limits
    ? `The results of a queued batch are kept for ${hours(limits.batch_result_retention_hours)}`
    : "Queued batch results are kept for a limited time";
  return `The results have expired. ${kept}; run the batch again.`;
}
