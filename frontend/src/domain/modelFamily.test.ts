import { describe, expect, it } from "vitest";
import { familyLabel, fallbackCount, modelFamily, servedByFallback } from "./modelFamily";

const x = (endpoint: string, model_id: string) => ({ endpoint: endpoint as never, model_id });

describe("modelFamily", () => {
  it("reads the family from the model_id the service sent", () => {
    expect(modelFamily("mars-xgboost-ecfp-desc-v1")).toBe("xgboost");
    expect(modelFamily("mars-kermt-single-v1")).toBe("kermt");
    expect(modelFamily("mars-kermt-multitask-v1")).toBe("kermt");
    expect(modelFamily("stub-v0")).toBe("stub");
    expect(modelFamily("rdkit-sascore")).toBe("rule_based");
    expect(modelFamily("something-new")).toBe("other");
  });
  it("labels each family; a stub row has no label (its hatch and tag say it); an unknown id shows itself", () => {
    expect(familyLabel("mars-xgboost-ecfp-v1")).toBe("XGBoost");
    expect(familyLabel("mars-kermt-single-v1")).toBe("KERMT");
    expect(familyLabel("rdkit-sascore")).toBe("RDKit");
    expect(familyLabel("stub-v0")).toBe("");
    expect(familyLabel("something-new")).toBe("something-new");
  });
});

describe("servedByFallback", () => {
  const routed = ["bbb_permeability", "clearance_microsomal"];
  it("is true only for a routed endpoint answered by XGBoost", () => {
    expect(servedByFallback(x("bbb_permeability", "mars-xgboost-ecfp-desc-v1"), routed)).toBe(true);
    expect(servedByFallback(x("bbb_permeability", "mars-kermt-single-v1"), routed)).toBe(false);
    expect(servedByFallback(x("solubility_logs", "mars-xgboost-ecfp-desc-v1"), routed)).toBe(false);
  });
  it("is not a stub, not a missing row, and not a deployment with KERMT off", () => {
    expect(servedByFallback(x("bbb_permeability", "stub-v0"), routed)).toBe(false);
    expect(servedByFallback(undefined, routed)).toBe(false);
    expect(servedByFallback(x("bbb_permeability", "mars-xgboost-ecfp-desc-v1"), [])).toBe(false);
  });
  it("counts the fallbacks in a response", () => {
    const preds = [
      x("bbb_permeability", "mars-xgboost-ecfp-desc-v1"),
      x("clearance_microsomal", "mars-kermt-single-v1"),
      x("solubility_logs", "mars-xgboost-ecfp-desc-v1"),
    ];
    expect(fallbackCount(preds, routed)).toBe(1);
  });
});
