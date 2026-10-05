// /predict as a query. Disabled when no API base is configured, so the default
// experience is the fixture with zero network. When configured, the hook drives
// the real Predict result (the roster is still reconciled client-side; the
// response only supplies values — ADR-008).
import { useQuery } from "@tanstack/react-query";
import { API_BASE, fetchPrediction } from "./client";
import type { Endpoint } from "../types/contracts";

export function usePrediction(smiles: string, endpoints?: Endpoint[] | null) {
  return useQuery({
    queryKey: ["predict", smiles, endpoints ?? "all"],
    queryFn: () => fetchPrediction(smiles, endpoints),
    enabled: !!API_BASE && smiles.trim().length > 0,
  });
}

export const USING_API = !!API_BASE;
