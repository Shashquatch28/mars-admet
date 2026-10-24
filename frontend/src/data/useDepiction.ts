// The 2D drawing of one molecule (ADR-039). A drawing is a pure function of the structure, so it is fetched once per SMILES
// and kept for the session; the service caches it too. Nothing is requested without a SMILES or without an API.
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { USING_API, fetchDepiction } from "./client";

export const depictionKey = (smiles: string) => ["depiction", smiles] as const;

export function useDepiction(smiles: string | null | undefined): UseQueryResult<string, Error> {
  const s = smiles?.trim() ?? "";
  return useQuery({
    queryKey: depictionKey(s),
    queryFn: () => fetchDepiction(s),
    enabled: USING_API && s.length > 0,
    retry: false,
    staleTime: Infinity,
  });
}
