// Ask for a password-reset link (ADR-042). Reachable without a session. The answer is the same for every address, and the screen
// says so in words: it never claims an email was sent, because the service never says whether the account exists.
import { useId, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import styles from "./auth.module.css";
import { ApiError, USING_API, requestPasswordReset } from "../data/client";
import { useLimits } from "../data/useLimits";
import { resetLinkLifetime } from "../domain/limitsCopy";
import { REQUEST_ANSWER, REQUEST_ANSWER_TITLE, requestFailureMessage, validateResetEmail } from "../domain/passwordReset";

export function ForgotPassword() {
  const limits = useLimits();
  const [email, setEmail] = useState("");
  const [local, setLocal] = useState<string | null>(null);
  const id = useId();
  const ask = useMutation({ mutationFn: (e: string) => requestPasswordReset(e) });

  const failure = ask.error ? requestFailureMessage(ask.error instanceof ApiError ? ask.error.status : 0, ask.error.message) : null;
  const message = local ?? failure;

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const problem = validateResetEmail(email);
    setLocal(problem);
    if (problem) return;
    ask.mutate(email.trim());
  }

  if (!USING_API) {
    return (
      <section className={styles.slot} aria-label="Forgot password">
        <div className={`${styles.panel} ${styles.single}`}>
          <div className={styles.formcol}>
            <p className={styles.body}>No API is configured, so there are no accounts to recover.</p>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className={styles.slot} aria-label="Forgot password">
      <div className={`${styles.panel} ${styles.single}`}>
        <div className={styles.formcol}>
          <h2 className={styles.title}>{ask.isSuccess ? REQUEST_ANSWER_TITLE : "Forgot your password?"}</h2>
          {ask.isSuccess ? (
            <div className={styles.stack}>
              <p className={styles.body}>{REQUEST_ANSWER}</p>
              <p className={styles.body}>{resetLinkLifetime(limits)}</p>
              <p className={styles.note}>
                Nothing arrives? Check the spam folder, wait a few minutes, and ask again; the service allows a few requests an hour for one address.
              </p>
              <Link className={styles.secondary} to="/library">
                Back to sign in
              </Link>
            </div>
          ) : (
            <form onSubmit={onSubmit} noValidate aria-label="Ask for a password-reset link">
              <p className={styles.body}>Enter the email address of your MARS account and we will send a link to choose a new password.</p>
              {message && (
                <p className={styles.error} role="alert" id={`${id}-err`}>
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
                  aria-describedby={message ? `${id}-err` : undefined}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <button type="submit" className={styles.submit} disabled={ask.isPending}>
                {ask.isPending ? "Working…" : "Send the link"}
              </button>
              <p className={styles.note}>
                <Link to="/library">Back to sign in</Link>
              </p>
            </form>
          )}
        </div>
      </div>
    </section>
  );
}
