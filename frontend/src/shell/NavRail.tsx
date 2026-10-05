import { NavLink } from "react-router-dom";
import styles from "./shell.module.css";
import type { ReactNode } from "react";

interface Dest {
  to: string;
  label: string;
  icon: ReactNode;
}

const molecule = (
  <svg width="19" height="19" viewBox="0 0 22 22">
    <circle cx="11" cy="4.5" r="2.2" />
    <circle cx="4.5" cy="15" r="2.2" />
    <circle cx="17.5" cy="15" r="2.2" />
    <path d="M11 6.7 6 13M11 6.7 16 13M6.7 15h8.6" />
  </svg>
);
const grid = (
  <svg width="19" height="19" viewBox="0 0 22 22">
    <rect x="3.5" y="3.5" width="15" height="15" rx="1" />
    <path d="M3.5 8.5h15M3.5 13.5h15M8.5 3.5v15" />
  </svg>
);
const panels = (
  <svg width="19" height="19" viewBox="0 0 22 22">
    <rect x="3.5" y="3.5" width="6.5" height="15" rx="1" />
    <rect x="12" y="3.5" width="6.5" height="15" rx="1" />
  </svg>
);
const archive = (
  <svg width="19" height="19" viewBox="0 0 22 22">
    <path d="M3.5 6.5 11 3l7.5 3.5-7.5 3.5z" />
    <path d="M3.5 6.5v9L11 19l7.5-3.5v-9M11 10v9" />
  </svg>
);
const gear = (
  <svg width="19" height="19" viewBox="0 0 22 22">
    <circle cx="11" cy="11" r="3" />
    <path d="M11 2v3M11 17v3M2 11h3M17 11h3M4.6 4.6l2.1 2.1M15.3 15.3l2.1 2.1M17.4 4.6l-2.1 2.1M6.7 15.3l-2.1 2.1" />
  </svg>
);

const DESTS: Dest[] = [
  { to: "/predict", label: "Predict", icon: molecule },
  { to: "/batch", label: "Batch", icon: grid },
  { to: "/compare", label: "Compare", icon: panels },
  { to: "/library", label: "Library", icon: archive },
];

function item({ icon, label }: Dest) {
  return (
    <>
      {icon}
      <span className={styles.navLabel}>{label}</span>
    </>
  );
}

export function NavRail() {
  const cls = ({ isActive }: { isActive: boolean }) =>
    isActive ? `${styles.navitem} ${styles.navActive}` : styles.navitem;
  return (
    <nav className={styles.rail} aria-label="Workspaces">
      {DESTS.map((d) => (
        <NavLink key={d.to} to={d.to} className={cls}>
          {item(d)}
        </NavLink>
      ))}
      <span className={styles.grow} />
      <NavLink to="/settings" className={cls}>
        {gear}
        <span className={styles.navLabel}>Settings</span>
      </NavLink>
    </nav>
  );
}
