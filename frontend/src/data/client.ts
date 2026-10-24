// Typed API client. Talks to the real FastAPI service (API_ROUTES.md). When
// VITE_API_BASE is unset the app never calls this and shows no values (ADR-032).
//
// VITE_API_BASE is "/api" in dev and in the production build (ADR-025): Vite proxies
// it to the API in dev, and the API container serves the bundle and /api together in
// production, so the browser only ever makes same-origin requests and CORS never
// applies. Requests send `credentials: "include"` for the HttpOnly session cookie.
// Cookies are SameSite=Lax, so the SPA and API must be same-site; one origin is.
// A split deployment would need the API's explicit CORS origin list (CORS_ALLOW_ORIGINS).
import { parseProgressEvents, type JobProgress } from "../domain/batchJob";
import type { ExplainAnswer } from "../domain/explain";
import type {
  BatchPredictResponse,
  CompareRequest,
  CompareResponse,
  ConformerResponse,
  DeleteAccountRequest,
  DepictRequest,
  Endpoint,
  ExplainJobStatus,
  ExplainResponse,
  LoginResponse,
  MeResponse,
  PasswordResetConfirmRequest,
  PasswordResetRequestModel,
  GenerationsResponse,
  LimitsResponse,
  PredictionResponse,
  RegisterResponse,
  SaveMoleculeRequest,
  SaveReportRequest,
  SavedMoleculeResponse,
  SavedReportResponse,
} from "../types/contracts";

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

// Called when a gated route answers 401: the session is gone, so the app drops to
// anonymous and the workspace shows its sign-in state in place (ADR-022). /auth/*
// 401s are answers to the auth calls themselves (wrong password, no session) and
// are handled by their callers, not here.
let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: (() => void) | null): void {
  onUnauthorized = fn;
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
    if (res.status === 401 && !path.startsWith("/auth/")) onUnauthorized?.();
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
  // The `endpoints` field of the request: null = no subset (all). Rows the user left
  // out are NOT REQUESTED rather than NOT RETURNED, so the request must be remembered.
  sent: Endpoint[] | null;
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
  return { response, latencyMs: Math.round(performance.now() - t0), submitted: smiles, sent: endpoints ?? null };
}

