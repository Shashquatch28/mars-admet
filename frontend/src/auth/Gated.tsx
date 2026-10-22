// A workspace that needs a session (ADR-022). The destination is always reachable
// and keeps its place in the rail; an anonymous user lands in the workspace, which
// explains why an account is needed, what stays free, and offers the forms. The
// reason lives here in words, never only in a tooltip (never-do #8).
import { useEffect, type ReactNode } from "react";
import styles from "./auth.module.css";
import { AccountForm } from "./AccountForm";
import { useAuthSession } from "../app/authSession";
import { useUiState } from "../app/uiState";
import { USING_API } from "../data/client";
import { mustSignIn } from "../domain/session";

const LOCK = (
  <svg width="12" height="12" viewBox="0 0 16 16" aria-hidden="true">
    <rect x="3" y="7" width="10" height="7" rx="1" />
    <path d="M5 7V5a3 3 0 0 1 6 0v2" />
  </svg>
);

const COPY = {
  Batch: {
    title: "Batch needs an account",
    why: "Batch takes a file of up to 50,000 molecules and runs it with live progress. Each batch belongs to the account that uploaded it, which is how MARS knows whose results they are.",
  },
  Library: {
    title: "Library needs an account",
    why: "Library keeps the molecules and reports you save. They are stored against your account, which is how MARS knows whose they are.",
  },
} as const;

export function Gated({ name, children }: { name: keyof typeof COPY; children: ReactNode }) {
  const { status } = useAuthSession();
  const { setIsSample } = useUiState();
  const gate = mustSignIn({ usingApi: USING_API, status, gated: true });
  const checking = USING_API && status === "unknown";
  // The sign-in and checking states show no values, so nothing on screen is illustrative.
  useEffect(() => {
    if (gate || checking) setIsSample(false);
  }, [gate, checking, setIsSample]);
  if (!gate) {
    // Unknown: the first /auth/me has not answered. Say so rather than flash the sign-in
    // state at someone who is already signed in, or sample data at someone who is not.
    if (USING_API && status === "unknown") {
      return (
        <section className={styles.slot} aria-label={name}>
          <p className={styles.body}>Checking your session…</p>
        </section>
      );
    }
    return <>{children}</>;
  }
  const c = COPY[name];
  return (
    <section className={styles.slot} aria-label={`${name}: sign in`}>
      <div className={styles.panel}>
        <div className={styles.why}>
          <span className={styles.kicker}>
            {LOCK} Account required
          </span>
          <h2 className={styles.title}>{c.title}</h2>
          <p className={styles.body}>{c.why}</p>
          <p className={styles.free}>
            <b>Stays free</b>
            Predict and Compare need no account. Nothing you do there is stored against one.
          </p>
        </div>
        <div className={styles.formcol}>
          <AccountForm />
        </div>
      </div>
    </section>
  );
}
