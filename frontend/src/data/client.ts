// Typed API client. Talks to the real FastAPI service (API_ROUTES.md). When
// VITE_API_BASE is unset the app never calls this — it runs on the fixture.
//
// In dev VITE_API_BASE is "/api": Vite proxies it to the API (vite.config.ts), so
// the browser only ever makes same-origin requests and CORS never applies.
// Requests send `credentials: "include"` for the HttpOnly session cookie. That
// also works cross-origin because the API answers with an explicit origin list
// and allow_credentials (CORS_ALLOW_ORIGINS) — never `*`, which browsers reject
// together with credentials. Cookies are SameSite=Lax, so the SPA and API must
// be same-site (e.g. app.x.com and api.x.com).
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

// FastAPI sends `detail` as a string for HTTPException and as a list of
// {loc, msg, …} objects for request-validation failures.
function describeDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : ""))
      .filter(Boolean);
    if (msgs.length) return msgs.join("; ");
  }
  return fallback;
}

async function request(path: string, init?: RequestInit): Promise<Response> {
  if (!API_BASE) throw new ApiError(0, "No API base configured");
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { credentials: "include", ...init });
  } catch {
    // fetch rejects (TypeError) when the server is unreachable or the request is blocked
    throw new ApiError(0, "API unreachable");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = describeDetail(((await res.json()) as { detail?: unknown })?.detail, detail);
    } catch {
      /* non-JSON error body (e.g. a proxy 502) */
    }
    throw new ApiError(res.status, detail || `HTTP ${res.status}`);
  }
  return res;
}

export interface TimedPrediction {
  response: PredictionResponse;
  latencyMs: number; // measured round trip as the browser saw it
  // What was sent. The service's `smiles_input` is not the raw input: it comes
  // back already standardized, so it cannot tell us whether the string was rewritten.
  submitted: string;
}

export async function fetchPrediction(
  smiles: string,
  endpoints?: Endpoint[] | null,
): Promise<TimedPrediction> {
  const t0 = performance.now();
  const res = await request("/predict", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ smiles, endpoints: endpoints ?? null }),
  });
  const response = (await res.json()) as PredictionResponse;
  return { response, latencyMs: Math.round(performance.now() - t0), submitted: smiles };
}

// Liveness only (`/health`). Readiness (`/health/ready`) reports Postgres/Redis
// connectivity, which the badge does not claim.
// Resolves `true` on a 2xx (React Query rejects `undefined` as query data); any
// failure throws.
export async function fetchHealth(): Promise<true> {
  await request("/health");
  return true;
}

export const USING_API = !!API_BASE;
