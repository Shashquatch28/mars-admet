// OOD / STUB / RULE are tags. No other variants exist (ADR-006) — there is
// deliberately no "good"/"safe"/"low risk" member. The two absent states have no
// tag: the row says it in words in the value cell (NOT RETURNED / NOT REQUESTED)
// and in the edge — solid for a service failure, dashed for the user's own
// omission (ADR-028). The switch is exhaustive so a new state has to be decided here.
import styles from "./dataviz.module.css";
import type { Reliability } from "../../domain/rowState";

export function ReliabilityTag({ reliability }: { reliability: Reliability }) {
  switch (reliability) {
    case "ood":
      return <span className={`${styles.tag} ${styles.ood}`}>OOD</span>;
    case "stub":
      return <span className={`${styles.tag} ${styles.stub}`}>STUB</span>;
    case "rule":
      return <span className={`${styles.tag} ${styles.rule}`}>RULE</span>;
    case "notreturned":
    case "notrequested":
    case null:
      return null;
    default: {
      const unreachable: never = reliability;
      return unreachable;
    }
  }
}
