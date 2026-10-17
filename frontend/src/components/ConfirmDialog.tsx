// The one modal MARS uses: a destructive confirmation (INTERACTIONS.md, Overlays). It is
// reached only by an explicit action, and it is left only by an explicit action: Cancel,
// Esc (which is Cancel), or the confirm button. A click on the backdrop does nothing.
//
// Accessibility: role="alertdialog" with a name and description, focus moves in on open
// (to `initialFocus` when given, otherwise to Cancel, the non-destructive choice), Tab
// cycles inside the dialog, and focus returns to what opened it. It is an overlay, so it
// is the one place a scrim and a shadow are allowed. Nothing animates.
import { useEffect, useId, useRef, type ReactNode, type RefObject } from "react";
import styles from "./confirmDialog.module.css";

interface Props {
  title: string;
  children: ReactNode;
  confirmLabel: string;
  confirmDisabled?: boolean;
  busy?: boolean;
  /** Shown above the buttons as an alert; the dialog stays open so the user can retry or cancel. */
  error?: string | null;
  /** Element to focus on open, e.g. a password field. Defaults to Cancel. */
  initialFocus?: RefObject<HTMLElement | null>;
  onConfirm: () => void;
  onCancel: () => void;
}

const FOCUSABLE = 'button:not([disabled]), input:not([disabled]), [href], select:not([disabled]), textarea:not([disabled])';

export function ConfirmDialog({
  title,
  children,
  confirmLabel,
  confirmDisabled,
  busy,
  error,
  initialFocus,
  onConfirm,
  onCancel,
}: Props) {
  const titleId = useId();
  const bodyId = useId();
  const box = useRef<HTMLDivElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    (initialFocus?.current ?? cancel.current)?.focus();
    return () => opener?.focus?.();
    // Only on open: re-running would steal focus from whatever the user is typing in.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      if (!busy) onCancel();
      return;
    }
    if (e.key !== "Tab" || !box.current) return;
    const items = [...box.current.querySelectorAll<HTMLElement>(FOCUSABLE)];
    if (items.length === 0) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  };

  return (
    <div className={styles.scrim} onKeyDown={onKeyDown}>
      <div
        ref={box}
        className={styles.dialog}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={bodyId}
      >
        <h2 id={titleId} className={styles.title}>
          {title}
        </h2>
        <div id={bodyId} className={styles.body}>
          {children}
        </div>
        {error && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}
        <div className={styles.actions}>
          <button ref={cancel} type="button" className={styles.cancel} onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button type="button" className={styles.confirm} onClick={onConfirm} disabled={busy || confirmDisabled}>
            {busy ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
