import { describe, expect, it } from "vitest";
import {
  DELETE_ACCOUNT_EFFECTS,
  deleteAccountError,
  deleteItemError,
  filterLibrary,
  newestFirst,
  provenanceLine,
  shortDate,
  summarizeSnapshot,
  toMoleculeItem,
  toReportItem,
} from "./library";
import type { PredictionResponse, SavedMoleculeResponse, SavedReportResponse } from "../types/contracts";

const pred = (version: string): PredictionResponse => ({
  smiles_input: "CCO",
  smiles_standardized: "CCO",
  molecule_id: "m1",
  predictions: [],
  model_version: version,
  served_at: "2026-10-18T10:00:00Z",
  cache_hit: false,
});

const mol = (over: Partial<SavedMoleculeResponse> = {}): SavedMoleculeResponse => ({
  id: "a",
  smiles: "CCO",
  label: null,
  notes: null,
  tags: [],
  predictions_snapshot: pred("v0.2.0-dev"),
  model_version: "v0.2.0-dev",
  created_at: "2026-10-18T09:00:00Z",
  updated_at: "2026-10-18T09:00:00Z",
  ...over,
});

const rep = (snapshot: Record<string, unknown>, over: Partial<SavedReportResponse> = {}): SavedReportResponse => ({
  id: "r",
  type: "batch",
  source_batch_job_id: null,
  results_snapshot: snapshot,
  molecule_ids: [],
  notes: null,
  tags: [],
  created_at: "2026-10-17T08:00:00Z",
  ...over,
});

describe("toMoleculeItem", () => {
  it("titles by label, falls back to the SMILES, and ignores a blank label", () => {
    expect(toMoleculeItem(mol({ label: "aspirin" })).title).toBe("aspirin");
    expect(toMoleculeItem(mol({ label: "   " })).title).toBe("CCO");
    expect(toMoleculeItem(mol()).title).toBe("CCO");
  });
  it("keeps the frozen snapshot and the model version it was made with", () => {
    const item = toMoleculeItem(mol({ model_version: "v0.1.0-dev" }));
    expect(item.modelVersion).toBe("v0.1.0-dev");
    expect(item.response.model_version).toBe("v0.2.0-dev");
  });
});

describe("provenanceLine", () => {
  it("says it is a frozen copy and names the model, never 'current'", () => {
    const line = provenanceLine(toMoleculeItem(mol()));
    expect(line).toContain("2026-10-18");
    expect(line).toContain("v0.2.0-dev");
    expect(line).toContain("frozen copy");
    expect(line.toLowerCase()).not.toContain("current");
  });
  it("does not invent a version when the service sent none", () => {
    expect(provenanceLine(toMoleculeItem(mol({ model_version: "" })))).toContain("unknown");
  });
});

describe("summarizeSnapshot", () => {
  it("counts a batch's rows and failures and lists distinct model versions", () => {
    const s = summarizeSnapshot({
      results: [
        { ok: true, prediction: pred("v2") },
        { ok: true, prediction: pred("v1") },
        { ok: false, error: "bad", prediction: null },
        { ok: true, prediction: pred("v1") },
      ],
    });
    expect(s).toEqual({ shape: "batch", rows: 4, failedRows: 1, modelVersions: ["v1", "v2"] });
  });
  it("recognises a single prediction", () => {
    expect(summarizeSnapshot({ ...pred("v1") })).toEqual({
      shape: "single",
      rows: 1,
      failedRows: 0,
      modelVersions: ["v1"],
    });
  });
  it("calls an unexpected shape unrecognised instead of zero rows of something", () => {
    expect(summarizeSnapshot({ hello: 1 }).shape).toBe("unrecognised");
    expect(summarizeSnapshot({}).rows).toBe(0);
  });
  it("survives junk inside results", () => {
    const s = summarizeSnapshot({ results: [null, 3, { ok: false }, "x"] });
    expect(s.rows).toBe(4);
    expect(s.failedRows).toBe(1);
  });
});

describe("toReportItem", () => {
  it("describes a batch by its size and date", () => {
    const item = toReportItem(rep({ results: [{ ok: true, prediction: pred("v1") }] }, { molecule_ids: ["x", "y"] }));
    expect(item.title).toBe("Batch of 1, 2026-10-17");
    expect(item.moleculeCount).toBe(2);
  });
  it("does not label an unrecognised snapshot as a batch or a molecule", () => {
    expect(toReportItem(rep({ nope: true })).title).toBe("Report, 2026-10-17");
  });
});

describe("shortDate", () => {
  it("takes the date part of an ISO datetime and passes anything else through", () => {
    expect(shortDate("2026-10-18T09:00:00Z")).toBe("2026-10-18");
    expect(shortDate("yesterday")).toBe("yesterday");
  });
});

describe("newestFirst and filterLibrary", () => {
  const a = toMoleculeItem(mol({ id: "a", created_at: "2026-10-01T00:00:00Z", label: "Alpha", tags: ["cyp"] }));
  const b = toMoleculeItem(mol({ id: "b", created_at: "2026-10-03T00:00:00Z", smiles: "c1ccccc1", notes: "ring" }));
  it("orders by saved time, newest first, without mutating the input", () => {
    const input = [a, b];
    expect(newestFirst(input).map((i) => i.id)).toEqual(["b", "a"]);
    expect(input.map((i) => i.id)).toEqual(["a", "b"]);
  });
  it("matches title, SMILES, notes and tags, ignoring case, and returns everything for a blank query", () => {
    expect(filterLibrary([a, b], "").length).toBe(2);
    expect(filterLibrary([a, b], "ALPHA").map((i) => i.id)).toEqual(["a"]);
    expect(filterLibrary([a, b], "c1cccc").map((i) => i.id)).toEqual(["b"]);
    expect(filterLibrary([a, b], "ring").map((i) => i.id)).toEqual(["b"]);
    expect(filterLibrary([a, b], "cyp").map((i) => i.id)).toEqual(["a"]);
    expect(filterLibrary([a, b], "zzz")).toEqual([]);
  });
});

describe("account and delete errors", () => {
  it("says nothing was deleted for every failure, with a distinct reason", () => {
    const msgs = [403, 401, 0, 500].map((s) => deleteAccountError(s, "boom"));
    for (const m of msgs) expect(m.toLowerCase()).toContain("nothing was deleted");
    expect(new Set(msgs).size).toBe(4);
  });
  it("treats a 404 on a saved-item delete as already gone, not an error", () => {
    expect(deleteItemError(404, "Not found")).toBeNull();
    expect(deleteItemError(500, "boom")).toContain("Nothing was deleted");
  });
  it("lists what deleting the account removes", () => {
    expect(DELETE_ACCOUNT_EFFECTS.join(" ")).toMatch(/saved molecules/);
    expect(DELETE_ACCOUNT_EFFECTS.join(" ")).toMatch(/session/);
  });
});
