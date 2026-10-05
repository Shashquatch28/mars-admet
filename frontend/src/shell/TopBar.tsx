import { useLocation } from "react-router-dom";
import styles from "./shell.module.css";
import { useUiState } from "../app/uiState";

const WORKSPACE_SUB: Record<string, string> = {
  "/predict": "Single molecule",
  "/batch": "Many molecules",
  "/compare": "Side by side",
  "/library": "Saved",
  "/settings": "",
};

export function TopBar() {
  const { setPaletteOpen } = useUiState();
  const { pathname } = useLocation();
  const base = "/" + (pathname.split("/")[1] || "predict");
  const label = (base.slice(1) || "predict").toUpperCase();
  const sub = WORKSPACE_SUB[base] ?? "";

  return (
    <header className={styles.topbar}>
      <div className={styles.brand}>
        <span className={styles.logo} aria-hidden="true">
          <svg width="22" height="22" viewBox="0 0 22 22" fill="none" stroke="currentColor" strokeWidth="1.5">
            <circle cx="11" cy="4.5" r="2.2" />
            <circle cx="4.5" cy="15" r="2.2" />
            <circle cx="17.5" cy="15" r="2.2" />
            <path d="M11 6.7 6 13M11 6.7 16 13M6.7 15h8.6" />
          </svg>
        </span>
        <span className={styles.brandName}>MARS</span>
        <span className={styles.brandSub}>ADMET Rapid Screening</span>
      </div>
      <div className={styles.crumb}>
        <span className={styles.crumbW}>{label}</span>
        {sub && <span className={styles.crumbSep}>/</span>}
        {sub && <span className={styles.crumbSub}>{sub}</span>}
      </div>
      <div className={styles.spacer} />
      <button className={styles.kbar} aria-label="Open command palette" onClick={() => setPaletteOpen(true)}>
        <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
          <circle cx="7" cy="7" r="4.5" />
          <path d="M11 11l3 3" />
        </svg>
        <span className={styles.kbarPh}>Search molecules, endpoints, commands</span>
        <kbd className={styles.kbd}>⌘K</kbd>
      </button>
      <div className={styles.serving} role="button" tabIndex={0}>
        <span className={styles.servingLbl}>Serving</span>
        <span className={styles.servingVal}>mars-routing@v0.3.1</span>
        <span className={styles.chev} aria-hidden="true">▾</span>
      </div>
      <div className={styles.apistat}>
        <span className={styles.dot} />
        <span className={styles.apistatLbl}>API Ready</span>
      </div>
      <div className={styles.acct}>SK</div>
    </header>
  );
}
