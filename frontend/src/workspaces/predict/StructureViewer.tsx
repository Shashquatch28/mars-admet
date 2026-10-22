// Conformer viewer. Live mode renders the API's MMFF94 conformer with 3Dmol.js
// (lazy-loaded; ~0.5 MB). With no API there is no structure to draw and the panel
// says so; it never draws stand-in geometry. A 404 is a normal
// state, not an error. Atom colours are the element palette tokens
// (--viewer-*), which carry no interface meaning. Nothing animates.
import { useEffect, useRef, useState } from "react";
import styles from "./predict.module.css";
import { useConformer } from "../../data/useConformer";
import { conformerView } from "../../domain/conformer";
import type { ConformerResponse } from "../../types/contracts";

type Mode = "hero" | "analysis";

const cssVar = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

// Hero: ball-and-stick, heavy atoms only. Analysis: every atom as sticks, hydrogens
// included, and no labels (atom numbering would be a claim nothing cites yet; labels
// can return with Q11, when something refers to them).
async function drawConformer(host: HTMLElement, c: ConformerResponse, mode: Mode) {
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
  viewer.zoomTo();
  viewer.render();
  return viewer;
}

const NOTES = {
  idle: "A structure appears here once a molecule has been predicted.",
  loading: "Generating conformer…",
  unavailable: "No conformer for this molecule: its prediction cache entry has expired. Run it again to regenerate.",
  unsupported: "This API environment cannot generate conformers (RDKit is not installed there).",
} as const;

function Frame({ mode, setMode, children, caption }: { mode?: Mode; setMode?: (m: Mode) => void; children: React.ReactNode; caption?: string }) {
  return (
    <div className={styles.viewer}>
      <div className={styles.vhd}>
        <span className={styles.panelTitle}>Structure</span>
        {mode && setMode && (
          <div className={styles.seg}>
            <button className={mode === "hero" ? styles.segOn : ""} aria-pressed={mode === "hero"} onClick={() => setMode("hero")}>
              Hero
            </button>
            <button className={mode === "analysis" ? styles.segOn : ""} aria-pressed={mode === "analysis"} onClick={() => setMode("analysis")}>
              Analysis
            </button>
          </div>
        )}
      </div>
      <div className={styles.vstage}>{children}</div>
      {caption && <div className={styles.vcap}>{caption}</div>}
    </div>
  );
}

function LiveViewer({ moleculeId }: { moleculeId: string | null | undefined }) {
  const [mode, setMode] = useState<Mode>("hero");
  const q = useConformer(moleculeId);
  const view = conformerView({ moleculeId, isPending: q.isPending, data: q.data, error: q.error });
  const host = useRef<HTMLDivElement>(null);
  const [drawError, setDrawError] = useState<string | null>(null);

  const data = view.kind === "ready" ? q.data : undefined;
  useEffect(() => {
    const el = host.current;
    if (!el || !data) return;
    // Each run draws into its own node: 3Dmol appends its canvas asynchronously
    // (after the dynamic import), so a run that was cleaned up mid-flight must be
    // able to discard exactly its own canvas — never a newer run's.
    const mount = document.createElement("div");
    mount.style.cssText = "position:relative;width:100%;height:100%";
    el.appendChild(mount);
    let viewer: Awaited<ReturnType<typeof drawConformer>> | null = null;
    let disposed = false;
    setDrawError(null);
    drawConformer(mount, data, mode).then(
      (v) => {
        if (disposed) v.clear();
        else viewer = v;
      },
      (e: unknown) => !disposed && setDrawError(e instanceof Error ? e.message : "3D rendering failed (WebGL unavailable?)"),
    );
    const ro = new ResizeObserver(() => viewer?.resize());
    ro.observe(mount);
    return () => {
      disposed = true;
      ro.disconnect();
      viewer?.clear();
      mount.remove();
    };
  }, [data, mode]);

  if (view.kind === "ready") {
    return (
      <Frame mode={mode} setMode={setMode} caption={drawError ? undefined : view.caption}>
        {drawError ? (
          <p className={styles.nostate}>Could not draw the structure: {drawError}</p>
        ) : (
          <div ref={host} style={{ position: "relative", width: "100%", height: "100%" }} aria-label="3D structure" role="img" />
        )}
      </Frame>
    );
  }
  const note = view.kind === "error" ? `Conformer request failed: ${view.message}` : NOTES[view.kind];
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

export function StructureViewer({ live, moleculeId }: { live: boolean; moleculeId?: string | null }) {
  return live ? <LiveViewer moleculeId={moleculeId} /> : <NoApiViewer />;
}
