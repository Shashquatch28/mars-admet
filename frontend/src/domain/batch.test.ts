import { describe, expect, it } from "vitest";
import {
  buildBatch,
  filterRows,
  makeBatchFixture,
  sortRows,
  NO_FILTER,
  type BatchRow,
} from "./batch";
import { ALL_ENDPOINTS, ML_ENDPOINTS } from "./endpoints";
import type { BatchPredictResponse, PredictionResponse } from "../types/contracts";

function pred(over: Partial<PredictionResponse> = {}): PredictionResponse {
  return {
    smiles_input: "CCO",
    smiles_standardized: "CCO",
    molecule_id: "abc123",
    predictions: [],
    model_version: "v1",
    served_at: "2026-10-06T00:00:00Z",
    cache_hit: false,
    ...over,
  };
}

const resp = (results: BatchPredictResponse["results"]): BatchPredictResponse => ({
  job_id: null,
  status: "done",
  total: results?.length ?? 0,
  completed: results?.length ?? 0,
  results,
});

describe("buildBatch", () => {
  it("gives every row one cell per endpoint, even when nothing was returned", () => {
    const b = buildBatch(resp([{ row_index: 0, smiles_input: "CCO", ok: true, error: null, prediction: pred() }]));
    expect(b.rows).toHaveLength(1);
    expect(b.rows[0].cells).toHaveLength(ALL_ENDPOINTS.length);
    // nothing returned => every ML cell is not_returned, none are dropped
    expect(b.rows[0].flags.notReturned).toBe(ML_ENDPOINTS.length);
  });

  it("keeps a failed row as a row, with its error", () => {
    const b = buildBatch(
      resp([{ row_index: 0, smiles_input: "C1CC", ok: false, error: "unclosed ring", prediction: null }]),
    );
    expect(b.rows[0].ok).toBe(false);
    expect(b.rows[0].error).toBe("unclosed ring");
    expect(b.rows[0].cells).toHaveLength(ALL_ENDPOINTS.length);
    expect(b.counts.failedRows).toBe(1);
  });

  it("excludes the rule-based endpoint from the flag counts", () => {
    const b = buildBatch(
      resp([
        {
          row_index: 0,
          smiles_input: "CCO",
          ok: true,
          error: null,
          prediction: pred({
            predictions: [
              {
                endpoint: "synthetic_accessibility",
                value: 2.4,
                unit: "SA score",
                confidence_low: 2.4,
                confidence_high: 2.4,
                in_domain: true,
                knn_distance: 0,
                model_id: "rdkit-sascore",
              },
            ],
          }),
        },
      ]),
    );
    // SA is present as a cell but never counted as returned/ood/stub
    expect(b.rows[0].cells.some((c) => c.endpoint === "synthetic_accessibility")).toBe(true);
    expect(b.rows[0].flags.notReturned).toBe(ML_ENDPOINTS.length);
  });

  it("counts rows with out-of-domain and stub cells, ignoring failed rows", () => {
    const b = buildBatch(makeBatchFixture(60));
    const ok = b.rows.filter((r) => r.ok);
    expect(b.counts.molecules).toBe(60);
    expect(b.counts.rowsWithStub).toBe(ok.length); // cyp2c9 is stub for every row
    expect(b.counts.failedRows).toBe(b.rows.length - ok.length);
  });
});

describe("sortRows", () => {
  const b = buildBatch(makeBatchFixture(40));

  it("input order is the contract row_index", () => {
    const sorted = sortRows(b.rows, { kind: "input" });
    expect(sorted.map((r) => r.rowIndex)).toEqual([...b.rows.map((r) => r.rowIndex)].sort((x, y) => x - y));
  });

  it("raw sort orders by the endpoint value in the requested direction", () => {
    const asc = sortRows(b.rows, { kind: "raw", endpoint: "lipophilicity_logp", dir: "asc" });
    const vals = asc
      .map((r) => r.cells.find((c) => c.endpoint === "lipophilicity_logp")?.prediction?.value)
      .filter((v): v is number => v != null);
    expect(vals).toEqual([...vals].sort((x, y) => x - y));
  });

  it("sorts rows with no value last in BOTH directions, never as a number", () => {
    const missing: BatchRow[] = buildBatch(
      resp([
        { row_index: 0, smiles_input: "A", ok: true, error: null, prediction: pred() }, // nothing returned
        {
          row_index: 1,
          smiles_input: "B",
          ok: true,
          error: null,
          prediction: pred({
            predictions: [
              {
                endpoint: "lipophilicity_logp",
                value: 3.4,
                unit: "logP",
                confidence_low: 3.1,
                confidence_high: 3.7,
                in_domain: true,
                knn_distance: 0.3,
                model_id: "mars-xgboost-ecfp-v1",
              },
            ],
          }),
        },
      ]),
    ).rows;

    for (const dir of ["asc", "desc"] as const) {
      const sorted = sortRows(missing, { kind: "raw", endpoint: "lipophilicity_logp", dir });
      expect(sorted[sorted.length - 1].smilesInput).toBe("A");
    }
  });
});

describe("filterRows", () => {
  const b = buildBatch(makeBatchFixture(80));

  it("no filter returns everything", () => {
    expect(filterRows(b.rows, NO_FILTER)).toHaveLength(b.rows.length);
  });

  it("onlyFailed keeps only rows the service could not process", () => {
    const out = filterRows(b.rows, { ...NO_FILTER, onlyFailed: true });
    expect(out.every((r) => !r.ok)).toBe(true);
  });

  it("onlyOod keeps only rows carrying at least one out-of-domain cell", () => {
    const out = filterRows(b.rows, { ...NO_FILTER, onlyOod: true });
    expect(out.every((r) => r.flags.outOfDomain > 0)).toBe(true);
  });

  it("text matches smiles or molecule id", () => {
    const target = b.rows.find((r) => r.ok)!;
    const out = filterRows(b.rows, { ...NO_FILTER, text: target.moleculeId!.slice(0, 6) });
    expect(out.some((r) => r.moleculeId === target.moleculeId)).toBe(true);
  });

  it("filtering never removes cells from a visible row", () => {
    const out = filterRows(b.rows, { ...NO_FILTER, onlyOod: true });
    for (const r of out) expect(r.cells).toHaveLength(ALL_ENDPOINTS.length);
  });
});

describe("makeBatchFixture", () => {
  it("is deterministic for a given seed", () => {
    const a = JSON.stringify(makeBatchFixture(25, 7));
    const b = JSON.stringify(makeBatchFixture(25, 7));
    expect(a).toBe(b);
  });
});
