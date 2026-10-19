import { describe, expect, it } from "vitest";
import { batchAnnouncement, predictionAnnouncement } from "./announce";
import type { BatchPhase, JobProgress } from "./batchJob";

const running = (completed: number, total = 100): BatchPhase => ({
  kind: "running",
  jobId: "j",
  progress: { job_id: "j", status: "running", total, completed } as JobProgress,
});

describe("predictionAnnouncement", () => {
  it("states what came back, and only mentions the reliability facts that apply", () => {
    expect(predictionAnnouncement({ requested: 14, returned: 14, outOfDomain: 0, stubServed: 0 })).toBe(
      "Prediction complete. 14 of 14 endpoints returned.",
    );
    expect(predictionAnnouncement({ requested: 14, returned: 12, outOfDomain: 3, stubServed: 2 })).toBe(
      "Prediction complete. 12 of 14 endpoints returned, 3 out of domain, 2 stub-served, 2 not returned.",
    );
  });

  it("rates nothing", () => {
    const text = predictionAnnouncement({ requested: 14, returned: 14, outOfDomain: 5, stubServed: 0 }).toLowerCase();
    for (const word of ["good", "bad", "safe", "risk", "pass", "fail", "favourable", "better"]) expect(text).not.toContain(word);
  });
});

describe("batchAnnouncement", () => {
  it("announces the start once", () => {
    expect(batchAnnouncement({ kind: "uploading", fileName: "a.csv" }, running(0))).toBe("Batch started.");
    expect(batchAnnouncement(running(0), running(3))).toBeNull();
  });

  it("announces each quarter once, not every progress event", () => {
    const events = [10, 20, 24, 25, 26, 49, 50, 74, 75, 99].map((n) => running(n));
    let prev = running(0);
    const said: string[] = [];
    for (const e of events) {
      const m = batchAnnouncement(prev, e);
      if (m) said.push(m);
      prev = e;
    }
    expect(said).toEqual(["Batch 25 percent complete.", "Batch 50 percent complete.", "Batch 75 percent complete."]);
  });

  it("announces a jump across several quarters as the latest one", () => {
    expect(batchAnnouncement(running(10), running(80))).toBe("Batch 75 percent complete.");
  });

  it("announces completion, leaves failure to its alert, and is quiet before a total is known", () => {
    expect(batchAnnouncement({ kind: "fetching", jobId: "j" }, { kind: "done" })).toBe("Batch finished. Results are in the grid.");
    expect(batchAnnouncement(running(50), { kind: "failed", message: "boom" })).toBeNull();
    const noTotal: BatchPhase = { kind: "running", jobId: "j", progress: null };
    expect(batchAnnouncement(noTotal, noTotal)).toBeNull();
  });
});
