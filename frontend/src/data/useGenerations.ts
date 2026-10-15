// The deployed model generation, as the API reports it (ADR-026). Absent (undefined) until the
// first answer and whenever the API is unreachable: the top bar then shows a dash, never the
// last prediction's model_version, which can be "stub-v0" while a real model is deployed.
import { useQuery } from "@tanstack/react-query";
import { USING_API, fetchGenerations } from "./client";
import type { GenerationsResponse } from "../types/contracts";

export function useGenerations(): GenerationsResponse | undefined {
  const q = useQuery({
    queryKey: ["generations"],
    queryFn: fetchGenerations,
    enabled: USING_API,
    retry: false,
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: true,
  });
  return q.data;
}
