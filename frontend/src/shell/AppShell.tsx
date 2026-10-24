// The 1440×900 frame: top bar, rail, workspace slot, status bar.
// Owns the global keyboard shortcuts. Workspaces fill the slot with their own
// columns (COMPONENTS.md). Below the supported width it shows the designed
// minimum-width notice rather than a broken layout (RESPONSIVE_STRATEGY).
import { useEffect } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import styles from "./shell.module.css";
import { TopBar } from "./TopBar";
import { NavRail } from "./NavRail";
import { StatusBar } from "./StatusBar";
import { CommandPalette } from "./CommandPalette";
import { useUiState } from "../app/uiState";

const WS_KEYS: Record<string, string> = { "1": "/predict", "2": "/batch", "3": "/compare", "4": "/library", "5": "/molecule" };

// WCAG 2.4.2: the page title names the workspace. (The printed report sets its own while it prints.)
const WS_TITLE: Record<string, string> = {
  "/predict": "Predict",
  "/batch": "Batch",
  "/compare": "Compare",
  "/library": "Library",
  "/molecule": "Molecule",
  "/settings": "Settings",
  "/forgot-password": "Forgot password",
  "/reset-password": "Reset password",
};

export function AppShell() {
  const { paletteOpen, setPaletteOpen, shortcutsEnabled } = useUiState();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const workspace = "/" + (pathname.split("/")[1] || "predict");

  useEffect(() => {
    document.title = `${WS_TITLE[workspace] ?? "MARS"} · MARS ADMET Rapid Screening`;
  }, [workspace]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen(!paletteOpen);
        return;
      }
      if (paletteOpen) return;
      const el = document.activeElement;
      // Typing in a field, or drawing in the structure editor, which has its own key bindings (ADR-035).
      const typing =
        el instanceof HTMLElement && (/^(INPUT|TEXTAREA)$/.test(el.tagName) || el.closest("[data-owns-keys]") !== null);
      if (shortcutsEnabled && !typing && WS_KEYS[e.key]) navigate(WS_KEYS[e.key]);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [paletteOpen, setPaletteOpen, navigate, shortcutsEnabled]);

  return (
    <>
    <div className={styles.app}>
      <a className={styles.skip} href="#main">
        Skip to workspace
      </a>
      <p className={styles.narrow} role="note">
        MARS is laid out for a window 1080&nbsp;px wide or more. At this width, or at high zoom, scroll sideways to
        reach everything; nothing is hidden.
      </p>
      <TopBar />
      <div className={styles.main}>
        <NavRail />
        <main id="main" tabIndex={-1} className={styles.workspace}>
          <Outlet />
        </main>
      </div>
      <StatusBar />
      {paletteOpen && <CommandPalette />}
    </div>
    </>
  );
}
