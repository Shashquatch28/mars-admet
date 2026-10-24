// The printed report (ADR-029). Rendered only to be printed: on screen it is not displayed at all, and
// in print it is the only thing shown. It reads a `ReportModel` and adds no judgement of its own: the
// value cell is one ink in every state, reliability is its own column (words) plus an edge and, for a
// stub, the diagonal hatch (ADR-006, ADR-007).
import { Fragment, useEffect } from "react";
import { createPortal } from "react-dom";
import styles from "./report.module.css";
import { reportTitle, type ReportModel, type ReportRow } from "../../domain/report";
import { inkSvg, svgDataUrl } from "../../domain/depiction";

const EDGE: Partial<Record<ReportRow["stateKind"], string>> = {
  out_of_domain: styles.edgeOod,
  not_returned: styles.edgeNotReturned,
  not_requested: styles.edgeNotRequested,
};

function RowView({ row }: { row: ReportRow }) {
  return (
    <tr className={EDGE[row.stateKind]}>
      <th scope="row">{row.endpoint}</th>
      <td className={row.hatch ? `${styles.value} ${styles.hatch}` : styles.value}>{row.value ?? "—"}</td>
      <td>{row.unit}</td>
      <td className={styles.num}>{row.spread ?? ""}</td>
      <td className={styles.num}>{row.heldOutError ?? ""}</td>
      <td>{row.domain}</td>
      <td className={styles.status}>{row.status ?? ""}</td>
      <td className={styles.model}>
        {row.model ?? ""}
        {row.fellBack ? " †" : ""}
      </td>
    </tr>
  );
}

// The report's ink is a token like every other colour (--report-ink); read it where it is used.
const reportInk = () => (typeof document === "undefined" ? "" : getComputedStyle(document.documentElement).getPropertyValue("--report-ink"));

export function PrintReport({ model }: { model: ReportModel }) {
  // The saved PDF's default file name is the page title; restore it afterwards.
  useEffect(() => {
    const before = document.title;
    document.title = reportTitle(model);
    return () => {
      document.title = before;
    };
  }, [model]);

  const c = model.counts;
  return createPortal(
    <article className={styles.report} data-print-report aria-hidden="true">
      <header>
        <h1>MARS prediction report</h1>
        <p className={styles.sub}>ADMET Rapid Screening · generated {model.generatedAt.replace("T", " ").slice(0, 16)} UTC</p>
      </header>

      <dl className={styles.facts}>
        {model.batchRow != null && (
          <>
            <dt>Batch row</dt>
            <dd>{model.batchRow}</dd>
          </>
        )}
        <dt>Input SMILES</dt>
        <dd className={styles.mono}>{model.smilesInput}</dd>
        {model.smilesStandardized && (
          <>
            <dt>Standardized SMILES</dt>
            <dd className={styles.mono}>{model.smilesStandardized}</dd>
          </>
        )}
        {model.name?.map((n) => (
          <Fragment key={n.label}>
            <dt>{n.label}</dt>
            <dd>{n.value}</dd>
          </Fragment>
        ))}
        {model.moleculeId && (
          <>
            <dt>Molecule ID</dt>
            <dd className={styles.mono}>{model.moleculeId}</dd>
          </>
        )}
        {model.modelVersion && (
          <>
            <dt>Model version</dt>
            <dd className={styles.mono}>{model.modelVersion}</dd>
          </>
        )}
        {model.servedAt && (
          <>
            <dt>Served at</dt>
            <dd className={styles.mono}>{model.servedAt}</dd>
          </>
        )}
      </dl>

      {model.structure && (
        <figure className={styles.structure}>
          {model.structure.kind === "drawn" ? (
            <img src={svgDataUrl(inkSvg(model.structure.svg, reportInk()))} alt="" width={320} height={220} />
          ) : (
            <p>Structure drawing not available: {model.structure.reason}</p>
          )}
          {model.structure.kind === "drawn" && <figcaption>Structure (RDKit drawing of the standardized SMILES)</figcaption>}
        </figure>
      )}

      {model.failure ? (
        <p className={styles.failure}>
          <b>No result for this molecule.</b> {model.failure}
        </p>
      ) : (
        <>
          <p className={styles.recon}>
            <b>{c.requested}</b> ML endpoints requested · <b>{c.returned}</b> returned · <b>{c.outOfDomain}</b> out of
            domain · <b>{c.stubServed}</b> stub-served · <b>{c.notReturned}</b> not returned
            {c.notRequested > 0 && (
              <>
                {" "}
                · <b>{c.notRequested}</b> not requested
              </>
            )}
          </p>
          {model.groups.map((g) => (
            <section key={g.group} className={styles.group}>
              <table>
                <caption>{g.label}</caption>
                <thead>
                  <tr>
                    <th scope="col">Endpoint</th>
                    <th scope="col">Value</th>
                    <th scope="col">Unit</th>
                    <th scope="col">Seed spread ±1σ</th>
                    <th scope="col">Held-out error</th>
                    <th scope="col">Applicability domain</th>
                    <th scope="col">Status</th>
                    <th scope="col">Model</th>
                  </tr>
                </thead>
                <tbody>
                  {g.rows.map((r) => (
                    <RowView key={r.endpoint} row={r} />
                  ))}
                </tbody>
              </table>
            </section>
          ))}
        </>
      )}

      {model.properties && !model.failure && (
        <section className={styles.group}>
          <table className={styles.propTable}>
            <caption>Computed properties ({model.properties.source}; not predictions)</caption>
            <thead>
              <tr>
                <th scope="col">Property</th>
                <th scope="col">Value</th>
                <th scope="col">Unit</th>
              </tr>
            </thead>
            <tbody>
              {model.properties.lines.map((l) => (
                <tr key={l.key}>
                  <th scope="row">{l.label}</th>
                  <td className={styles.value}>{l.value}</td>
                  <td>{l.unit}</td>
                </tr>
              ))}
              {model.properties.alerts.map((g) => (
                <tr key={g.catalog}>
                  <th scope="row">Structural alerts: {g.catalog}</th>
                  <td colSpan={2}>{g.names.length === 0 ? "no match" : g.names.join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <ul className={styles.propNotes}>
            {model.properties.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </section>
      )}

      <section className={styles.notes}>
        <h2>How to read this report</h2>
        <ul>
          {model.statements.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ul>
      </section>
    </article>,
    document.body,
  );
}
