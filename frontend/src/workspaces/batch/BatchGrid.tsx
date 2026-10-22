// The Batch matrix: molecules down, the full 15-endpoint roster across.
//
// Implements the WCAG grid pattern for a VIRTUALIZED grid, which is the part
// CRAFT_AND_INTERACTION §8 promised and the reason this component exists:
//
//  - the scroll container is the single Tab stop (role="grid")
//  - arrow keys move a focused CELL in two dimensions, Enter opens the row
//  - focus is tracked as {row index in the data, column index} — NOT as a DOM
//    node. A virtualized cell unmounts when it scrolls out of the window, so
//    holding real DOM focus on it would drop focus to the body. Instead the
//    container keeps focus and aria-activedescendant points at the focused
//    cell's id, which is the correct ARIA pattern here and survives scrolling.
//  - aria-rowindex reports the TRUE index in the data, so a screen reader says
//    "row 412 of 240-plus" rather than the position in the rendered window.
import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import styles from "./batch.module.css";
import {
  ALL_ENDPOINTS,
  DISPLAY_GROUP_LABEL,
  DISPLAY_GROUP_ORDER,
  ENDPOINT_METADATA,
  SHORT_LABEL,
  displayGroupOf,
} from "../../domain/endpoints";
import { fmtValue } from "../../domain/format";
import type { BatchRow, SortSpec } from "../../domain/batch";
import type { Endpoint } from "../../types/contracts";

const COL_COUNT = ALL_ENDPOINTS.length + 1; // +1 for the molecule row header

const GROUP_SPANS = DISPLAY_GROUP_ORDER.map((g) => ({
  group: g,
  label: DISPLAY_GROUP_LABEL[g],
  span: ALL_ENDPOINTS.filter((e) => displayGroupOf(e) === g).length,
})).filter((g) => g.span > 0);

const cellId = (rowIndex: number, col: number) => `bc-${rowIndex}-${col}`;

/** Accessible name for a cell: the state is in the name, not only in the colour. */
function cellLabel(row: BatchRow, endpoint: Endpoint, cell: BatchRow["cells"][number]): string {
  const name = `${endpoint}, molecule ${row.rowIndex + 1}`;
  switch (cell.state.kind) {
    case "not_returned":
      return `${name}: not returned`;
    case "not_requested":
      return `${name}: not requested`;
    case "out_of_domain":
      return `${name}: ${fmtValue(cell.prediction!, cell.meta)}, outside applicability domain`;
    case "stub_served":
      return `${name}: ${fmtValue(cell.prediction!, cell.meta)}, stub-served, not a trained prediction`;
    case "rule_based":
      return `${name}: ${fmtValue(cell.prediction!, cell.meta)}, computed rule`;
    default:
      return `${name}: ${fmtValue(cell.prediction!, cell.meta)}`;
  }
}

