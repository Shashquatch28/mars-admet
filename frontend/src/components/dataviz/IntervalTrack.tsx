// Bounded-axis interval + point tick. Refuses to render without an explicit
// domain — the type-level guard against inventing a scale (ADR-005). A caller
// that has no validated display range must use NumericInterval instead.
import styles from "./dataviz.module.css";
import { scalePct } from "./scale";

export interface IntervalTrackProps {
  low: number;
  high: number;
  value: number;
  domain: readonly [number, number]; // required, no default
}

export function IntervalTrack({ low, high, value, domain }: IntervalTrackProps) {
  const lo = scalePct(low, domain);
  const hi = scalePct(high, domain);
  const v = scalePct(value, domain);
  return (
    <span className={styles.track} aria-hidden="true">
      <span className={styles.rail} />
      <span className={styles.band} style={{ left: `${lo}%`, width: `${Math.max(0, hi - lo)}%` }} />
      <span className={styles.tick} style={{ left: `${v}%` }} />
    </span>
  );
}
