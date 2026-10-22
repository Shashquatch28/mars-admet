// The deployed policy numbers (ADR-034 item 8). Undefined until the first answer and whenever the
// API is unreachable: copy built from it (domain/limitsCopy.ts) then leaves the numbers out.
import { useQuery } from "@tanstack/react-query";
import { USING_API, fetchLimits } from "./client";
import type { LimitsResponse } from "../types/contracts";

export function useLimits(): LimitsResponse | undefined {
  const q = useQuery({
    queryKey: ["limits"],
    queryFn: fetchLimits,
    enabled: USING_API,
    retry: false,
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: true,
  });
  return q.data;
}
