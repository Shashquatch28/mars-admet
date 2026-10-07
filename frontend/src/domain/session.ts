// Who is using the app, and what that means for the shell (ADR-022). Pure, so the
// decisions that gate a workspace or show a lock glyph are testable without a DOM.
//
// Three session values: unknown (the first /auth/me has not answered), anonymous,
// signed in. Predict and Compare are anonymous; Batch and Library need a session,
// as the API already enforces. A gated destination is shown, never hidden.
import type { MeResponse } from "../types/contracts";

export type SessionStatus = "unknown" | "anonymous" | "signed_in";

/** Rail destinations the API only serves to a signed-in user. */
export const GATED_PATHS: readonly string[] = ["/batch", "/library"];

export function isGatedPath(path: string): boolean {
  const base = "/" + (path.split("/")[1] ?? "");
  return GATED_PATHS.includes(base);
}

export function sessionStatus(q: {
  usingApi: boolean;
  pending: boolean; // the /auth/me request has not answered yet
  me: MeResponse | null | undefined; // null = answered 401
}): SessionStatus {
  // With no API configured there is nothing to sign in to: the sample data is open.
  if (!q.usingApi) return "anonymous";
  if (q.me) return "signed_in";
  if (q.pending) return "unknown";
  return "anonymous"; // a 401 or an unreachable API: either way, no session
}

/** Whether a gated workspace must show its in-workspace sign-in state. Fixture mode
 *  (no API) never gates: Batch keeps working on its labelled sample data. */
export function mustSignIn(q: { usingApi: boolean; status: SessionStatus; gated: boolean }): boolean {
  return q.usingApi && q.gated && q.status === "anonymous";
}

/** The rail's lock glyph. Neutral while the session is unknown (no flash), absent once signed in. */
export function showsLock(q: { usingApi: boolean; status: SessionStatus; gated: boolean }): boolean {
  return q.usingApi && q.gated && q.status === "anonymous";
}

/** One character for the account button; the full address is in its accessible name. */
export function accountInitial(email: string): string {
  const c = email.trim().charAt(0);
  return c ? c.toUpperCase() : "?";
}

export type AuthMode = "signin" | "register";

/** Cheap checks that spare a round trip. The service stays the authority (it also
 *  validates the address), so these only catch what is obvious. */
export function validateCredentials(mode: AuthMode, email: string, password: string): string | null {
  if (!email.trim()) return "Enter your email address.";
  if (!/^\S+@\S+$/.test(email.trim())) return "That does not look like an email address.";
  if (!password) return "Enter your password.";
  if (mode === "register" && password.length < 8) return "Use at least 8 characters for the password.";
  return null;
}

/** What to tell the user. Login 401 is deliberately generic: the API returns the same
 *  body for an unknown address and a wrong password, and the UI must not hint which. */
export function authErrorMessage(err: { status: number; message: string }, mode: AuthMode): string {
  if (err.status === 0) return "The API is unreachable. Check that it is running, then try again.";
  if (err.status === 401) return "Email or password is incorrect.";
  if (err.status === 409) return "An account with this email already exists. Sign in instead.";
  if (err.status === 429) return "Too many attempts. Wait a minute and try again.";
  if (err.status === 422) return `The service rejected those details: ${err.message}`;
  const what = mode === "register" ? "Creating the account" : "Signing in";
  return `${what} failed (${err.status}): ${err.message}`;
}
