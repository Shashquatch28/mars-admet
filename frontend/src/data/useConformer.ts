// GET /molecule/{id}/3d for the molecule the last prediction was about. 404 and
// 501 are answers, not failures to retry (COMPONENTS: a 404 is a normal state).
import { useQuery } from "@tanstack/react-query";
import { ApiError, USING_API, fetchConformer } from "./client";

const FINAL = new Set([404, 422, 501]);

export function useConformer(moleculeId: string | null | undefined) {
  return useQuery({
    queryKey: ["conformer", moleculeId],
    queryFn: () => fetchConformer(moleculeId as string),
    enabled: USING_API && !!moleculeId,
    retry: (count, err) => !(err instanceof ApiError && FINAL.has(err.status)) && count < 1,
    staleTime: 5 * 60 * 1000,
  });
}
