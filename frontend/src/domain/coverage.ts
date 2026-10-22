// The Batch coverage table (ADR-034 item 5): for each ML endpoint, what happened across the run, as counts.
// Computed in the browser from the rows already in hand, so it needs no API change and adds no cache.
//
// It is descriptive and nothing else. It counts reliability states and which model answered; for a regression
// endpoint it prints the smallest, middle and largest value the service returned for THIS batch. It never marks
// a value or a molecule as unusual (that would colour or flag a value by its magnitude, never-do #1), draws no
// chart (no axis to invent, never-do #4), ranks nothing and orders endpoints by the fixed roster only.
import type { Endpoint } from "../types/contracts";
import type { BatchRow } from "./batch";
import { DISPLAY_UNIT, ML_ENDPOINTS } from "./endpoints";
import { decimalPlaces, fmtNum } from "./format";
import { modelFamily, servedByFallback } from "./modelFamily";

export interface ObservedRange {
  min: number;
  median: number;
  max: number;
}

export interface CoverageRow {
  endpoint: Endpoint;
  task: "regression" | "classification";
  unit: string;
  /** Molecules this endpoint was asked of (everything except "not requested"). */
  requested: number;
  returned: number;
  notReturned: number;
  /** Returned model values flagged out of domain. A stub value is counted under `stubServed`, not here. */
  outOfDomain: number;
  stubServed: number;
  /** Returned, non-stub values by the model family that answered, with fallbacks kept apart from KERMT. */
  xgboost: number;
  kermt: number;
  /** Routed to KERMT but answered by XGBoost for that request (ADR-033). Not counted in `xgboost`. */
  fellBack: number;
  other: number;
  /** Regression only; the values the service returned, stub values left out. Null when there are none. */
  observed: ObservedRange | null;
}

export interface Coverage {
  rows: CoverageRow[];
  /** Molecules that returned a result: the denominator of every count above. */
  molecules: number;
  /** Molecules that failed before inference. They have no cells and are in no count. */
  failedRows: number;
}

function median(sorted: number[]): number {
  const n = sorted.length;
  const mid = n >> 1;
  return n % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

export function buildCoverage(rows: readonly BatchRow[], kermtEndpoints: readonly string[] = []): Coverage {
  const ok = rows.filter((r) => r.ok);
  const out: CoverageRow[] = ML_ENDPOINTS.map((endpoint) => {
    const c: CoverageRow = {
      endpoint,
      task: "regression",
      unit: DISPLAY_UNIT[endpoint],
      requested: 0,
      returned: 0,
      notReturned: 0,
      outOfDomain: 0,
      stubServed: 0,
      xgboost: 0,
      kermt: 0,
      fellBack: 0,
      other: 0,
      observed: null,
    };
    const values: number[] = [];
    for (const r of ok) {
      const cell = r.cells.find((x) => x.endpoint === endpoint);
      if (!cell) continue;
      c.task = cell.meta.taskType === "classification" ? "classification" : "regression";
      const kind = cell.state.kind;
      if (kind === "not_requested") continue;
      c.requested += 1;
      if (kind === "not_returned" || !cell.prediction) {
        c.notReturned += 1;
        continue;
      }
      c.returned += 1;
      if (kind === "stub_served") {
        c.stubServed += 1;
        continue;
      }
      if (kind === "out_of_domain") c.outOfDomain += 1;
      const family = modelFamily(cell.prediction.model_id);
      if (servedByFallback(cell.prediction, kermtEndpoints)) c.fellBack += 1;
      else if (family === "xgboost") c.xgboost += 1;
      else if (family === "kermt") c.kermt += 1;
      else c.other += 1;
      if (cell.meta.taskType === "regression") values.push(cell.prediction.value);
    }
    if (c.task === "regression" && values.length > 0) {
      values.sort((a, b) => a - b);
      c.observed = { min: values[0], median: median(values), max: values[values.length - 1] };
    }
    return c;
  });
  return { rows: out, molecules: ok.length, failedRows: rows.length - ok.length };
}

/** One observed range as text, at the same decimals the screen uses for that endpoint. */
export function fmtObserved(endpoint: Endpoint, o: ObservedRange): string {
  const dp = decimalPlaces(endpoint);
  return `${fmtNum(o.min, dp)} · ${fmtNum(o.median, dp)} · ${fmtNum(o.max, dp)}`;
}

/** Fixed text printed with the table. Each line is something the table must not leave to the reader to assume. */
export const COVERAGE_NOTES: readonly string[] = [
  "Counts are over the molecules that returned a result. Rows that failed before inference have no cells and are in no count.",
  "Out of domain counts returned model values flagged out of domain; a stub value is counted only as stub-served, never as a model value.",
  "XGBoost and KERMT count the model that answered. † fell back counts values for an endpoint the deployment routes to KERMT that XGBoost answered because the KERMT service did not; those are not counted under XGBoost.",
  "Observed (min · median · max) is the smallest, middle and largest value the service returned for this batch, out-of-domain values included, stub values left out. It describes this batch only. MARS defines no direction of good, so it says nothing about any molecule or value.",
  "The rule-based synthetic accessibility score is computed, not predicted, and is not in this table.",
];
