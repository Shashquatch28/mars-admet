// The Batch workspace's file, run state and result, held above the router so switching
// workspace (keys 1-4) neither loses the chosen file nor a running job. A run is a
// deliberate action, not a query: the service owns the job and the 24 h result retention,
// so the client keeps no cache that could outlive or contradict it.
//
// Flow (API_ROUTES.md /batch/*): POST the file; if the answer carries results (up to
// 100 molecules) it is done; otherwise follow the progress stream, then fetch results.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  ApiError,
  USING_API,
  fetchBatchResults,
  followBatchProgress,
  postBatch,
} from "../data/client";
import { settleProgress, validateUpload, type BatchPhase } from "../domain/batchJob";
import { ML_ENDPOINTS } from "../domain/endpoints";
import { endpointsForRequest, requestedMlEndpoints } from "../domain/reconcile";
import { expiredResultsMessage } from "../domain/limitsCopy";
import { useLimits } from "../data/useLimits";
import type { BatchPredictResponse, Endpoint, LimitsResponse } from "../types/contracts";

interface BatchSession {
  file: File | null;
  /** A reason the chosen file cannot be sent; null when it can (or none is chosen). */
  fileProblem: string | null;
  chooseFile: (f: File | null) => void;
  smilesColumn: string;
  setSmilesColumn: (s: string) => void;
  /** ML endpoints the next run will ask for (roster order). The rule-based score is not selectable. */
  selected: Endpoint[];
  setSelected: (e: Endpoint[]) => void;
  /** The ML endpoints the run that produced `result` asked for. NOT REQUESTED follows this, not the selector (ADR-028). */
  requested: Endpoint[];
  phase: BatchPhase;
  /** The last complete result; null before the first run and while a new run is in flight. */
  result: BatchPredictResponse | null;
  /** Increments with every completed result, so views can reset their sort and filter. */
  resultId: number;
  canRun: boolean;
  busy: boolean;
  run: () => void;
  clear: () => void;
}

const Ctx = createContext<BatchSession | null>(null);

function describeError(e: unknown, limits: LimitsResponse | undefined): string {
  if (e instanceof ApiError) {
    if (e.status === 0) return "The API is unreachable.";
    if (e.status === 401) return "Your session has ended. Sign in again to run a batch.";
    if (e.status === 410) return expiredResultsMessage(limits);
    return e.message;
  }
  return e instanceof Error ? e.message : "The batch failed.";
}

export function BatchSessionProvider({ children }: { children: ReactNode }) {
  const [file, setFile] = useState<File | null>(null);
  const [smilesColumn, setSmilesColumn] = useState("");
  const [selected, setSelectedRaw] = useState<Endpoint[]>(ML_ENDPOINTS);
  const [sent, setSent] = useState<Endpoint[] | null>(null);
  const [phase, setPhase] = useState<BatchPhase>({ kind: "idle" });
  const [result, setResult] = useState<BatchPredictResponse | null>(null);
  const [resultId, setResultId] = useState(0);
  const abort = useRef<AbortController | null>(null);
  const limits = useLimits();
  const limitsRef = useRef(limits);
  limitsRef.current = limits;
  const runToken = useRef(0);

  useEffect(() => () => abort.current?.abort(), []);

  const fileProblem = file ? validateUpload(file) : null;
  const busy = phase.kind === "uploading" || phase.kind === "running" || phase.kind === "fetching";
  const canRun = USING_API && !!file && !fileProblem && !busy;

  // Keep roster order whatever order the boxes were ticked in.
  const setSelected = useCallback((e: Endpoint[]) => setSelectedRaw(ML_ENDPOINTS.filter((m) => e.includes(m))), []);

  const chooseFile = useCallback((f: File | null) => {
    setFile(f);
    setPhase({ kind: "idle" });
  }, []);

  const run = useCallback(() => {
    if (!canRun || !file) return;
    const token = ++runToken.current;
    const live = () => token === runToken.current;
    const ctl = new AbortController();
    abort.current = ctl;
    const endpoints = endpointsForRequest(selected);
    setResult(null);
    setPhase({ kind: "uploading", fileName: file.name });

    (async () => {
      try {
        const first = await postBatch(file, { smilesColumn, endpoints });
        if (!live()) return;
        let done = first;
        if (!first.job_id) {
          // Interactive tier: the rows are in this response.
          if (first.status !== "done" || !first.results) throw new Error(`Unexpected response (${first.status}).`);
        } else {
          const jobId = first.job_id;
          setPhase({ kind: "running", jobId, progress: null });
          const last = await followBatchProgress(
            jobId,
            (progress) => live() && setPhase({ kind: "running", jobId, progress }),
            ctl.signal,
          );
          if (!live()) return;
          const settled = settleProgress(last);
          if (!settled.ok) {
            setPhase({ kind: "failed", message: settled.message });
            return;
          }
          setPhase({ kind: "fetching", jobId });
          done = await fetchBatchResults(jobId);
          if (!live()) return;
        }
        setResult(done);
        setSent(endpoints);
        setResultId((n) => n + 1);
        setPhase({ kind: "done" });
      } catch (e) {
        if (!live() || ctl.signal.aborted) return;
        setPhase({ kind: "failed", message: describeError(e, limitsRef.current) });
      }
    })();
  }, [canRun, file, smilesColumn, selected]);

  const clear = useCallback(() => {
    runToken.current++; // abandons any run in flight
    abort.current?.abort();
    setFile(null);
    setResult(null);
    setPhase({ kind: "idle" });
  }, []);

  const value = useMemo<BatchSession>(
    () => ({
      file,
      fileProblem,
      chooseFile,
      smilesColumn,
      setSmilesColumn,
      selected,
      setSelected,
      requested: requestedMlEndpoints(sent),
      phase,
      result,
      resultId,
      canRun,
      busy,
      run,
      clear,
    }),
    [file, fileProblem, chooseFile, smilesColumn, selected, setSelected, sent, phase, result, resultId, canRun, busy, run, clear],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useBatchSession(): BatchSession {
  const v = useContext(Ctx);
  if (!v) throw new Error("useBatchSession must be used within BatchSessionProvider");
  return v;
}
