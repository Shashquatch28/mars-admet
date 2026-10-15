// Batch — high-density triage. Composes the matrix and a molecule inspector.
// Runs on the illustrative fixture (240 molecules, so virtualization and the
// keyboard model are genuinely exercised); the real path is POST /batch/predict,
// which requires an account, and is not wired yet.
//
// Honesty rules that shape this screen specifically:
//   - sorting is RAW numeric on one endpoint, never favourability (AGENTS.md #3)
//   - filtering hides rows the user asked to hide; it never hides a cell
//   - a failed row stays a row, carrying its error
//   - no aggregate score across endpoints, because no weighting is validated
import { useEffect, useMemo, useState } from "react";
import styles from "./batch.module.css";
import { useUiState } from "../../app/uiState";
import {
  buildBatch,
  filterRows,
  isFiltered,
  makeBatchFixture,
  sortRows,
  NO_FILTER,
  type BatchRow,
  type FilterSpec,
  type SortSpec,
} from "../../domain/batch";
import { SHORT_LABEL } from "../../domain/endpoints";
import { fmtValue } from "../../domain/format";
import { BatchGrid } from "./BatchGrid";

export function BatchWorkspace() {
  const { density, setIsSample } = useUiState();
  const rowH = density === "compact" ? 30 : 36;

  useEffect(() => setIsSample(true), [setIsSample]);

  const summary = useMemo(() => buildBatch(makeBatchFixture(240)), []);
  const [sort, setSort] = useState<SortSpec>({ kind: "input" });
  const [filter, setFilter] = useState<FilterSpec>(NO_FILTER);
  const [selected, setSelected] = useState<number | null>(null);

  const visible = useMemo(
    () => sortRows(filterRows(summary.rows, filter), sort),
    [summary.rows, filter, sort],
  );

  const selectedRow = useMemo(
    () => summary.rows.find((r) => r.rowIndex === selected) ?? null,
    [summary.rows, selected],
  );

  const c = summary.counts;
  const toggle = (k: keyof FilterSpec) => setFilter((f) => ({ ...f, [k]: !f[k] }));

  return (
    <>
      <section className={styles.batch} aria-label="Batch">
        <div className={styles.bhd}>
          <span className={styles.bTitle}>Batch</span>
          <span className={styles.recon}>
            <b>{c.molecules}</b> molecules <span className={styles.reconD}>·</span>{" "}
            <b className={styles.reconOod}>{c.rowsWithOod}</b> with out-of-domain{" "}
            <span className={styles.reconD}>·</span> <b>{c.rowsWithStub}</b> with stub-served{" "}
            <span className={styles.reconD}>·</span> <b>{c.cellsNotReturned}</b> cells not returned{" "}
            <span className={styles.reconD}>·</span> <b>{c.failedRows}</b> failed
          </span>
          <span style={{ flex: 1 }} />
          {isFiltered(filter) && (
            <span className={styles.sortnote}>
              showing <b>{visible.length}</b> of <b>{summary.rows.length}</b>
            </span>
          )}
        </div>

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

        <div className={styles.gridwrap} style={{ ["--row-h" as string]: `${rowH}px` }}>
          <BatchGrid
            rows={visible}
            rowH={rowH}
            selected={selected}
            onSelect={(r: BatchRow) => setSelected(r.rowIndex)}
            sort={sort}
            onSort={setSort}
          />
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
            rather than being ordered as though they were numbers.
          </p>
        </div>
      </section>

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
              </>
            )}
          </div>
        )}

        <div className={styles.inspfoot}>
          <button>Open in Predict</button>
          <button>Export row</button>
        </div>
      </aside>
    </>
  );
}
