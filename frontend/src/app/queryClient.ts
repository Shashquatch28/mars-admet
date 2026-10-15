import { QueryClient } from "@tanstack/react-query";

// The API already has a 48h server cache and a cache_hit flag; the client cache
// must not contradict it (ARCHITECTURE). Conservative defaults: one retry, no
// refetch on focus — a prediction does not change under the user's feet.
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 5 * 60 * 1000,
    },
  },
});
