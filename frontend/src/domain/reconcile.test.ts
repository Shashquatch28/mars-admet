import { describe, it, expect } from "vitest";
import { reconcile } from "./reconcile";
import { FIXTURE_RESPONSE } from "./fixtures";
import { displayGroupOf } from "./endpoints";

describe("reconcile (fixture)", () => {
  const r = reconcile(FIXTURE_RESPONSE);

  it("renders the full 15-row roster, in order", () => {
    expect(r.rows).toHaveLength(15);
    expect(r.rows[0].endpoint).toBe("solubility_logs");
    expect(r.rows[r.rows.length - 1].endpoint).toBe("synthetic_accessibility");
  });

  it("counts over the 14 ML endpoints only (SA excluded)", () => {
    expect(r.counts).toEqual({ requested: 14, returned: 13, outOfDomain: 2, stubServed: 1 });
  });

  it("synthesises a not_returned row for the absent endpoint", () => {
    const clearance = r.rows.find((x) => x.endpoint === "clearance_microsomal");
    expect(clearance?.state.kind).toBe("not_returned");
  });

  it("marks the out-of-domain and stub rows", () => {
    expect(r.rows.find((x) => x.endpoint === "caco2_permeability")?.reliability).toBe("ood");
    expect(r.rows.find((x) => x.endpoint === "bbb_permeability")?.reliability).toBe("ood");
    expect(r.rows.find((x) => x.endpoint === "cyp2c9_inhibition")?.reliability).toBe("stub");
  });

  it("puts synthetic_accessibility in its own trailing rule-based group", () => {
    expect(displayGroupOf("synthetic_accessibility")).toBe("rule-based");
    const last = r.groups[r.groups.length - 1];
    expect(last.group).toBe("rule-based");
    expect(last.rows.map((x) => x.endpoint)).toEqual(["synthetic_accessibility"]);
  });

  it("orders the display groups A/D/M/E/T then rule-based", () => {
    expect(r.groups.map((g) => g.group)).toEqual([
      "absorption",
      "distribution",
      "metabolism",
      "excretion",
      "toxicity",
      "rule-based",
    ]);
  });
});
