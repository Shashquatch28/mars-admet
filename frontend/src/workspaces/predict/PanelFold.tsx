// Folding a side panel away and back (ADR-045). Two small pieces: the toggle that sits in an open panel's header, and the
// rail a folded panel leaves behind. The rail is one button: its visible text names the panel, so nothing is explained
// only by a tooltip, and clicking anywhere on it opens the panel again. A folded panel's content stays mounted and
// hidden, so the molecule, the selected endpoint, an open explanation and the editor survive a fold and an unfold.
import styles from "./predict.module.css";

type Side = "left" | "right";

// the chevron points the way the panel goes: toward its own edge to fold, away from it to open
const chevron = (toward: Side) => (
  <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
    <path d={toward === "left" ? "M10 3 5 8l5 5" : "M6 3l5 5-5 5"} />
  </svg>
);

export function FoldToggle({ label, side, controls, onFold }: { label: string; side: Side; controls: string; onFold: () => void }) {
  return (
    <button type="button" className={styles.foldBtn} aria-label={`Fold ${label}`} aria-expanded={true} aria-controls={controls} onClick={onFold}>
      {chevron(side)}
    </button>
  );
}

export function FoldRail({ label, side, controls, onUnfold }: { label: string; side: Side; controls: string; onUnfold: () => void }) {
  return (
    <button type="button" className={styles.rail} aria-expanded={false} aria-controls={controls} onClick={onUnfold}>
      {chevron(side === "left" ? "right" : "left")}
      <span className={styles.railLabel}>{label}</span>
    </button>
  );
}
