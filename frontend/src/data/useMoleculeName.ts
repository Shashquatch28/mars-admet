// The name of one molecule, looked up from its structure (ADR-043). A name is a pure function of the structure, so it is asked
// for once per SMILES and kept for the session; the service caches it too. Nothing is asked without a SMILES or without an API.
//
// Two rules keep the lookup polite. A structure must stay on screen for SETTLE_MS before it is asked about, so scrolling past a
// row, or a SMILES that is still being typed, asks nobody; an answer already held is shown at once. And a failure is not kept
// for the session as if it were an answer: an `unavailable` answer is stale after UNAVAILABLE_STALE_MS, so the next time the
// molecule is shown MARS asks again, while "found" and "no name found" are kept.
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, USING_API, fetchName } from "./client";
import { nameView, shouldAsk, type NameView } from "../domain/moleculeName";

export const SETTLE_MS = 400;
export const UNAVAILABLE_STALE_MS = 30_000;

export const nameKey = (smiles: string) => ["name", smiles] as const;

export function useMoleculeName(smiles: string | null | undefined): NameView {
  const s = smiles?.trim() ?? "";
  const qc = useQueryClient();
  const known = s.length > 0 && qc.getQueryData(nameKey(s)) !== undefined;
  const [settled, setSettled] = useState("");
  useEffect(() => {
    if (!s || known) return;
    const t = window.setTimeout(() => setSettled(s), SETTLE_MS);
    return () => window.clearTimeout(t);
  }, [s, known]);

  const hasStructure = USING_API && s.length > 0;
  const q = useQuery({
    queryKey: nameKey(s),
    queryFn: () => fetchName(s),
    enabled: shouldAsk({ hasStructure, settled: settled === s, known }),
    retry: false,
    staleTime: (query) => (query.state.data?.status === "unavailable" ? UNAVAILABLE_STALE_MS : Infinity),
  });
  return nameView({
    hasStructure,
    pending: q.isPending,
    data: q.data,
    error: q.error ? { status: q.error instanceof ApiError ? q.error.status : 0, message: q.error.message } : null,
  });
}
