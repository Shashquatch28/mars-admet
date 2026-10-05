// OOD / STUB / RULE. No other variants exist (ADR-006) — there is deliberately
// no "good"/"safe"/"low risk" member. not_returned has no tag; it shows as the
// value text and a muted edge.
import styles from "./dataviz.module.css";
import type { Reliability } from "../../domain/rowState";

export function ReliabilityTag({ reliability }: { reliability: Reliability }) {
  if (reliability === "ood") return <span className={`${styles.tag} ${styles.ood}`}>OOD</span>;
  if (reliability === "stub") return <span className={`${styles.tag} ${styles.stub}`}>STUB</span>;
  if (reliability === "rule") return <span className={`${styles.tag} ${styles.rule}`}>RULE</span>;
  return null;
}
