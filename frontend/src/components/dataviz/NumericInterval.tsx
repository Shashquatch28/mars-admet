// The regression default: the interval printed, never drawn, because no
// validated per-endpoint display range exists (ADR-005).
import styles from "./dataviz.module.css";
import { fmtInterval } from "../../domain/format";

export function NumericInterval({ low, high, dp = 2 }: { low: number; high: number; dp?: number }) {
  return <span className={styles.numInterval}>{fmtInterval(low, high, dp)}</span>;
}
