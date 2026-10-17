// The Compare workspace's inputs and last result, held above the router so switching
// workspace (keys 1-4) keeps them, and so Predict can hand its molecule over ("Compare
// molecule") without re-entry (INTERACTIONS.md). A run is a deliberate action, not a query:
// the service owns the 48 h cache, so the client keeps no second one.
//
// /compare is anonymous (API_ROUTES.md), unlike Batch and Library, so nothing here is gated.
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { useMutation } from "@tanstack/react-query";
import { USING_API, fetchComparison } from "../data/client";
import { COMPARE_MAX, COMPARE_MIN, compareProblem, filledInputs } from "../domain/compare";
import type { CompareResponse } from "../types/contracts";

interface CompareSession {
  slots: string[]; // COMPARE_MIN or COMPARE_MAX entries
  setSlot: (i: number, value: string) => void;
  addThird: () => void;
  removeThird: () => void;
  /** Put a molecule into the first slot (the Predict hand-off) and discard any stale result. */
  seedFirst: (smiles: string) => void;
  /** Last successful response; null before a run, while one is in flight, and after an error. */
  result: CompareResponse | null;
  running: boolean;
  error: Error | null;
  /** Why Run is unavailable, in words; null when it can run. */
  problem: string | null;
  canRun: boolean;
  run: () => void;
  clear: () => void;
}

const Ctx = createContext<CompareSession | null>(null);

export function CompareSessionProvider({ children }: { children: ReactNode }) {
  const [slots, setSlots] = useState<string[]>(() => Array.from({ length: COMPARE_MIN }, () => ""));
  const mutation = useMutation({ mutationFn: (smiles: string[]) => fetchComparison(smiles) });
  const { mutate, reset } = mutation;

  const setSlot = useCallback((i: number, value: string) => setSlots((s) => s.map((x, j) => (j === i ? value : x))), []);
  const addThird = useCallback(() => setSlots((s) => (s.length < COMPARE_MAX ? [...s, ""] : s)), []);
  const removeThird = useCallback(() => setSlots((s) => (s.length > COMPARE_MIN ? s.slice(0, COMPARE_MIN) : s)), []);
  const seedFirst = useCallback(
    (smiles: string) => {
      reset();
      setSlots((s) => s.map((x, j) => (j === 0 ? smiles : x)));
    },
    [reset],
  );

  const problem = USING_API ? compareProblem(slots) : "No API is configured, so there is nothing to run.";
  const canRun = problem === null && !mutation.isPending;

  const run = useCallback(() => {
    if (!canRun) return;
    mutate(filledInputs(slots));
  }, [canRun, mutate, slots]);

  const clear = useCallback(() => {
    reset();
    setSlots(Array.from({ length: COMPARE_MIN }, () => ""));
  }, [reset]);

  const value = useMemo<CompareSession>(
    () => ({
      slots,
      setSlot,
      addThird,
      removeThird,
      seedFirst,
      result: mutation.data ?? null,
      running: mutation.isPending,
      error: mutation.error,
      problem,
      canRun,
      run,
      clear,
    }),
    [slots, setSlot, addThird, removeThird, seedFirst, mutation.data, mutation.isPending, mutation.error, problem, canRun, run, clear],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useCompareSession(): CompareSession {
  const v = useContext(Ctx);
  if (!v) throw new Error("useCompareSession must be used within CompareSessionProvider");
  return v;
}
