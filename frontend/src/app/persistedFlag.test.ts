import { afterEach, describe, expect, it, vi } from "vitest";
import { readFlag, writeFlag } from "./persistedFlag";

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

describe("persisted flag", () => {
  it("starts false and remembers true", () => {
    const store = stubStorage();
    expect(readFlag("k")).toBe(false);
    writeFlag("k", true);
    expect(store.k).toBe("1");
    expect(readFlag("k")).toBe(true);
  });

  it("forgets the key when turned off, so the default is the stored state", () => {
    const store = stubStorage({ k: "1" });
    writeFlag("k", false);
    expect("k" in store).toBe(false);
    expect(readFlag("k")).toBe(false);
  });

  it("works when storage throws (blocked or private window): reads false, writes do nothing", () => {
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
    expect(readFlag("k")).toBe(false);
    expect(() => writeFlag("k", true)).not.toThrow();
  });

  it("works when there is no window at all", () => {
    vi.stubGlobal("window", undefined);
    expect(readFlag("k")).toBe(false);
    expect(() => writeFlag("k", true)).not.toThrow();
  });
});
