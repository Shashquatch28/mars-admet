// The explanation of one molecule + endpoint (ADR-031, ADR-040). Reading is free of side effects, so the server
// is asked as soon as a row with a model is selected: that is what resumes a job after a reload, or shows a
// cached result with no click. Only `start` computes anything. A queued or running job is read again every few
// seconds. The answers that are states rather than failures (404, 409, 422, 429, 501, 503) are not retried.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { EXPLAIN_POLL_MS, shouldPoll, type ExplainAnswer } from "../domain/explain";
import type { Endpoint } from "../types/contracts";
import { ApiError, USING_API, cancelExplanation, readExplanation, startExplanation } from "./client";

const FINAL = new Set([404, 409, 422, 429, 501, 503]);

export function useExplanation(moleculeId: string | null | undefined, endpoint: Endpoint, enabled: boolean) {
  const qc = useQueryClient();
  const key = ["explanation", moleculeId, endpoint] as const;
  const keyText = `${moleculeId}:${endpoint}`;
  const remember = (answer: ExplainAnswer) => qc.setQueryData<ExplainAnswer>(key, answer);

  const read = useQuery({
    queryKey: key,
    queryFn: () => readExplanation(moleculeId as string, endpoint),
    enabled: USING_API && !!moleculeId && enabled,
    retry: (count, err) => !(err instanceof ApiError && FINAL.has(err.status)) && count < 1,
    // A finished result never changes; "nothing started" or a running job might, so ask again on return.
    staleTime: (q) => (q.state.data?.kind === "result" ? Infinity : 0),
    refetchInterval: (q) => (q.state.status !== "error" && shouldPoll(q.state.data) ? EXPLAIN_POLL_MS : false),
  });

  const start = useMutation({
    mutationFn: (_key: string) => startExplanation(moleculeId as string, endpoint),
    onSuccess: remember,
  });
  const cancel = useMutation({
    mutationFn: (_key: string) => cancelExplanation(moleculeId as string, endpoint),
    onSuccess: (answer) => answer.kind !== "none" && remember(answer),
  });
  // Mutation state belongs to the row it was sent for, not to whichever row is selected now.
  const mine = <T,>(m: { variables: string | undefined }, v: T): T | undefined => (m.variables === keyText ? v : undefined);

  const answer = read.data;
  const startError = mine(start, start.error);
  const cancelError = mine(cancel, cancel.error);
  return {
    answer,
    error: (startError ?? cancelError ?? read.error) as { status?: number; message: string } | null,
    pending: (mine(start, start.isPending) ? "start" : read.isPending && read.fetchStatus !== "idle" ? "check" : null) as
      | "start"
      | "check"
      | null,
    // Cancel was sent; the job stops between chunks, so it can report running for a moment longer.
    stopping: !!mine(cancel, cancel.isPending || (cancel.isSuccess && shouldPoll(answer))),
    start: () => {
      start.reset();
      start.mutate(keyText);
    },
    cancel: () => {
      cancel.reset();
      cancel.mutate(keyText);
    },
  };
}
