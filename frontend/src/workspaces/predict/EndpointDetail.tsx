// Inspector body for the selected endpoint. The 26px mono headline is the single
// focal value; the AD gauge is the one honest bounded instrument. Provenance is
// stated in words, never implied.
import styles from "./predict.module.css";
import type { Row } from "../../domain/reconcile";
import type { PredictionResponse } from "../../types/contracts";
import { DISPLAY_UNIT, PROB_DOMAIN } from "../../domain/endpoints";
import { fmtValue, fmtInterval, fmtDateTime, fmtNum } from "../../domain/format";
import { ADGauge } from "../../components/dataviz/ADGauge";

function Rule() {
  return <div className={styles.irule} />;
}

export function EndpointDetail({ row, response }: { row: Row; response: PredictionResponse }) {
  const { endpoint, meta, prediction, state } = row;

  const chips: string[] = [];
  chips.push(
    meta.taskType === "regression"
      ? "REGRESSION"
      : meta.taskType === "classification"
        ? "CLASSIFICATION"
        : "RULE-BASED",
  );
  if (state.kind === "out_of_domain") chips.push("OUT OF DOMAIN");
  if (state.kind === "stub_served") chips.push("STUB-SERVED");

  const header = (
    <>
      <div className={styles.isubject}>{endpoint}</div>
      <div className={styles.imeta}>
        {chips.map((c, i) => (
          <span key={c}>
            {i > 0 && <span className={styles.imetaD}>· </span>}
            {c}
          </span>
        ))}
      </div>
    </>
  );

  if (state.kind === "not_returned") {
    return (
      <div className={styles.inspbody}>
        {header}
        <div className={styles.headline}>
          <span className={styles.headlineV} style={{ fontSize: 18, color: "var(--text-tertiary)" }}>
            NOT RETURNED
          </span>
          <span className={styles.headlineU}>{DISPLAY_UNIT[endpoint]}</span>
        </div>
        <Rule />
        <div className={styles.isec}>
          <p className={styles.nostate}>
            This endpoint was requested but the service did not return it. The row is kept so the roster stays
            complete — absence is a state, not a gap. It can be retried without re-running the others.
          </p>
        </div>
      </div>
    );
  }

  if (!prediction) return <div className={styles.inspbody}>{header}</div>;

  // The cutoff comes from the response only (Q19). null means the endpoint has no
  // applicability-domain index: draw no tick rather than invent one.
  const threshold = prediction.ad_threshold;
  const showGauge =
    (state.kind === "ok" || state.kind === "out_of_domain") && threshold != null;

  return (
    <div className={styles.inspbody}>
      {header}

      <div className={styles.headline}>
        <span className={state.kind === "stub_served" ? `${styles.headlineV} ${styles.hatch}` : styles.headlineV}>
          {fmtValue(prediction, meta)}
        </span>
        <span className={styles.headlineU}>{DISPLAY_UNIT[endpoint]}</span>
      </div>
      <Rule />

      {meta.taskType === "regression" && (
        <div className={styles.isec}>
          <dl className={styles.ikv}>
            <dt>Interval</dt>
            <dd>{fmtInterval(prediction.confidence_low, prediction.confidence_high, prediction.unit === "% bound" ? 1 : 2)}</dd>
            <dt>Interval width</dt>
            <dd>{fmtNum(Math.abs(prediction.confidence_high - prediction.confidence_low), prediction.unit === "% bound" ? 1 : 2)}</dd>
            <dt>Derived from</dt>
            <dd className={styles.ddDerived}>Spread across the 5 cross-validation seeds, not a coverage guarantee.</dd>
          </dl>
        </div>
      )}
      {meta.taskType === "classification" && (
        <div className={styles.isec}>
          <dl className={styles.ikv}>
            <dt>Ensemble</dt>
            <dd>{fmtInterval(prediction.confidence_low, prediction.confidence_high, 2)}</dd>
            <dt>Derived from</dt>
            <dd className={styles.ddDerived}>Spread across the 5 cross-validation seeds, not a coverage guarantee.</dd>
          </dl>
        </div>
      )}
      {meta.taskType === "rule_based" && (
        <div className={styles.isec}>
          <p className={styles.nostate}>
            Computed, not predicted. A rule-based synthesis score has no interval and no applicability domain —
            and no pretence that either exists.
          </p>
        </div>
      )}

      {state.kind === "out_of_domain" && (
        <>
          <Rule />
          <div className={styles.isec}>
            <div className={styles.oodbox}>
              <div className={styles.oodboxH}>
                <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M8 2 15 14H1z" />
                  <path d="M8 6.5v3.5M8 12h.01" />
                </svg>
                Outside applicability domain
              </div>
              <p>
                This molecule sits outside the region of chemical space this endpoint was trained on. The value
                above is still the model&rsquo;s output — treat it as unreliable rather than as a result.
              </p>
            </div>
            {showGauge && (
              <ADGauge
                endpoint={endpoint}
                value={prediction.knn_distance}
                threshold={threshold!}
                domain={PROB_DOMAIN}
                inDomain={false}
              />
            )}
          </div>
        </>
      )}

      {state.kind === "stub_served" && (
        <>
          <Rule />
          <div className={styles.isec}>
            <p className={styles.nostate}>
              No promoted model served this endpoint — the value came from stub-v0. It carries a hatch so it
              reads as &ldquo;not real data&rdquo; rather than as a severity. No applicability domain applies.
            </p>
          </div>
        </>
      )}

      {state.kind === "ok" && showGauge && (
        <>
          <Rule />
          <div className={styles.isec}>
            <ADGauge
              endpoint={endpoint}
              value={prediction.knn_distance}
              threshold={threshold!}
              domain={PROB_DOMAIN}
              inDomain={true}
            />
          </div>
        </>
      )}

      <Rule />
      <div className={styles.isec}>
        <div className={styles.seclbl}>Provenance</div>
        <dl className={styles.ikv} style={{ marginTop: 10 }}>
          {meta.taskType === "rule_based" ? (
            <>
              <dt>method</dt>
              <dd className={styles.ddProv}>RDKit SA_Score</dd>
            </>
          ) : (
            <>
              <dt>model_id</dt>
              <dd className={styles.ddProv}>{prediction.model_id}</dd>
            </>
          )}
          <dt>generation</dt>
          <dd>{response.model_version}</dd>
          <dt>served at</dt>
          <dd>{fmtDateTime(response.served_at)}</dd>
          <dt>cache</dt>
          <dd className={styles.ddProv}>{response.cache_hit ? "HIT · cached" : "MISS · computed now"}</dd>
        </dl>
      </div>
    </div>
  );
}
