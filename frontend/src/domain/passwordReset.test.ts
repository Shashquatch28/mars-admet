import { describe, expect, it } from "vitest";
import {
  NOT_SIGNED_IN_NOTE,
  REQUEST_ANSWER,
  requestFailureMessage,
  resetFailureMessage,
  tokenFromHash,
  validateNewPassword,
  validateResetEmail,
} from "./passwordReset";
import { resetLinkLifetime } from "./limitsCopy";
import type { LimitsResponse } from "../types/contracts";

const TOKEN = "Zk3p_9aQ-w1X0yT7bLmN2cVd5eHfGjRsUoIqAx4B8Yk";

describe("tokenFromHash", () => {
  it("reads the token from the fragment of the emailed link", () => {
    expect(tokenFromHash(`#token=${TOKEN}`)).toBe(TOKEN);
    expect(tokenFromHash(`token=${TOKEN}`)).toBe(TOKEN);
    expect(tokenFromHash(`#utm=1&token=${TOKEN}`)).toBe(TOKEN);
  });
  it("is null for a missing, empty or malformed token, so the page can say the link is incomplete", () => {
    for (const h of ["", "#", "#token=", "#token=short", "#tok=" + TOKEN, "#token=has spaces in it ok", "#token=<script>alert(1)</script>"]) {
      expect(tokenFromHash(h), h).toBeNull();
    }
  });
});

describe("validateNewPassword", () => {
  it("catches what is obvious, in words", () => {
    expect(validateNewPassword("", "")).toMatch(/Enter a new password/);
    expect(validateNewPassword("short", "short")).toMatch(/at least 8/);
    expect(validateNewPassword("a".repeat(73), "a".repeat(73))).toMatch(/at most 72 bytes/);
    expect(validateNewPassword("a-valid-password", "a-different-one")).toMatch(/not the same/);
  });
  it("counts bytes, as bcrypt does, not characters", () => {
    expect(validateNewPassword("é".repeat(40), "é".repeat(40))).toMatch(/at most 72 bytes/); // 80 bytes, 40 characters
    expect(validateNewPassword("é".repeat(30), "é".repeat(30))).toBeNull();
  });
  it("accepts a good one", () => {
    expect(validateNewPassword("a-valid-password", "a-valid-password")).toBeNull();
  });
});

describe("validateResetEmail", () => {
  it("is a cheap shape check only", () => {
    expect(validateResetEmail("")).toMatch(/Enter/);
    expect(validateResetEmail("nope")).toMatch(/does not look/);
    expect(validateResetEmail(" a@b.co ")).toBeNull();
  });
});

describe("what the screens say", () => {
  it("never claims an email was sent, or that an account exists or does not", () => {
    expect(REQUEST_ANSWER).toMatch(/^If an account exists/);
    expect(REQUEST_ANSWER).toMatch(/same answer for every address/);
    expect(REQUEST_ANSWER.toLowerCase()).not.toMatch(/was sent|we sent|has been sent|no account|not found|doesn't exist/);
  });
  it("says a reset does not sign you in and ends every session", () => {
    expect(NOT_SIGNED_IN_NOTE).toMatch(/ends every session/);
    expect(NOT_SIGNED_IN_NOTE).toMatch(/does not sign you in/);
  });
  it("gives a bad link one message whatever the reason", () => {
    expect(resetFailureMessage(400, "Invalid or expired reset token")).toMatch(/not valid.*already have been used.*expired/);
    expect(resetFailureMessage(400, "anything else")).toBe(resetFailureMessage(400, "Invalid or expired reset token"));
    expect(resetFailureMessage(429, "x")).toMatch(/Too many/);
    expect(resetFailureMessage(0, "x")).toMatch(/unreachable/);
    expect(resetFailureMessage(422, "Password must be <= 72 bytes")).toContain("72 bytes");
    expect(requestFailureMessage(0, "x")).toMatch(/unreachable/);
  });
});

describe("the link's lifetime comes from the service, never a constant", () => {
  const limits = { password_reset_ttl_minutes: 45 } as LimitsResponse;
  it("states the number /limits reported", () => {
    expect(resetLinkLifetime(limits)).toBe("The link works once and expires in 45 minutes.");
    expect(resetLinkLifetime({ password_reset_ttl_minutes: 1 } as LimitsResponse)).toContain("1 minute.");
  });
  it("leaves the number out until the service has answered", () => {
    expect(resetLinkLifetime(undefined)).toBe("The link works once and expires after a short time.");
    expect(resetLinkLifetime(undefined)).not.toMatch(/\d/);
  });
});
