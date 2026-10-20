// GET /molecule/{id}/explain for one endpoint, only after the user asks (ADR-031: an explanation
// is computed on request). The answers that are states rather than failures are not retried.
import { useQuery } from "@tanstack/react-query";
import type { Endpoint } from "../types/contracts";
import { ApiError, USING_API, fetchExplanation } from "./client";

const FINAL = new Set([404, 409, 422, 501, 503]);

export function useExplanation(moleculeId: string | null | undefined, endpoint: Endpoint, asked: boolean) {
  return useQuery({
    queryKey: ["explanation", moleculeId, endpoint],
    queryFn: () => fetchExplanation(moleculeId as string, endpoint),
    enabled: USING_API && !!moleculeId && asked,
    retry: (count, err) => !(err instanceof ApiError && FINAL.has(err.status)) && count < 1,
    staleTime: 5 * 60 * 1000,
  });
}
