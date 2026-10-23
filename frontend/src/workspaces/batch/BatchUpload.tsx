// The live Batch input: choose a CSV or SDF, optionally name the SMILES column, run, and
// watch the job. Everything the user needs to know about limits is written here in
// words, not in a tooltip. Progress is a determinate bar only once the service has
// reported a total; before that the status line says what is happening. Nothing animates.
import { useEffect, useRef, useState, type DragEvent } from "react";
import styles from "./batch.module.css";
import { useBatchSession } from "../../app/batchSession";
import { SaveControl } from "../../components/SaveControl";
import { saveReport } from "../../data/client";
import { buildBatchReportRequest, reportKey, saveNote } from "../../domain/save";
import { percentDone, phaseLabel, type BatchPhase } from "../../domain/batchJob";
import { batchUploadNote } from "../../domain/limitsCopy";
import { useLimits } from "../../data/useLimits";
import { useAnnounce } from "../../app/announce";
import { batchAnnouncement } from "../../domain/announce";
import { EndpointSelector } from "../predict/EndpointSelector";

export function BatchUpload() {
  const s = useBatchSession();
  const limits = useLimits();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  // The service reports every half second; the status line below is not live. What is announced is the start,
  // each quarter and the finish (domain/announce.ts); a failure is a role="alert".
  const announce = useAnnounce();
  const prevPhase = useRef<BatchPhase>(s.phase);
  useEffect(() => {
    const message = batchAnnouncement(prevPhase.current, s.phase);
    prevPhase.current = s.phase;
    if (message) announce(message);
  }, [s.phase, announce]);

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

        <EndpointSelector selected={s.selected} onChange={s.setSelected} disabled={s.busy} />

        <span style={{ flex: 1 }} />
        <button type="button" className={`${styles.upBtn} ${styles.upPrimary}`} disabled={!s.canRun} onClick={s.run}>
          Run batch
        </button>
        <button type="button" className={styles.upBtn} disabled={!s.file && s.phase.kind === "idle"} onClick={s.clear}>
          Clear
        </button>
      </div>

      <div className={styles.upRow}>
        <span className={failed ? styles.upErr : styles.upStatus} role={failed ? "alert" : undefined}>
          {s.fileProblem ?? phaseLabel(s.phase)}
        </span>
        {pct != null && (
          <progress className={styles.upProg} max={100} value={pct} aria-label="Batch progress">
            {pct}%
          </progress>
        )}
      </div>

      {s.result && (
        <div className={styles.upRow} style={{ flexWrap: "wrap" }}>
          <SaveControl
            kind="report"
            buttonLabel="Save report"
            buttonClassName={styles.upBtn}
            markKey={reportKey(s.resultId)}
            note={saveNote("report", null, s.result.results?.length ?? s.result.total)}
            save={(input) => saveReport(buildBatchReportRequest(s.result!, input))}
          />
        </div>
      )}

      <p className={styles.upNote}>{batchUploadNote(limits)}</p>
    </div>
  );
}
