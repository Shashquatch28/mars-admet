// Draw-to-predict (ADR-035, building on ADR-027). A trigger under the SMILES field opens a non-modal panel that
// holds Ketcher. The SMILES field stays the source of truth and the contract is untouched: the drawing writes
// SMILES into the field, SMILES typed into the field is drawn on the canvas, and the user still presses Run.
//
// Honesty rules the panel keeps: an empty canvas, or one that cannot become a single SMILES, never overwrites what
// the user typed, and the panel says so in text. Ketcher is loaded on first open (dynamic import), so the main
// bundle does not pay for it, and if WebAssembly or the chunk is unavailable the panel says that and the field
// still works.
//
// Focus: opening moves focus to the panel (named "Structure editor"); Ketcher then takes it into its own canvas as
// soon as it has loaded. Closing, by the trigger, the Close button or Esc, returns focus to the trigger. Esc inside
// the Ketcher canvas belongs to Ketcher (cancel the tool, close its dialog), so there the way out is Tab to the Close
// button, which follows the canvas in Tab order, or the trigger. The panel is not a modal: the SMILES field and Run
// stay usable beside it.
import {
  Component,
  Suspense,
  lazy,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import type { Ketcher } from "ketcher-core";
import { useAnnounce } from "../../app/announce";
import { usePredictSession } from "../../app/predictSession";
import {
  conversionReason,
  interpretDrawn,
  obviousSmilesFault,
  shouldLoadTyped,
  statusIsProblem,
  statusText,
  webAssemblyAvailable,
  type EditorStatus,
} from "../../domain/structureEditor";
import styles from "./structureEditor.module.css";

// The Ketcher chunk: fetched the first time the panel opens, never in the main bundle.
const KetcherCanvas = lazy(() => import("./KetcherCanvas"));

/** Quiet period after the last edit before the other side is updated, so a drag does not convert every frame. */
const SETTLE_MS = 300;

class LoadBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <p className={styles.problem} role="alert">
        The structure editor could not be loaded ({this.state.error.message}). The SMILES field above still works.
      </p>
    );
  }
}

