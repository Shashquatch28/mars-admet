import { describe, expect, it } from "vitest";
import type { EndpointPrediction, ExplainJobStatus, ExplainResponse } from "../types/contracts";
import { explainAnnouncement } from "./announce";
import {
  atomHighlights,
  convergenceNote,
  describeJob,
  explainView,
  fmtDuration,
  fmtSigned,
  focusHighlights,
  fragmentKey,
  isAskable,
  outputSpaceLabel,
  seedAgreementNote,
  shouldPoll,
  signOf,
  totalRows,
  type ExplainAnswer,
  type ExplainInputs,
} from "./explain";

const PRED = { endpoint: "herg_cardiotoxicity", model_id: "mars-kermt-toxicity-cls-v1" } as EndpointPrediction;

const DATA: ExplainResponse = {
  molecule_id: "0123456789abcdef",
  endpoint: "herg_cardiotoxicity",
  method: "integrated_gradients",
  model_id: "mars-kermt-toxicity-cls-v1",
  output_space: "score",
  unit: null,
  n_seeds: 3,
  base_value: 0.4,
  output_value: 0.7,
  baseline: "empty graph",
  atom_attributions: [0.2, -0.1, 0],
  fragment_attributions: [],
  whole_molecule_attributions: [],
  whole_molecule_rest: 0,
  structure_total: 0.1,
  whole_molecule_total: 0.2,
  unmapped_total: 0,
  completeness_error: 0,
  converged: true,
  seed_agreement: 0.8,
  n_steps: 64,
  model_version: "v",
};

const JOB: ExplainJobStatus = {
  job_id: "j1",
  molecule_id: "0123456789abcdef",
  endpoint: "herg_cardiotoxicity",
  state: "running",
  queue_position: null,
  seeds_done: 1,
  seeds_total: 3,
  stage: "seed 2 of 3, 128 steps",
  elapsed_seconds: 125,
  submitted_at: "2026-10-23T10:00:00Z",
  error: null,
};
const result = (data: ExplainResponse = DATA): ExplainAnswer => ({ kind: "result", data });
const job = (over: Partial<ExplainJobStatus> = {}): ExplainAnswer => ({ kind: "job", job: { ...JOB, ...over } });

const base: ExplainInputs = {
  rowState: { kind: "ok" },
  prediction: PRED,
  pending: null,
  error: null,
};

describe("explainView", () => {
  it("nothing to explain without a model: each row state says why, in words", () => {
    for (const kind of ["not_requested", "not_returned", "stub_served", "rule_based"] as const) {
      const rowState = kind === "stub_served" ? ({ kind, modelId: "stub-v0" } as const) : ({ kind } as const);
      const v = explainView({ ...base, rowState });
      expect(v.kind).toBe("not_askable");
      expect(v.kind === "not_askable" && v.why.length).toBeGreaterThan(20);
    }
  });

  it("is idle until the user starts it, then starting, then ready", () => {
    expect(explainView(base)).toEqual({ kind: "idle", cancelled: false, background: true });
    expect(explainView({ ...base, answer: { kind: "none" } }).kind).toBe("idle");
    expect(explainView({ ...base, pending: "check" }).kind).toBe("checking");
    expect(explainView({ ...base, pending: "start" }).kind).toBe("starting");
    expect(explainView({ ...base, answer: result() })).toEqual({ kind: "ready", data: DATA });
  });

  it("a tree model is not described as a background job, a graph model is", () => {
    const xgb = { endpoint: "solubility_logs", model_id: "mars-xgboost-ecfp-desc-v1" } as EndpointPrediction;
    expect(explainView({ ...base, prediction: xgb })).toMatchObject({ kind: "idle", background: false });
    expect(explainView(base)).toMatchObject({ kind: "idle", background: true });
  });

  it("a queued or running job is shown as a job, and a refresh mid-poll keeps showing it", () => {
    expect(explainView({ ...base, answer: job({ state: "queued", queue_position: 2 }) }).kind).toBe("job");
    expect(explainView({ ...base, answer: job(), pending: "check" }).kind).toBe("job");
    expect(explainView({ ...base, answer: job(), stopping: true })).toMatchObject({ kind: "job", stopping: true });
  });

  it("a cancelled job returns to idle and says so", () => {
    expect(explainView({ ...base, answer: job({ state: "cancelled" }) })).toMatchObject({ kind: "idle", cancelled: true });
  });

  it("only rows with a model are read from the server", () => {
    expect(isAskable({ kind: "ok" }, PRED)).toBe(true);
    expect(isAskable({ kind: "out_of_domain", knnDistance: 0.9 }, PRED)).toBe(true);
    expect(isAskable({ kind: "stub_served", modelId: "stub-v0" }, PRED)).toBe(false);
    expect(isAskable({ kind: "not_returned" }, undefined)).toBe(false);
  });

  it("an out-of-domain value can still be explained: reliability is a separate channel", () => {
    expect(explainView({ ...base, rowState: { kind: "out_of_domain", knnDistance: 0.9 }, answer: result() }).kind).toBe("ready");
  });

  it("refuses to show an explanation of a different model than the value on screen", () => {
    const v = explainView({ ...base, answer: result({ ...DATA, model_id: "mars-xgboost-ecfp-desc-v1" }) });
    expect(v).toEqual({ kind: "mismatch", explained: "mars-xgboost-ecfp-desc-v1", served: "mars-kermt-toxicity-cls-v1" });
  });

  it("maps each service answer to its own state", () => {
    const err = (status: number) => explainView({ ...base, error: { status, message: "m" } }).kind;
    expect(err(404)).toBe("expired");
    expect(err(409)).toBe("no_model");
    expect(err(422)).toBe("unexplainable");
    expect(err(429)).toBe("limited");
    expect(err(501)).toBe("unsupported");
    expect(err(503)).toBe("busy");
    expect(err(500)).toBe("error");
    expect(err(0)).toBe("error");
  });
});

