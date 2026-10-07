// The Predict workspace's input and its last result, held above the router so
// switching workspace (keys 1–4) neither loses the molecule nor the response the
// shell's status bar and top bar read from. A run is a deliberate user action
// (a mutation, not a query): the server owns the 48 h cache and says so through
// `cache_hit`, so the client does not keep a second cache that could contradict it.
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { useMutation } from "@tanstack/react-query";
import { CELECOXIB_SMILES } from "../domain/fixtures";
import { ML_ENDPOINTS } from "../domain/endpoints";
import { endpointsForRequest } from "../domain/reconcile";
import type { Endpoint } from "../types/contracts";
import { USING_API, fetchPrediction, type TimedPrediction } from "../data/client";

interface PredictSession {
  smiles: string;
  setSmiles: (s: string) => void;
  /** ML endpoints the next run will ask for (roster order). Rule-based SA is not selectable. */
  selected: Endpoint[];
  setSelected: (e: Endpoint[]) => void;
  /** Last successful response; null before the first run, while a new run is in flight, and after an error. */
  result: TimedPrediction | null;
  running: boolean;
  error: Error | null;
  canRun: boolean;
  run: () => void;
  clear: () => void;
}

const Ctx = createContext<PredictSession | null>(null);

export function PredictSessionProvider({ children }: { children: ReactNode }) {
  // Without an API the workspace shows the illustrative fixture, whose molecule is celecoxib.
  const [smiles, setSmiles] = useState(USING_API ? "" : CELECOXIB_SMILES);
  const [selected, setSelectedRaw] = useState<Endpoint[]>(ML_ENDPOINTS);
  const mutation = useMutation({
    mutationFn: ({ s, endpoints }: { s: string; endpoints: Endpoint[] | null }) => fetchPrediction(s, endpoints),
  });

  // Keep roster order whatever order the boxes were ticked in.
  const setSelected = useCallback(
    (e: Endpoint[]) => setSelectedRaw(ML_ENDPOINTS.filter((m) => e.includes(m))),
    [],
  );

  const canRun = USING_API && smiles.trim().length > 0 && selected.length > 0 && !mutation.isPending;
  const { mutate, reset } = mutation;

  const run = useCallback(() => {
    if (!canRun) return;
    mutate({ s: smiles.trim(), endpoints: endpointsForRequest(selected) });
  }, [canRun, mutate, smiles, selected]);

  const clear = useCallback(() => {
    reset();
    setSmiles("");
  }, [reset]);

  const value = useMemo<PredictSession>(
    () => ({
      smiles,
      setSmiles,
      selected,
      setSelected,
      result: mutation.data ?? null,
      running: mutation.isPending,
      error: mutation.error,
      canRun,
      run,
      clear,
    }),
    [smiles, selected, setSelected, mutation.data, mutation.isPending, mutation.error, canRun, run, clear],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function usePredictSession(): PredictSession {
  const v = useContext(Ctx);
  if (!v) throw new Error("usePredictSession must be used within PredictSessionProvider");
  return v;
}
