// Conformer viewer host. The 3Dmol.js wiring is Module 7; this is the shell and
// its hero/analysis toggle, with a placeholder geometry. A 404 here is a normal
// state, not an error.
import { useState } from "react";
import styles from "./predict.module.css";

export function StructureViewer() {
  const [mode, setMode] = useState<"hero" | "analysis">("hero");
  return (
    <div className={styles.viewer}>
      <div className={styles.vhd}>
        <span className={styles.panelTitle}>Structure</span>
        <div className={styles.seg}>
          <button className={mode === "hero" ? styles.segOn : ""} aria-pressed={mode === "hero"} onClick={() => setMode("hero")}>
            Hero
          </button>
          <button
            className={mode === "analysis" ? styles.segOn : ""}
            aria-pressed={mode === "analysis"}
            onClick={() => setMode("analysis")}
          >
            Analysis
          </button>
        </div>
      </div>
      <div className={styles.vstage}>
        <svg width="200" height="150" viewBox="0 0 200 150" fill="none" strokeWidth="3" aria-hidden="true">
          <path
            className={styles.vbond}
            d="M62 95 42 108M62 95 60 72M60 72 82 60M82 60 104 72M104 72 102 96M102 96 80 108M80 108 62 95M104 72 128 66M128 66 146 80M128 66 132 44M132 44 116 30"
          />
          <circle className={styles.vatom} cx="62" cy="95" r="6" stroke="none" />
          <circle className={styles.vatom} cx="60" cy="72" r="6" stroke="none" />
          <circle className={styles.vatom} cx="82" cy="60" r="6" stroke="none" />
          <circle className={styles.vatomFocus} cx="104" cy="72" r="7" stroke="none" />
          <circle className={styles.vatom} cx="102" cy="96" r="6" stroke="none" />
          <circle className={styles.vatom} cx="80" cy="108" r="6" stroke="none" />
          <circle className={styles.vatom} cx="42" cy="108" r="6" stroke="none" />
          <circle className={styles.vatom} cx="128" cy="66" r="6" stroke="none" />
          <circle className={styles.vatomHetero} cx="146" cy="80" r="6" stroke="none" />
          <circle className={styles.vatom} cx="132" cy="44" r="6" stroke="none" />
          <circle className={styles.vatomHetero} cx="116" cy="30" r="6" stroke="none" />
        </svg>
      </div>
      <div className={styles.vcap}>ETKDGv3 · MMFF94 · −42.8 kcal/mol</div>
    </div>
  );
}