// Two or three molecules, anonymous. A single invalid SMILES fails the whole comparison (422)
// rather than comparing against a fabricated result. `per_endpoint_winner` comes back null and
// is never read (ADR-007).
export async function fetchComparison(smiles: string[], endpoints?: Endpoint[] | null): Promise<CompareResponse> {
  const body: CompareRequest = { smiles, endpoints: endpoints ?? null };
  const res = await request("/compare", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  return (await res.json()) as CompareResponse;
}

// 404: unknown or expired molecule_id (a normal state); 501: the API has no RDKit.
export async function fetchConformer(moleculeId: string): Promise<ConformerResponse> {
  const res = await request(`/molecule/${encodeURIComponent(moleculeId)}/3d`);
  return (await res.json()) as ConformerResponse;
}

// A plain black-line 2D drawing as SVG text (ADR-039). POST, so the SMILES is never written into a URL. 501: the API has no RDKit;
// 422: a SMILES it cannot parse or draw. The service caches by canonical SMILES; the browser keeps the text for the session.
export async function fetchDepiction(smiles: string): Promise<string> {
  const body: DepictRequest = { smiles };
  const res = await request("/depict", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  return res.text();
}

// Explanation of the model that served `endpoint` (ADR-031, ADR-040). A tree model answers at once; a KERMT
// explanation is a background job that takes minutes, so the URL has three verbs: GET reads (no side effect),
// POST starts or joins, DELETE cancels. 200 is a result (or, from DELETE, the cancelled job), 202 a job that is
// queued or running, 204 nothing started. 404 expired molecule, 409 nothing to explain, 422 cannot be explained,
// 429 limit, 501 no ml stack, 503 cannot explain now: each is an answer with its own state, not a crash.
async function explainCall(method: "GET" | "POST" | "DELETE", moleculeId: string, endpoint: Endpoint): Promise<ExplainAnswer> {
  const q = new URLSearchParams({ endpoint });
  const res = await request(`/molecule/${encodeURIComponent(moleculeId)}/explain?${q}`, { method });
  if (res.status === 204) return { kind: "none" };
  const body = (await res.json()) as ExplainResponse | ExplainJobStatus;
  return "job_id" in body ? { kind: "job", job: body } : { kind: "result", data: body };
}

export const readExplanation = (moleculeId: string, endpoint: Endpoint) => explainCall("GET", moleculeId, endpoint);
export const startExplanation = (moleculeId: string, endpoint: Endpoint) => explainCall("POST", moleculeId, endpoint);
export const cancelExplanation = (moleculeId: string, endpoint: Endpoint) => explainCall("DELETE", moleculeId, endpoint);

const jsonBody = (body: unknown): RequestInit => ({
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

const jsonPost = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

// Who the session cookie belongs to, or null when there is no valid session (401).
// Any other failure (unreachable, 5xx) throws.
export async function fetchMe(): Promise<MeResponse | null> {
  try {
    return (await (await request("/auth/me")).json()) as MeResponse;
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return null;
    throw e;
  }
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  return (await (await request("/auth/login", jsonPost({ email, password }))).json()) as LoginResponse;
}

// Turnstile is not wired in the client (ADR-022 item 6): the server skips verification
// when its secret is unset, and this placeholder satisfies the required field.
export async function register(email: string, password: string): Promise<RegisterResponse> {
  const body = { email, password, turnstile_token: "unset" };
  return (await (await request("/auth/register", jsonPost(body))).json()) as RegisterResponse;
}

// Always 202 with no body, whether or not the address has an account (ADR-043): there is nothing here to learn from.
export async function requestPasswordReset(email: string): Promise<void> {
  const body: PasswordResetRequestModel = { email };
  await request("/auth/password-reset/request", jsonPost(body));
}

// 204 on success (no session is started). 400 is the one answer for an unknown, used or expired link; 429 is the per-IP limit.
export async function confirmPasswordReset(token: string, newPassword: string): Promise<void> {
  const body: PasswordResetConfirmRequest = { token, new_password: newPassword };
  await request("/auth/password-reset/confirm", jsonPost(body));
}

export async function logout(): Promise<void> {
  await request("/auth/logout", { method: "POST" });
}

// Liveness only (`/health`). Readiness (`/health/ready`) reports Postgres/Redis
// connectivity, which the badge does not claim.
// Resolves `true` on a 2xx (React Query rejects `undefined` as query data); any
// failure throws.
export async function fetchHealth(): Promise<true> {
  await request("/health");
  return true;
}

// The deployed model generation (ADR-026). Anonymous, like /predict.
export async function fetchGenerations(): Promise<GenerationsResponse> {
  return (await (await request("/generations")).json()) as GenerationsResponse;
}

// The deployed policy numbers (batch cap, interactive threshold, retention, anonymous rate). Anonymous.
export async function fetchLimits(): Promise<LimitsResponse> {
  return (await (await request("/limits")).json()) as LimitsResponse;
}

// --- batch (account required; API_ROUTES.md /batch/*) ---

/**
 * Upload a CSV or SDF. Up to the service's interactive threshold (`GET /limits`) come back in this response
 * (`job_id` null, `status` "done"); more are queued and `job_id` is set. `endpoints` null means
 * no subset. Not sent as JSON: the body is multipart, so no Content-Type is set and the
 * browser adds the boundary.
 */
export async function postBatch(
  file: File,
  opts: { smilesColumn?: string; endpoints?: Endpoint[] | null } = {},
): Promise<BatchPredictResponse> {
  const query = new URLSearchParams();
  if (opts.smilesColumn?.trim()) query.set("smiles_column", opts.smilesColumn.trim());
  for (const e of opts.endpoints ?? []) query.append("endpoints", e);
  const qs = query.toString();
  const body = new FormData();
  body.append("file", file, file.name);
  const res = await request(`/batch/predict${qs ? `?${qs}` : ""}`, { method: "POST", body });
  return (await res.json()) as BatchPredictResponse;
}

/**
 * Follow GET /batch/progress/{job_id} (server-sent events) until the service closes the
 * stream, calling `onProgress` for each report. Read with fetch rather than EventSource
 * so a 401/404 reaches the same error handling as every other call. Resolves with the
 * last report seen (null if the stream carried none).
 */
export async function followBatchProgress(
  jobId: string,
  onProgress: (p: JobProgress) => void,
  signal?: AbortSignal,
): Promise<JobProgress | null> {
  const res = await request(`/batch/progress/${encodeURIComponent(jobId)}`, { signal });
  if (!res.body) throw new ApiError(0, "The progress stream is not readable in this browser");
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let last: JobProgress | null = null;
  for (;;) {
    const { done, value } = await reader.read();
    if (value) buffer += decoder.decode(value, { stream: !done });
    const parsed = parseProgressEvents(done ? buffer + "\n\n" : buffer);
    buffer = done ? "" : parsed.rest;
    for (const ev of parsed.events) {
      last = ev;
      onProgress(ev);
    }
    if (done) return last;
  }
}

// 409: still running; 410: results expired (24 h retention); 404: not this account's job.
export async function fetchBatchResults(jobId: string): Promise<BatchPredictResponse> {
  return (await (await request(`/batch/results/${encodeURIComponent(jobId)}`)).json()) as BatchPredictResponse;
}

// --- library (account required; API_ROUTES.md /molecules, /reports, /account) ---

// Snapshot-on-save: the service freezes exactly what is sent. 201 on success.
export async function saveMolecule(body: SaveMoleculeRequest): Promise<SavedMoleculeResponse> {
  return (await (await request("/molecules/save", jsonPost(body))).json()) as SavedMoleculeResponse;
}

export async function saveReport(body: SaveReportRequest): Promise<SavedReportResponse> {
  return (await (await request("/reports/save", jsonPost(body))).json()) as SavedReportResponse;
}

export async function fetchSavedMolecules(): Promise<SavedMoleculeResponse[]> {
  return (await (await request("/molecules")).json()) as SavedMoleculeResponse[];
}

export async function fetchSavedReports(): Promise<SavedReportResponse[]> {
  return (await (await request("/reports")).json()) as SavedReportResponse[];
}

// 404 means it is not this account's (or already gone): callers treat it as gone.
export async function deleteSavedMolecule(id: string): Promise<void> {
  await request(`/molecules/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function deleteSavedReport(id: string): Promise<void> {
  await request(`/reports/${encodeURIComponent(id)}`, { method: "DELETE" });
}

// Cascades on the server to saved molecules, saved reports and batch jobs, and revokes every
// session. 403 = wrong password. 204 = gone; the caller then drops to anonymous.
export async function deleteAccount(password: string): Promise<void> {
  const body: DeleteAccountRequest = { password };
  await request("/account", { method: "DELETE", ...jsonBody(body) });
}

export const USING_API = !!API_BASE;
