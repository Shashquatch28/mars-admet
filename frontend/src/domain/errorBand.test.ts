import { describe, expect, it } from "vitest";
import { errorBandNote, errorBandOf } from "./errorBand";
import type { EndpointPrediction } from "../types/contracts";

const base: EndpointPrediction = {
  endpoint: "solubility_logs",
  value: -4.2,
  unit: null,
  confidence_low: -4.3,
  confidence_high: -4.1,
  in_domain: true,
  knn_distance: 0.3,
  ad_threshold: 0.5,
  model_id: "mars-xgboost-ecfp-desc-v1",
};

describe("errorBandOf", () => {
  it("reads a complete band", () => {
    const b = errorBandOf({ ...base, heldout_error_halfwidth: 1.677, heldout_error_level: 0.9, heldout_error_n: 4700 });
    expect(b).toEqual({ halfwidth: 1.677, levelPct: 90, n: 4700 });
  });

  it("is null when the service sent none (older response, classification, stub)", () => {
    expect(errorBandOf(base)).toBeNull();
    expect(errorBandOf({ ...base, heldout_error_halfwidth: null, heldout_error_level: null, heldout_error_n: null })).toBeNull();
  });

  it("is null when the band is partial or nonsensical, rather than showing half a claim", () => {
    const full = { heldout_error_halfwidth: 1, heldout_error_level: 0.9, heldout_error_n: 100 };
    expect(errorBandOf({ ...base, ...full, heldout_error_level: null })).toBeNull();
    expect(errorBandOf({ ...base, ...full, heldout_error_n: null })).toBeNull();
    expect(errorBandOf({ ...base, ...full, heldout_error_halfwidth: 0 })).toBeNull();
    expect(errorBandOf({ ...base, ...full, heldout_error_halfwidth: Number.NaN })).toBeNull();
    expect(errorBandOf({ ...base, ...full, heldout_error_level: 1.2 })).toBeNull();
    expect(errorBandOf({ ...base, ...full, heldout_error_n: 0 })).toBeNull();
  });
});

describe("errorBandNote", () => {
  it("states what was measured and what it is not, with no evaluative wording", () => {
    const text = errorBandNote({ halfwidth: 1.677, levelPct: 90, n: 4700 });
    expect(text).toContain("90% of the 4,700 errors");
    expect(text).toContain("not a range for this molecule");
    expect(text).toContain("not a guarantee for an out-of-domain one");
    expect(text).not.toMatch(/\b(good|safe|better|worse|reliable|confidence|certain)\b/i);
  });
});
