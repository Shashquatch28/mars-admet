// Settings. Today it holds the Account section only: sign in or out, and delete the
// account behind a confirmation modal (ADR-022 phase 2).
import styles from "../../auth/auth.module.css";
import { AccountForm } from "../../auth/AccountForm";
import { useAuthSession } from "../../app/authSession";
import { useUiState } from "../../app/uiState";
import { USING_API } from "../../data/client";
import { NAME_DISCLOSURE } from "../../domain/moleculeName";
import { DeleteAccount } from "./DeleteAccount";

export function SettingsWorkspace() {
  const { status, user, busy, signOut } = useAuthSession();
  const { shortcutsEnabled, setShortcutsEnabled } = useUiState();

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
        <DeleteAccount />
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
          <span className={styles.kicker}>Molecule names</span>
          <p className={styles.body}>
            When MARS shows a structure it also looks up that molecule's name, and says where the name came from. The name
            comes from PubChem. {NAME_DISCLOSURE} A name says who a molecule is and nothing about any prediction. A molecule
            PubChem has no record of shows "No name found", and a lookup that fails says why and changes nothing else.
          </p>
          <span className={styles.kicker}>Keyboard</span>
          <label className={styles.check}>
            <input
              type="checkbox"
              checked={shortcutsEnabled}
              onChange={(e) => setShortcutsEnabled(e.target.checked)}
            />
            <span>Single-key shortcuts: keys 1 to 5 switch workspace</span>
          </label>
          <p className={styles.body}>
            Turn this off if a stray key press moves you between workspaces. Ctrl or ⌘ + K for the command palette is
            not affected. The choice is remembered in this browser.
          </p>
        </div>
      </div>
    </section>
  );
}
