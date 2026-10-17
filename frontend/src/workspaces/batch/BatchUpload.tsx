// The live Batch input: choose a CSV or SDF, optionally name the SMILES column, run, and
// watch the job. Everything the user needs to know about limits is written here in
// words, not in a tooltip. Progress is a determinate bar only once the service has
// reported a total; before that the status line says what is happening. Nothing animates.
import { useRef, useState, type DragEvent } from "react";
import styles from "./batch.module.css";
import { useBatchSession } from "../../app/batchSession";
import { BATCH_INTERACTIVE_MAX, BATCH_MAX_MOLECULES, percentDone, phaseLabel } from "../../domain/batchJob";

export function BatchUpload() {
  const s = useBatchSession();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    if (s.busy) return;
    const f = e.dataTransfer.files?.[0];
    if (f) s.chooseFile(f);
  };

  const pct = s.phase.kind === "running" ? percentDone(s.phase.progress) : null;
  const failed = s.phase.kind === "failed" || !!s.fileProblem;

  return (
    <div
      className={`${styles.upload} ${over ? styles.uploadOver : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
    >
      <div className={styles.upRow}>
        <input
          ref={input}
          type="file"
          accept=".csv,.sdf"
          className={styles.upHidden}
          aria-label="Batch file (.csv or .sdf)"
          disabled={s.busy}
          onChange={(e) => {
            s.chooseFile(e.target.files?.[0] ?? null);
            e.target.value = ""; // allow choosing the same file again after Clear
          }}
        />
        <button type="button" className={styles.upBtn} disabled={s.busy} onClick={() => input.current?.click()}>
          Choose file
        </button>
        <span className={styles.upName}>{s.file ? s.file.name : "or drop a .csv or .sdf here"}</span>

        <label className={styles.upField}>
          <span>SMILES column</span>
          <input
            value={s.smilesColumn}
            disabled={s.busy}
            onChange={(e) => s.setSmilesColumn(e.target.value)}
            placeholder="auto-detect"
            aria-label="SMILES column name (CSV only; blank detects it)"
          />
        </label>

        <span style={{ flex: 1 }} />
        <button type="button" className={`${styles.upBtn} ${styles.upPrimary}`} disabled={!s.canRun} onClick={s.run}>
          Run batch
        </button>
        <button type="button" className={styles.upBtn} disabled={!s.file && s.phase.kind === "idle"} onClick={s.clear}>
          Clear
        </button>
      </div>

      <div className={styles.upRow}>
        <span className={failed ? styles.upErr : styles.upStatus} role={failed ? "alert" : "status"}>
          {s.fileProblem ?? phaseLabel(s.phase)}
        </span>
        {pct != null && (
          <progress className={styles.upProg} max={100} value={pct} aria-label="Batch progress">
            {pct}%
          </progress>
        )}
      </div>

      <p className={styles.upNote}>
        Up to {BATCH_INTERACTIVE_MAX.toLocaleString()} molecules are returned directly. Larger files, up to{" "}
        {BATCH_MAX_MOLECULES.toLocaleString()}, run as a queued job with live progress. Results are kept for 24
        hours. Each batch belongs to your account.
      </p>
    </div>
  );
}
