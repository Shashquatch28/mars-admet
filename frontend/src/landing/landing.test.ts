import { afterEach, describe, expect, it, vi } from "vitest";
import { ADMET } from "./admet";
import { EXAMPLE_SMILES, SEEN_LANDING_KEY, entryTarget, hasSeenLanding, markLandingSeen } from "./entry";
import { ML_ENDPOINTS } from "../domain/endpoints";

function stubStorage(store: Record<string, string> = {}) {
  vi.stubGlobal("window", {
    localStorage: {
      getItem: (k: string) => (k in store ? store[k] : null),
      setItem: (k: string, v: string) => void (store[k] = v),
      removeItem: (k: string) => void delete store[k],
    },
  });
  return store;
}
afterEach(() => vi.unstubAllGlobals());

describe("the front door", () => {
  it("shows the landing on a first visit and Predict after that", () => {
    expect(entryTarget(false)).toBe("landing");
    expect(entryTarget(true)).toBe("predict");
  });
  it("remembers the visit in this browser only, under one key", () => {
    const store = stubStorage();
    expect(hasSeenLanding()).toBe(false);
    markLandingSeen();
    expect(store[SEEN_LANDING_KEY]).toBe("1");
    expect(hasSeenLanding()).toBe(true);
  });
  it("still works when storage is blocked: the landing is simply shown each time", () => {
    vi.stubGlobal("window", {
      localStorage: {
        getItem: () => {
          throw new Error("blocked");
        },
        setItem: () => {
          throw new Error("blocked");
        },
        removeItem: () => {
          throw new Error("blocked");
        },
      },
    });
    expect(hasSeenLanding()).toBe(false);
    expect(() => markLandingSeen()).not.toThrow();
  });
  it("offers one example, as an input only", () => {
    expect(EXAMPLE_SMILES.length).toBeGreaterThan(0);
  });
});

describe("the ADMET letters", () => {
  it("are the five categories, in order, and their counts add up to the roster's ML endpoints", () => {
    expect(ADMET.map((c) => c.label[0]).join("")).toBe("ADMET");
    expect(ADMET.reduce((n, c) => n + c.count, 0)).toBe(ML_ENDPOINTS.length);
  });
  it("leave out the rule-based score, which is not one of the counted endpoints", () => {
    expect(ADMET.map((c) => c.group)).not.toContain("rule-based");
    expect(ADMET.map((c) => c.short).join(" ")).not.toContain("SA");
  });
});
