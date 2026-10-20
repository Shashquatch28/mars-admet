import { describe, expect, it } from "vitest";
import type { EndpointPrediction, ExplainResponse } from "../types/contracts";
import {
  atomHighlights,
  explainView,
  fmtSigned,
  focusHighlights,
  fragmentKey,
  outputSpaceLabel,
  signOf,
  totalRows,
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
  n_steps: 64,
  model_version: "v",
};

const base: ExplainInputs = {
  rowState: { kind: "ok" },
  prediction: PRED,
  asked: true,
  isPending: false,
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

  it("is idle until the user asks, then loading, then ready", () => {
    expect(explainView({ ...base, asked: false }).kind).toBe("idle");
    expect(explainView({ ...base, isPending: true }).kind).toBe("loading");
    expect(explainView({ ...base, data: DATA })).toEqual({ kind: "ready", data: DATA });
  });

  it("an out-of-domain value can still be explained: reliability is a separate channel", () => {
    expect(explainView({ ...base, rowState: { kind: "out_of_domain", knnDistance: 0.9 }, data: DATA }).kind).toBe("ready");
  });

  it("refuses to show an explanation of a different model than the value on screen", () => {
    const v = explainView({ ...base, data: { ...DATA, model_id: "mars-xgboost-ecfp-desc-v1" } });
    expect(v).toEqual({ kind: "mismatch", explained: "mars-xgboost-ecfp-desc-v1", served: "mars-kermt-toxicity-cls-v1" });
  });

  it("maps each service answer to its own state", () => {
    const err = (status: number) => explainView({ ...base, error: { status, message: "m" } }).kind;
    expect(err(404)).toBe("expired");
    expect(err(409)).toBe("no_model");
    expect(err(501)).toBe("unsupported");
    expect(err(503)).toBe("busy");
    expect(err(500)).toBe("error");
    expect(err(0)).toBe("error");
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
