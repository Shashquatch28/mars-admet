import { describe, expect, it } from "vitest";
import { batchGateWhy, batchUploadNote, expiredResultsMessage } from "./limitsCopy";
import type { LimitsResponse } from "../types/contracts";

const limits: LimitsResponse = {
  batch_size_cap: 7000,
  batch_interactive_threshold: 20,
  batch_result_retention_hours: 12,
  anon_predict_rate_per_minute: 30,
  password_reset_ttl_minutes: 45,
};

describe("limits copy", () => {
  it("states the numbers the service reported, not constants", () => {
    const note = batchUploadNote(limits);
    expect(note).toContain("Up to 20 molecules are returned directly");
    expect(note).toContain("up to 7,000");
    expect(note).toContain("kept for 12 hours");
    expect(note).not.toMatch(/\b100\b|50,000|24 hours/);
    expect(batchGateWhy(limits)).toContain("up to 7,000 molecules");
    expect(expiredResultsMessage(limits)).toContain("kept for 12 hours");
  });
  it("says one hour in the singular", () => {
    expect(expiredResultsMessage({ ...limits, batch_result_retention_hours: 1 })).toContain("kept for 1 hour;");
  });
  it("leaves every number out until the service has answered", () => {
    for (const text of [batchUploadNote(undefined), batchGateWhy(undefined), expiredResultsMessage(undefined)]) {
      expect(text).not.toMatch(/\d/);
    }
  });
});
