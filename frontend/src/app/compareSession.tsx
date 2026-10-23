// The Compare workspace's inputs and last result, held above the router so switching
// workspace (keys 1-4) keeps them, and so Predict can hand its molecule over ("Compare
// molecule") without re-entry (INTERACTIONS.md). A run is a deliberate action, not a query:
// the service owns the 48 h cache, so the client keeps no second one.
//
// /compare is anonymous (API_ROUTES.md), unlike Batch and Library, so nothing here is gated.
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { useMutation } from "@tanstack/react-query";
import { USING_API, fetchComparison } from "../data/client";
import { COMPARE_MAX, COMPARE_MIN, addToSlots, compareProblem, filledInputs, handoffNote } from "../domain/compare";
import { ML_ENDPOINTS } from "../domain/endpoints";
import { endpointsForRequest } from "../domain/reconcile";
import type { CompareResponse, Endpoint } from "../types/contracts";

interface CompareSession {
  slots: string[]; // COMPARE_MIN or COMPARE_MAX entries
  setSlot: (i: number, value: string) => void;
  addThird: () => void;
  removeThird: () => void;
  /** Put a molecule into the first slot (the Predict hand-off) and discard any stale result. */
  seedFirst: (smiles: string) => void;
  /** Put a molecule from another workspace into the first free slot (Library, Batch), discard any stale result and say what happened in `note`. */
  addMolecule: (smiles: string, source: string) => void;
  /** What the last hand-off did, in words; cleared by the next edit, run or clear. */
  note: string | null;
  /** ML endpoints the next run will ask for (roster order). The rule-based score is not selectable. */
  selected: Endpoint[];
  setSelected: (e: Endpoint[]) => void;
  /** The `endpoints` field of the run that produced `result`: null = no subset. NOT REQUESTED follows this, not the selector (ADR-028). */
  sent: Endpoint[] | null;
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
  const [selected, setSelectedRaw] = useState<Endpoint[]>(ML_ENDPOINTS);
  const [note, setNote] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: ({ smiles, endpoints }: { smiles: string[]; endpoints: Endpoint[] | null }) => fetchComparison(smiles, endpoints),
  });
  const { mutate, reset } = mutation;

  // Keep roster order whatever order the boxes were ticked in.
  const setSelected = useCallback((e: Endpoint[]) => setSelectedRaw(ML_ENDPOINTS.filter((m) => e.includes(m))), []);
  const setSlot = useCallback((i: number, value: string) => {
    setNote(null);
    setSlots((s) => s.map((x, j) => (j === i ? value : x)));
  }, []);
  const addThird = useCallback(() => setSlots((s) => (s.length < COMPARE_MAX ? [...s, ""] : s)), []);
  const removeThird = useCallback(() => setSlots((s) => (s.length > COMPARE_MIN ? s.slice(0, COMPARE_MIN) : s)), []);
  const seedFirst = useCallback(
    (smiles: string) => {
      reset();
      setNote(null);
      setSlots((s) => s.map((x, j) => (j === 0 ? smiles : x)));
    },
    [reset],
  );
  // The slots are read from the current state, not a closure, so two hand-offs in a row fill two slots.
  const slotsRef = useRef(slots);
  slotsRef.current = slots;
  const addMolecule = useCallback(
    (smiles: string, source: string) => {
      const a = addToSlots(slotsRef.current, smiles);
      slotsRef.current = a.slots;
      reset(); // a result for other molecules would no longer match the slots
      setSlots(a.slots);
      setNote(handoffNote(a, source));
    },
    [reset],
  );

  const problem = USING_API ? compareProblem(slots) : "No API is configured, so there is nothing to run.";
  const canRun = problem === null && !mutation.isPending;

  const run = useCallback(() => {
    if (!canRun) return;
    setNote(null);
    mutate({ smiles: filledInputs(slots), endpoints: endpointsForRequest(selected) });
  }, [canRun, mutate, slots, selected]);

  const clear = useCallback(() => {
    reset();
    setNote(null);
    setSlots(Array.from({ length: COMPARE_MIN }, () => ""));
  }, [reset]);

  const value = useMemo<CompareSession>(
    () => ({
      slots,
      setSlot,
      addThird,
      removeThird,
      seedFirst,
      addMolecule,
      note,
      selected,
      setSelected,
      sent: mutation.variables?.endpoints ?? null,
      result: mutation.data ?? null,
      running: mutation.isPending,
      error: mutation.error,
      problem,
      canRun,
      run,
      clear,
    }),
    [slots, setSlot, addThird, removeThird, seedFirst, addMolecule, note, selected, setSelected, mutation.variables, mutation.data, mutation.isPending, mutation.error, problem, canRun, run, clear],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useCompareSession(): CompareSession {
  const v = useContext(Ctx);
  if (!v) throw new Error("useCompareSession must be used within CompareSessionProvider");
  return v;
}
