// One endpoint, all states — the load-bearing component. There is deliberately
// no variant/tone/severity/status prop (ADR-006): every visual state is derived
// from the contract via deriveRowState upstream. The channels sit on different
// CSS properties so none can overwrite another, and the value cell is never
// restyled by hover/focus/selection or by reliability.
import styles from "./predict.module.css";
import type { Row } from "../../domain/reconcile";
import { DISPLAY_UNIT, PROB_DOMAIN, STUB_MODEL_ID } from "../../domain/endpoints";
import { fmtValue } from "../../domain/format";
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
  rowIndex: number;
}

export function EndpointRow({ row, selected, focused, loading, onSelect, rowRef, rowIndex }: EndpointRowProps) {
  const { endpoint, meta, prediction, state, reliability } = row;

  // Loading: the roster is known before the result (ADR-008), so rows keep their
  // final height and show a quiet placeholder instead of reflowing when values
  // land. No shimmer.
  if (loading) {
    const dash = { color: "var(--text-disabled)" } as const;
    return (
      <div ref={rowRef} role="row" aria-rowindex={rowIndex} className={styles.erow}>
        <span className={styles.edge} />
        <span className={styles.ename}>{endpoint}</span>
        <span className={styles.etask}>
          {meta.taskType === "regression" ? "REG" : meta.taskType === "classification" ? "CLS" : "RULE"}
        </span>
        <span className={styles.eval} style={dash}>·</span>
        <span className={styles.eunit}>{DISPLAY_UNIT[endpoint]}</span>
        <span className={styles.eunit} style={dash}>·</span>
        <span className={styles.edom} />
        <span className={styles.esource} style={dash}>·</span>
      </div>
    );
  }

  const edgeClass =
    reliability === "ood" || reliability === "stub"
      ? `${styles.edge} ${styles.edgeAmber}`
      : reliability === "notreturned"
        ? `${styles.edge} ${styles.edgeMuted}`
        : styles.edge;

  const cls = [styles.erow, focused ? styles.focused : "", selected ? styles.selected : ""]
    .filter(Boolean)
    .join(" ");

  // value cell
  let valueCell;
  if (state.kind === "not_returned") {
    valueCell = <span className={styles.evalNa}>not returned</span>;
  } else if (prediction) {
    const text = fmtValue(prediction, meta);
    valueCell =
      state.kind === "stub_served" ? (
        <span className={styles.eval}>
          <span className={styles.hatch}>{text}</span>
        </span>
      ) : (
        <span className={styles.eval}>{text}</span>
      );
  } else {
    valueCell = <span className={styles.eval} />;
  }

  // interval cell
  let intervalCell;
  if (!prediction || state.kind === "not_returned" || meta.taskType === "rule_based") {
    intervalCell = <span className={styles.eunit}>not applicable</span>;
  } else if (meta.taskType === "regression") {
    intervalCell = (
      <NumericInterval
        low={prediction.confidence_low}
        high={prediction.confidence_high}
        dp={prediction.unit === "% bound" ? 1 : 2}
      />
    );
  } else {
    intervalCell = (
      <span className={styles.eint}>
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
  const isReal =
    !!prediction && prediction.model_id !== STUB_MODEL_ID && meta.taskType !== "rule_based";
  const sourceCell =
    state.kind === "not_returned" ? (
      <span className={`${styles.esource} ${styles.esourceDash}`}>—</span>
    ) : isReal ? (
      <span className={styles.esource}>v1</span>
    ) : (
      <span className={styles.esource} />
    );

  return (
    <div
      ref={rowRef}
      role="row"
      aria-rowindex={rowIndex}
      aria-selected={selected}
      className={cls}
      onClick={() => onSelect(row)}
    >
      <span className={edgeClass} />
      <span className={styles.ename}>{endpoint}</span>
      <span className={styles.etask}>
        {meta.taskType === "regression" ? "REG" : meta.taskType === "classification" ? "CLS" : "RULE"}
      </span>
      {valueCell}
      <span className={styles.eunit}>{DISPLAY_UNIT[endpoint]}</span>
      {intervalCell}
      <span className={styles.edom}>
        <ReliabilityTag reliability={reliability} />
      </span>
      {sourceCell}
    </div>
  );
}