describe("job progress, in words", () => {
  it("says where a queued job is, never a percentage or a time left", () => {
    const d = describeJob({ ...JOB, state: "queued", queue_position: 2, seeds_done: 0, stage: null, elapsed_seconds: 7 });
    expect(d).toEqual({ status: "Waiting in the queue, position 2.", detail: null, elapsed: "Elapsed 7 s." });
  });
  it("says which seed and how many steps a running job is on", () => {
    const d = describeJob(JOB);
    expect(d.status).toBe("Running: seed 2 of 3, 128 steps.");
    expect(d.detail).toBe("1 of 3 seeds attributed so far.");
    expect(d.elapsed).toBe("Elapsed 2 min 05 s.");
    expect(JSON.stringify(d)).not.toMatch(/%|remaining|bleftb|betab|about/i);
  });
  it("formats durations", () => {
    expect([fmtDuration(0), fmtDuration(59.6), fmtDuration(60), fmtDuration(1085)]).toEqual([
      "0 s",
      "1 min 00 s",
      "1 min 00 s",
      "18 min 05 s",
    ]);
  });
  it("polls only a queued or running job", () => {
    expect(shouldPoll(job())).toBe(true);
    expect(shouldPoll(job({ state: "queued" }))).toBe(true);
    expect(shouldPoll(job({ state: "cancelled" }))).toBe(false);
    expect(shouldPoll(result())).toBe(false);
    expect(shouldPoll({ kind: "none" })).toBe(false);
    expect(shouldPoll(undefined)).toBe(false);
  });
});

describe("what a finished explanation says about itself", () => {
  it("says nothing extra when it converged, or when the method has no iteration", () => {
    expect(convergenceNote(DATA)).toBeNull();
    expect(convergenceNote({ ...DATA, converged: null })).toBeNull();
  });
  it("says in words how much was left unplaced when it did not converge", () => {
    const note = convergenceNote({ ...DATA, converged: false, n_steps: 256, unmapped_total: -0.1234 });
    expect(note).toContain("256 steps");
    expect(note).toContain("0.123");
    expect(note).toContain("still add up");
  });
  it("describes seed agreement as a number and what it measures, without a verdict", () => {
    expect(seedAgreementNote({ ...DATA, seed_agreement: null })).toBeNull();
    const note = seedAgreementNote({ ...DATA, seed_agreement: 0.2 }) ?? "";
    expect(note).toContain("0.20");
    expect(note).not.toMatch(/\b(risk|safe|good|bad|better|worse|reliable|unreliable|poor)\b/i);
  });
});

