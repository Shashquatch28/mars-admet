// The Predict workspace's input and its last result, held above the router so
// switching workspace (keys 1–4) neither loses the molecule nor the response the
// shell's status bar and top bar read from. A run is a deliberate user action
// (a mutation, not a query): the server owns the 48 h cache and says so through
// `cache_hit`, so the client does not keep a second cache that could contradict it.
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { useMutation } from "@tanstack/react-query";
import { CELECOXIB_SMILES } from "../domain/fixtures";
import { USING_API, fetchPrediction, type TimedPrediction } from "../data/client";

interface PredictSession {
  smiles: string;
  setSmiles: (s: string) => void;
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
  const mutation = useMutation({ mutationFn: (s: string) => fetchPrediction(s) });

  const canRun = USING_API && smiles.trim().length > 0 && !mutation.isPending;
  const { mutate, reset } = mutation;

  const run = useCallback(() => {
    if (canRun) mutate(smiles.trim());
  }, [canRun, mutate, smiles]);

  const clear = useCallback(() => {
    reset();
    setSmiles("");
  }, [reset]);

  const value = useMemo<PredictSession>(
    () => ({
      smiles,
      setSmiles,
      result: mutation.data ?? null,
      running: mutation.isPending,
      error: mutation.error,
      canRun,
      run,
      clear,
    }),
    [smiles, mutation.data, mutation.isPending, mutation.error, canRun, run, clear],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function usePredictSession(): PredictSession {
  const v = useContext(Ctx);
  if (!v) throw new Error("usePredictSession must be used within PredictSessionProvider");
  return v;
}
