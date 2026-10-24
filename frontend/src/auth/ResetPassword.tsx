// Choose a new password from an emailed link (ADR-042). The link carries its token in the URL fragment, which a browser never
// sends to a server; it is read once, kept in memory and removed from the address bar. A reset ends every session of the
// account and does not sign anyone in: the done state says so and points to sign-in.
import { useEffect, useId, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import styles from "./auth.module.css";
import { useAuthSession } from "../app/authSession";
import { ApiError, USING_API, confirmPasswordReset } from "../data/client";
import { NOT_SIGNED_IN_NOTE, resetFailureMessage, tokenFromHash, validateNewPassword } from "../domain/passwordReset";

export function ResetPassword() {
  const { forgetSession } = useAuthSession();
  // Read once, before anything can re-render: the fragment is then removed so the token is not left in the address bar or history.
  const [token] = useState(() => tokenFromHash(window.location.hash));
  useEffect(() => {
    if (window.location.hash) window.history.replaceState(null, "", window.location.pathname + window.location.search);
  }, []);

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [local, setLocal] = useState<string | null>(null);
  const id = useId();
  const reset = useMutation({
    mutationFn: (p: string) => confirmPasswordReset(token ?? "", p),
    // The service ended every session of the account, this browser's included.
    onSuccess: () => forgetSession(),
  });
  const failure = reset.error ? resetFailureMessage(reset.error instanceof ApiError ? reset.error.status : 0, reset.error.message) : null;
  const message = local ?? failure;

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const problem = validateNewPassword(password, confirm);
    setLocal(problem);
    if (problem) return;
    reset.mutate(password);
  }

  let body;
  if (!USING_API) body = <p className={styles.body}>No API is configured, so there are no accounts to recover.</p>;
  else if (reset.isSuccess)
    body = (
      <div className={styles.stack}>
        <h2 className={styles.title}>Password changed</h2>
        <p className={styles.body}>{NOT_SIGNED_IN_NOTE}</p>
        <Link className={styles.secondary} to="/library">
          Go to sign in
        </Link>
      </div>
    );
  else if (!token)
    body = (
      <div className={styles.stack}>
        <h2 className={styles.title}>This link is incomplete</h2>
        <p className={styles.body}>
          This page needs the link from the email, including everything after the <code>#</code>. Open it again from the email, or ask for a new one.
        </p>
        <Link className={styles.secondary} to="/forgot-password">
          Ask for a new link
        </Link>
      </div>
    );
  else
    body = (
      <form onSubmit={onSubmit} noValidate aria-label="Choose a new password">
        <h2 className={styles.title}>Choose a new password</h2>
        <p className={styles.body}>{NOT_SIGNED_IN_NOTE}</p>
        {message && (
          <p className={styles.error} role="alert" id={`${id}-err`}>
            {message}{" "}
            {reset.error instanceof ApiError && reset.error.status === 400 && <Link to="/forgot-password">Ask for a new link</Link>}
          </p>
        )}
        <div className={styles.field}>
          <label className={styles.label} htmlFor={`${id}-pw`}>
            New password
          </label>
          <input
            id={`${id}-pw`}
            className={styles.input}
            type="password"
            autoComplete="new-password"
            aria-invalid={message ? true : undefined}
            aria-describedby={[message ? `${id}-err` : "", `${id}-hint`].filter(Boolean).join(" ")}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <span id={`${id}-hint`} className={styles.hint}>
            At least 8 characters.
          </span>
        </div>
        <div className={styles.field}>
          <label className={styles.label} htmlFor={`${id}-pw2`}>
            Type it again
          </label>
          <input
            id={`${id}-pw2`}
            className={styles.input}
            type="password"
            autoComplete="new-password"
            aria-invalid={message ? true : undefined}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
          />
        </div>
        <button type="submit" className={styles.submit} disabled={reset.isPending}>
          {reset.isPending ? "Working…" : "Change the password"}
        </button>
      </form>
    );

  return (
    <section className={styles.slot} aria-label="Reset password">
      <div className={`${styles.panel} ${styles.single}`}>
        <div className={styles.formcol}>{body}</div>
      </div>
    </section>
  );
}
