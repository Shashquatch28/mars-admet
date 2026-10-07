// Batch triage domain layer. Three jobs, all pure and unit-testable:
//
//  1. Turn a BatchPredictResponse into a matrix of molecules × the full endpoint
//     roster. Every row runs through the SAME reconcile() the Predict workspace
//     uses, so ADR-008 holds here too: a molecule always has one cell per
//     endpoint, and an endpoint the service did not return is a marked cell,
//     never a gap in the row.
//  2. Sort. Only two kinds exist: input order, and a RAW numeric sort on one
//     endpoint. There is no favourability sort and no ranking (AGENTS.md #3) —
//     MARS has no direction-of-good, so "best first" is not expressible.
//  3. Filter, by text or by reliability state. Filtering hides rows the user
//     asked to hide; it never hides a cell inside a visible row.
import type {
  BatchPredictResponse,
  Endpoint,
  EndpointPrediction,
  PredictionResponse,
} from "../types/contracts";
import { ML_ENDPOINTS, STUB_MODEL_ID, ALL_ENDPOINTS } from "./endpoints";
import { reconcile, type Row } from "./reconcile";

// A cell is exactly a Predict row: same endpoint, same derived state, same
// reliability channel. Reusing the type is deliberate — it is what keeps the two
// workspaces one product rather than two dashboards.
export type BatchCell = Row;

export interface BatchRow {
  rowIndex: number;
  smilesInput: string;
  ok: boolean;
  error: string | null;
  moleculeId: string | null;
  response: PredictionResponse | null;
  cells: BatchCell[];
  flags: { outOfDomain: number; stubServed: number; notReturned: number };
}

export interface BatchSummary {
  rows: BatchRow[];
  status: BatchPredictResponse["status"];
  total: number;
  completed: number;
  counts: {
    molecules: number;
    failedRows: number;
    rowsWithOod: number;
    rowsWithStub: number;
    cellsNotReturned: number;
  };
}

/** An empty response for a molecule that failed before inference ran. */
function failedResponse(smiles: string): PredictionResponse {
  return {
    smiles_input: smiles,
    smiles_standardized: "",
    molecule_id: "",
    predictions: [],
    model_version: "",
    served_at: "",
    cache_hit: false,
  };
}

export function buildBatch(
  response: BatchPredictResponse,
  requested: Endpoint[] = ML_ENDPOINTS,
): BatchSummary {
  const results = response.results ?? [];

  const rows: BatchRow[] = results.map((r) => {
    const pred = r.ok && r.prediction ? r.prediction : failedResponse(r.smiles_input);
    const cells = reconcile(pred, requested).rows;

    // Flags count ML cells only — the rule-based SA score is shown but never
    // counted, because it is computed rather than predicted (Q1/Q2).
    const ml = cells.filter((c) => c.meta.taskType !== "rule_based");
    return {
      rowIndex: r.row_index,
      smilesInput: r.smiles_input,
      ok: r.ok,
      error: r.error ?? null,
      moleculeId: r.ok && r.prediction ? r.prediction.molecule_id : null,
      response: r.ok && r.prediction ? r.prediction : null,
      cells,
      flags: {
        outOfDomain: ml.filter((c) => c.state.kind === "out_of_domain").length,
        stubServed: ml.filter((c) => c.state.kind === "stub_served").length,
        notReturned: ml.filter((c) => c.state.kind === "not_returned").length,
      },
    };
  });

  const ok = rows.filter((r) => r.ok);
  return {
    rows,
    status: response.status,
    total: response.total,
    completed: response.completed,
    counts: {
      molecules: rows.length,
      failedRows: rows.filter((r) => !r.ok).length,
      rowsWithOod: ok.filter((r) => r.flags.outOfDomain > 0).length,
      rowsWithStub: ok.filter((r) => r.flags.stubServed > 0).length,
      cellsNotReturned: ok.reduce((n, r) => n + r.flags.notReturned, 0),
    },
  };
}

// --- sorting -----------------------------------------------------------------

export type SortSpec =
  | { kind: "input" }
  | { kind: "raw"; endpoint: Endpoint; dir: "asc" | "desc" };

function valueFor(row: BatchRow, endpoint: Endpoint): number | null {
  const cell = row.cells.find((c) => c.endpoint === endpoint);
  if (!cell?.prediction) return null;
  return cell.prediction.value;
}

/**
 * A raw numeric sort on one endpoint's value. Explicitly NOT a ranking: the
 * direction is the user's, the UI labels it "raw", and nothing is marked best.
 *
 * Rows with no value for that endpoint (not returned, or a failed row) always
 * sort last in both directions. Ordering a missing value as though it were a
 * number — low in asc, high in desc — would invent data.
 */
export function sortRows(rows: BatchRow[], spec: SortSpec): BatchRow[] {
  if (spec.kind === "input") return [...rows].sort((a, b) => a.rowIndex - b.rowIndex);
  const sign = spec.dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const va = valueFor(a, spec.endpoint);
    const vb = valueFor(b, spec.endpoint);
    if (va == null && vb == null) return a.rowIndex - b.rowIndex;
    if (va == null) return 1;
    if (vb == null) return -1;
    if (va === vb) return a.rowIndex - b.rowIndex;
    return (va - vb) * sign;
  });
}

// --- filtering ---------------------------------------------------------------

export interface FilterSpec {
  text: string;
  onlyOod: boolean;
  onlyStub: boolean;
  onlyFailed: boolean;
}

