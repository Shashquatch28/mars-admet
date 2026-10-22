// One endpoint, all states — the load-bearing component. There is deliberately
// no variant/tone/severity/status prop (ADR-006): every visual state is derived
// from the contract via deriveRowState upstream. The channels sit on different
// CSS properties so none can overwrite another, and the value cell is never
// restyled by hover/focus/selection or by reliability.
import styles from "./predict.module.css";
import type { Row } from "../../domain/reconcile";
import { DISPLAY_UNIT, PROB_DOMAIN } from "../../domain/endpoints";
import { familyLabel, servedByFallback } from "../../domain/modelFamily";
import { useGenerations } from "../../data/useGenerations";
import { decimalPlaces, fmtValue } from "../../domain/format";
import { IntervalTrack } from "../../components/dataviz/IntervalTrack";
import { NumericInterval } from "../../components/dataviz/NumericInterval";
import { ReliabilityTag } from "../../components/dataviz/ReliabilityTag";

export interface EndpointRowProps {
  row: Row;
  selected: boolean; // user attention channel
  focused: boolean; // keyboard roving channel
  loading?: boolean; // values in flight — placeholder cells, roster height held
  onSelect: (row: Row) => void;
  rowRef?: (el: HTMLDivElement | null) => void;
}

/** The DOM id of an endpoint's row: the grid's `aria-activedescendant` points at it. */
export const rowId = (endpoint: string) => `erow-${endpoint}`;

export function EndpointRow({ row, selected, focused, loading, onSelect, rowRef }: EndpointRowProps) {
  const { endpoint, meta, prediction, state, reliability } = row;
  const kermtEndpoints = useGenerations()?.kermt_endpoints ?? [];

  // Loading: the roster is known before the result (ADR-008), so rows keep their
  // final height and show a quiet placeholder instead of reflowing when values
  // land. No shimmer.
  if (loading) {
    const dash = { color: "var(--text-disabled)" } as const;
    return (
      <div ref={rowRef} role="row" id={rowId(endpoint)} className={styles.erow}>
        <span className={styles.edge} aria-hidden="true" />
        <span className={styles.ename} role="rowheader">{endpoint}</span>
        <span className={styles.etask} role="gridcell">
          {meta.taskType === "regression" ? "REG" : meta.taskType === "classification" ? "CLS" : "RULE"}
        </span>
        <span className={styles.eval} role="gridcell" style={dash}>
          <span aria-hidden="true">·</span>
          <span className="sr-only">value pending</span>
        </span>
        <span className={styles.eunit} role="gridcell">{DISPLAY_UNIT[endpoint]}</span>
        <span className={styles.eunit} role="gridcell" style={dash}>
          <span aria-hidden="true">·</span>
        </span>
        <span className={styles.edom} role="gridcell" />
        <span className={styles.esource} role="gridcell" style={dash}>
          <span aria-hidden="true">·</span>
        </span>
      </div>
    );
  }

  const edgeClass =
    reliability === "ood" || reliability === "stub"
      ? `${styles.edge} ${styles.edgeAmber}`
      : reliability === "notreturned"
        ? `${styles.edge} ${styles.edgeMuted}`
        : reliability === "notrequested"
          ? `${styles.edge} ${styles.edgeUnrequested}`
          : styles.edge;

  const cls = [styles.erow, focused ? styles.focused : "", selected ? styles.selected : ""]
    .filter(Boolean)
    .join(" ");

  // value cell
  let valueCell;
  if (state.kind === "not_returned") {
    valueCell = <span className={styles.evalNa} role="gridcell">not returned</span>;
  } else if (state.kind === "not_requested") {
    valueCell = <span className={styles.evalNa} role="gridcell">not requested</span>;
  } else if (prediction) {
    const text = fmtValue(prediction, meta);
    valueCell =
      state.kind === "stub_served" ? (
        <span className={styles.eval} role="gridcell">
          <span className={styles.hatch}>{text}</span>
        </span>
      ) : (
        <span className={styles.eval} role="gridcell">{text}</span>
      );
  } else {
    valueCell = <span className={styles.eval} role="gridcell" />;
  }

  // interval cell
  let intervalCell;
  if (!prediction || state.kind === "not_returned" || state.kind === "not_requested" || meta.taskType === "rule_based") {
    intervalCell = <span className={styles.eunit} role="gridcell">not applicable</span>;
  } else if (meta.taskType === "regression") {
    intervalCell = (
      <span role="gridcell" className={styles.cellfill}>
        <NumericInterval
          low={prediction.confidence_low}
          high={prediction.confidence_high}
          dp={decimalPlaces(prediction.endpoint)}
        />
      </span>
    );
  } else {
    intervalCell = (
      <span className={styles.eint} role="gridcell">
        <IntervalTrack
          low={prediction.confidence_low}
          high={prediction.confidence_high}
          value={prediction.value}
          domain={PROB_DOMAIN}
        />
      </span>
    );
  }

  // source cell
  // Which model answered, read from the row's own model_id (never a constant). A † marks a row the
  // deployment routes to KERMT that XGBoost answered for this request; the list's note says so in words.
  const sourceText = prediction ? familyLabel(prediction.model_id) : "";
  const fellBack = servedByFallback(prediction, kermtEndpoints);
  const sourceCell =
    state.kind === "not_returned" || state.kind === "not_requested" ? (
      <span className={`${styles.esource} ${styles.esourceDash}`} role="gridcell">
        <span aria-hidden="true">—</span>
        <span className="sr-only">no source</span>
      </span>
    ) : (
      <span className={styles.esource} role="gridcell">
        {sourceText}
        {fellBack && (
          <>
            <span aria-hidden="true"> †</span>
            <span className="sr-only"> (routed to KERMT, answered by XGBoost)</span>
          </>
        )}
      </span>
    );

  return (
    <div
      ref={rowRef}
      role="row"
      id={rowId(endpoint)}
      aria-selected={selected}
      className={cls}
      onClick={() => onSelect(row)}
    >
      <span className={edgeClass} aria-hidden="true" />
      <span className={styles.ename} role="rowheader">{endpoint}</span>
      <span className={styles.etask} role="gridcell">
        {meta.taskType === "regression" ? "REG" : meta.taskType === "classification" ? "CLS" : "RULE"}
      </span>
      {valueCell}
      <span className={styles.eunit} role="gridcell">{DISPLAY_UNIT[endpoint]}</span>
      {intervalCell}
      <span className={styles.edom} role="gridcell">
        <ReliabilityTag reliability={reliability} />
      </span>
      {sourceCell}
    </div>
  );
}
