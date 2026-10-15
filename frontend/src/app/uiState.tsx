// App-level UI state shared across the shell and the Predict workspace: which
// endpoint is selected (drives the inspector, and what the ⌘K palette jumps to),
// whether the palette is open, the density choice, and whether the values on
// screen are the illustrative fixture (which gates the "design prototype" strip).
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
  isSample: boolean;
  setIsSample: (s: boolean) => void;
}

const Ctx = createContext<UiState | null>(null);

export function UiStateProvider({ children }: { children: ReactNode }) {
  const [selectedEndpoint, setSelectedEndpoint] = useState<Endpoint | null>("caco2_permeability");
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [density, setDensity] = useState<Density>("compact");
  const [isSample, setIsSample] = useState(true);

  const value = useMemo(
    () => ({
      selectedEndpoint,
      setSelectedEndpoint,
      paletteOpen,
      setPaletteOpen,
      density,
      setDensity,
      isSample,
      setIsSample,
    }),
    [selectedEndpoint, paletteOpen, density, isSample],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useUiState(): UiState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useUiState must be used within UiStateProvider");
  return v;
}
