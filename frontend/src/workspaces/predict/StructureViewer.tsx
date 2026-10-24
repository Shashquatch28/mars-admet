// Conformer viewer. Live mode renders the API's MMFF94 conformer with 3Dmol.js
// (lazy-loaded; ~0.5 MB). With no API there is no structure to draw and the panel
// says so; it never draws stand-in geometry. A 404 is a normal
// state, not an error. Atom colours are the element palette tokens
// (--viewer-*), which carry no interface meaning. Nothing animates.
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import styles from "./predict.module.css";
import { useConformer } from "../../data/useConformer";
import { conformerView, describeConformer } from "../../domain/conformer";
import peekStyles from "./structurePeek.module.css";
import type { ConformerResponse } from "../../types/contracts";
import type { AtomHighlight } from "../../domain/explain";

type Mode = "hero" | "analysis";

const cssVar = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

// Hero: ball-and-stick, heavy atoms only. Analysis: every atom as sticks, hydrogens
// included, and no labels (atom numbering would be a claim nothing cites yet; labels
// can return with Q11, when something refers to them).
async function drawConformer(host: HTMLElement, c: ConformerResponse, mode: Mode, highlights: AtomHighlight[] | null) {
  const $3Dmol = await import("3dmol");
  const viewer = $3Dmol.createViewer(host, { backgroundAlpha: 0 });
  const carbon = cssVar("--viewer-atom");
  const hetero = cssVar("--viewer-hetero");
  viewer.addModel(c.sdf_block, "sdf");
  const stick = (radius: number, color: string) => ({ stick: { radius, color } });
  if (mode === "hero") {
    const ball = (radius: number, scale: number, color: string) => ({ stick: { radius, color }, sphere: { scale, color } });
    viewer.setStyle({}, ball(0.14, 0.22, carbon));
    viewer.setStyle({ not: { elem: "C" } }, ball(0.14, 0.26, hetero));
    viewer.setStyle({ elem: "H" }, {}); // heavy atoms only
  } else {
    viewer.setStyle({}, stick(0.1, carbon));
    viewer.setStyle({ not: { elem: ["C", "H"] as unknown as string } }, stick(0.1, hetero));
  }
  // Explanation (ADR-031). Heavy atoms come first in the SDF, in RDKit order, so an attribution index is
  // the viewer's atom index. Colour is the SIGN of the attribution (--attr-up / --attr-down, nothing
  // else), size and opacity are its strength; atoms with no direction keep the element palette.
  if (highlights) {
    const up = cssVar("--attr-up");
    const down = cssVar("--attr-down");
    for (const h of highlights) {
      if (h.sign === "none" || h.strength === 0) continue;
      const color = h.sign === "up" ? up : down;
      viewer.setStyle(
        { index: h.index },
        {
          stick: { radius: 0.1 + 0.06 * h.strength, color },
          sphere: { scale: 0.16 + 0.44 * h.strength, color, opacity: 0.35 + 0.65 * h.strength },
        },
      );
    }
  }
  fit(viewer);
  return viewer;
}

// Centre the molecule in the canvas with a margin, so the fit survives a resize and nothing touches the edge.
function fit(viewer: { zoomTo: () => void; zoom: (f: number) => void; render: () => void }) {
  viewer.zoomTo();
  viewer.zoom(0.85);
  viewer.render();
}

const NOTES = {
  idle: "A structure appears here once a molecule has been predicted.",
  loading: "Generating conformer…",
  unavailable: "No conformer for this molecule: its prediction cache entry has expired. Run it again to regenerate.",
  unsupported: "This API environment cannot generate conformers (RDKit is not installed there).",
} as const;

function Frame({ children, tools }: { children: React.ReactNode; tools?: React.ReactNode }) {
  return (
    <div className={styles.viewer}>
      <div className={styles.vhd}>
        <span className={styles.panelTitle}>Structure</span>
        {tools}
      </div>
      <div className={styles.vstage}>{children}</div>
    </div>
  );
}

function ModeSwitch({ mode, setMode }: { mode: Mode; setMode: (m: Mode) => void }) {
  return (
    <div className={styles.seg}>
      <button className={mode === "hero" ? styles.segOn : ""} aria-pressed={mode === "hero"} onClick={() => setMode("hero")}>
        Hero
      </button>
      <button className={mode === "analysis" ? styles.segOn : ""} aria-pressed={mode === "analysis"} onClick={() => setMode("analysis")}>
        Analysis
      </button>
    </div>
  );
}

// One 3Dmol canvas. The small pane and the peek each own one, drawn from the same cached conformer. 3Dmol sizes its
// canvas after the layout settles, so every resize re-fits the molecule: without that the first fit, made while the
// box was still being measured, leaves it off-centre and cropped.
function ConformerCanvas({
  data,
  mode,
  highlights,
  onClick,
}: {
  data: ConformerResponse;
  mode: Mode;
  highlights: AtomHighlight[] | null;
  /** A press-and-release that did not move: the stage was clicked, not dragged to rotate. */
  onClick?: () => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [drawError, setDrawError] = useState<string | null>(null);
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    // Each run draws into its own node: 3Dmol appends its canvas asynchronously
    // (after the dynamic import), so a run that was cleaned up mid-flight must be
    // able to discard exactly its own canvas — never a newer run's.
    const mount = document.createElement("div");
    mount.style.cssText = "position:relative;width:100%;height:100%";
    el.appendChild(mount);
    let viewer: Awaited<ReturnType<typeof drawConformer>> | null = null;
    let disposed = false;
    setDrawError(null);
    drawConformer(mount, data, mode, highlights).then(
      (v) => {
        if (disposed) v.clear();
        else viewer = v;
      },
      (e: unknown) => !disposed && setDrawError(e instanceof Error ? e.message : "3D rendering failed (WebGL unavailable?)"),
    );
    const ro = new ResizeObserver(() => {
      if (!viewer) return;
      viewer.resize();
      fit(viewer);
    });
    ro.observe(mount);
    return () => {
      disposed = true;
      ro.disconnect();
      viewer?.clear();
      mount.remove();
    };
  }, [data, mode, highlights]);

  const down = useRef<{ x: number; y: number } | null>(null);
  if (drawError) return <p className={styles.nostate}>Could not draw the structure: {drawError}</p>;
  return (
    <div
      ref={host}
      style={{ position: "relative", width: "100%", height: "100%" }}
      aria-label="3D structure"
      role="img"
      onPointerDown={onClick ? (e) => (down.current = { x: e.clientX, y: e.clientY }) : undefined}
      onPointerUp={
        onClick
          ? (e) => {
              const d = down.current;
              down.current = null;
              if (d && Math.hypot(e.clientX - d.x, e.clientY - d.y) < 4) onClick();
            }
          : undefined
      }
    />
  );
}

