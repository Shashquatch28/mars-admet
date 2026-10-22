// What the ⌘K palette offers. Pure and tested: every command is either really available or says
// why not, and nothing is listed that the app cannot do. The palette holds no sample molecules and
// no history: the only molecule it knows is the one Predict last returned (ADR-032).

export type PaletteCommandId = "run" | "copy_id" | "export" | "density";

export interface PaletteCommand {
  id: PaletteCommandId;
  label: string;
  /** Why the command cannot run right now; null when it can. Shown beside the command, not in a tooltip. */
  disabledReason: string | null;
}

export interface PaletteState {
  usingApi: boolean;
  smiles: string;
  endpointsSelected: number;
  running: boolean;
  hasResult: boolean;
}

export function paletteCommands(s: PaletteState): PaletteCommand[] {
  const runReason = !s.usingApi
    ? "no API configured"
    : s.running
      ? "run in progress"
      : s.smiles.trim().length === 0
        ? "enter a SMILES in Predict"
        : s.endpointsSelected === 0
          ? "no endpoints selected"
          : null;
  const noResult = s.hasResult ? null : "no result yet";
  return [
    { id: "run", label: "Run prediction", disabledReason: runReason },
    { id: "copy_id", label: "Copy molecule_id", disabledReason: noResult },
    { id: "export", label: "Export Predict result (CSV)", disabledReason: noResult },
    { id: "density", label: "Toggle density", disabledReason: null },
  ];
}

/** A SMILES shortened for one palette line; says nothing when it fits. */
export function clipLine(s: string, n = 44): string {
  return s.length > n ? `${s.slice(0, n)}…` : s;
}