describe("announcements", () => {
  it("announces the start and the end of a long explanation, not each poll", () => {
    expect(explainAnnouncement("starting", { kind: "job" })).toMatch(/started/);
    expect(explainAnnouncement("job", { kind: "job" })).toBeNull();
    expect(explainAnnouncement("job", { kind: "ready" })).toBe("Explanation ready.");
    expect(explainAnnouncement("starting", { kind: "ready" })).toBe("Explanation ready.");
    expect(explainAnnouncement("job", { kind: "idle" })).toBe("Explanation cancelled.");
    expect(explainAnnouncement("job", { kind: "busy" })).toMatch(/could not be completed/);
  });
  it("is silent when a cached result is simply shown, or when the row changed", () => {
    expect(explainAnnouncement("checking", { kind: "ready" })).toBeNull();
    expect(explainAnnouncement(null, { kind: "job" })).toBeNull();
    expect(explainAnnouncement("idle", { kind: "idle" })).toBeNull();
  });
});

describe("signed numbers", () => {
  it("uses a true minus and no sign on zero", () => {
    expect(fmtSigned(0.123)).toBe("+0.12");
    expect(fmtSigned(-0.123)).toBe("−0.12");
    expect(fmtSigned(0)).toBe("0.00");
  });
  it("a value that prints as zero carries no direction", () => {
    expect(signOf(0.004)).toBe("none");
    expect(signOf(-0.004)).toBe("none");
    expect(fmtSigned(-0.004)).toBe("0.00");
    expect(signOf(0.006)).toBe("up");
  });
});

describe("totals and labels", () => {
  it("lists the parts that add up, and marks only contributions with a sign", () => {
    const rows = totalRows(DATA);
    expect(rows.map((r) => r.key)).toEqual(["base", "structure", "whole", "unmapped", "output"]);
    expect(rows.find((r) => r.key === "structure")).toMatchObject({ text: "+0.10", sign: "up" });
    expect(rows.find((r) => r.key === "base")).toMatchObject({ text: "0.40", sign: "none" });
    expect(rows.find((r) => r.key === "output")?.sign).toBe("none");
  });
  it("names the output space, never calls a classification attribution a probability", () => {
    expect(outputSpaceLabel("log_odds", "ames_mutagenicity")).toBe("log-odds");
    expect(outputSpaceLabel("score", "herg_cardiotoxicity")).toBe("score");
    expect(outputSpaceLabel("native_unit", "solubility_logs")).toBe("logS");
  });
  it("never uses judgement words anywhere in its fixed text", () => {
    const text = JSON.stringify(totalRows(DATA)) + JSON.stringify(explainView({ ...base, rowState: { kind: "stub_served", modelId: "x" } }));
    expect(text).not.toMatch(/\b(risk|risky|safe|toxic|favou?rable|good|bad|better|worse)\b/i);
  });
});

describe("atomHighlights", () => {
  it("scales strength by this molecule's largest atom and keeps sign", () => {
    const h = atomHighlights([0.2, -0.1, 0]);
    expect(h.map((a) => a.sign)).toEqual(["up", "down", "none"]);
    expect(h.map((a) => a.strength)).toEqual([1, 0.5, 0]);
  });
  it("an all-zero structure part highlights nothing", () => {
    expect(atomHighlights([0, 0]).every((a) => a.sign === "none" && a.strength === 0)).toBe(true);
  });
});

describe("focusing one group", () => {
  it("keys a group by kind and atoms, so two groups of one kind differ", () => {
    expect(fragmentKey({ name: "benzene rings", atom_indices: [0, 1] })).not.toBe(
      fragmentKey({ name: "benzene rings", atom_indices: [5, 6] }),
    );
  });
  it("keeps the chosen atoms and returns every other atom to the element palette", () => {
    const all = atomHighlights([0.2, -0.1, 0.4]);
    const f = focusHighlights(all, [1]);
    expect(f.map((h) => h.sign)).toEqual(["none", "down", "none"]);
    expect(f.map((h) => h.strength)).toEqual([0, 0.25, 0]);
  });
});
