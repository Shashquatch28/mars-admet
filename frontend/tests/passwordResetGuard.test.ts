// Source guards for the password-reset flow (ADR-042): the properties a later edit could break without touching a test.
// Lives in tests/ because it reads the filesystem (see cssGuard.test.ts).
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(process.cwd(), "src");
const code = (f: string) =>
  readFileSync(join(SRC, f), "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/[^\n]*/g, "");

describe("password reset", () => {
  it("a reset does not sign anyone in: the new-password screen never calls login or submits credentials", () => {
    const src = code("auth/ResetPassword.tsx");
    expect(src).not.toMatch(/\blogin\b|\bsubmit\(|\bregister\b/);
    expect(src).toMatch(/forgetSession\(\)/); // it only drops this browser's session, which the service has ended
  });

  it("the token is read from the URL fragment, never the query string, and removed from the address bar", () => {
    const src = code("auth/ResetPassword.tsx");
    expect(src).toMatch(/window\.location\.hash/);
    expect(src).not.toMatch(/useSearchParams|location\.search\b[^)]*token|URLSearchParams/);
    expect(src).toMatch(/history\.replaceState/);
  });

  it("neither screen logs or stores the token or the password", () => {
    for (const f of ["auth/ResetPassword.tsx", "auth/ForgotPassword.tsx", "domain/passwordReset.ts"]) {
      const src = code(f);
      expect(src, f).not.toMatch(/console\.|localStorage|sessionStorage/);
    }
  });

  it("the request screen never says an email was sent or that an address has no account", () => {
    const src = code("auth/ForgotPassword.tsx").toLowerCase();
    expect(src).not.toMatch(/email (was|has been) sent|we sent|we have sent|no account (found|exists)|not registered/);
  });

  it("the sign-in form no longer says MARS has no recovery, and links to the reset flow", () => {
    const src = readFileSync(join(SRC, "auth", "AccountForm.tsx"), "utf8");
    expect(src).not.toMatch(/no password recovery|cannot be\s+recovered/i);
    expect(src).toContain('to="/forgot-password"');
  });

  it("the lifetime of a link is never written as a number in the screens: it is read from /limits", () => {
    for (const f of ["auth/ForgotPassword.tsx", "auth/ResetPassword.tsx", "domain/passwordReset.ts"]) {
      expect(code(f), f).not.toMatch(/\b\d+\s*(minutes?|hours?)\b/i);
    }
  });
});
