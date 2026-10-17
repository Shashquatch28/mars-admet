// Library: the molecules and reports this account saved. Each entry is a FROZEN snapshot of
// a response the user already received; the screen says which model_version made it and
// when, and never presents it as a current prediction (the service does not recompute it).
//
// Honesty rules that shape this screen:
//   - values keep the value-cell grammar: mono, tabular, --text-primary, never recoloured;
//     reliability (out of domain, stub, not returned) is a separate mark beside the value
//   - the full roster renders for a saved molecule, so an endpoint the snapshot lacks is a
//     marked row, never a gap (ADR-008)
//   - no ranking, no score across entries; the list is newest first and filterable by text
//   - an empty list says why it is empty, including that Save is not wired yet
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import styles from "./library.module.css";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { useUiState } from "../../app/uiState";
import {
  ApiError,
  USING_API,
  deleteSavedMolecule,
  deleteSavedReport,
  fetchSavedMolecules,
  fetchSavedReports,
} from "../../data/client";
import { ML_ENDPOINTS } from "../../domain/endpoints";
import { fmtValue } from "../../domain/format";
import {
  deleteItemError,
  filterLibrary,
  newestFirst,
  provenanceLine,
  shortDate,
  toMoleculeItem,
  toReportItem,
  type LibraryItem,
  type MoleculeItem,
  type ReportItem,
} from "../../domain/library";
import { reconcile } from "../../domain/reconcile";

type Tab = "molecules" | "reports";
const KEYS = { molecules: ["library", "molecules"], reports: ["library", "reports"] } as const;

