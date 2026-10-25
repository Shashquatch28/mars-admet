// What the landing says about accounts (ADR-046). Pure, so it is testable without a DOM.
// It follows the session the rest of the app uses: nothing is shown while the first /auth/me is unanswered,
// and with no API there is nothing to sign in to.
import type { SessionStatus } from "../domain/session";

export type LandingAccount = "sign_in" | "signed_in" | "none";

/** What the header offers: a way in, the signed-in state, or nothing yet (never a placeholder identity). */
export function landingAccount(q: { usingApi: boolean; status: SessionStatus }): LandingAccount {
  if (!q.usingApi) return "none";
  if (q.status === "anonymous") return "sign_in";
  if (q.status === "signed_in") return "signed_in";
  return "none";
}

/** The line under a workspace tile. A gated workspace says how to get in while the visitor has no session;
 *  the workspace itself then shows the sign-in and create-account forms. */
export function workspaceAccess(q: { gated: boolean; usingApi: boolean; status: SessionStatus }): string {
  if (!q.gated) return "No account";
  if (q.usingApi && q.status === "anonymous") return "Account required. Sign in or create one.";
  return "Account";
}
