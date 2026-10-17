// The batch calls of data/client.ts against a stubbed fetch: what is sent, how the
// progress stream is read across chunk boundaries, and how errors surface.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { JobProgress } from "../domain/batchJob";

import type * as ClientModule from "./client";

type Client = typeof ClientModule;

async function loadClient(): Promise<Client> {
  vi.resetModules();
  vi.stubEnv("VITE_API_BASE", "/api");
  return import("./client");
}

const sse = (chunks: string[]): Response => {
  const enc = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      for (const ch of chunks) c.enqueue(enc.encode(ch));
      c.close();
    },
  });
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
};
const ev = (status: string, completed: number, total = 2000) =>
  `data: ${JSON.stringify({ job_id: "j1", status, total, completed })}\n\n`;

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("postBatch", () => {
  it("sends the file as multipart with the column and each endpoint as query params, credentials included", async () => {
    const { postBatch } = await loadClient();
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ job_id: null, status: "done", total: 1, completed: 1, results: [] }), { status: 200 }),
    );
    const file = new File(["smiles\nCCO\n"], "mols.csv", { type: "text/csv" });
    const r = await postBatch(file, { smilesColumn: " smiles ", endpoints: ["ames_mutagenicity", "hia_absorption"] as never });
    expect(r.status).toBe("done");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/batch/predict?smiles_column=smiles&endpoints=ames_mutagenicity&endpoints=hia_absorption");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("include");
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("file")).toBeInstanceOf(File);
    // multipart: the browser must add the boundary, so no Content-Type may be set by hand
    expect(init.headers).toBeUndefined();
  });

  it("sends no query string when there is nothing to say", async () => {
    const { postBatch } = await loadClient();
    fetchMock.mockResolvedValue(new Response("{}", { status: 200 }));
    await postBatch(new File(["x"], "a.sdf"));
    expect(fetchMock.mock.calls[0][0]).toBe("/api/batch/predict");
  });

  it("surfaces the service's reason as an ApiError carrying the status", async () => {
    const { postBatch, ApiError } = await loadClient();
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "Batch exceeds cap of 50000 molecules" }), { status: 422 }),
    );
    const err = await postBatch(new File(["x"], "a.csv")).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(422);
    expect(err.message).toBe("Batch exceeds cap of 50000 molecules");
  });
});

describe("followBatchProgress", () => {
  it("reports every event and resolves with the last one, even when chunks split an event", async () => {
    const { followBatchProgress } = await loadClient();
    const whole = ev("running", 700) + ev("done", 2000);
    fetchMock.mockResolvedValue(sse([ev("queued", 0), whole.slice(0, 15), whole.slice(15, 70), whole.slice(70)]));
    const seen: JobProgress[] = [];
    const last = await followBatchProgress("j1", (p) => seen.push(p));
    expect(seen.map((p) => p.completed)).toEqual([0, 700, 2000]);
    expect(last?.status).toBe("done");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/batch/progress/j1");
  });

  it("reads a final event that arrives without its blank-line terminator", async () => {
    const { followBatchProgress } = await loadClient();
    fetchMock.mockResolvedValue(sse([ev("running", 5).trimEnd(), ""]));
    expect((await followBatchProgress("j1", () => undefined))?.completed).toBe(5);
  });

  it("resolves null for an empty stream", async () => {
    const { followBatchProgress } = await loadClient();
    fetchMock.mockResolvedValue(sse([]));
    expect(await followBatchProgress("j1", () => undefined)).toBeNull();
  });

  it("rejects with the status when the job is not this account's", async () => {
    const { followBatchProgress } = await loadClient();
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: "Not found" }), { status: 404 }));
    await expect(followBatchProgress("nope", () => undefined)).rejects.toMatchObject({ status: 404 });
  });
});

describe("fetchBatchResults", () => {
  it("maps 410 to an error with the service's own words", async () => {
    const { fetchBatchResults } = await loadClient();
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "Results have expired and are no longer available (24h retention)" }), {
        status: 410,
      }),
    );
    await expect(fetchBatchResults("j1")).rejects.toMatchObject({ status: 410 });
  });
});
