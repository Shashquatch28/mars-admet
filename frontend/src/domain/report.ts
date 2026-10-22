// The printed report for one molecule (ship checklist D5, ADR-029): what the screen says, as a document.
//
// A pure function from the same `ExportMolecule` the CSV export uses to the words and numbers a report
// prints. It decides nothing new. Row state still comes from `deriveRowState`; values are formatted by the
// screen's own formatters; the full roster is printed whether or not the service returned an endpoint
// (ADR-008), and absence is a row that says so, never a gap. Nothing here ranks, scores, colours by
// magnitude or calls a value good, safe or favourable: the value is printed the same way in every state and
// reliability is its own column (ADR-006).
import { DISPLAY_UNIT, STUB_MODEL_ID, type DisplayGroup } from "./endpoints";
import { FALLBACK_NOTE, familyLabel, fallbackCountInRows, servedByFallback } from "./modelFamily";
import type { ExportMolecule } from "./exportCsv";
import { errorBandOf } from "./errorBand";
import { decimalPlaces, fmtDateTime, fmtInterval, fmtNum, fmtValue } from "./format";
import type { Row } from "./reconcile";
import { DISPLAY_GROUP_LABEL, DISPLAY_GROUP_ORDER, displayGroupOf } from "./endpoints";
import type { EndpointRowState } from "./rowState";

export interface ReportRow {
  endpoint: string;
  task: "regression" | "classification" | "rule_based";
  /** null when there is no value to print (not returned, not requested). */
  value: string | null;
  unit: string;
  /** "Seed spread ±1σ: a … b"; null when there is none (rule-based, no value). */
  spread: string | null;
  /** Regression only, and only when the service sent a complete band (ADR-024). */
  heldOutError: string | null;
  /** Applicability domain, in words and numbers. Never a verdict on the value. */
  domain: string;
  /** The reliability channel in words; null for a plain in-domain model value. */
  status: string | null;
  stateKind: EndpointRowState["kind"];
  /** The family that answered (XGBoost, KERMT, RDKit), read from the service's model_id; "stub" for a stub value. */
  model: string | null;
  /** The deployment routes this endpoint to KERMT but XGBoost answered it for this request (printed as a dagger). */
  fellBack: boolean;
  /** True only for a stub value: the report draws the diagonal hatch on its value cell (ADR-007). */
  hatch: boolean;
}

export interface ReportGroup {
  group: DisplayGroup;
  label: string;
  rows: ReportRow[];
}

export interface ReportCounts {
  requested: number;
  returned: number;
  outOfDomain: number;
  stubServed: number;
  notReturned: number;
  notRequested: number;
}

export interface ReportModel {
  generatedAt: string;
  smilesInput: string;
  smilesStandardized: string | null;
  moleculeId: string | null;
  modelVersion: string | null;
  servedAt: string | null;
  batchRow: number | null;
  /** Set when a Batch row failed before inference: there is nothing to tabulate, only the reason. */
  failure: string | null;
  counts: ReportCounts;
  /** Rows routed to KERMT that XGBoost answered for this request. */
  fallbackCount: number;
  groups: ReportGroup[];
  statements: string[];
}

/** Fixed text, printed on every report. Each line is something the report must not leave to the reader to assume. */
export const REPORT_STATEMENTS: readonly string[] = [
  "Classification values are model scores between 0 and 1, not calibrated probabilities (ADR-023).",
  "MARS has no validated risk threshold and no validated direction of good. Nothing in this report ranks, scores or " +
    "rates the molecule, and no value is called good, safe, favourable or better.",
  "Seed spread is the spread across the 5 cross-validation seeds: not a coverage guarantee. Held-out error, where " +
    "shown, is one value per endpoint measured on molecules the models were not trained on; it is not a range for this molecule.",
  "A value marked out of domain is the model's output for a molecule outside the chemical space that endpoint was " +
    "trained on: treat it as unreliable rather than as a result. A stub value is not a real prediction.",
  "Every endpoint in the roster is listed. One the service did not return reads NOT RETURNED; one left out of the " +
    "request reads NOT REQUESTED.",
  "The Model column names the family of model that answered each row, read from the service's own model identifier.",
  "Not included: a 2D structure drawing, and drug-likeness flags, which the service does not compute.",
];

/** Printed only when a row was routed to KERMT and answered by XGBoost, so it is never printed as noise. */
export const FALLBACK_STATEMENT = `† ${FALLBACK_NOTE[0].toUpperCase()}${FALLBACK_NOTE.slice(1)}. The Model column says which model answered the row.`;

