// Formatters. Numbers are mono + tabular everywhere; negatives use a true minus
// sign (U+2212), not a hyphen, so columns align and read as an instrument.
import type { Endpoint, EndpointPrediction } from "../types/contracts";
import type { EndpointMeta } from "./endpoints";

const MINUS = "−";

export function fmtNum(n: number, dp = 2): string {
  const s = Math.abs(n).toFixed(dp);
  return n < 0 ? MINUS + s : s;
}

// % bound reads at 1 dp, everything else at 2 dp. Keyed on the endpoint, not on
// `prediction.unit`: the service sends `unit: null` for every real-model row, so a
// unit-keyed rule silently stops applying against live data.
export function decimalPlaces(endpoint: Endpoint): number {
  return endpoint === "ppb_binding" ? 1 : 2;
}

export function fmtValue(p: EndpointPrediction, meta: EndpointMeta): string {
  if (meta.taskType === "classification") return fmtNum(p.value, 2);
  if (meta.taskType === "rule_based") return fmtNum(p.value, 2);
  return fmtNum(p.value, decimalPlaces(p.endpoint));
}

export function fmtInterval(low: number, high: number, dp = 2): string {
  return `${fmtNum(low, dp)} … ${fmtNum(high, dp)}`;
}

// The column label shown for a row's unit. Classification carries no unit in the
// contract (null); the UI labels the axis "probability".
export function unitLabel(p: EndpointPrediction, meta: EndpointMeta): string {
  if (p.unit) return p.unit;
  if (meta.taskType === "classification") return "probability";
  return "";
}

export function fmtDateTime(iso: string): string {
  // Render the served_at timestamp as UTC, matching the status bar in the comps.
  try {
    const d = new Date(iso);
    const pad = (n: number) => String(n).padStart(2, "0");
    return (
      `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ` +
      `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}Z`
    );
  } catch {
    return iso;
  }
}