export const NO_FILTER: FilterSpec = { text: "", onlyOod: false, onlyStub: false, onlyFailed: false };

export function filterRows(rows: BatchRow[], spec: FilterSpec): BatchRow[] {
  const q = spec.text.trim().toLowerCase();
  return rows.filter((r) => {
    if (spec.onlyFailed && r.ok) return false;
    if (spec.onlyOod && r.flags.outOfDomain === 0) return false;
    if (spec.onlyStub && r.flags.stubServed === 0) return false;
    if (q) {
      const hay = `${r.smilesInput} ${r.moleculeId ?? ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

export function isFiltered(spec: FilterSpec): boolean {
  return !!spec.text.trim() || spec.onlyOod || spec.onlyStub || spec.onlyFailed;
}

// --- fixture -----------------------------------------------------------------
// Illustrative only. Deterministic (seeded, no Math.random) so values are stable
// across renders — a virtualized grid that re-randomised on scroll would be
// unusable, and unstable fixtures hide real bugs.

const POOL: [string, string][] = [
  ["CC(=O)Oc1ccccc1C(=O)O", "aspirin"],
  ["CN1C=NC2=C1C(=O)N(C)C(=O)N2C", "caffeine"],
  ["CC(C)Cc1ccc(C(C)C(=O)O)cc1", "ibuprofen"],
  ["CC(=O)Nc1ccc(O)cc1", "paracetamol"],
  ["CC1=CC=C(C=C1)C1=CC(=NN1C1=CC=C(C=C1)S(N)(=O)=O)C(F)(F)F", "celecoxib"],
  ["CC(C)NCC(O)COc1ccccc1OCC=C", "oxprenolol"],
  ["Clc1ccccc1C1=NCC(=O)Nc2ccc(Cl)cc21", "lorazepam-like"],
  ["COc1ccc2cc(ccc2c1)C(C)C(=O)O", "naproxen"],
  ["CN(C)CCCN1c2ccccc2Sc2ccc(Cl)cc21", "chlorpromazine"],
  ["OC(=O)C1=CC=CC=C1O", "salicylic acid"],
  ["CCN(CC)CCNC(=O)c1cc(Cl)c(N)cc1OC", "metoclopramide"],
  ["CC(C)(C)NCC(O)c1ccc(O)c(CO)c1", "salbutamol"],
];

function lcg(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

const REG_RANGE: Partial<Record<Endpoint, [number, number]>> = {
  solubility_logs: [-6.5, -0.5],
  lipophilicity_logp: [-0.5, 5.5],
  caco2_permeability: [-6.5, -4.2],
  ppb_binding: [55, 99.5],
  clearance_microsomal: [2, 60],
  synthetic_accessibility: [1.4, 5.2],
};

export function makeBatchFixture(n = 240, seed = 20261006): BatchPredictResponse {
  const rnd = lcg(seed);
  const results = [];

  for (let i = 0; i < n; i++) {
    const [smiles, name] = POOL[i % POOL.length];
    const id = (0x1000000 + Math.floor(rnd() * 0xeffffff)).toString(16).padStart(8, "0");

    // ~3% of rows fail validation before inference — a real, non-blocking
    // per-row error (BatchRowResult.error), not an empty row.
    if (rnd() < 0.03) {
      results.push({
        row_index: i,
        smiles_input: smiles.slice(0, Math.max(6, Math.floor(smiles.length * 0.6))),
        ok: false,
        error: "unclosed ring bond at position 14",
        prediction: null,
      });
      continue;
    }

    const oodProne = rnd() < 0.14;
    const dropClearance = rnd() < 0.18;
    const predictions: EndpointPrediction[] = [];

    for (const e of ALL_ENDPOINTS) {
      if (e === "clearance_microsomal" && dropClearance) continue;

      const range = REG_RANGE[e];
      const isReg = !!range;
      const base = isReg ? range[0] + rnd() * (range[1] - range[0]) : rnd();
      const value = isReg ? Math.round(base * 100) / 100 : Math.round(base * 100) / 100;
      const spread = isReg ? (range[1] - range[0]) * 0.06 : 0.07;
      const stub = e === "cyp2c9_inhibition";
      const inDomain = stub ? true : !(oodProne && rnd() < 0.45);

      predictions.push({
        endpoint: e,
        value,
        unit: isReg ? null : null,
        confidence_low: Math.round((value - spread) * 100) / 100,
        confidence_high: Math.round((value + spread) * 100) / 100,
        in_domain: inDomain,
        knn_distance: Math.round((inDomain ? 0.2 + rnd() * 0.3 : 0.6 + rnd() * 0.3) * 100) / 100,
        model_id: stub ? STUB_MODEL_ID : "mars-xgboost-ecfp-v1",
        ad_threshold: stub ? null : 0.58,
      });
    }

    results.push({
      row_index: i,
      smiles_input: smiles,
      ok: true,
      error: null,
      prediction: {
        smiles_input: smiles,
        smiles_standardized: smiles,
        molecule_id: `${id}${name.length.toString(16)}${(i % 16).toString(16)}`.slice(0, 16),
        predictions,
        model_version: "mars-routing@v0.3.1",
        served_at: "2026-10-06T09:12:44Z",
        cache_hit: false,
      },
    });
  }

  return { job_id: "job_7f2a19c4", status: "done", total: n, completed: n, results };
}
