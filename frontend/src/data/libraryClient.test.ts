// The Library and account calls of data/client.ts against a stubbed fetch.
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

describe("library reads", () => {
  it("lists saved molecules and reports with credentials", async () => {
    const { fetchSavedMolecules, fetchSavedReports } = await loadClient();
    fetchMock.mockResolvedValueOnce(new Response("[]", { status: 200 })).mockResolvedValueOnce(new Response("[]", { status: 200 }));
    expect(await fetchSavedMolecules()).toEqual([]);
    expect(await fetchSavedReports()).toEqual([]);
    expect(fetchMock.mock.calls.map((c) => c[0])).toEqual(["/api/molecules", "/api/reports"]);
    expect((fetchMock.mock.calls[0][1] as RequestInit).credentials).toBe("include");
  });
});

describe("library deletes", () => {
  it("sends DELETE to the owner-scoped route with the id escaped", async () => {
    const { deleteSavedMolecule, deleteSavedReport } = await loadClient();
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await deleteSavedMolecule("a/b");
    await deleteSavedReport("r1");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/molecules/a%2Fb");
    expect((fetchMock.mock.calls[0][1] as RequestInit).method).toBe("DELETE");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/reports/r1");
  });
  it("reports a 404 with its status so the caller can treat it as already gone", async () => {
    const { deleteSavedMolecule } = await loadClient();
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: "Not found" }), { status: 404 }));
    await expect(deleteSavedMolecule("x")).rejects.toMatchObject({ status: 404 });
  });
});

describe("deleteAccount", () => {
  it("sends the password as a JSON body on DELETE /account", async () => {
    const { deleteAccount } = await loadClient();
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await deleteAccount("hunter22");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/account");
    expect(init.method).toBe("DELETE");
    expect(init.credentials).toBe("include");
    expect(new Headers(init.headers).get("Content-Type")).toBe("application/json");
    expect(JSON.parse(init.body as string)).toEqual({ password: "hunter22" });
  });
  it("surfaces a wrong password as a 403 without firing the session-ended handler", async () => {
    const { deleteAccount, setUnauthorizedHandler } = await loadClient();
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: "Incorrect password" }), { status: 403 }));
    await expect(deleteAccount("nope")).rejects.toMatchObject({ status: 403, message: "Incorrect password" });
    expect(onUnauthorized).not.toHaveBeenCalled();
  });
  it("fires the session-ended handler on a 401, which is not a wrong password", async () => {
    const { deleteAccount, setUnauthorizedHandler } = await loadClient();
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: "Not authenticated" }), { status: 401 }));
    await expect(deleteAccount("x")).rejects.toMatchObject({ status: 401 });
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });
});
