// Computed molecule properties and structural alerts (ADR-034 item 3), in the molecule column under Identity.
// They describe the structure, not a model, so they sit outside the endpoint roster and its counts. Plain values
// in one ink, no colour, no verdict; the notes say what they are and are not, in text and not in a tooltip.
import { Fragment } from "react";
import styles from "./predict.module.css";
import { PROPERTY_NOTES, PROPERTY_SOURCE, alertGroups, propertyLines } from "../../domain/properties";
import type { MoleculeProperties } from "../../types/contracts";

export function PropertiesPanel({ properties }: { properties: MoleculeProperties }) {
  const lines = propertyLines(properties);
  const groups = alertGroups(properties);
  return (
    <section aria-label="Computed properties">
      <div className={styles.flabel}>
        Computed properties <span className={styles.propSrc}>{PROPERTY_SOURCE} · not predictions</span>
      </div>
      <dl className={styles.idgrid}>
        {lines.map((l) => (
          <Fragment key={l.key}>
            <dt>{l.label}</dt>
            <dd>
              {l.value}
              {l.unit && <span className={styles.propUnit}> {l.unit}</span>}
            </dd>
          </Fragment>
        ))}
      </dl>
      <div className={`${styles.flabel} ${styles.propAlertHd}`}>Structural alerts</div>
      {groups.map((g) => (
        <p key={g.catalog} className={styles.alertLine}>
          <b>{g.catalog}</b> {g.names.length === 0 ? "no match" : g.names.join(", ")}
        </p>
      ))}
      {PROPERTY_NOTES.map((n) => (
        <p key={n} className={`${styles.vnote} ${styles.propNote}`}>
          {n}
        </p>
      ))}
    </section>
  );
}
