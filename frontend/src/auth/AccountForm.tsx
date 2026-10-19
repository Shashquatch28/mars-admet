// Sign in / create account. The cookie is set by the API; this only sends the
// credentials and reports what the service said. Password reset is not offered:
// the API issues a token but no email is sent, so MARS launches without account
// recovery and says so here (ADR-022 item 7).
import { useId, useState, type FormEvent } from "react";
import styles from "./auth.module.css";
import { useAuthSession } from "../app/authSession";
import { authErrorMessage, validateCredentials, type AuthMode } from "../domain/session";

export function AccountForm() {
  const { submit, busy, error, clearError } = useAuthSession();
  const [mode, setMode] = useState<AuthMode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [local, setLocal] = useState<string | null>(null);
  const id = useId();
  const errId = `${id}-err`;

  const message = local ?? (error ? authErrorMessage(error, mode) : null);

  function switchMode(m: AuthMode) {
    setMode(m);
    setLocal(null);
    clearError();
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const problem = validateCredentials(mode, email, password);
    setLocal(problem);
    if (problem) return;
    clearError();
    await submit(mode, email, password); // on success the session flips and this form unmounts
  }

  return (
    <form onSubmit={onSubmit} noValidate aria-label={mode === "signin" ? "Sign in" : "Create account"}>
      <div className={styles.seg} role="group" aria-label="Sign in or create an account">
        <button
          type="button"
          className={mode === "signin" ? styles.segOn : ""}
          aria-pressed={mode === "signin"}
          onClick={() => switchMode("signin")}
        >
          Sign in
        </button>
        <button
          type="button"
          className={mode === "register" ? styles.segOn : ""}
          aria-pressed={mode === "register"}
          onClick={() => switchMode("register")}
        >
          Create account
        </button>
      </div>

      {message && (
        <p id={errId} className={styles.error} role="alert">
          {message}
        </p>
      )}

      <div className={styles.field}>
        <label className={styles.label} htmlFor={`${id}-email`}>
          Email
        </label>
        <input
          id={`${id}-email`}
          className={styles.input}
          type="email"
          autoComplete="username"
          spellCheck={false}
          aria-invalid={message ? true : undefined}
          aria-describedby={message ? errId : undefined}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </div>
      <div className={styles.field}>
        <label className={styles.label} htmlFor={`${id}-pw`}>
          Password
        </label>
        <input
          id={`${id}-pw`}
          className={styles.input}
          type="password"
          autoComplete={mode === "signin" ? "current-password" : "new-password"}
          aria-invalid={message ? true : undefined}
          aria-describedby={[message ? errId : "", mode === "register" ? `${id}-hint` : ""].filter(Boolean).join(" ") || undefined}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {mode === "register" && (
          <span id={`${id}-hint`} className={styles.hint}>
            At least 8 characters.
          </span>
        )}
      </div>

      <button type="submit" className={styles.submit} disabled={busy}>
        {busy ? "Working…" : mode === "signin" ? "Sign in" : "Create account"}
      </button>
      <p className={styles.note}>
        MARS has no password recovery. If you forget this password, the account and its saved items cannot be
        recovered.
      </p>
    </form>
  );
}