export function StructureEditor() {
  const { smiles, setSmiles } = usePredictSession();
  const announce = useAnnounce();
  const [open, setOpen] = useState(false);
  const [ready, setReady] = useState(false);
  const [status, setStatus] = useState<EditorStatus>({ kind: "idle" });

  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const host = useRef<HTMLDivElement>(null);
  const ketcher = useRef<Ketcher | null>(null);
  // The SMILES the field and the canvas last agreed on: what the editor wrote to the field, or what was loaded from it.
  const synced = useRef<string | null>(null);
  // The editor's own rendering of the last typed SMILES it loaded. A change event that only echoes it is not an edit.
  const echo = useRef<string | null>(null);
  const writeTimer = useRef<number>(0);
  const writeSeq = useRef(0);
  const wasOpen = useRef(false);

  const panelId = useId();
  const titleId = useId();
  const wasm = webAssemblyAvailable();

  const show = useCallback(
    (next: EditorStatus) => {
      setStatus(next);
      // The panel's text is not a live region (one announcer, a11yGuard); problems are said through it.
      if (statusIsProblem(next)) announce(statusText(next));
    },
    [announce],
  );

  // Canvas -> SMILES field.
  const writeFromCanvas = useCallback(async () => {
    const k = ketcher.current;
    if (!k) return;
    const seq = ++writeSeq.current;
    let raw: string;
    try {
      raw = await k.getSmiles();
    } catch (e) {
      if (seq === writeSeq.current) show({ kind: "unusable", reason: conversionReason(e) });
      return;
    }
    if (seq !== writeSeq.current || !ketcher.current) return; // a newer edit, or the panel closed
    const drawn = interpretDrawn(raw);
    if (drawn.kind === "empty") return show({ kind: "empty" });
    if (drawn.kind === "unusable") return show(drawn);
    if (drawn.smiles === echo.current) return show({ kind: "drawn" }); // just the typed text, redrawn
    echo.current = null;
    synced.current = drawn.smiles;
    setSmiles(drawn.smiles);
    show({ kind: "written" });
  }, [setSmiles, show]);

  const onCanvasChange = useCallback(() => {
    window.clearTimeout(writeTimer.current);
    writeTimer.current = window.setTimeout(() => void writeFromCanvas(), SETTLE_MS);
  }, [writeFromCanvas]);

  // SMILES field -> canvas.
  const loadTyped = useCallback(
    async (typed: string) => {
      const k = ketcher.current;
      if (!k) return;
      const fault = obviousSmilesFault(typed);
      if (fault) return show({ kind: "undrawable", reason: fault });
      try {
        await k.setMolecule(typed.trim());
      } catch (e) {
        show({ kind: "undrawable", reason: conversionReason(e) });
        return;
      }
      if (ketcher.current !== k) return;
      synced.current = typed;
      try {
        echo.current = (await k.getSmiles()).trim() || null;
      } catch {
        echo.current = null;
      }
      show({ kind: "drawn" });
    },
    [show],
  );

  const onReady = useCallback(
    (k: Ketcher) => {
      ketcher.current = k;
      k.editor.subscribe("change", onCanvasChange);
      setReady(true);
    },
    [onCanvasChange],
  );

  // Typed text arrives while the panel is open (or the panel has just opened on a non-empty field).
  useEffect(() => {
    if (!open || !ready || !shouldLoadTyped(smiles, synced.current)) return;
    const t = window.setTimeout(() => void loadTyped(smiles), SETTLE_MS);
    return () => window.clearTimeout(t);
  }, [open, ready, smiles, loadTyped]);

  // Closing: drop the editor and put focus back on the trigger. Opening: focus the panel so its name is read.
  useEffect(() => {
    if (open) {
      panel.current?.focus();
    } else if (wasOpen.current) {
      ketcher.current = null;
      window.clearTimeout(writeTimer.current);
      writeSeq.current++;
      synced.current = null;
      echo.current = null;
      setReady(false);
      setStatus({ kind: "idle" });
      trigger.current?.focus();
    }
    wasOpen.current = open;
  }, [open]);

  useEffect(() => () => window.clearTimeout(writeTimer.current), []);

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key !== "Escape" || e.defaultPrevented) return;
    if (host.current?.contains(e.target as Node)) return; // Esc inside the canvas is Ketcher's
    e.stopPropagation();
    setOpen(false);
  }

  const mount = typeof document === "undefined" ? null : document.getElementById("main");
  const body = !wasm ? (
    <p className={styles.problem} role="alert">
      This browser has no WebAssembly, which the structure editor needs. The SMILES field above still works.
    </p>
  ) : (
    <LoadBoundary>
      <Suspense fallback={<p className={styles.note}>Loading the structure editor…</p>}>
        <KetcherCanvas
          onReady={onReady}
          onError={(message) => show({ kind: "reported", message })}
        />
      </Suspense>
    </LoadBoundary>
  );

  const panelEl = open && (
    <div
      ref={panel}
      id={panelId}
      className={styles.panel}
      role="dialog"
      aria-modal="false"
      aria-labelledby={titleId}
      tabIndex={-1}
      data-owns-keys=""
      onKeyDown={onKeyDown}
    >
      <div className={styles.head}>
        <h2 id={titleId} className={styles.title}>
          Structure editor
        </h2>
      </div>
      <p className={statusIsProblem(status) ? styles.problem : styles.note}>{statusText(status)}</p>
      <div ref={host} className={styles.canvas}>
        {body}
      </div>
      {/* After the canvas in reading and Tab order: Ketcher takes focus once it loads, and Tab from its last control lands here. */}
      <div className={styles.foot}>
        <button type="button" className={styles.close} onClick={() => setOpen(false)}>
          Close
        </button>
      </div>
    </div>
  );

  return (
    <>
      <button
        ref={trigger}
        type="button"
        className={styles.trigger}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        aria-haspopup="dialog"
        onClick={() => setOpen((o) => !o)}
      >
        {open ? "Close structure editor" : "Draw a structure"}
      </button>
      {panelEl && (mount ? createPortal(panelEl, mount) : panelEl)}
    </>
  );
}
