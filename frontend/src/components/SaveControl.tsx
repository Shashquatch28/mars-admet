// "Save to library": one control for saving a molecule or a report. Closed it is a button;
// open it is a small inline form (label, tags, notes) that first says what saving does: the
// service freezes a copy of what is on screen, with the model version it was made with, and
// never updates it. Saving needs an account, so an anonymous user is told so in words and
// pointed at sign-in rather than shown a form that cannot succeed. A failure says nothing
// was saved and keeps what the user typed. Nothing animates; the reason a control is
// disabled is written beside it, not left to a tooltip.
import { useId, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import styles from "./saveControl.module.css";
import { useAuthSession } from "../app/authSession";
import { useSavedMarks } from "../app/savedMarks";
import { ApiError } from "../data/client";
import { EMPTY_SAVE_INPUT, saveError, type SaveInput } from "../domain/save";

interface Props {
  kind: "molecule" | "report";
  /** Identity of the thing being saved (domain/save.ts); null when there is nothing to save yet. */
  markKey: string | null;
  buttonLabel: string;
  buttonClassName?: string;
  /** What saving does, shown before the user commits (domain/save.ts saveNote). */
  note: string;
  /** Why saving is unavailable right now, in words; null when it is available. */
  disabledReason?: string | null;
  /** Molecules have a label; a report does not. */
  withLabel?: boolean;
  save: (input: SaveInput) => Promise<unknown>;
}

export function SaveControl({ kind, markKey, buttonLabel, buttonClassName, note, disabledReason, withLabel, save }: Props) {
  const { status } = useAuthSession();
  const marks = useSavedMarks();
  const qc = useQueryClient();
  const id = useId();
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState<SaveInput>(EMPTY_SAVE_INPUT);

  const mutation = useMutation({
    mutationFn: save,
    onSuccess: () => {
      if (markKey) marks.mark(markKey);
      void qc.invalidateQueries({ queryKey: ["library"] });
      setOpen(false);
      setInput(EMPTY_SAVE_INPUT);
    },
  });

  const saved = markKey != null && marks.isSaved(markKey);
  const noun = kind === "molecule" ? "molecule" : "report";

  if (saved) {
    return (
      <span className={styles.saved} role="status">
        Saved to Library. <Link to="/library">Open Library</Link>
      </span>
    );
  }
  if (disabledReason || markKey == null) {
    return (
      <>
        <button type="button" className={buttonClassName} disabled>
          {buttonLabel}
        </button>
        <span className={styles.why}>{disabledReason ?? `Nothing to save yet.`}</span>
      </>
    );
  }

  const error = mutation.error
    ? saveError(mutation.error instanceof ApiError ? mutation.error.status : 0, mutation.error.message)
    : null;

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!mutation.isPending) mutation.mutate(input);
  };
  const close = () => {
    setOpen(false);
    mutation.reset();
  };

  return (
    <>
      <button
        type="button"
        className={buttonClassName}
        aria-expanded={open}
        onClick={() => (open ? close() : setOpen(true))}
      >
        {buttonLabel}
      </button>
      {open && (
        <div className={styles.panel} role="group" aria-label={`Save ${noun}`}>
          {status === "unknown" ? (
            <p className={styles.note}>Checking your session…</p>
          ) : status !== "signed_in" ? (
            <p className={styles.note}>
              Saving needs an account. <Link to="/settings">Sign in or create one</Link>, then save again. Nothing
              has been saved.
            </p>
          ) : (
            <form onSubmit={onSubmit} noValidate>
              <p className={styles.note}>{note}</p>
              {withLabel && (
                <label className={styles.field} htmlFor={`${id}-label`}>
                  <span>Label (optional)</span>
                  <input
                    id={`${id}-label`}
                    value={input.label}
                    disabled={mutation.isPending}
                    onChange={(e) => setInput({ ...input, label: e.target.value })}
                  />
                </label>
              )}
              <label className={styles.field} htmlFor={`${id}-tags`}>
                <span>Tags (optional, comma-separated)</span>
                <input
                  id={`${id}-tags`}
                  value={input.tags}
                  disabled={mutation.isPending}
                  onChange={(e) => setInput({ ...input, tags: e.target.value })}
                />
              </label>
              <label className={styles.field} htmlFor={`${id}-notes`}>
                <span>Notes (optional)</span>
                <textarea
                  id={`${id}-notes`}
                  rows={2}
                  value={input.notes}
                  disabled={mutation.isPending}
                  onChange={(e) => setInput({ ...input, notes: e.target.value })}
                />
              </label>
              {error && (
                <p className={styles.error} role="alert">
                  {error}
                </p>
              )}
              <div className={styles.actions}>
                <button type="submit" className={styles.go} disabled={mutation.isPending}>
                  {mutation.isPending ? "Saving…" : `Save ${noun}`}
                </button>
                <button type="button" onClick={close} disabled={mutation.isPending}>
                  Cancel
                </button>
              </div>
            </form>
          )}
        </div>
      )}
    </>
  );
}
