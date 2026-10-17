// Delete account (ADR-022 phase 2). The one irreversible action in MARS, so it sits behind
// the confirmation modal and asks for the password again. The dialog says what is removed
// before the user commits, and a failure says nothing was deleted and keeps the dialog
// open. On success the session is gone: the app drops to anonymous and every piece of
// account-owned state held in the browser is discarded.
import { useRef, useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import styles from "../../auth/auth.module.css";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { useAuthSession } from "../../app/authSession";
import { useBatchSession } from "../../app/batchSession";
import { ApiError, deleteAccount } from "../../data/client";
import { DELETE_ACCOUNT_EFFECTS, deleteAccountError } from "../../domain/library";

export function DeleteAccount() {
  const { user, forgetSession } = useAuthSession();
  const batch = useBatchSession();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const field = useRef<HTMLInputElement>(null);

  const del = useMutation({
    mutationFn: () => deleteAccount(password),
    onSuccess: () => {
      qc.removeQueries({ queryKey: ["library"] });
      batch.clear(); // the chosen file and any result belonged to the account
      forgetSession();
    },
  });

  const close = () => {
    setOpen(false);
    setPassword("");
    del.reset();
  };
  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (password && !del.isPending) del.mutate();
  };

  const error = del.error
    ? deleteAccountError(del.error instanceof ApiError ? del.error.status : 0, del.error.message)
    : null;

  return (
    <div className={styles.stack}>
      <span className={styles.kicker}>Delete account</span>
      <p className={styles.body}>
        Permanently removes this account and everything stored against it. This cannot be undone.
      </p>
      <div>
        <button type="button" className={styles.secondary} onClick={() => setOpen(true)}>
          Delete account…
        </button>
      </div>

      {open && (
        <ConfirmDialog
          title="Delete this account?"
          confirmLabel="Delete account"
          confirmDisabled={!password}
          busy={del.isPending}
          error={error}
          initialFocus={field}
          onConfirm={() => submit()}
          onCancel={close}
        >
          <p style={{ margin: 0 }}>
            {user ? `${user.email} will be deleted.` : "This account will be deleted."} That removes:
          </p>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {DELETE_ACCOUNT_EFFECTS.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
          <form onSubmit={submit} className={styles.field} noValidate>
            <label className={styles.label} htmlFor="delete-account-password">
              Enter your password to confirm
            </label>
            <input
              id="delete-account-password"
              ref={field}
              className={styles.input}
              type="password"
              autoComplete="current-password"
              value={password}
              disabled={del.isPending}
              onChange={(e) => setPassword(e.target.value)}
            />
          </form>
        </ConfirmDialog>
      )}
    </div>
  );
}
