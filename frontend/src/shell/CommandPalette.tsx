// ⌘K palette — the signature keyboard moment (UX principle 7). Fuzzy search over
// endpoints, molecules and commands; opens focused, arrows move, Enter commits,
// Esc closes. Reliability language travels with the results: a stub endpoint
// shows its STUB tag here exactly as in the table.
import { useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import styles from "./shell.module.css";
import { useUiState } from "../app/uiState";
import { ALL_ENDPOINTS } from "../domain/endpoints";
import { reconcile } from "../domain/reconcile";
import { FIXTURE_RESPONSE } from "../domain/fixtures";
import { ReliabilityTag } from "../components/dataviz/ReliabilityTag";
import type { Endpoint } from "../types/contracts";
import type { Reliability } from "../domain/rowState";

type Item =
  | { type: "endpoint"; id: Endpoint; meta: string; reliability: Reliability }
  | { type: "molecule"; id: string; meta: string }
  | { type: "command"; id: string; meta: string };

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
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);

  const relByEndpoint = useMemo(() => {
    const m = new Map<Endpoint, Reliability>();
    for (const row of reconcile(FIXTURE_RESPONSE).rows) m.set(row.endpoint, row.reliability);
    return m;
  }, []);

  const endpoints: Item[] = ALL_ENDPOINTS.map((id) => ({
    type: "endpoint",
    id,
    meta: "",
    reliability: relByEndpoint.get(id) ?? null,
  }));
  const molecules: Item[] = [
    { type: "molecule", id: "a3f2c81d9b4e6027", meta: "current · celecoxib" },
    { type: "molecule", id: "CN1C=NC2=C1C(=O)N(C)…", meta: "recent · 11m" },
  ];
  const commands: Item[] = [
    { type: "command", id: "Run prediction", meta: "⌘⏎" },
    { type: "command", id: "Copy molecule_id", meta: "" },
    { type: "command", id: "Export results", meta: "" },
    { type: "command", id: "Toggle density", meta: "" },
  ];

  const query = q.trim().toLowerCase();
  const match = (s: string) => !query || s.toLowerCase().includes(query);
  const eps = endpoints.filter((e) => match(e.id));
  const mols = molecules.filter((m) => match(m.id) || match(m.meta));
  const cmds = commands.filter((c) => match(c.id));
  const items: Item[] = [...eps, ...mols, ...cmds];

  useEffect(() => {
    inputRef.current?.focus();
  }, []);
  useEffect(() => {
    setSel(0);
  }, [q]);

  function activate(it: Item | undefined) {
    if (!it) return;
    if (it.type === "endpoint") {
      setSelectedEndpoint(it.id);
      navigate("/predict");
      setPaletteOpen(false);
    } else if (it.type === "command") {
      if (it.id === "Toggle density") setDensity(density === "compact" ? "comfortable" : "compact");
      setPaletteOpen(false);
    } else {
      setPaletteOpen(false);
    }
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
        key={`${it.type}-${name}`}
        role="option"
        aria-selected={i === sel}
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
      <div className={styles.scrim} onClick={() => setPaletteOpen(false)} />
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
          {mols.map((m) => renderItem(m, moleculeIcon, m.id, m.meta))}
          {cmds.length > 0 && <div className={styles.palGroup}>Commands</div>}
          {cmds.map((c) => renderItem(c, commandIcon, c.id, c.meta))}
        </div>
        <div className={styles.palFoot}>
          <span><b>↑↓</b> navigate</span>
          <span><b>⏎</b> open</span>
          <span><b>esc</b> close</span>
          <span className={styles.palFootR}>transform-origin: the ⌘K field</span>
        </div>
      </div>
    </>
  );
}
