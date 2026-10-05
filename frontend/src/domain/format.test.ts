import { describe, it, expect } from "vitest";
import { fmtNum, fmtInterval, fmtValue } from "./format";
import { ENDPOINT_METADATA } from "./endpoints";
import type { EndpointPrediction } from "../types/contracts";

const MINUS = "−";

describe("fmtNum", () => {
  it("uses a true minus sign for negatives and fixed decimals", () => {
    expect(fmtNum(-4.18)).toBe(`${MINUS}4.18`);
    expect(fmtNum(3.42)).toBe("3.42");
    expect(fmtNum(96.4, 1)).toBe("96.4");
  });
});

describe("fmtInterval", () => {
  it("joins with an ellipsis and keeps the minus sign", () => {
    expect(fmtInterval(-4.55, -3.81)).toBe(`${MINUS}4.55 … ${MINUS}3.81`);
  });
});

describe("fmtValue", () => {
  const base: EndpointPrediction = {
    endpoint: "hia_absorption",
    value: 0.94,
    unit: null,
    confidence_low: 0.87,
    confidence_high: 0.99,
    in_domain: true,
    knn_distance: 0.41,
    model_id: "mars-xgboost-ecfp-v1",
  };

  it("formats classification probability to 2dp", () => {
    expect(fmtValue(base, ENDPOINT_METADATA.hia_absorption)).toBe("0.94");
  });

  it("formats % bound regression to 1dp", () => {
    const ppb = { ...base, endpoint: "ppb_binding" as const, value: 96.4, unit: "% bound" };
    expect(fmtValue(ppb, ENDPOINT_METADATA.ppb_binding)).toBe("96.4");
  });

  it("formats other regression to 2dp with a minus sign", () => {
    const caco2 = { ...base, endpoint: "caco2_permeability" as const, value: -5.06, unit: "log cm/s" };
    expect(fmtValue(caco2, ENDPOINT_METADATA.caco2_permeability)).toBe(`${MINUS}5.06`);
  });
});
