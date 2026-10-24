// A molecule's looked-up name, with its source, in words (ADR-044). It takes a SMILES, asks the name hook and shows one of five
// states: nothing to name, looking, found, no name found, unavailable and why. It knows nothing about predictions, endpoints or
// values, so nothing it shows can depend on one, and it never colours or marks a name: a name is identity, not a verdict.
//
// `line` is for a header or a row (the name, then its source beside it); `block` is for a panel, where the IUPAC name, a few
// synonyms, the source's own record and what was sent to it all have room. No state is explained only by a tooltip.
import styles from "./moleculeName.module.css";
import { useMoleculeName } from "../data/useMoleculeName";
import { NAME_DISCLOSURE, NAME_DISCLOSURE_SHORT, type NameView } from "../domain/moleculeName";

export function NameLine({ view }: { view: NameView }) {
  switch (view.kind) {
    case "idle":
      return null;
    case "looking":
      return <span className={styles.src}>Looking up the name…</span>;
    case "found":
      return view.name ? (
        <span className={styles.line}>
          <span className={styles.name}>{view.name}</span> <span className={styles.src}>{view.source}</span>
        </span>
      ) : (
        <span className={styles.src}>{view.source} has a record for this structure but lists no name</span>
      );
    case "none":
      return (
        <span className={styles.line}>
          <span className={styles.none}>No name found</span> <span className={styles.src}>{view.source} has no record of this structure</span>
        </span>
      );
    case "unavailable":
      return (
        <span className={styles.line}>
          <span className={styles.none}>Name unavailable</span> <span className={styles.src}>{view.reason}</span>
        </span>
      );
  }
}

export function NameBlock({ view, disclose = true }: { view: NameView; disclose?: boolean }) {
  if (view.kind === "idle") return null;
  if (view.kind !== "found") {
    return (
      <div className={styles.block}>
        <NameLine view={view} />
        {view.kind === "none" && (
          <p className={styles.note}>
            This is an answer, not an error: the source holds no record for exactly this structure (stereochemistry and any salt are
            part of it), so MARS shows no name rather than guess one.
          </p>
        )}
        {view.kind === "unavailable" && <p className={styles.note}>The molecule is unaffected. MARS asks again the next time it is shown.</p>}
        {disclose && view.kind !== "looking" && <p className={styles.note}>{NAME_DISCLOSURE}</p>}
      </div>
    );
  }
  return (
    <div className={styles.block}>
      {view.name ? <p className={styles.nameBig}>{view.name}</p> : <p className={styles.src}>The record lists no name.</p>}
      {view.iupac && (
        <p className={styles.row}>
          <span className={styles.key}>IUPAC</span> {view.iupac}
        </p>
      )}
      {view.synonyms.length > 0 && (
        <p className={styles.row}>
          <span className={styles.key}>Also listed as</span> {view.synonyms.join("; ")}
        </p>
      )}
      <p className={styles.src}>
        Name from {view.source}
        {view.url && (
          <>
            {" · "}
            <a className={styles.link} href={view.url} target="_blank" rel="noreferrer noopener">
              open the record
            </a>
          </>
        )}
      </p>
      {disclose && <p className={styles.note}>{NAME_DISCLOSURE}</p>}
    </div>
  );
}

/**
 * Asks for the name of `smiles` and shows it. Use `useMoleculeName` and the parts above directly when the view is needed elsewhere
 * too. `disclose` adds the statement of what was sent: in full under a block, in one short line under a line.
 */
export function LookedUpName({ smiles, variant = "line", disclose }: { smiles: string | null | undefined; variant?: "line" | "block"; disclose?: boolean }) {
  const view = useMoleculeName(smiles);
  if (variant === "block") return <NameBlock view={view} disclose={disclose} />;
  return (
    <>
      <NameLine view={view} />
      {disclose && view.kind !== "idle" && view.kind !== "looking" && <span className={styles.noteLine}>{NAME_DISCLOSURE_SHORT}</span>}
    </>
  );
}
