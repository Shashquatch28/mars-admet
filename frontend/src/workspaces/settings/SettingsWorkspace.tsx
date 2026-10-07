// Settings. Today it holds the Account section only: sign in or out. Deleting an
// account (behind a confirmation modal) is Phase 2 of ADR-022.
import { useEffect } from "react";
import styles from "../../auth/auth.module.css";
import { AccountForm } from "../../auth/AccountForm";
import { useAuthSession } from "../../app/authSession";
import { useUiState } from "../../app/uiState";
import { USING_API } from "../../data/client";

export function SettingsWorkspace() {
  const { status, user, busy, signOut } = useAuthSession();
  const { setIsSample } = useUiState();
  useEffect(() => setIsSample(false), [setIsSample]); // Settings shows no values: nothing is illustrative

  let body;
  if (!USING_API) {
    body = (
      <p className={styles.body}>
        No API is configured, so there are no accounts. Predict and the Batch sample data work without one.
      </p>
    );
  } else if (status === "unknown") {
    body = <p className={styles.body}>Checking your session…</p>;
  } else if (status === "signed_in" && user) {
    body = (
      <>
        <p className={styles.body}>Signed in as</p>
        <p className={styles.who}>{user.email}</p>
        <div>
          <button type="button" className={styles.secondary} onClick={signOut} disabled={busy}>
            Sign out
          </button>
        </div>
      </>
    );
  } else {
    body = <AccountForm />;
  }

  return (
    <section className={styles.slot} aria-label="Settings">
      <div className={`${styles.panel} ${styles.single}`}>
        <div className={`${styles.formcol} ${styles.stack}`}>
          <span className={styles.kicker}>Account</span>
          {body}
        </div>
      </div>
    </section>
  );
}