const STATUS_WORDS: Record<EndpointRowState["kind"], string | null> = {
  ok: null,
  out_of_domain: "OUT OF DOMAIN",
  stub_served: "STUB",
  not_returned: "NOT RETURNED",
  not_requested: "NOT REQUESTED",
  rule_based: "RULE-BASED",
};

function domainText(row: Row): string {
  const p = row.prediction;
  if (!p || row.state.kind === "not_returned" || row.state.kind === "not_requested") return "";
  if (row.state.kind === "rule_based") return "none: computed, not predicted";
  if (row.state.kind === "stub_served") return "none: no promoted model";
  const dist = fmtNum(p.knn_distance, 3);
  const threshold = p.ad_threshold != null ? ` against a cutoff of ${fmtNum(p.ad_threshold, 3)}` : "";
  return `${p.in_domain ? "in domain" : "out of domain"}, 5-NN distance ${dist}${threshold}`;
}

function toReportRow(row: Row, kermtEndpoints: readonly string[]): ReportRow {
  const p = row.prediction;
  const kind = row.state.kind;
  const hasValue = !!p && kind !== "not_returned" && kind !== "not_requested";
  const dp = decimalPlaces(row.endpoint);
  const band = hasValue && row.meta.taskType === "regression" ? errorBandOf(p!) : null;
  return {
    endpoint: row.endpoint,
    task: row.meta.taskType,
    value: hasValue ? fmtValue(p!, row.meta) : null,
    unit: DISPLAY_UNIT[row.endpoint],
    // The rule-based score has no spread: the service repeats the value, and a fake one is not printed.
    spread:
      hasValue && kind !== "rule_based"
        ? fmtInterval(p!.confidence_low, p!.confidence_high, row.meta.taskType === "regression" ? dp : 2)
        : null,
    heldOutError: band ? `±${fmtNum(band.halfwidth, dp)} (${band.levelPct}% of ${band.n.toLocaleString("en-US")} errors)` : null,
    domain: domainText(row),
    status: STATUS_WORDS[kind],
    stateKind: kind,
    model: hasValue ? familyLabel(p!.model_id) || "stub" : null,
    fellBack: hasValue && servedByFallback(p, kermtEndpoints),
    hatch: hasValue && p!.model_id === STUB_MODEL_ID,
  };
}

export function reportCounts(cells: Row[]): ReportCounts {
  const ml = cells.filter((c) => c.meta.taskType !== "rule_based");
  const asked = ml.filter((c) => c.state.kind !== "not_requested");
  const returned = asked.filter((c) => c.state.kind !== "not_returned");
  return {
    requested: asked.length,
    returned: returned.length,
    outOfDomain: returned.filter((c) => c.state.kind === "out_of_domain").length,
    stubServed: returned.filter((c) => c.state.kind === "stub_served").length,
    notReturned: asked.filter((c) => c.state.kind === "not_returned").length,
    notRequested: ml.filter((c) => c.state.kind === "not_requested").length,
  };
}

export function buildReport(m: ExportMolecule, now: Date = new Date(), kermtEndpoints: readonly string[] = []): ReportModel {
  const r = m.response;
  const failed = !!m.error || !r;
  const groups: ReportGroup[] = failed
    ? []
    : DISPLAY_GROUP_ORDER.map((group) => ({
        group,
        label: DISPLAY_GROUP_LABEL[group],
        rows: m.cells.filter((c) => displayGroupOf(c.endpoint) === group).map((c) => toReportRow(c, kermtEndpoints)),
      })).filter((g) => g.rows.length > 0);
  const fallbackCount = failed ? 0 : fallbackCountInRows(m.cells, kermtEndpoints);
  return {
    generatedAt: now.toISOString(),
    smilesInput: m.smilesInput,
    smilesStandardized: r?.smiles_standardized ?? null,
    moleculeId: r?.molecule_id ?? null,
    modelVersion: r?.model_version ?? null,
    servedAt: r?.served_at ? fmtDateTime(r.served_at).replace(/Z$/, " UTC") : null,
    batchRow: m.row ?? null,
    failure: failed ? (m.error ?? "no result for this molecule") : null,
    counts: failed ? reportCounts([]) : reportCounts(m.cells),
    fallbackCount,
    groups,
    statements: fallbackCount > 0 ? [...REPORT_STATEMENTS, FALLBACK_STATEMENT] : [...REPORT_STATEMENTS],
  };
}

export function reportTitle(m: ReportModel): string {
  const id = (m.moleculeId ?? "").replace(/[^A-Za-z0-9_-]/g, "").slice(0, 16);
  return `MARS prediction report${id ? ` ${id}` : ""}`;
}
