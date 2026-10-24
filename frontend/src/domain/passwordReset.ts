// Password reset, as the screens say it (ADR-042). Pure and tested.
//
// What the service guarantees, and the words must not claim more or less: asking for a link answers the same whether or not the
// address has an account, so the screen can never say an email "was sent"; it says what happens if an account exists. A link
// works once and for a limited time, and a successful reset ends every session of the account but does not sign anyone in.

export const MIN_PASSWORD = 8;
export const MAX_PASSWORD_BYTES = 72; // bcrypt's hard limit; the service refuses longer ones

/** The token in a reset link's fragment (`#token=...`), or null. The link carries it there so it is never sent to a server. */
export function tokenFromHash(hash: string): string | null {
  const m = /^#?(?:.*&)?token=([A-Za-z0-9_-]{16,256})(?:&.*)?$/.exec(hash);
  return m ? m[1] : null;
}

/** Cheap checks that spare a round trip; the service stays the authority. */
export function validateNewPassword(password: string, confirm: string): string | null {
  if (!password) return "Enter a new password.";
  if (password.length < MIN_PASSWORD) return `Use at least ${MIN_PASSWORD} characters.`;
  if (new TextEncoder().encode(password).length > MAX_PASSWORD_BYTES) return `Use at most ${MAX_PASSWORD_BYTES} bytes (about ${MAX_PASSWORD_BYTES} plain characters).`;
  if (password !== confirm) return "The two passwords are not the same.";
  return null;
}

export function validateResetEmail(email: string): string | null {
  if (!email.trim()) return "Enter the email address of your account.";
  if (!/^\S+@\S+$/.test(email.trim())) return "That does not look like an email address.";
  return null;
}

/** The answer after a link was asked for. It is the same for every address, by design, and it says so. */
export const REQUEST_ANSWER =
  "If an account exists for that address, a link to choose a new password is on its way. MARS gives the same answer for every address, so this screen cannot tell you whether the account exists.";

export const REQUEST_ANSWER_TITLE = "Check your email";

export const NOT_SIGNED_IN_NOTE = "Choosing a new password ends every session of the account, on every device. It does not sign you in; sign in with the new password.";

/** Why setting the password failed. A bad link is one message: the service does not say whether it was unknown, used or expired. */
export function resetFailureMessage(status: number, message: string): string {
  if (status === 0) return "The API is unreachable. Check that it is running, then try again.";
  if (status === 400) return "This link is not valid. It may already have been used, or it has expired. Ask for a new one.";
  if (status === 429) return "Too many attempts. Wait a while and try again.";
  if (status === 422) return `The service rejected that password: ${message}`;
  return `Choosing the password failed (${status}): ${message}`;
}

export function requestFailureMessage(status: number, message: string): string {
  if (status === 0) return "The API is unreachable. Check that it is running, then try again.";
  if (status === 422) return "That does not look like an email address.";
  return `The request failed (${status}): ${message}`;
}
