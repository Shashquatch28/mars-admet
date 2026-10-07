// Endpoint subset selector: a popover (INTERACTIONS: Esc and outside click close
// it) beside Run. It chooses which ML endpoints the next run asks for. The
// rule-based SA score is not selectable — it is computed and always requested.
// A deselected endpoint stays in the roster as NOT REQUESTED (ADR-028).
import { useEffect, useRef, useState } from "react";
import styles from "./predict.module.css";
import {
  DISPLAY_GROUP_LABEL,
  DISPLAY_GROUP_ORDER,
  ML_ENDPOINTS,
  displayGroupOf,
  endpointSelectionLabel,
} from "../../domain/endpoints";
import type { Endpoint } from "../../types/contracts";

const GROUPS = DISPLAY_GROUP_ORDER.map((group) => ({
  group,
  label: DISPLAY_GROUP_LABEL[group],
  endpoints: ML_ENDPOINTS.filter((e) => displayGroupOf(e) === group),
})).filter((g) => g.endpoints.length > 0);

export function EndpointSelector({
  selected,
  onChange,
  disabled,
}: {
  selected: Endpoint[];
  onChange: (e: Endpoint[]) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const first = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    first.current?.focus();
    const onDown = (e: MouseEvent) => {
      if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        setOpen(false);
        trigger.current?.focus();
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey, true);
    };
  }, [open]);

  const toggle = (e: Endpoint) =>
    onChange(selected.includes(e) ? selected.filter((s) => s !== e) : [...selected, e]);

  return (
    <div className={styles.selwrap} ref={wrap}>
      <button
        ref={trigger}
        type="button"
        className={styles.selbtn}
        aria-haspopup="dialog"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
      >
        {endpointSelectionLabel(selected)} <span style={{ color: "var(--text-quiet)" }}>▾</span>
      </button>
      {open && (
        <div className={styles.selpop} role="dialog" aria-label="Endpoints to run">
          {GROUPS.map((g, gi) => (
            <fieldset key={g.group} className={styles.selgroup}>
              <legend className={styles.sellegend}>{g.label}</legend>
              {g.endpoints.map((e, ei) => (
                <label key={e} className={styles.selopt}>
                  <input
                    ref={gi === 0 && ei === 0 ? first : undefined}
                    type="checkbox"
                    checked={selected.includes(e)}
                    onChange={() => toggle(e)}
                  />
                  <span>{e}</span>
                </label>
              ))}
            </fieldset>
          ))}
          <div className={styles.selfoot}>
            <button type="button" onClick={() => onChange(ML_ENDPOINTS)} disabled={selected.length === ML_ENDPOINTS.length}>
              All
            </button>
            <button type="button" onClick={() => onChange([])} disabled={selected.length === 0}>
              None
            </button>
            <span className={styles.selnote}>
              {selected.length === 0
                ? "Pick at least one to run."
                : "Unticked endpoints stay listed as NOT REQUESTED."}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