export function LibraryWorkspace() {
  const { setIsSample } = useUiState();
  useEffect(() => setIsSample(false), [setIsSample]); // saved snapshots are real, not illustrative

  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("molecules");
  const [text, setText] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [confirmReport, setConfirmReport] = useState<ReportItem | null>(null);
  const [confirmMol, setConfirmMol] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const mols = useQuery({ queryKey: KEYS.molecules, queryFn: fetchSavedMolecules, enabled: USING_API, retry: false });
  const reps = useQuery({ queryKey: KEYS.reports, queryFn: fetchSavedReports, enabled: USING_API, retry: false });

  const molItems = useMemo(() => newestFirst((mols.data ?? []).map(toMoleculeItem)), [mols.data]);
  const repItems = useMemo(() => newestFirst((reps.data ?? []).map(toReportItem)), [reps.data]);
  const items: LibraryItem[] = tab === "molecules" ? molItems : repItems;
  const visible = useMemo(() => filterLibrary(items, text), [items, text]);
  const active = tab === "molecules" ? mols : reps;

  const selectedItem = useMemo(() => items.find((i) => i.id === selected) ?? null, [items, selected]);

  const remove = useMutation({
    mutationFn: async (item: LibraryItem) => {
      try {
        if (item.kind === "molecule") await deleteSavedMolecule(item.id);
        else await deleteSavedReport(item.id);
      } catch (e) {
        // 404 = not this account's or already gone: the list should simply refresh.
        const msg = deleteItemError(e instanceof ApiError ? e.status : 0, e instanceof Error ? e.message : "");
        if (msg) throw new Error(msg);
      }
    },
    onSuccess: (_d, item) => {
      setProblem(null);
      setSelected((s) => (s === item.id ? null : s));
      void qc.invalidateQueries({ queryKey: item.kind === "molecule" ? KEYS.molecules : KEYS.reports });
    },
    onError: (e) => setProblem(e.message),
    onSettled: () => {
      setConfirmReport(null);
      setConfirmMol(null);
    },
  });

  if (!USING_API) {
    return (
      <section className={styles.lib} aria-label="Library">
        <p className={styles.empty}>
          No API is configured, so there is no Library. It holds the molecules and reports an account saves.
        </p>
      </section>
    );
  }

  const switchTab = (t: Tab) => {
    setTab(t);
    setSelected(null);
    setConfirmMol(null);
    setProblem(null);
  };

  return (
    <>
      <section className={styles.lib} aria-label="Library">
        <div className={styles.hd}>
          <span className={styles.title}>Library</span>
          <div className={styles.seg} role="group" aria-label="What to list">
            <button type="button" aria-pressed={tab === "molecules"} className={tab === "molecules" ? styles.segOn : ""} onClick={() => switchTab("molecules")}>
              Molecules <span className={styles.ct}>{mols.data ? molItems.length : "…"}</span>
            </button>
            <button type="button" aria-pressed={tab === "reports"} className={tab === "reports" ? styles.segOn : ""} onClick={() => switchTab("reports")}>
              Reports <span className={styles.ct}>{reps.data ? repItems.length : "…"}</span>
            </button>
          </div>
          <span style={{ flex: 1 }} />
          {text && items.length > 0 && (
            <span className={styles.note}>
              showing <b>{visible.length}</b> of <b>{items.length}</b>
            </span>
          )}
        </div>

        <div className={styles.filter}>
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Filter by label, SMILES, notes or tag"
            aria-label="Filter the library"
          />
        </div>

        {problem && (
          <p className={styles.error} role="alert">
            {problem}
          </p>
        )}

        <div className={styles.list}>
          {active.isPending ? (
            <p className={styles.empty}>Loading…</p>
          ) : active.isError ? (
            <p className={styles.error} role="alert">
              {active.error instanceof ApiError && active.error.status === 0
                ? "The API is unreachable."
                : `Could not load the library. ${active.error.message}`}
            </p>
          ) : items.length === 0 ? (
            <p className={styles.empty}>
              Nothing is saved. The Save controls in Predict and Batch are not wired yet, so this list stays empty
              until they are.
            </p>
          ) : visible.length === 0 ? (
            <p className={styles.empty}>No entry matches the filter. The filter hides entries; it changes none.</p>
          ) : (
            <ul className={styles.items}>
              {visible.map((it) => (
                <li key={it.id}>
                  <button
                    type="button"
                    className={`${styles.item} ${it.id === selected ? styles.itemOn : ""}`}
                    aria-pressed={it.id === selected}
                    onClick={() => setSelected(it.id)}
                  >
                    <span className={styles.itemTitle}>{it.title}</span>
                    {it.kind === "molecule" && it.title !== it.smiles && <span className={styles.itemSub}>{it.smiles}</span>}
                    <span className={styles.itemMeta}>
                      saved {shortDate(it.savedAt)}
                      {it.kind === "molecule" ? ` · ${it.modelVersion || "unknown model"}` : ` · ${it.summary.rows} rows`}
                      {it.tags.length > 0 && ` · ${it.tags.join(", ")}`}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <aside className={styles.insp} aria-label="Saved entry detail">
        <div className={styles.insphd}>
          <span className={styles.panelTitle}>{tab === "molecules" ? "Saved molecule" : "Saved report"}</span>
        </div>
        {!selectedItem ? (
          <p className={styles.empty}>Select an entry to see what was saved, which model made it and when.</p>
        ) : selectedItem.kind === "molecule" ? (
          <MoleculeDetail
            item={selectedItem}
            confirming={confirmMol === selectedItem.id}
            busy={remove.isPending}
            onAskDelete={() => setConfirmMol(selectedItem.id)}
            onCancelDelete={() => setConfirmMol(null)}
            onDelete={() => remove.mutate(selectedItem)}
          />
        ) : (
          <ReportDetail item={selectedItem} onAskDelete={() => setConfirmReport(selectedItem)} />
        )}
      </aside>

      {confirmReport && (
        <ConfirmDialog
          title="Delete this saved report?"
          confirmLabel="Delete report"
          busy={remove.isPending}
          onConfirm={() => remove.mutate(confirmReport)}
          onCancel={() => setConfirmReport(null)}
        >
          <p style={{ margin: 0 }}>
            {confirmReport.title} will be removed from your library. Molecules you saved separately are kept.
            This cannot be undone.
          </p>
        </ConfirmDialog>
      )}
    </>
  );
}

function MoleculeDetail({
  item,
  confirming,
  busy,
  onAskDelete,
  onCancelDelete,
  onDelete,
}: {
  item: MoleculeItem;
  confirming: boolean;
  busy: boolean;
  onAskDelete: () => void;
  onCancelDelete: () => void;
  onDelete: () => void;
}) {
  const rows = useMemo(() => reconcile(item.response, ML_ENDPOINTS).rows, [item.response]);
  return (
    <div className={styles.detail}>
      <div className={styles.sec}>
        <p className={styles.smiles}>{item.smiles}</p>
        <p className={styles.prov}>{provenanceLine(item)}</p>
        {item.notes && <p className={styles.notes}>{item.notes}</p>}
        {item.tags.length > 0 && <p className={styles.itemMeta}>tags: {item.tags.join(", ")}</p>}
      </div>
      <div className={styles.minihd}>
        <span style={{ flex: 1 }}>Endpoint</span>
        <span>Value as saved</span>
      </div>
      <div className={styles.minilist}>
        {rows.map((cell) => {
          const k = cell.state.kind;
          const missing = k === "not_returned" || k === "not_requested";
          const edge = k === "out_of_domain" ? styles.edgeOod : k === "stub_served" ? styles.edgeStub : missing ? styles.edgeMissing : "";
          return (
            <div key={cell.endpoint} className={`${styles.minirow} ${edge}`}>
              <span className={styles.miniName}>{cell.endpoint}</span>
              {k === "out_of_domain" && <span className={styles.tag}>out of domain</span>}
              {k === "stub_served" && <span className={styles.tag}>stub</span>}
              {missing ? (
                <span className={styles.miniMissing}>{k === "not_requested" ? "not requested" : "not returned"}</span>
              ) : (
                <span className={styles.miniVal}>{fmtValue(cell.prediction!, cell.meta)}</span>
              )}
            </div>
          );
        })}
      </div>
      <div className={styles.foot}>
        {confirming ? (
          <>
            <span className={styles.confirmText}>Delete this saved molecule?</span>
            <button type="button" className={styles.danger} onClick={onDelete} disabled={busy}>
              {busy ? "Deleting…" : "Delete"}
            </button>
            <button type="button" onClick={onCancelDelete} disabled={busy}>
              Cancel
            </button>
          </>
        ) : (
          <button type="button" onClick={onAskDelete}>
            Delete…
          </button>
        )}
      </div>
    </div>
  );
}

function ReportDetail({ item, onAskDelete }: { item: ReportItem; onAskDelete: () => void }) {
  const s = item.summary;
  return (
    <div className={styles.detail}>
      <div className={styles.sec}>
        <p className={styles.smiles}>{item.title}</p>
        <p className={styles.prov}>
          Saved {shortDate(item.savedAt)}. A frozen copy of the results as they were, not a new run.
        </p>
        <dl className={styles.dl}>
          <dt>Kind</dt>
          <dd>{s.shape === "unrecognised" ? "unrecognised snapshot" : s.shape}</dd>
          <dt>Molecules</dt>
          <dd>{s.rows}</dd>
          {s.shape === "batch" && (
            <>
              <dt>Failed rows</dt>
              <dd>{s.failedRows}</dd>
            </>
          )}
          <dt>Model</dt>
          <dd>{s.modelVersions.length ? s.modelVersions.join(", ") : "none recorded"}</dd>
          <dt>Linked saves</dt>
          <dd>{item.moleculeCount}</dd>
        </dl>
        {item.notes && <p className={styles.notes}>{item.notes}</p>}
        {item.tags.length > 0 && <p className={styles.itemMeta}>tags: {item.tags.join(", ")}</p>}
      </div>
      <div className={styles.foot}>
        <button type="button" onClick={onAskDelete}>
          Delete…
        </button>
      </div>
    </div>
  );
}
