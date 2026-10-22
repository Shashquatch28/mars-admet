// Batch — high-density triage. Composes the matrix and a molecule inspector.
// It takes a CSV or SDF, runs POST /batch/predict, follows the progress stream for
// queued jobs and shows the returned rows through buildBatch and the grid. It shows
// only rows the service returned: with no API, or before a run, the grid is empty and
// says why (ADR-032).
//
// Honesty rules that shape this screen specifically:
//   - sorting is RAW numeric on one endpoint, never favourability (AGENTS.md #3)
//   - filtering hides rows the user asked to hide; it never hides a cell
//   - a failed row stays a row, carrying its error
//   - no aggregate score across endpoints, because no weighting is validated
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useBatchSession } from "../../app/batchSession";
import { usePredictSession } from "../../app/predictSession";
import { USING_API, saveMolecule } from "../../data/client";
import { downloadText } from "../../data/download";
import { usePrintReport } from "../../components/report/usePrintReport";
import { batchFileName, batchRowFileName, buildCsv, type ExportMolecule } from "../../domain/exportCsv";
import { SaveControl } from "../../components/SaveControl";
import { buildMoleculeRequest, moleculeKey, saveNote } from "../../domain/save";
import styles from "./batch.module.css";
import { useUiState } from "../../app/uiState";
import {
  buildBatch,
  filterRows,
  isFiltered,
  sortRows,
  NO_FILTER,
  type BatchRow,
  type FilterSpec,
  type SortSpec,
} from "../../domain/batch";
import { SHORT_LABEL } from "../../domain/endpoints";
import { fmtValue } from "../../domain/format";
import { BatchGrid } from "./BatchGrid";
import { BatchCoverage } from "./BatchCoverage";
import { ModelSource } from "../../components/ModelSource";
import { useGenerations } from "../../data/useGenerations";
import { FALLBACK_NOTE, fallbackCountInRows } from "../../domain/modelFamily";
import { BatchUpload } from "./BatchUpload";

