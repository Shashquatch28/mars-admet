// Liveness of the API as the badge reports it. `unconfigured` (no VITE_API_BASE)
// is its own state: the badge must not say "ready" for a service nobody asked.
import { useQuery } from "@tanstack/react-query";
import { USING_API, fetchHealth } from "./client";

export type ApiHealth = "unconfigured" | "checking" | "ready" | "unreachable";

export function useApiHealth(): ApiHealth {
  const q = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    enabled: USING_API,
    retry: false,
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
    staleTime: 0,
  });
  if (!USING_API) return "unconfigured";
  if (q.isError) return "unreachable";
  if (q.isSuccess) return "ready";
  return "checking";
}
