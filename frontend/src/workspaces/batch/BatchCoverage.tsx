// Coverage by endpoint for the run in hand (ADR-034 item 5). A text table of counts and, for regression
// endpoints, the smallest, middle and largest value returned in this batch. No chart, no flag on any value,
// no ordering by value: the rows are the fixed roster and the numbers are plain ink. Reliability is counted
// in its own columns and never recolours anything (domain/coverage.ts says why).
import { useMemo } from "react";
import styles from "./batch.module.css";
import { useGenerations } from "../../data/useGenerations";
import type { BatchRow } from "../../domain/batch";
import { COVERAGE_NOTES, buildCoverage, fmtObserved } from "../../domain/coverage";
import { SHORT_LABEL } from "../../domain/endpoints";

export function BatchCoverage({ rows }: { rows: BatchRow[] }) {
  const kermtEndpoints = useGenerations()?.kermt_endpoints;
  const cov = useMemo(() => buildCoverage(rows, kermtEndpoints ?? []), [rows, kermtEndpoints]);
  const anyFallback = cov.rows.some((r) => r.fellBack > 0);

  return (
    <div className={styles.covwrap}>
      <table className={styles.cov}>
        <caption className={styles.covCap}>
          Coverage by endpoint · <b>{cov.molecules.toLocaleString("en-US")}</b> molecules returned a result
          {cov.failedRows > 0 && (
            <>
              {" "}
              · <b>{cov.failedRows.toLocaleString("en-US")}</b> failed before inference and are not counted
            </>
          )}
          . All {rows.length.toLocaleString("en-US")} rows of the run, whatever the Rows view is filtered to.
        </caption>
        <thead>
          <tr>
            <th scope="col" className={styles.covL}>Endpoint</th>
            <th scope="col">Requested</th>
            <th scope="col">Returned</th>
            <th scope="col">Not returned</th>
            <th scope="col">Out of domain</th>
            <th scope="col">Stub-served</th>
            <th scope="col">XGBoost</th>
            <th scope="col">KERMT</th>
            <th scope="col">† fell back</th>
            <th scope="col" className={styles.covL}>Observed in this batch (min · median · max)</th>
            <th scope="col" className={styles.covL}>Unit</th>
          </tr>
        </thead>
        <tbody>
          {cov.rows.map((r) => (
            <tr key={r.endpoint}>
              <th scope="row" className={styles.covL} title={r.endpoint}>
                {SHORT_LABEL[r.endpoint]} <span className={styles.covTask}>{r.task === "regression" ? "REG" : "CLS"}</span>
              </th>
              <td>{r.requested}</td>
              <td>{r.returned}</td>
              <td>{r.notReturned}</td>
              <td>{r.outOfDomain}</td>
              <td>{r.stubServed}</td>
              <td>{r.xgboost}</td>
              <td>{r.kermt}</td>
              <td>{r.fellBack}</td>
              <td className={`${styles.covL} ${styles.covObs}`}>{r.observed ? fmtObserved(r.endpoint, r.observed) : "—"}</td>
              <td className={styles.covL}>{r.task === "regression" ? r.unit : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <ul className={styles.covNotes}>
        {COVERAGE_NOTES.map((n) => (
          <li key={n}>{n}</li>
        ))}
        {anyFallback && (
          <li>
            † fell back is non-zero in this batch: those values are for endpoints the deployment routes to KERMT, answered by XGBoost because the
            KERMT service did not answer.
          </li>
        )}
      </ul>
    </div>
  );
}