function LiveViewer({ moleculeId, highlights }: { moleculeId: string | null | undefined; highlights: AtomHighlight[] | null }) {
  const [mode, setMode] = useState<Mode>("hero");
  const [peek, setPeek] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const q = useConformer(moleculeId);
  const view = conformerView({ moleculeId, isPending: q.isPending, data: q.data, error: q.error });

  if (view.kind === "ready" && q.data) {
    const data = q.data;
    return (
      <>
        <Frame
          tools={
            <div className={styles.vtools}>
              <button
                ref={trigger}
                type="button"
                className={styles.expand}
                aria-haspopup="dialog"
                aria-expanded={peek}
                onClick={() => setPeek(true)}
              >
                Expand
              </button>
              <ModeSwitch mode={mode} setMode={setMode} />
            </div>
          }
        >
          <ConformerCanvas data={data} mode={mode} highlights={highlights} onClick={() => setPeek(true)} />
        </Frame>
        {peek && (
          <StructurePeek
            data={data}
            mode={mode}
            setMode={setMode}
            highlights={highlights}
            onClose={() => {
              setPeek(false);
              trigger.current?.focus();
            }}
          />
        )}
      </>
    );
  }
  const note = view.kind === "error" ? `Conformer request failed: ${view.message}` : view.kind === "ready" ? NOTES.loading : NOTES[view.kind];
  return (
    <Frame>
      <p className={styles.nostate}>{note}</p>
    </Frame>
  );
}

function NoApiViewer() {
  return (
    <Frame>
      <p className={styles.nostate}>No API is configured, so there is no structure to draw.</p>
    </Frame>
  );
}

export function StructureViewer({
  live,
  moleculeId,
  highlights = null,
}: {
  live: boolean;
  moleculeId?: string | null;
  highlights?: AtomHighlight[] | null; // memoize: a new array redraws the structure
}) {
  return live ? <LiveViewer moleculeId={moleculeId} highlights={highlights} /> : <NoApiViewer />;
}

// The peek: a larger centred pane over a scrim, opened from the small one. It holds the same conformer at size and says,
// in text, what is being drawn. It is not a modal form: Esc, the scrim and Close all dismiss it, focus goes to it on open
// and back to the Expand button on close, and keys 1-5 do not switch workspace while it is open (data-owns-keys).
const CLOSE_MS = 140;

function StructurePeek({
  data,
  mode,
  setMode,
  highlights,
  onClose,
}: {
  data: ConformerResponse;
  mode: Mode;
  setMode: (m: Mode) => void;
  highlights: AtomHighlight[] | null;
  onClose: () => void;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const [closing, setClosing] = useState(false);
  const info = describeConformer(data, mode, highlights !== null);

  const close = () => {
    if (closing) return;
    const reduce = typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) return onClose();
    setClosing(true);
    window.setTimeout(onClose, CLOSE_MS);
  };

  useEffect(() => {
    panel.current?.focus();
  }, []);

  function onKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Escape") {
      e.stopPropagation();
      close();
      return;
    }
    if (e.key !== "Tab" || !panel.current) return;
    // keep Tab inside the pane while it is open
    const items = [...panel.current.querySelectorAll<HTMLElement>("button, a[href]")].filter((n) => !n.hasAttribute("disabled"));
    if (items.length === 0) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (e.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  return createPortal(
    <div className={`${peekStyles.scrim} ${closing ? peekStyles.scrimOut : ""}`} onMouseDown={(e) => e.target === e.currentTarget && close()}>
      <div
        ref={panel}
        className={`${peekStyles.panel} ${closing ? peekStyles.panelOut : ""}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="structure-peek-title"
        tabIndex={-1}
        data-owns-keys=""
        onKeyDown={onKeyDown}
      >
        <div className={peekStyles.head}>
          <h2 id="structure-peek-title" className={peekStyles.title}>
            Structure
          </h2>
          <div className={peekStyles.headTools}>
            <ModeSwitch mode={mode} setMode={setMode} />
            <button type="button" className={peekStyles.close} onClick={close}>
              Close
            </button>
          </div>
        </div>
        <div className={peekStyles.body}>
          <div className={peekStyles.stage}>
            <ConformerCanvas data={data} mode={mode} highlights={highlights} />
          </div>
          <div className={peekStyles.info}>
            <h3 className={peekStyles.infoHd}>What is shown</h3>
            {info.map((p) => (
              <p key={p}>{p}</p>
            ))}
            <Link to="/molecule" className={peekStyles.more} onClick={close}>
              2D drawing, computed properties and structural alerts
            </Link>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
