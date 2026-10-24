// "See it work": the real roster and inspector for one example molecule, from a real call to the service
// (ADR-032: nothing on screen is invented, so with no answer there are no values, only the roster).
// It reads the same reconciliation, formatters and data-viz components as Predict, so the reliability
// channels look and mean the same thing here: the value cell is one ink, the edge and tag carry reliability,
// the hatch means the value did not come from a promoted model. Selecting a row here is local to this page.
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import styles from "./landing.module.css";
import { USING_API, fetchPrediction } from "../data/client";
import { EXAMPLE_SMILES } from "./entry";
import { DISPLAY_UNIT, PROB_DOMAIN, SHORT_LABEL } from "../domain/endpoints";
import { reconcile, requestedMlEndpoints, type Row } from "../domain/reconcile";
import { decimalPlaces, fmtInterval, fmtValue } from "../domain/format";
import { familyLabel } from "../domain/modelFamily";
import { ADGauge } from "../components/dataviz/ADGauge";
import { IntervalTrack } from "../components/dataviz/IntervalTrack";
import { NumericInterval } from "../components/dataviz/NumericInterval";
import { ReliabilityTag } from "../components/dataviz/ReliabilityTag";
import type { Endpoint } from "../types/contracts";

// With no answer yet there is no reliability to show, so a row waiting for the service has no edge: "not
// returned" is a statement about a request that was made and answered without the row, not about one in flight.
function edgeClass(r: Row, answered: boolean): string {
  if (!answered) return styles.edge;
  if (r.reliability === "ood" || r.reliability === "stub") return `${styles.edge} ${styles.edgeAmber}`;
  if (r.reliability === "notreturned" || r.reliability === "rule") return `${styles.edge} ${styles.edgeMuted}`;
  return styles.edge;
}

