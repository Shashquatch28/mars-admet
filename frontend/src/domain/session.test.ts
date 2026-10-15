// Session logic and the auth client, against REAL captured responses
// (src/domain/real-responses/auth-*.json; see its README). ADR-022.
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MeResponse } from "../types/contracts";
import {
  accountInitial,
  authErrorMessage,
  isGatedPath,
  mustSignIn,
  sessionStatus,
  showsLock,
  validateCredentials,
} from "./session";

import me200 from "./real-responses/auth-me-200.json";
import me401 from "./real-responses/auth-me-401.json";
import login200 from "./real-responses/auth-login-200.json";
import login401 from "./real-responses/auth-login-401.json";
import register201 from "./real-responses/auth-register-201.json";
import register409 from "./real-responses/auth-register-409.json";
import register422 from "./real-responses/auth-register-422.json";

const ME = me200 as MeResponse;

describe("real auth response shapes", () => {
  it("/auth/me carries exactly user_id and email (the MeResponse mirror)", () => {
    expect(Object.keys(me200).sort()).toEqual(["email", "user_id"]);
  });
  it("login and register bodies carry no token (it travels in an HttpOnly cookie)", () => {
    expect(Object.keys(login200)).toEqual(["user_id"]);
    expect(Object.keys(register201)).toEqual(["user_id"]);
  });
  it("the account created is the account /auth/me reports", () => {
    expect(me200.user_id).toBe(login200.user_id);
    expect(me200.user_id).toBe(register201.user_id);
  });
});

describe("sessionStatus", () => {
  it("is anonymous with no API: there is nothing to sign in to", () => {
    expect(sessionStatus({ usingApi: false, pending: true, me: undefined })).toBe("anonymous");
  });
  it("is unknown until the first /auth/me answers", () => {
    expect(sessionStatus({ usingApi: true, pending: true, me: undefined })).toBe("unknown");
  });
  it("is signed in when /auth/me returned a user", () => {
    expect(sessionStatus({ usingApi: true, pending: false, me: ME })).toBe("signed_in");
  });
  it("is anonymous after a 401 (null) or an unreachable API (no data, not pending)", () => {
    expect(sessionStatus({ usingApi: true, pending: false, me: null })).toBe("anonymous");
    expect(sessionStatus({ usingApi: true, pending: false, me: undefined })).toBe("anonymous");
  });
});

describe("gating (ADR-022)", () => {
  it("gates Batch and Library, never Predict, Compare or Settings", () => {
    expect(isGatedPath("/batch")).toBe(true);
    expect(isGatedPath("/library")).toBe(true);
    expect(isGatedPath("/batch/anything")).toBe(true);
    for (const p of ["/predict", "/compare", "/settings", "/"]) expect(isGatedPath(p), p).toBe(false);
  });

  const q = (over: Partial<Parameters<typeof mustSignIn>[0]>) => ({
    usingApi: true,
    status: "anonymous" as const,
    gated: true,
    ...over,
  });
  it("shows the sign-in state, and the lock, only for an anonymous user on a gated destination", () => {
    expect(mustSignIn(q({}))).toBe(true);
    expect(showsLock(q({}))).toBe(true);
  });
  it("is neutral while the session is unknown: no gate, no lock", () => {
    expect(mustSignIn(q({ status: "unknown" }))).toBe(false);
    expect(showsLock(q({ status: "unknown" }))).toBe(false);
  });
  it("drops both once signed in", () => {
    expect(mustSignIn(q({ status: "signed_in" }))).toBe(false);
    expect(showsLock(q({ status: "signed_in" }))).toBe(false);
  });
  it("never gates fixture mode: Batch keeps its labelled sample data", () => {
    expect(mustSignIn(q({ usingApi: false }))).toBe(false);
    expect(showsLock(q({ usingApi: false }))).toBe(false);
  });
  it("never gates an anonymous destination", () => {
    expect(mustSignIn(q({ gated: false }))).toBe(false);
    expect(showsLock(q({ gated: false }))).toBe(false);
  });
});

describe("accountInitial", () => {
  it("is the first character, upper-cased, from the real address", () => {
    expect(accountInitial(ME.email)).toBe(ME.email.charAt(0).toUpperCase());
    expect(accountInitial("  ada@example.com")).toBe("A");
  });
  it("never invents an identity from nothing", () => {
    expect(accountInitial("")).toBe("?");
  });
});

