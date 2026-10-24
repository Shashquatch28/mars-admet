// The name call of data/client.ts against a stubbed fetch (ADR-044): POST with the SMILES in the body and never in the URL, the
// three answers passed through as they are, and at most three requests outstanding.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type * as ClientModule from "./client";

type Client = typeof ClientModule;

async function loadClient(): Promise<Client> {
  vi.resetModules();
  vi.stubEnv("VITE_API_BASE", "/api");
  return import("./client");
}

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const FOUND = { status: "found", inchikey: "K", source: "PubChem", source_record: "CID 2244", preferred_name: "Aspirin", synonyms: [] };

describe("fetchName", () => {
  it("posts the SMILES in the body, to /name, with nothing in the URL", async () => {
    const { fetchName } = await loadClient();
    fetchMock.mockResolvedValue(json(FOUND));
    const out = await fetchName("CC(=O)Oc1ccccc1C(=O)O");
    expect(out).toEqual(FOUND);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/name");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ smiles: "CC(=O)Oc1ccccc1C(=O)O" });
  });

  it("passes no-match and source-failure answers through as answers, not errors", async () => {
    const { fetchName } = await loadClient();
    fetchMock.mockResolvedValueOnce(json({ ...FOUND, status: "not_found", preferred_name: null }));
    fetchMock.mockResolvedValueOnce(json({ ...FOUND, status: "unavailable", reason: "PubChem could not be reached" }));
    expect((await fetchName("CCO")).status).toBe("not_found");
    expect((await fetchName("CCN")).status).toBe("unavailable");
  });

  it("raises an ApiError with the status for 429, 422 and 501", async () => {
    const { fetchName, ApiError } = await loadClient();
    for (const status of [429, 422, 501]) {
      fetchMock.mockResolvedValueOnce(json({ detail: "why" }, status));
      await expect(fetchName("CCO")).rejects.toMatchObject({ status, message: "why" });
    }
    fetchMock.mockRejectedValueOnce(new TypeError("failed"));
    await expect(fetchName("CCO")).rejects.toBeInstanceOf(ApiError);
  });

  it("keeps at most three requests outstanding and runs the rest as slots free up", async () => {
    const { fetchName } = await loadClient();
    let active = 0;
    let peak = 0;
    const release: Array<() => void> = [];
    fetchMock.mockImplementation(
      () =>
        new Promise<Response>((resolve) => {
          active++;
          peak = Math.max(peak, active);
          release.push(() => {
            active--;
            resolve(json(FOUND));
          });
        }),
    );
    const all = Promise.all(Array.from({ length: 8 }, (_, i) => fetchName(`C${"C".repeat(i)}`)));
    for (let i = 0; i < 20 && fetchMock.mock.calls.length < 8; i++) {
      await new Promise((r) => setTimeout(r, 0));
      release.splice(0).forEach((r) => r());
    }
    const out = await all;
    expect(out).toHaveLength(8);
    expect(peak).toBe(3);
    expect(fetchMock).toHaveBeenCalledTimes(8);
  });
});