export function BatchWorkspace() {
  const { density } = useUiState();
  const rowH = density === "compact" ? 30 : 36;

  const session = useBatchSession();
  const kermtEndpoints = useGenerations()?.kermt_endpoints ?? [];
  const navigate = useNavigate();
  const predict = usePredictSession();

  const summary = useMemo(
    () => buildBatch(session.result ?? { status: "done", total: 0, completed: 0, results: [] }),
    [session.result],
  );
  const [sort, setSort] = useState<SortSpec>({ kind: "input" });
  const [filter, setFilter] = useState<FilterSpec>(NO_FILTER);
  const [selected, setSelected] = useState<number | null>(null);
  // Rows: the molecule grid. Coverage: counts per endpoint over the whole run (ADR-034 item 5).
  const [view, setView] = useState<"rows" | "coverage">("rows");

  // A new result starts from input order with nothing filtered or selected.
  useEffect(() => {
    setSort({ kind: "input" });
    setFilter(NO_FILTER);
    setSelected(null);
  }, [session.resultId]);

  const visible = useMemo(
    () => sortRows(filterRows(summary.rows, filter), sort),
    [summary.rows, filter, sort],
  );

  const selectedRow = useMemo(
    () => summary.rows.find((r) => r.rowIndex === selected) ?? null,
    [summary.rows, selected],
  );

  const c = summary.counts;
  // Export covers the whole run in run order, not what the filter happens to show, and only real
  // results.
  const toExport = (r: (typeof summary.rows)[number]): ExportMolecule => ({
    row: r.rowIndex + 1,
    smilesInput: r.smilesInput,
    response: r.response,
    cells: r.cells,
    error: r.ok ? null : (r.error ?? "row failed"),
  });
  const canExport = USING_API && summary.rows.length > 0;
  const printReport = usePrintReport();
  const toggle = (k: keyof FilterSpec) => setFilter((f) => ({ ...f, [k]: !f[k] }));

  return (
    <>
      <section className={styles.batch} aria-label="Batch">
        {USING_API && <BatchUpload />}
        <div className={styles.bhd}>
          <span className={styles.bTitle}>Batch</span>
          <div className={styles.viewSw} role="group" aria-label="Batch view">
            <button
              type="button"
              className={`${styles.chip} ${view === "rows" ? styles.chipOn : ""}`}
              aria-pressed={view === "rows"}
              onClick={() => setView("rows")}
            >
              Rows
            </button>
            <button
              type="button"
              className={`${styles.chip} ${view === "coverage" ? styles.chipOn : ""}`}
              aria-pressed={view === "coverage"}
              onClick={() => setView("coverage")}
            >
              Coverage by endpoint
            </button>
          </div>
          <span className={styles.recon}>
            <b>{c.molecules}</b> molecules <span className={styles.reconD} aria-hidden="true">·</span>{" "}
            <b className={styles.reconOod}>{c.rowsWithOod}</b> with out-of-domain{" "}
            <span className={styles.reconD} aria-hidden="true">·</span> <b>{c.rowsWithStub}</b> with stub-served{" "}
            <span className={styles.reconD} aria-hidden="true">·</span> <b>{c.cellsNotReturned}</b> cells not returned{" "}
            <span className={styles.reconD} aria-hidden="true">·</span> <b>{c.failedRows}</b> failed
          </span>
          <span style={{ flex: 1 }} />
          <button
            className={styles.exportBtn}
            disabled={!canExport}
            title={`Download all ${summary.rows.length} rows of this run as CSV`}
            onClick={() =>
              downloadText(batchFileName(summary.rows.length), buildCsv(summary.rows.map(toExport)))
            }
          >
            Export results
          </button>
          {isFiltered(filter) && (
            <span className={styles.sortnote}>
              showing <b>{visible.length}</b> of <b>{summary.rows.length}</b>
            </span>
          )}
        </div>

        {view === "rows" && (
        <div className={styles.filterbar}>
          <label className={styles.search}>
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
              <circle cx="7" cy="7" r="4.2" />
              <path d="M10.2 10.2 13.5 13.5" />
            </svg>
            <input
              value={filter.text}
              onChange={(e) => setFilter((f) => ({ ...f, text: e.target.value }))}
              placeholder="Filter by SMILES or molecule_id"
              aria-label="Filter by SMILES or molecule id"
            />
          </label>

          <button
            className={`${styles.chip} ${filter.onlyOod ? styles.chipOn : ""}`}
            aria-pressed={filter.onlyOod}
            onClick={() => toggle("onlyOod")}
          >
            <span className={`${styles.chipMark} ${styles.markOod}`} aria-hidden="true" />
            Out of domain <span className={styles.chipCt}>{c.rowsWithOod}</span>
          </button>
          <button
            className={`${styles.chip} ${filter.onlyStub ? styles.chipOn : ""}`}
            aria-pressed={filter.onlyStub}
            onClick={() => toggle("onlyStub")}
          >
            <span className={`${styles.chipMark} ${styles.markStub}`} aria-hidden="true" />
            Stub-served <span className={styles.chipCt}>{c.rowsWithStub}</span>
          </button>
          <button
            className={`${styles.chip} ${filter.onlyFailed ? styles.chipOn : ""}`}
            aria-pressed={filter.onlyFailed}
            onClick={() => toggle("onlyFailed")}
          >
            <span className={`${styles.chipMark} ${styles.markFail}`} aria-hidden="true" />
            Failed <span className={styles.chipCt}>{c.failedRows}</span>
          </button>

          <span style={{ flex: 1 }} />

          {sort.kind === "raw" ? (
            <span className={styles.sortnote}>
              raw numeric sort · <b>{SHORT_LABEL[sort.endpoint]}</b> {sort.dir}
              <button className={styles.clearsort} onClick={() => setSort({ kind: "input" })}>
                clear
              </button>
            </span>
          ) : (
            <span className={styles.sortnote}>input order · click a column to sort by raw value</span>
          )}
        </div>
        )}

        <div className={styles.gridwrap} style={{ ["--row-h" as string]: `${rowH}px` }}>
          {summary.rows.length === 0 ? (
            <p className={styles.gridempty}>
              {!USING_API
                ? "No API is configured, so there is nothing to run. Batch needs the service."
                : session.busy
                ? "Waiting for the service. Rows appear here when the batch finishes."
                : session.phase.kind === "failed"
                  ? "The last run returned no rows. The reason is above; fix it and run again."
                  : "No batch has been run. Choose a CSV or SDF above and run it; every molecule gets one cell per endpoint, including the ones the service did not return."}
            </p>
          ) : view === "coverage" ? (
            <BatchCoverage rows={summary.rows} />
          ) : (
            <BatchGrid
              rows={visible}
              rowH={rowH}
              selected={selected}
              onSelect={(r: BatchRow) => setSelected(r.rowIndex)}
              sort={sort}
              onSort={setSort}
            />
          )}
        </div>

        <div className={styles.bfoot}>
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <circle cx="8" cy="8" r="6.5" />
            <path d="M8 7.3v4M8 5h.01" />
          </svg>
          <p>
            Every molecule carries one cell per endpoint, whether or not the service returned it. Sorting is a
            raw numeric sort on a single endpoint — MARS defines no direction of good, so nothing here is
            ranked, scored, or marked best, and rows with no value for the sorted endpoint always sort last
            rather than being ordered as though they were numbers.{" "}
            <span className={styles.flagLegend}>
              Row flags: <b>▲N</b> means N of that molecule's endpoints are out of domain; <b>—N</b> means N
              endpoints were not returned by the service.
            </span>
          </p>
        </div>
      </section>

      {printReport.element}
      <aside className={styles.inspector} aria-label="Molecule detail">
        <div className={styles.insphd}>
          <span className={styles.panelTitle}>Molecule detail</span>
          {selectedRow && (
            <span className={styles.sortnote}>
              row <b>{selectedRow.rowIndex + 1}</b>
            </span>
          )}
        </div>

        {!selectedRow ? (
          <p className={styles.nostate}>
            Select a molecule to inspect its full endpoint roster, reliability flags and provenance. Arrow keys
            move the focused cell; Enter opens the row.
          </p>
        ) : (
          <div className={styles.inspbody}>
            <div className={styles.inspsec}>
              <p className={styles.inspSmiles}>{selectedRow.smilesInput}</p>
              <dl>
                <dt>molecule_id</dt>
                <dd>{selectedRow.moleculeId ?? "—"}</dd>
                <dt>Generation</dt>
                <dd>{selectedRow.response?.model_version ?? "—"}</dd>
              </dl>
            </div>

            {!selectedRow.ok ? (
              <div className={styles.inspsec}>
                <div className={styles.failLabel}>Row failed</div>
                <p style={{ margin: "6px 0 0", fontSize: 10, lineHeight: 1.55, color: "var(--text-secondary)" }}>
                  {selectedRow.error}
                </p>
              </div>
            ) : (
              <>
                <div className={styles.minihd}>
                  <span style={{ flex: 1 }}>Endpoint</span>
                  <span className={styles.miniSrc}>Source</span>
                  <span>Value</span>
                </div>
                <div className={styles.minilist}>
                  {selectedRow.cells.map((cell) => {
                    const k = cell.state.kind;
                    const edge =
                      k === "out_of_domain"
                        ? styles.miniEdgeOod
                        : k === "stub_served"
                          ? styles.miniEdgeStub
                          : k === "not_returned" || k === "not_requested"
                            ? styles.miniEdgeMissing
                            : "";
                    return (
                      <div key={cell.endpoint} className={`${styles.minirow} ${edge}`}>
                        <span className={styles.miniName}>{cell.endpoint}</span>
                        <span className={styles.miniSrc}>
                          <ModelSource prediction={cell.prediction} />
                        </span>
                        {k === "not_returned" || k === "not_requested" ? (
                          <span className={styles.miniValMissing}>
                            {k === "not_requested" ? "not requested" : "not returned"}
                          </span>
                        ) : (
                          <span className={styles.miniVal}>{fmtValue(cell.prediction!, cell.meta)}</span>
                        )}
                      </div>
                    );
                  })}
                </div>
                {fallbackCountInRows(selectedRow.cells, kermtEndpoints) > 0 && (
                  <p className={styles.miniNote}>
                    † {FALLBACK_NOTE}. The Source column says which model answered each endpoint.
                  </p>
                )}
              </>
            )}
          </div>
        )}

        <div className={styles.inspfoot} style={{ flexWrap: "wrap" }}>
          <button
            disabled={!selectedRow}
            title="Load this molecule's SMILES into Predict (nothing is run until you press Run)"
            onClick={() => {
              if (!selectedRow) return;
              predict.clear(); // drop any result for a different molecule
              predict.setSmiles(selectedRow.smilesInput);
              navigate("/predict");
            }}
          >
            Open in Predict
          </button>
          <button
            disabled={!USING_API || !selectedRow}
            onClick={() =>
              selectedRow &&
              downloadText(batchRowFileName(selectedRow.rowIndex + 1), buildCsv([toExport(selectedRow)]))
            }
          >
            Export row
          </button>
          <button
            disabled={!USING_API || !selectedRow}
            title="Open this molecule as a printable report; choose Save as PDF in the print dialog"
            onClick={() => selectedRow && printReport.print(toExport(selectedRow))}
          >
            Report
          </button>
          {USING_API && (
            <SaveControl
              kind="molecule"
              withLabel
              buttonLabel="Save molecule"
              markKey={selectedRow?.response ? moleculeKey(selectedRow.response) : null}
              disabledReason={
                selectedRow?.response
                  ? null
                  : !selectedRow
                    ? "Select a molecule to save it."
                    : "This row failed, so there is nothing to save."
              }
              note={saveNote("molecule", selectedRow?.response?.model_version ?? null)}
              save={(input) => saveMolecule(buildMoleculeRequest(selectedRow!.response!, input))}
            />
          )}
        </div>
      </aside>
    </>
  );
}
