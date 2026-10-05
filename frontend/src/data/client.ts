// Typed API client. Talks to the real FastAPI service (API_ROUTES.md). When
// VITE_API_BASE is unset the app never calls this — it runs on the fixture.
import type { Endpoint, PredictionResponse } from "../types/contracts";

export const API_BASE = import.meta.env.VITE_API_BASE;

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function fetchPrediction(
  smiles: string,
  endpoints?: Endpoint[] | null,
): Promise<PredictionResponse> {
  if (!API_BASE) throw new ApiError(0, "No API base configured");
  const res = await fetch(`${API_BASE}/predict`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include", // session cookie is HttpOnly (Module 13)
    body: JSON.stringify({ smiles, endpoints: endpoints ?? null }),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as PredictionResponse;
}
