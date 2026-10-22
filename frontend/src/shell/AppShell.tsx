// The 1440×900 frame: prototype strip, top bar, rail, workspace slot, status bar.
// Owns the global keyboard shortcuts. Workspaces fill the slot with their own
// columns (COMPONENTS.md). Below the supported width it shows the designed
// minimum-width notice rather than a broken layout (RESPONSIVE_STRATEGY).
import { useEffect } from "react";
import { Outlet, useNavigate } from "react-router-dom";
import styles from "./shell.module.css";
import { TopBar } from "./TopBar";
import { NavRail } from "./NavRail";
import { StatusBar } from "./StatusBar";
import { CommandPalette } from "./CommandPalette";
import { useUiState } from "../app/uiState";

const WS_KEYS: Record<string, string> = { "1": "/predict", "2": "/batch", "3": "/compare", "4": "/library" };

export function AppShell() {
  const { paletteOpen, setPaletteOpen, isSample } = useUiState();
  const navigate = useNavigate();

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen(!paletteOpen);
        return;
      }
      if (paletteOpen) return;
      const el = document.activeElement;
      const typing = el instanceof HTMLElement && /^(INPUT|TEXTAREA)$/.test(el.tagName);
      if (!typing && WS_KEYS[e.key]) navigate(WS_KEYS[e.key]);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [paletteOpen, setPaletteOpen, navigate]);

  return (
    <>
    <div className={styles.minwidth}>
      <p>
        MARS is a desktop workstation. Open it at <b>1280&nbsp;px</b> or wider.
        <span>minimum width not met</span>
      </p>
    </div>
    <div className={styles.app}>
      {isSample && (
        <div className={styles.protostrip}>
          <span className={styles.protoswatch} aria-hidden="true" />
          <span className={styles.protolabel}>Design prototype</span>
          <span className={styles.protonote}>Every value below is illustrative, not model output.</span>
        </div>
      )}
      <TopBar />
      <div className={styles.main}>
        <NavRail />
        <Outlet />
      </div>
      <StatusBar />
      {paletteOpen && <CommandPalette />}
    </div>
    </>
  );
}
