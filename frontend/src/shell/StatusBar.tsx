// Every readout here comes from the last real /predict response and the browser's
// own timing of it. Nothing the service does not tell us (cache TTL, rate-limit
// headroom) is shown: a value with no source is absent, not a plausible number.
import styles from "./shell.module.css";
import { fmtDateTime } from "../domain/format";
import { usePredictSession } from "../app/predictSession";

export function StatusBar() {
  const { result, running } = usePredictSession();
  return (
    <footer className={styles.statusbar}>
      {result ? (
        <>
          <span>{fmtDateTime(result.response.served_at)}</span>
          <span className={styles.cache}>
            ■ CACHE {result.response.cache_hit ? "HIT" : "MISS"} · {result.latencyMs} ms
          </span>
        </>
      ) : (
        <span>{running ? "request in flight" : "no request yet"}</span>
      )}
      <span className={styles.spacer} />
      <span className={styles.hints}>
        <span><b>↑↓</b> move row</span>
        <span><b>⏎</b> inspect</span>
        <span><b>⌘K</b> command</span>
        <span><b>⌘⏎</b> run</span>
      </span>
    </footer>
  );
}
