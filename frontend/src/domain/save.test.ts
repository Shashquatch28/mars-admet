import { describe, expect, it } from "vitest";
import {
  buildBatchReportRequest,
  buildMoleculeRequest,
  EMPTY_SAVE_INPUT,
  moleculeKey,
  parseTags,
  reportKey,
  saveError,
  saveNote,
} from "./save";
import type { BatchPredictResponse, PredictionResponse } from "../types/contracts";

const pred = (over: Partial<PredictionResponse> = {}): PredictionResponse => ({
  smiles_input: "CCO",
  smiles_standardized: "CCO",
  molecule_id: "m1",
  predictions: [],
  model_version: "v0.2.0-dev",
  served_at: "2026-10-18T10:00:00Z",
  cache_hit: false,
  ...over,
});

describe("parseTags", () => {
  it("trims, drops blanks and case-insensitive repeats, and keeps order", () => {
    expect(parseTags(" cyp , ,Cyp, demo ,DEMO,x")).toEqual(["cyp", "demo", "x"]);
  });
  it("is empty for blank input", () => {
    expect(parseTags("")).toEqual([]);
    expect(parseTags(" , , ")).toEqual([]);
  });
});

describe("buildMoleculeRequest", () => {
  it("sends the response unchanged and nulls blank label and notes", () => {
    const p = pred();
    const r = buildMoleculeRequest(p, { label: "  ", notes: "", tags: "a, b" });
    expect(r.prediction).toBe(p);
    expect(r.label).toBeNull();
    expect(r.notes).toBeNull();
    expect(r.tags).toEqual(["a", "b"]);
  });
  it("trims what the user typed", () => {
    expect(buildMoleculeRequest(pred(), { ...EMPTY_SAVE_INPUT, label: "  aspirin ", notes: " n " })).toMatchObject({
      label: "aspirin",
      notes: "n",
    });
  });
});

describe("buildBatchReportRequest", () => {
  const results: BatchPredictResponse = { job_id: "job-1", status: "done", total: 2, completed: 2, results: [] };
  it("freezes the whole result, records the job as provenance and links no saved molecules", () => {
    const r = buildBatchReportRequest(results, { ...EMPTY_SAVE_INPUT, tags: "pilot" });
    expect(r.type).toBe("batch");
    expect(r.results).toBe(results);
    expect(r.source_batch_job_id).toBe("job-1");
    expect(r.molecule_ids).toEqual([]);
    expect(r.tags).toEqual(["pilot"]);
  });
  it("has no source job for the interactive tier", () => {
    expect(buildBatchReportRequest({ ...results, job_id: null }, EMPTY_SAVE_INPUT).source_batch_job_id).toBeNull();
    expect(buildBatchReportRequest({ status: "done", total: 0, completed: 0 }, EMPTY_SAVE_INPUT).source_batch_job_id).toBeNull();
  });
});

describe("keys", () => {
  it("tells two runs of the same molecule apart by when they were served", () => {
    expect(moleculeKey(pred())).not.toBe(moleculeKey(pred({ served_at: "2026-10-18T11:00:00Z" })));
    expect(moleculeKey(pred())).toBe(moleculeKey(pred()));
  });
  it("keys a report by the result it came from", () => {
    expect(reportKey(3)).not.toBe(reportKey(4));
  });
});

describe("saveError and saveNote", () => {
  it("says nothing was saved for every failure, with a distinct reason", () => {
    const msgs = [401, 0, 500].map((s) => saveError(s, "boom"));
    for (const m of msgs) expect(m.toLowerCase()).toContain("nothing was saved");
    expect(new Set(msgs).size).toBe(3);
    expect(saveError(422, "bad body")).toContain("bad body"); // the service's own reason is shown
  });
  it("describes a molecule save as a frozen copy that names the model and the stub caveat", () => {
    const n = saveNote("molecule", "v0.2.0-dev");
    expect(n).toContain("frozen copy");
    expect(n).toContain("v0.2.0-dev");
    expect(n).toContain("stub");
  });
  it("describes a report save with its row count and that failed rows are kept", () => {
    const n = saveNote("report", null, 1200);
    expect(n).toContain("1,200");
    expect(n).toContain("failed rows");
  });
});
