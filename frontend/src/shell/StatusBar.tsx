import styles from "./shell.module.css";
import { fmtDateTime } from "../domain/format";
import { FIXTURE_RESPONSE } from "../domain/fixtures";

export function StatusBar() {
  const r = FIXTURE_RESPONSE;
  return (
    <footer className={styles.statusbar}>
      <span>{fmtDateTime(r.served_at)}</span>
      <span className={styles.cache}>■ CACHE {r.cache_hit ? "HIT" : "MISS"} · 412 ms</span>
      <span>computed now · cached for 48 h</span>
      <span>rate 7/60 per min</span>
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
