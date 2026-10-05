import { describe, it, expect } from "vitest";
import { deriveRowState, reliabilityOf } from "./rowState";
import { ENDPOINT_METADATA } from "./endpoints";
import type { EndpointPrediction } from "../types/contracts";

function pred(over: Partial<EndpointPrediction>): EndpointPrediction {
  return {
    endpoint: "hia_absorption",
    value: 0.5,
    unit: null,
    confidence_low: 0.4,
    confidence_high: 0.6,
    in_domain: true,
    knn_distance: 0.3,
    model_id: "mars-xgboost-ecfp-v1",
    ...over,
  };
}

describe("deriveRowState", () => {
  it("is not_returned when there is no prediction", () => {
    expect(deriveRowState(ENDPOINT_METADATA.hia_absorption, undefined)).toEqual({ kind: "not_returned" });
  });

  it("is rule_based for a rule-based endpoint regardless of the prediction", () => {
    const s = deriveRowState(ENDPOINT_METADATA.synthetic_accessibility, pred({ endpoint: "synthetic_accessibility" }));
    expect(s).toEqual({ kind: "rule_based" });
  });

  it("is stub_served when model_id is the stub", () => {
    const s = deriveRowState(ENDPOINT_METADATA.cyp2c9_inhibition, pred({ model_id: "stub-v0" }));
    expect(s).toEqual({ kind: "stub_served", modelId: "stub-v0" });
  });

  it("gives stub precedence over out-of-domain", () => {
    // A stub value is 'not a real prediction' — a more fundamental fact than AD,
    // which does not apply without a promoted model.
    const s = deriveRowState(ENDPOINT_METADATA.cyp2c9_inhibition, pred({ model_id: "stub-v0", in_domain: false }));
    expect(s.kind).toBe("stub_served");
  });

  it("is out_of_domain for a real model outside its domain, carrying the distance", () => {
    const s = deriveRowState(ENDPOINT_METADATA.caco2_permeability, pred({ in_domain: false, knn_distance: 0.71 }));
    expect(s).toEqual({ kind: "out_of_domain", knnDistance: 0.71 });
  });

  it("is ok for an in-domain real-model prediction", () => {
    expect(deriveRowState(ENDPOINT_METADATA.hia_absorption, pred({ in_domain: true })).kind).toBe("ok");
  });
});

describe("reliabilityOf", () => {
  it("maps each state to its single visual channel", () => {
    expect(reliabilityOf({ kind: "ok" })).toBeNull();
    expect(reliabilityOf({ kind: "out_of_domain", knnDistance: 0.7 })).toBe("ood");
    expect(reliabilityOf({ kind: "stub_served", modelId: "stub-v0" })).toBe("stub");
    expect(reliabilityOf({ kind: "not_returned" })).toBe("notreturned");
    expect(reliabilityOf({ kind: "rule_based" })).toBe("rule");
  });
});
