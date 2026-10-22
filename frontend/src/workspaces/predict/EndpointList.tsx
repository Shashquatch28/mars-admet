// The results column: reconciliation header, column heads, the grouped roster,
// and the footnote. Implements the WCAG grid roving-focus pattern — one Tab stop,
// arrow keys move the focused row, Enter opens it in the inspector. Focus
// (keyboard) and selection (drives the inspector) are distinct states.
import { useEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent as ReactKeyboardEvent } from "react";
import styles from "./predict.module.css";
import { useUiState } from "../../app/uiState";
import type { Reconciliation, Row } from "../../domain/reconcile";
import { EndpointRow, rowId } from "./EndpointRow";
import { fallbackCount } from "../../domain/modelFamily";
import { useGenerations } from "../../data/useGenerations";

export function EndpointList({
  recon,
  loading,
  idle,
  onExport,
  onReport,
}: {
  recon: Reconciliation;
  loading?: boolean;
  idle?: boolean; // live session, nothing run yet — there is no request to reconcile
  onExport?: () => void; // absent when there is no real result to export (sample data, nothing run, failure)
  onReport?: () => void; // the same condition: a report is of a real result only
}) {
  const { selectedEndpoint, setSelectedEndpoint, density, setDensity } = useUiState();
  const rows = recon.rows;

  const indexOfEndpoint = useMemo(() => {
    const m = new Map<string, number>();
    rows.forEach((r, i) => m.set(r.endpoint, i));
    return m;
  }, [rows]);

  const [focused, setFocused] = useState(() =>
    selectedEndpoint ? (indexOfEndpoint.get(selectedEndpoint) ?? 0) : 0,
  );
  const rowEls = useRef<(HTMLDivElement | null)[]>([]);

  // when selection changes from elsewhere (⌘K), move focus to it and reveal it
  useEffect(() => {
    if (!selectedEndpoint) return;
    const i = indexOfEndpoint.get(selectedEndpoint);
    if (i == null) return;
    setFocused(i);
    rowEls.current[i]?.scrollIntoView({ block: "nearest" });
  }, [selectedEndpoint, indexOfEndpoint]);

  function move(to: number) {
    const i = Math.max(0, Math.min(rows.length - 1, to));
    setFocused(i);
    rowEls.current[i]?.scrollIntoView({ block: "nearest" });
  }

  function onKeyDown(e: ReactKeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      move(focused + 1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      move(focused - 1);
    } else if (e.key === "Home") {
      e.preventDefault();
      move(0);
    } else if (e.key === "End") {
      e.preventDefault();
      move(rows.length - 1);
    } else if (e.key === "Enter") {
      e.preventDefault();
      setSelectedEndpoint(rows[focused].endpoint);
    }
  }

  const select = (row: Row) => {
    setSelectedEndpoint(row.endpoint);
    setFocused(indexOfEndpoint.get(row.endpoint) ?? 0);
  };

  const c = recon.counts;
  // Rows the deployment routes to KERMT that XGBoost answered for this request (the KERMT service did not).
  const kermtEndpoints = useGenerations()?.kermt_endpoints ?? [];
  const fellBack = loading || idle
    ? 0
    : fallbackCount(
        rows.flatMap((r) => (r.prediction ? [r.prediction] : [])),
        kermtEndpoints,
      );

  return (
    <section
      className={styles.results}
      aria-label="Predictions"
      style={{ ["--row-h" as string]: density === "compact" ? "30px" : "36px" } as CSSProperties}
    >
      <div className={styles.reshd}>
        <span className={styles.resTitle}>Predictions</span>
        <span className={styles.recon}>
          {idle ? (
            "No request yet"
          ) : loading ? (
            <>
              <b>{c.requested}</b> requested
            </>
          ) : (
            <>
              <b>{c.requested}</b> requested <span className={styles.reconD} aria-hidden="true">·</span> <b>{c.returned}</b> returned{" "}
              <span className={styles.reconD} aria-hidden="true">·</span> <b className={styles.reconOod}>{c.outOfDomain}</b> out of domain{" "}
              <span className={styles.reconD} aria-hidden="true">·</span> <b>{c.stubServed}</b> stub-served
            </>
          )}
        </span>
        <span style={{ flex: 1 }} />
        <button className={styles.exp} onClick={onExport} disabled={!onExport} title="Download this result as CSV">
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M8 2v8M5 7l3 3 3-3M3 13h10" />
          </svg>
          Export
        </button>
        <button
          className={styles.exp}
          onClick={onReport}
          disabled={!onReport}
          title="Open this result as a printable report; choose Save as PDF in the print dialog"
        >
          Report
        </button>
        <div className={styles.densetog} role="group" aria-label="Density">
          <button
            className={density === "compact" ? styles.densetogOn : ""}
            aria-pressed={density === "compact"}
            onClick={() => setDensity("compact")}
          >
            Compact
          </button>
          <button
            className={density === "comfortable" ? styles.densetogOn : ""}
            aria-pressed={density === "comfortable"}
            onClick={() => setDensity("comfortable")}
          >
            Comfortable
          </button>
        </div>
      </div>

      <div
        className={styles.rowscroll}
        role="grid"
        aria-label="Endpoint predictions"
        aria-colcount={7}
        aria-activedescendant={rows[focused] ? rowId(rows[focused].endpoint) : undefined}
        tabIndex={0}
        onKeyDown={onKeyDown}
      >
        <div className={styles.colhead} role="row">
          <span role="columnheader">Endpoint</span>
          <span role="columnheader">Task</span>
          <span role="columnheader" className={styles.colR}>Value</span>
          <span role="columnheader">Unit</span>
          <span role="columnheader">Seed spread ±1σ</span>
          <span role="columnheader">Domain</span>
          <span role="columnheader" className={styles.colR}>Source</span>
        </div>
        {recon.groups.map((g) => (
          <div key={g.group} role="rowgroup">
            <div className={styles.grouphd} role="row">
              <div role="gridcell" aria-colspan={7} className={styles.grouphdCell}>
                <h2 className={styles.grouphdName}>{g.label}</h2>
                <span className={styles.grouphdCt}>
                  {g.rows.length}
                  <span className="sr-only"> endpoints</span>
                </span>
                <span className={styles.grouphdCl}>{g.cluster}</span>
              </div>
            </div>
            {g.rows.map((row) => {
              const i = indexOfEndpoint.get(row.endpoint) ?? 0;
              return (
                <EndpointRow
                  key={row.endpoint}
                  row={row}
                  selected={row.endpoint === selectedEndpoint}
                  focused={i === focused}
                  loading={loading}
                  onSelect={select}
                  rowRef={(el) => (rowEls.current[i] = el)}
                />
              );
            })}
          </div>
        ))}
      </div>

      <div className={styles.resfoot}>
        <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
          <circle cx="8" cy="8" r="6.5" />
          <path d="M8 7.3v4M8 5h.01" />
        </svg>
        <p>
          Every endpoint MARS can serve is listed on every result, whether or not the service returned it. An
          endpoint the model did not return, or that you left out of the run, is shown as a marked row (NOT RETURNED,
          NOT REQUESTED), never omitted. MARS applies no risk
          threshold and defines no direction of good — no value on this screen is styled as good or bad.
          {fellBack > 0 && (
            <>
              {" "}
              <b>†</b> {fellBack === 1 ? "1 endpoint is" : `${fellBack} endpoints are`} routed to KERMT but{" "}
              {fellBack === 1 ? "was" : "were"} answered by XGBoost for this request, because the KERMT service did not
              answer. The SOURCE column says which model answered each row.
            </>
          )}
        </p>
      </div>
    </section>
  );
}
