import { describe, expect, it } from "vitest";
import {
  describeResult,
  parseProgressEvents,
  percentDone,
  phaseLabel,
  settleProgress,
  validateUpload,
  type JobProgress,
} from "./batchJob";

const ev = (status: JobProgress["status"], completed = 0, total = 2000): string =>
  `data: ${JSON.stringify({ job_id: "j1", status, total, completed })}\n\n`;

describe("validateUpload", () => {
  it("accepts csv and sdf in any case", () => {
    expect(validateUpload({ name: "mols.csv", size: 10 })).toBeNull();
    expect(validateUpload({ name: "MOLS.SDF", size: 10 })).toBeNull();
  });
  it("names the file and the accepted types when the extension is wrong", () => {
    const msg = validateUpload({ name: "mols.xlsx", size: 10 });
    expect(msg).toContain("mols.xlsx");
    expect(msg).toContain(".csv");
  });
  it("refuses an empty file", () => {
    expect(validateUpload({ name: "a.csv", size: 0 })).toContain("empty");
  });
});

describe("parseProgressEvents", () => {
  it("reads complete events and keeps the unfinished tail", () => {
    const { events, rest } = parseProgressEvents(ev("running", 5) + ev("running", 9) + 'data: {"job_id":"j1","sta');
    expect(events.map((e) => e.completed)).toEqual([5, 9]);
    expect(rest).toBe('data: {"job_id":"j1","sta');
  });
  it("reassembles an event split across chunks", () => {
    const whole = ev("done", 2000);
    const a = parseProgressEvents(whole.slice(0, 20));
    expect(a.events).toEqual([]);
    const b = parseProgressEvents(a.rest + whole.slice(20));
    expect(b.events).toHaveLength(1);
    expect(b.events[0].status).toBe("done");
    expect(b.rest).toBe("");
  });
  it("handles CRLF framing", () => {
    expect(parseProgressEvents(ev("queued").replace(/\n/g, "\r\n")).events).toHaveLength(1);
  });
  it("drops a block that is not JSON or lacks job_id and status", () => {
    const { events } = parseProgressEvents('data: nope\n\ndata: {"x":1}\n\n: comment\n\n');
    expect(events).toEqual([]);
  });
  it("reads the service's unknown event, which carries no counts", () => {
    const { events } = parseProgressEvents('data: {"job_id": "j1", "status": "unknown"}\n\n');
    expect(events[0].status).toBe("unknown");
    expect(events[0].total).toBeUndefined();
  });
});

describe("percentDone", () => {
  it("is null until a total is known", () => {
    expect(percentDone(null)).toBeNull();
    expect(percentDone({ total: 0, completed: 0 })).toBeNull();
    expect(percentDone({})).toBeNull();
  });
  it("floors, clamps and never exceeds 100", () => {
    expect(percentDone({ total: 3, completed: 1 })).toBe(33);
    expect(percentDone({ total: 10, completed: 12 })).toBe(100);
    expect(percentDone({ total: 10, completed: -1 })).toBe(0);
  });
});

describe("phaseLabel", () => {
  it("states counts for a running job and says when nothing has reported", () => {
    expect(phaseLabel({ kind: "running", jobId: "j", progress: null })).toContain("Queued");
    const p: JobProgress = { job_id: "j", status: "running", total: 2000, completed: 500 };
    expect(phaseLabel({ kind: "running", jobId: "j", progress: p })).toBe("Running: 500 of 2000 molecules (25%)");
  });
  it("carries a failure message verbatim", () => {
    expect(phaseLabel({ kind: "failed", message: "boom" })).toBe("boom");
  });
});

describe("settleProgress", () => {
  it("is ok only for done", () => {
    expect(settleProgress({ job_id: "j", status: "done" })).toEqual({ ok: true });
  });
  it("treats failed, unknown, an unfinished stream and an empty stream as errors with distinct words", () => {
    const msgs = [
      settleProgress({ job_id: "j", status: "failed" }),
      settleProgress({ job_id: "j", status: "unknown" }),
      settleProgress({ job_id: "j", status: "running" }),
      settleProgress(null),
    ].map((r) => (r.ok ? "ok" : r.message));
    expect(msgs).not.toContain("ok");
    expect(new Set(msgs).size).toBe(4);
  });
});

describe("describeResult", () => {
  it("reports returned rows against the total without judging them", () => {
    expect(describeResult({ status: "done", total: 3, completed: 3, results: [], job_id: null })).toBe(
      "0 of 3 rows returned (interactive)",
    );
  });
});
