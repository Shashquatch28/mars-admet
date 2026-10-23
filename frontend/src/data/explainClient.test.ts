// The explanation calls of data/client.ts against a stubbed fetch (ADR-035): three verbs on one URL, and the
// three kinds of answer (a result, a job, nothing started) told apart by status and shape.
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

const JOB = { job_id: "j1", state: "running", seeds_done: 1, seeds_total: 3 };
const RESULT = { molecule_id: "m", atom_attributions: [0.1], model_id: "mars-kermt-toxicity-cls-v1" };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

describe("explanation calls", () => {
  it("reads with GET, starts with POST and cancels with DELETE, on the same escaped URL", async () => {
    const { readExplanation, startExplanation, cancelExplanation } = await loadClient();
    fetchMock.mockImplementation(() => Promise.resolve(new Response(null, { status: 204 })));
    await readExplanation("a/b", "herg_cardiotoxicity");
    await startExplanation("a/b", "herg_cardiotoxicity");
    await cancelExplanation("a/b", "herg_cardiotoxicity");
    const calls = fetchMock.mock.calls.map((c) => [(c[1] as RequestInit).method, c[0]]);
    expect(calls).toEqual([
      ["GET", "/api/molecule/a%2Fb/explain?endpoint=herg_cardiotoxicity"],
      ["POST", "/api/molecule/a%2Fb/explain?endpoint=herg_cardiotoxicity"],
      ["DELETE", "/api/molecule/a%2Fb/explain?endpoint=herg_cardiotoxicity"],
    ]);
  });

  it("204 is nothing started, 202 a job, 200 a result, and a 200 job (a cancelled one) is still a job", async () => {
    const { readExplanation } = await loadClient();
    fetchMock
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(json(JOB, 202))
      .mockResolvedValueOnce(json(RESULT))
      .mockResolvedValueOnce(json({ ...JOB, state: "cancelled" }));
    expect(await readExplanation("m", "herg_cardiotoxicity")).toEqual({ kind: "none" });
    expect(await readExplanation("m", "herg_cardiotoxicity")).toEqual({ kind: "job", job: JOB });
    expect(await readExplanation("m", "herg_cardiotoxicity")).toEqual({ kind: "result", data: RESULT });
    expect(await readExplanation("m", "herg_cardiotoxicity")).toMatchObject({ kind: "job", job: { state: "cancelled" } });
  });

  it("errors carry their status and the server's words, so the panel can tell a failed job from a full queue", async () => {
    const { readExplanation } = await loadClient();
    fetchMock.mockResolvedValue(json({ detail: "its descriptor vector has non-finite values" }, 422));
    await expect(readExplanation("m", "herg_cardiotoxicity")).rejects.toMatchObject({
      status: 422,
      message: "its descriptor vector has non-finite values",
    });
  });
});