export function Specimen() {
  const q = useQuery({
    queryKey: ["landing-specimen", EXAMPLE_SMILES],
    queryFn: () => fetchPrediction(EXAMPLE_SMILES),
    enabled: USING_API,
    retry: false,
    staleTime: Infinity,
  });
  const result = q.data ?? null;
  const recon = useMemo(
    () => reconcile(result?.response ?? null, requestedMlEndpoints(result?.sent)),
    [result],
  );
  const [selected, setSelected] = useState<Endpoint>("solubility_logs");
  const row = recon.rows.find((r) => r.endpoint === selected) ?? recon.rows[0];
  const loading = USING_API && q.isPending;
  const answered = result !== null;

  const status = !USING_API
    ? "No API is configured, so there are no values to show."
    : loading
      ? "Running the example against the service."
      : q.isError
        ? "The service did not answer, so no values are shown."
        : null;
  const c = recon.counts;

  return (
    <div className={styles.spec}>
      <div className={styles.specMain}>
        <div className={styles.specHd}>
          <span className={styles.label}>Example molecule</span>
          <span className={styles.specSmiles}>{EXAMPLE_SMILES}</span>
          <span className={styles.specSp} />
          <span className={styles.specCount}>
            {status ?? (
              <>
                <b>{c.requested}</b> requested <span aria-hidden="true">·</span> <b>{c.returned}</b> returned{" "}
                <span aria-hidden="true">·</span> <b>{c.outOfDomain}</b> out of domain
              </>
            )}
          </span>
        </div>
        <div className={styles.specScroll}>
          <div className={styles.specGrid}>
            <div className={`${styles.srow} ${styles.shead}`}>
              <span />
              <span className={styles.sName}>Endpoint</span>
              <span>Value</span>
              <span>Seed spread ±1σ</span>
              <span>State</span>
              <span>Source</span>
            </div>
            {recon.groups.map((g) => (
              <div key={g.group}>
                <div className={styles.sgroup}>{g.label}</div>
                {g.rows.map((r) => {
                  const p = r.prediction;
                  const on = r.endpoint === row.endpoint;
                  return (
                    <button
                      key={r.endpoint}
                      type="button"
                      className={on ? `${styles.srow} ${styles.srowBtn} ${styles.srowOn}` : `${styles.srow} ${styles.srowBtn}`}
                      aria-pressed={on}
                      onClick={() => setSelected(r.endpoint)}
                    >
                      <span className={edgeClass(r, answered)} aria-hidden="true" />
                      <span className={styles.sName}>
                        {r.endpoint}
                        <span className={styles.sShort}>{SHORT_LABEL[r.endpoint]}</span>
                      </span>
                      <span className={styles.sVal}>
                        {p ? (
                          r.state.kind === "stub_served" ? (
                            <span className={styles.hatch}>{fmtValue(p, r.meta)}</span>
                          ) : (
                            fmtValue(p, r.meta)
                          )
                        ) : answered && r.state.kind === "not_returned" ? (
                          <span className={styles.sNa}>not returned</span>
                        ) : (
                          <>
                            <span className={styles.sNa} aria-hidden="true">·</span>
                            <span className="sr-only">value pending</span>
                          </>
                        )}
                        <span className={styles.sUnit}>{DISPLAY_UNIT[r.endpoint]}</span>
                      </span>
                      <span className={styles.sSpread}>
                        {p && r.meta.taskType === "regression" && (
                          <NumericInterval low={p.confidence_low} high={p.confidence_high} dp={decimalPlaces(p.endpoint)} />
                        )}
                        {p && r.meta.taskType === "classification" && (
                          <>
                            <IntervalTrack low={p.confidence_low} high={p.confidence_high} value={p.value} domain={PROB_DOMAIN} />
                            <span className={styles.sRange}>{fmtInterval(p.confidence_low, p.confidence_high)}</span>
                          </>
                        )}
                      </span>
                      <span>
                        <ReliabilityTag reliability={r.reliability} />
                      </span>
                      <span className={styles.sSrc}>{p ? familyLabel(p.model_id) : "—"}</span>
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className={styles.specSide}>
        <div className={styles.label}>Selected</div>
        <div className={styles.sideName}>{row.endpoint}</div>
        {row.prediction ? (
          <>
            <div className={styles.sideHead}>
              <span className={row.state.kind === "stub_served" ? `${styles.sideVal} ${styles.hatch}` : styles.sideVal}>
                {fmtValue(row.prediction, row.meta)}
              </span>
              <span className={styles.sideUnit}>{DISPLAY_UNIT[row.endpoint]}</span>
            </div>
            <dl className={styles.sideDl}>
              {row.meta.taskType !== "rule_based" && (
                <>
                  <dt>Seed spread ±1σ</dt>
                  <dd>{fmtInterval(row.prediction.confidence_low, row.prediction.confidence_high, decimalPlaces(row.endpoint))}</dd>
                </>
              )}
              <dt>Served by</dt>
              <dd>{row.meta.taskType === "rule_based" ? "RDKit rule, not a model" : (familyLabel(row.prediction.model_id) || "stub")}</dd>
              <dt>model_id</dt>
              <dd>{row.prediction.model_id}</dd>
            </dl>
            {(row.state.kind === "ok" || row.state.kind === "out_of_domain") && row.prediction.ad_threshold != null && (
              <div className={styles.sideGauge}>
                <ADGauge
                  endpoint={row.endpoint}
                  value={row.prediction.knn_distance}
                  threshold={row.prediction.ad_threshold}
                  domain={PROB_DOMAIN}
                  inDomain={row.state.kind === "ok"}
                />
              </div>
            )}
            {row.state.kind === "stub_served" && (
              <p className={styles.sideNote}>This value did not come from a promoted model, so it carries the hatch and has no applicability domain.</p>
            )}
          </>
        ) : answered && row.state.kind === "not_returned" ? (
          <p className={styles.sideNote}>
            The service was asked for this endpoint and did not answer. It stays in the roster so its absence is visible; MARS does not fill it in.
          </p>
        ) : (
          <p className={styles.sideNote}>Select a row to see its value, spread, source and applicability domain once the example has run.</p>
        )}
      </div>
    </div>
  );
}
