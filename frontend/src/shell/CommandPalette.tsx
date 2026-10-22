// ⌘K palette — the signature keyboard moment (UX principle 7). Search over endpoints, the
// current molecule and commands; opens focused, arrows move, Enter commits, Esc closes.
// Everything here is real (ADR-031): the roster is the fixed endpoint list, the one molecule is
// whatever Predict last returned, and a command that cannot run says why instead of pretending.
// Reliability language travels with the endpoints: a stub endpoint shows its STUB tag here
// exactly as in the table.
import { useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import styles from "./shell.module.css";
import { useUiState } from "../app/uiState";
import { useAnnounce } from "../app/announce";
import { usePredictSession } from "../app/predictSession";
import { USING_API } from "../data/client";
import { copyText } from "../data/clipboard";
import { downloadText } from "../data/download";
import { ALL_ENDPOINTS } from "../domain/endpoints";
import { buildCsv, predictFileName } from "../domain/exportCsv";
import { clipLine, paletteCommands, type PaletteCommandId } from "../domain/palette";
import { reconcile, requestedMlEndpoints } from "../domain/reconcile";
import { ReliabilityTag } from "../components/dataviz/ReliabilityTag";
import type { Endpoint } from "../types/contracts";
import type { Reliability } from "../domain/rowState";

type Item =
  | { type: "endpoint"; id: Endpoint; reliability: Reliability }
  | { type: "molecule"; id: string; search: string; meta: string }
  | { type: "command"; id: PaletteCommandId; label: string; reason: string | null };

const endpointIcon = (
  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
    <path d="M2 5h12M2 8h12M2 11h8" />
  </svg>
);
const moleculeIcon = (
  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
    <circle cx="8" cy="4" r="1.8" />
    <circle cx="4" cy="11" r="1.8" />
    <circle cx="12" cy="11" r="1.8" />
    <path d="M8 5.5 5 9.5M8 5.5l3 4M5 11h6" />
  </svg>
);
const commandIcon = (
  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
    <path d="M4 5l3 3-3 3M8 11h5" />
  </svg>
);

export function CommandPalette() {
  const { setPaletteOpen, setSelectedEndpoint, setDensity, density } = useUiState();
  const { smiles, selected, result, running, run } = usePredictSession();
  const announce = useAnnounce();
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);

  // Reliability tags come from the last real result; with none, an endpoint carries no tag.
  const recon = useMemo(
    () => (result ? reconcile(result.response, requestedMlEndpoints(result.sent)) : null),
    [result],
  );
  const relByEndpoint = useMemo(() => {
    const m = new Map<Endpoint, Reliability>();
    for (const row of recon?.rows ?? []) m.set(row.endpoint, row.reliability);
    return m;
  }, [recon]);

  const endpoints: Item[] = ALL_ENDPOINTS.map((id) => ({
    type: "endpoint",
    id,
    reliability: relByEndpoint.get(id) ?? null,
  }));
  // The only molecule the app has is the one Predict last returned. No history is kept, so none is listed.
  const molecules: Item[] = result
    ? [
        {
          type: "molecule",
          id: clipLine(result.submitted),
          search: `${result.submitted} ${result.response.molecule_id}`,
          meta: `current · ${result.response.molecule_id}`,
        },
      ]
    : [];
  const commands: Item[] = paletteCommands({
    usingApi: USING_API,
    smiles,
    endpointsSelected: selected.length,
    running,
    hasResult: !!result,
  }).map((c) => ({ type: "command", id: c.id, label: c.label, reason: c.disabledReason }));

  const query = q.trim().toLowerCase();
  const match = (s: string) => !query || s.toLowerCase().includes(query);
  const eps = endpoints.filter((e) => e.type === "endpoint" && match(e.id));
  const mols = molecules.filter((m) => m.type === "molecule" && match(m.search));
  const cmds = commands.filter((c) => c.type === "command" && match(c.label));
  const items: Item[] = [...eps, ...mols, ...cmds];

  useEffect(() => {
    inputRef.current?.focus();
  }, []);
  useEffect(() => {
    setSel(0);
  }, [q]);

  function runCommand(id: PaletteCommandId) {
    if (id === "density") {
      setDensity(density === "compact" ? "comfortable" : "compact");
    } else if (id === "run") {
      navigate("/predict");
      run();
    } else if (id === "copy_id" && result) {
      const moleculeId = result.response.molecule_id;
      void copyText(moleculeId).then((ok) => announce(ok ? "Copied molecule_id" : "Could not copy molecule_id"));
    } else if (id === "export" && result && recon) {
      downloadText(
        predictFileName(result.response.molecule_id),
        buildCsv([{ smilesInput: result.submitted, response: result.response, cells: recon.rows }]),
      );
    }
  }

  function activate(it: Item | undefined) {
    if (!it) return;
    if (it.type === "command") {
      if (it.reason) return; // cannot run: the palette stays open and the reason stays visible
      runCommand(it.id);
    } else if (it.type === "endpoint") {
      setSelectedEndpoint(it.id);
      navigate("/predict");
    } else {
      navigate("/predict");
    }
    setPaletteOpen(false);
  }

  function onKeyDown(e: ReactKeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSel((s) => Math.min(items.length - 1, s + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSel((s) => Math.max(0, s - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      activate(items[sel]);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setPaletteOpen(false);
    }
  }

  let idx = -1;
  const renderItem = (it: Item, icon: ReactNode, name: string, meta: string, tag?: ReactNode) => {
    idx += 1;
    const i = idx;
    return (
      <div
        key={`${it.type}-${it.id}`}
        role="option"
        aria-selected={i === sel}
        aria-disabled={it.type === "command" && it.reason ? true : undefined}
        className={i === sel ? `${styles.palItem} ${styles.palSel}` : styles.palItem}
        onMouseMove={() => setSel(i)}
        onClick={() => activate(it)}
      >
        <span className={styles.palIcon}>{icon}</span>
        <span className={styles.palName}>{name}</span>
        {tag}
        <span className={styles.palMeta}>{meta}</span>
      </div>
    );
  };

  return (
    <>
      <div className={styles.scrim} role="presentation" aria-hidden="true" onClick={() => setPaletteOpen(false)} />
      <div className={styles.palette} role="dialog" aria-modal="true" aria-label="Command palette">
        <div className={styles.palInput}>
          <span className={styles.palPrompt}>&gt;</span>
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Search molecules, endpoints, commands"
            autoComplete="off"
            spellCheck={false}
          />
          <span className={styles.palCount}>{items.length ? `${items.length} results` : ""}</span>
        </div>
        <div className={styles.palList}>
          {items.length === 0 && <div className={styles.palEmpty}>No matches for &ldquo;{q}&rdquo;</div>}
          {eps.length > 0 && <div className={styles.palGroup}>Endpoints</div>}
          {eps.map((e) =>
            renderItem(
              e,
              endpointIcon,
              e.id,
              "",
              e.type === "endpoint" ? <ReliabilityTag reliability={e.reliability} /> : null,
            ),
          )}
          {mols.length > 0 && <div className={styles.palGroup}>Molecules</div>}
          {mols.map((m) => m.type === "molecule" && renderItem(m, moleculeIcon, m.id, m.meta))}
          {cmds.length > 0 && <div className={styles.palGroup}>Commands</div>}
          {cmds.map((c) => c.type === "command" && renderItem(c, commandIcon, c.label, c.reason ?? ""))}
        </div>
        <div className={styles.palFoot}>
          <span><b>↑↓</b> navigate</span>
          <span><b>⏎</b> open</span>
          <span><b>esc</b> close</span>
        </div>
      </div>
    </>
  );
}