export function BatchGrid({
  rows,
  rowH,
  selected,
  onSelect,
  sort,
  onSort,
}: {
  rows: BatchRow[];
  rowH: number;
  selected: number | null;
  onSelect: (row: BatchRow) => void;
  sort: SortSpec;
  onSort: (s: SortSpec) => void;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [focus, setFocus] = useState<{ r: number; c: number }>({ r: 0, c: 0 });

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => rowH,
    overscan: 12,
  });

  // Re-measure when the density changes.
  useEffect(() => virtualizer.measure(), [rowH, virtualizer]);

  // Keep the focused cell inside the data when filtering or sorting shrinks it.
  useEffect(() => {
    setFocus((f) => ({ r: Math.min(f.r, Math.max(0, rows.length - 1)), c: f.c }));
  }, [rows.length]);

  const focusedRow = rows[focus.r];
  const activeId = focusedRow ? cellId(focusedRow.rowIndex, focus.c) : undefined;

  function move(r: number, c: number) {
    const nr = Math.max(0, Math.min(rows.length - 1, r));
    const nc = Math.max(0, Math.min(COL_COUNT - 1, c));
    setFocus({ r: nr, c: nc });
    virtualizer.scrollToIndex(nr, { align: "auto" });
  }

  function onKeyDown(e: ReactKeyboardEvent) {
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        move(focus.r + 1, focus.c);
        break;
      case "ArrowUp":
        e.preventDefault();
        move(focus.r - 1, focus.c);
        break;
      case "ArrowRight":
        e.preventDefault();
        move(focus.r, focus.c + 1);
        break;
      case "ArrowLeft":
        e.preventDefault();
        move(focus.r, focus.c - 1);
        break;
      case "Home":
        e.preventDefault();
        move(0, focus.c);
        break;
      case "End":
        e.preventDefault();
        move(rows.length - 1, focus.c);
        break;
      case "Enter":
        e.preventDefault();
        if (focusedRow) onSelect(focusedRow);
        break;
      default:
    }
  }

  function headerSort(endpoint: Endpoint) {
    if (sort.kind === "raw" && sort.endpoint === endpoint) {
      onSort(sort.dir === "desc" ? { kind: "raw", endpoint, dir: "asc" } : { kind: "input" });
    } else {
      onSort({ kind: "raw", endpoint, dir: "desc" });
    }
  }

  const items = virtualizer.getVirtualItems();
  const gridRow = `${styles.gridrow}`;

  return (
    <div
      className={styles.vscroll}
      ref={scrollRef}
      role="grid"
      aria-label="Batch predictions"
      aria-rowcount={rows.length}
      aria-colcount={COL_COUNT}
      aria-activedescendant={activeId}
      tabIndex={0}
      onKeyDown={onKeyDown}
    >
      <div className={styles.stickyhead}>
        {/* endpoint grouping — the same categories as Predict, spanning their columns */}
        <div className={`${gridRow} ${styles.groupbar}`} role="row" aria-hidden="true">
          <span />
          {GROUP_SPANS.map((g) => (
            <span key={g.group} style={{ gridColumn: `span ${g.span}` }}>
              {g.label}
              <span className={styles.groupbarCt}>{g.span}</span>
            </span>
          ))}
        </div>

        <div className={`${gridRow} ${styles.colhead}`} role="row">
          <span role="columnheader" aria-colindex={1}>
            Molecule
          </span>
          {ALL_ENDPOINTS.map((e, i) => {
            const active = sort.kind === "raw" && sort.endpoint === e;
            const meta = ENDPOINT_METADATA[e];
            return (
              <button
                key={e}
                role="columnheader"
                aria-colindex={i + 2}
                aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}
                className={active ? styles.colheadOn : undefined}
                title={`${e} — ${meta.taskType}. Click to sort by raw value.`}
                onClick={() => headerSort(e)}
              >
                {SHORT_LABEL[e]}
                {active && <span className={styles.sortcaret}>{sort.dir === "asc" ? "↑" : "↓"}</span>}
              </button>
            );
          })}
        </div>
      </div>

      <div className={styles.vsizer} style={{ height: virtualizer.getTotalSize() }}>
        {items.map((v) => {
          const row = rows[v.index];
          if (!row) return null;
          const isSel = selected === row.rowIndex;
          const isFocusRow = focus.r === v.index;

          return (
            <div
              key={row.rowIndex}
              role="row"
              aria-rowindex={row.rowIndex + 1}
              aria-selected={isSel}
              className={`${gridRow} ${styles.row} ${isSel ? styles.rowSel : ""}`}
              style={{ height: v.size, transform: `translateY(${v.start}px)` }}
            >
              {/* molecule row header */}
              <div
                role="rowheader"
                aria-colindex={1}
                id={cellId(row.rowIndex, 0)}
                className={`${styles.mol} ${isFocusRow && focus.c === 0 ? styles.cellFocus : ""}`}
                onClick={() => onSelect(row)}
                title={row.smilesInput}
              >
                <span className={styles.molIx}>{row.rowIndex + 1}</span>
                <span className={styles.molSmiles}>{row.smilesInput}</span>
                <span className={styles.molFlags}>
                  {row.flags.outOfDomain > 0 && (
                    <span className={styles.flagOod} title={`${row.flags.outOfDomain} out of domain`}>
                      ▲{row.flags.outOfDomain}
                    </span>
                  )}
                  {row.flags.notReturned > 0 && (
                    <span className={styles.flagMissing} title={`${row.flags.notReturned} not returned`}>
                      —{row.flags.notReturned}
                    </span>
                  )}
                </span>
              </div>

              {row.ok ? (
                ALL_ENDPOINTS.map((e, i) => {
                  const cell = row.cells[i];
                  const k = cell.state.kind;
                  const isMissing = k === "not_returned" || k === "not_requested";
                  const cls = [
                    styles.cell,
                    k === "out_of_domain" ? styles.cellOod : "",
                    k === "stub_served" ? styles.cellStub : "",
                    isMissing ? styles.cellMissing : "",
                    isFocusRow && focus.c === i + 1 ? styles.cellFocus : "",
                  ]
                    .filter(Boolean)
                    .join(" ");
                  return (
                    <div
                      key={e}
                      role="gridcell"
                      aria-colindex={i + 2}
                      id={cellId(row.rowIndex, i + 1)}
                      className={cls}
                      aria-label={cellLabel(row, e, cell)}
                    >
                      {isMissing ? "—" : fmtValue(cell.prediction!, cell.meta)}
                      {k === "out_of_domain" && (
                        <span className={styles.oodMark} aria-hidden="true">
                          ▲
                        </span>
                      )}
                    </div>
                  );
                })
              ) : (
                // A row the service could not process stays a row, carrying its
                // error. It is never dropped and never left blank (ADR-008).
                <div role="gridcell" aria-colindex={2} className={styles.failrow}>
                  <span className={styles.failEdge} aria-hidden="true" />
                  <span className={styles.failLabel}>Row failed</span>
                  <span className={styles.failMsg}>{row.error ?? "could not be standardized"}</span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
