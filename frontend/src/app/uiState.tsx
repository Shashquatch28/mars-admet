// App-level UI state shared across the shell and the Predict workspace: which
// endpoint is selected (drives the inspector, and what the ⌘K palette jumps to),
// whether the palette is open, and the density choice.
import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import type { Endpoint } from "../types/contracts";

export type Density = "compact" | "comfortable";

interface UiState {
  selectedEndpoint: Endpoint | null;
  setSelectedEndpoint: (e: Endpoint | null) => void;
  paletteOpen: boolean;
  setPaletteOpen: (open: boolean) => void;
  density: Density;
  setDensity: (d: Density) => void;
  shortcutsEnabled: boolean;
  setShortcutsEnabled: (on: boolean) => void;
}

const Ctx = createContext<UiState | null>(null);

// WCAG 2.1.4: the 1-4 workspace keys are single-character shortcuts, so they can be turned off. On by default;
// the choice is remembered in this browser. Storage can be blocked, so every access is guarded.
const SHORTCUTS_KEY = "mars.singleKeyShortcuts";
function readShortcuts(): boolean {
  try {
    return window.localStorage.getItem(SHORTCUTS_KEY) !== "off";
  } catch {
    return true;
  }
}

export function UiStateProvider({ children }: { children: ReactNode }) {
  const [selectedEndpoint, setSelectedEndpoint] = useState<Endpoint | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [density, setDensity] = useState<Density>("compact");
  const [shortcutsEnabled, setShortcuts] = useState<boolean>(readShortcuts);
  const setShortcutsEnabled = (on: boolean) => {
    setShortcuts(on);
    try {
      window.localStorage.setItem(SHORTCUTS_KEY, on ? "on" : "off");
    } catch {
      // not remembered, still applied for this session
    }
  };

  const value = useMemo(
    () => ({
      selectedEndpoint,
      setSelectedEndpoint,
      paletteOpen,
      setPaletteOpen,
      density,
      setDensity,
      shortcutsEnabled,
      setShortcutsEnabled,
    }),
    [selectedEndpoint, paletteOpen, density, shortcutsEnabled],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useUiState(): UiState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useUiState must be used within UiStateProvider");
  return v;
}