describe("validateCredentials", () => {
  it("catches the obvious before a round trip", () => {
    expect(validateCredentials("signin", "", "x")).toMatch(/email/i);
    expect(validateCredentials("signin", "nope", "x")).toMatch(/email/i);
    expect(validateCredentials("signin", "a@b.co", "")).toMatch(/password/i);
    expect(validateCredentials("register", "a@b.co", "short")).toMatch(/8 characters/);
  });
  it("accepts a plausible pair; the length rule applies to creating an account only", () => {
    expect(validateCredentials("register", "a@b.co", "long-enough")).toBeNull();
    expect(validateCredentials("signin", "a@b.co", "short")).toBeNull();
  });
});

describe("authErrorMessage", () => {
  it("keeps login 401 generic, as the service does (it will not say which part was wrong)", () => {
    const msg = authErrorMessage({ status: 401, message: login401.detail }, "signin");
    expect(msg).toBe("Email or password is incorrect.");
    expect(msg).not.toMatch(/exist|unknown|no account/i);
  });
  it("explains the real 409 and points at signing in", () => {
    expect(register409.detail).toMatch(/already registered/i);
    expect(authErrorMessage({ status: 409, message: register409.detail }, "register")).toMatch(/Sign in instead/);
  });
  it("shows the service's reason for a 422 rather than a bare status", () => {
    const first = (register422.detail as { msg: string }[])[0].msg;
    expect(authErrorMessage({ status: 422, message: first }, "register")).toContain(first);
  });
  it("names an unreachable API", () => {
    expect(authErrorMessage({ status: 0, message: "API unreachable" }, "signin")).toMatch(/unreachable/i);
  });
  it("falls back to the status and message for anything else", () => {
    expect(authErrorMessage({ status: 500, message: "boom" }, "register")).toBe("Creating the account failed (500): boom");
    expect(authErrorMessage({ status: 500, message: "boom" }, "signin")).toBe("Signing in failed (500): boom");
  });
});

describe("auth client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    vi.resetModules();
  });
  const json = (status: number, body: unknown) =>
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  async function client(res: (url: string, init?: RequestInit) => Response) {
    vi.stubEnv("VITE_API_BASE", "/api");
    const fetchMock = vi.fn((url: string, init?: RequestInit) => Promise.resolve(res(url, init)));
    vi.stubGlobal("fetch", fetchMock);
    vi.resetModules();
    return { ...(await import("../data/client")), fetchMock };
  }

  it("fetchMe returns the user on 200", async () => {
    const { fetchMe } = await client(() => json(200, me200));
    await expect(fetchMe()).resolves.toEqual(ME);
  });
  it("fetchMe returns null on the real 401 (no session is an answer, not an error)", async () => {
    const { fetchMe } = await client(() => json(401, me401));
    await expect(fetchMe()).resolves.toBeNull();
  });
  it("fetchMe still throws when the API is unreachable, so it is not mistaken for 'signed out'", async () => {
    vi.stubEnv("VITE_API_BASE", "/api");
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
    vi.resetModules();
    const { fetchMe } = await import("../data/client");
    await expect(fetchMe()).rejects.toMatchObject({ status: 0 });
  });

  it("login posts the credentials with the cookie jar and surfaces the real 401", async () => {
    const { login, fetchMock } = await client(() => json(401, login401));
    await expect(login("a@b.co", "pw")).rejects.toMatchObject({ status: 401, message: login401.detail });
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/auth/login");
    expect(init.credentials).toBe("include");
    expect(JSON.parse(init.body as string)).toEqual({ email: "a@b.co", password: "pw" });
  });
  it("register sends the required turnstile field as an explicit placeholder, and surfaces the real 409", async () => {
    const { register, fetchMock } = await client(() => json(409, register409));
    await expect(register("a@b.co", "long-enough")).rejects.toMatchObject({ status: 409 });
    const body = JSON.parse((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body as string);
    expect(Object.keys(body).sort()).toEqual(["email", "password", "turnstile_token"]);
  });
  it("register's real 422 list becomes readable text", async () => {
    const { register } = await client(() => json(422, register422));
    await expect(register("a@b.co", "abc")).rejects.toMatchObject({
      status: 422,
      message: "String should have at least 8 characters",
    });
  });

  describe("401 from a gated call", () => {
    it("tells the app the session is gone", async () => {
      const { setUnauthorizedHandler, fetchConformer } = await client(() => json(401, me401));
      const handler = vi.fn();
      setUnauthorizedHandler(handler);
      await expect(fetchConformer("x")).rejects.toMatchObject({ status: 401 });
      expect(handler).toHaveBeenCalledTimes(1);
    });
    it("does not, for the auth calls' own 401s (wrong password, no session)", async () => {
      const { setUnauthorizedHandler, login, fetchMe } = await client(() => json(401, login401));
      const handler = vi.fn();
      setUnauthorizedHandler(handler);
      await expect(login("a@b.co", "pw")).rejects.toBeDefined();
      await fetchMe();
      expect(handler).not.toHaveBeenCalled();
    });
  });
});
