# MARS API Route Contract (Phase 0)

Blueprint Module 8's endpoint table, pinned to concrete request/response field
names. This is one of the three Phase 0 contracts (with the prediction-response
shape in `mars_contracts/prediction.py` and the conformer shape in
`mars_contracts/conformer.py`).

**Status:** field names below are locked for MVP. `/predict`, `/compare`,
`/batch/*`, `/molecule/{id}/3d`, and Module 13's auth/persistence routes are
all implemented (M3, 2026-09-17) — stub predictor plus real registry-backed
inference for endpoints with a promoted trained artifact (see `ml/serve/`);
real conformer generation reuses Module 3 Stage 5. `GET /health/ready`
(readiness: DB+Redis) exists alongside `/health` (liveness) though it isn't
in Module 8's original table. `/molecule/{id}/explain` is implemented (ADR-031, modelled
below as `ExplainResponse`); `/molecule/{id}/report` remains M4/Post-MVP.

Base URL (local): `http://localhost:8000/api`. Every route is mounted under `/api` in every
environment (frontend ADR-025), so one origin can serve the API and the built frontend; the
paths in the table below are relative to that prefix, e.g. `/health` is `GET /api/health`.
Interactive docs are at `/api/docs`.

| Route | Method | Auth | Request model | Response model | Milestone |
|---|---|---|---|---|---|
| `/health` | GET | none | — | `{"status": "ok"}` | M0 ✅ |
| `/health/ready` | GET | none | — | `{"status", "checks": {"database", "redis"}}` | M3 ✅ (not in original Module 8 table; readiness vs. liveness split) |
| `/generations` | GET | none | — | `GenerationsResponse` (`{"active", "available", "kermt_endpoints"}`; `active` is the version `/predict` stamps: the configured `model_version` plus `+kermt.<digest>` when KERMT serving is on; `available` is `[active]` until a second generation exists; `kermt_endpoints` lists the endpoints routed to KERMT, empty when it is off; frontend ADR-026, ADR-033) | M4 ✅ (not in original Module 8 table) |
| `/limits` | GET | none | — | `LimitsResponse` (`{"batch_size_cap", "batch_interactive_threshold", "batch_result_retention_hours", "anon_predict_rate_per_minute"}`), read from the settings the service enforces so no client writes them into its own copy; frontend ADR-034 item 8 | ✅ (not in original Module 8 table) |
| `/predict` | POST | none (IP rate-limited) | `PredictionRequest` | `PredictionResponse` (now with an optional `properties`: RDKit-computed molecule properties and PAINS/Brenk alerts, frontend ADR-034 item 3; null without RDKit or for an older cached response) | M3 ✅ (real per-endpoint routing + stub fallback; M0 shipped the stub-only version) |
| `/batch/predict` | POST | account | multipart file (CSV or SDF) + `smiles_column`/`endpoints` query params | `BatchPredictResponse` | M3 ✅ |
| `/batch/progress/{job_id}` | GET (SSE) | account | — | `text/event-stream` of `BatchJobStatus`-shaped JSON | M3 ✅ |
| `/batch/results/{job_id}` | GET | account | — | `BatchPredictResponse` (results populated) | M3 ✅ |
| `/depict` | POST | none (IP rate-limited, its own limit) | `DepictRequest` | `image/svg+xml`: a plain black-line 2D drawing of the molecule (one ink, no element colours, nothing highlighted or labelled; RDKit, so 501 where rdkit is absent, 422 for a SMILES it cannot parse or draw). POST so the SMILES stays out of URLs and logs; cached by canonical SMILES and drawing version; frontend ADR-039 | ✅ (not in original Module 8 table) |
| `/name` | POST | none (IP rate-limited, its own limit) | `NameRequest` | `NameResponse` (`status` `found` / `not_found` / `unavailable`, `inchikey`, `source`, `source_record`, `source_url`, `preferred_name`, `iupac_name`, `synonyms`, `reason`). The service computes the molecule's standard InChIKey with RDKit and asks PubChem about the key only; the SMILES is never sent to it. 200 for every molecule that parses: `not_found` is an answer (kept 24 h), `unavailable` is the source failing (timeout, busy, down, breaker open, switched off, with `reason`; never kept). 422 for a SMILES RDKit cannot parse; 501 where rdkit is absent; 429 past the per-IP limit. POST so the SMILES stays out of URLs and logs; cached by InChIKey (7 days for a found name); timeout, request-rate ceiling and circuit breaker so a slow source never touches `/predict`; frontend ADR-044 | ✅ (not in original Module 8 table) |
| `/compare` | POST | none | `CompareRequest` | `CompareResponse` | M3 ✅ |
| `/molecule/{id}/3d` | GET | none | — | `ConformerResponse` | M3 ✅ — `{id}` must have been seen by `/predict` in the current cache window (see below) |
| `/molecule/{id}/explain?endpoint=<Endpoint>` | POST / GET / DELETE | none (POST rate-limited with `/predict`) | query param `endpoint` | `ExplainResponse` or `ExplainJobStatus` (see below) | M4 ✅ — `{id}` must have been seen by `/predict` in the current cache window, like `/3d` |
| `/molecule/{id}/report` | GET | none | — | `application/pdf` (binary; no JSON model) | **Not built, superseded**: the report is made in the client (print, Save as PDF), frontend ADR-029 |

`GET /molecule/{id}/3d` needs the id -> SMILES mapping `/predict` registers
in Redis (same TTL as the prediction cache) — an id from a `/predict` call
whose cache entry has since expired, or one that was never requested, 404s
rather than guessing. Real conformer generation needs rdkit (the built
container); 501 in an environment without it.

`{id}` = `PredictionResponse.molecule_id` (16-hex truncated SHA-256 of standardized SMILES).

## Cross-cutting (Module 8)

- **Every** JSON response that carries predictions includes `model_version`
  (routing-table version tag). It is also part of the Redis cache key:
  `key = (standardized_smiles, sorted(endpoint_set), model_version)`, TTL 48h.
- **Every `EndpointPrediction` also carries its own `model_id`** (M3 addition,
  additive/non-breaking, defaults to `"stub-v0"`): which specific trained
  artifact served *that endpoint*, since the routing table can have real
  coverage for some endpoints and none for others at the same time. Since the
  2026-09-17 sweep all 14 ML endpoints have a promoted XGBoost model locally
  (`mars-xgboost-ecfp-desc-v1`); an environment without `ml/artifacts/` or
  without the ml stack falls back to `"stub-v0"` per endpoint. The rule-based
  SA score is served with `model_id: "rdkit-sascore"` when rdkit is present.
  Top-level `model_version` is the routing-table tag (`MODEL_VERSION`); it
  changes whenever response shape or routing changes, because it is part of the
  cache key.
- **Every `EndpointPrediction` carries `ad_threshold`** (Q19/ADR-020, additive,
  nullable): the cutoff `in_domain` was judged against (90th percentile of the
  endpoint's own leave-one-out 5-NN distances). `null` for stub-served and
  rule-based rows; clients must not invent a cutoff.
- `confidence_low` / `confidence_high` are the spread across the 5 CV seeds, not
  a confidence interval. The field names are historical (ADR-024).
- `/compare` returns `per_endpoint_winner: null` always: MARS has no validated
  direction-of-good, so the field is never populated and the UI never consumes it.
- Rate limits: anonymous 60 `/predict`/min per IP; per-account 5 concurrent
  batch jobs, 50,000-molecule cap, interactive threshold `BATCH_INTERACTIVE_THRESHOLD` (default 100; `GET /limits` reports the deployed value).
- Batch uploads (R2) auto-deleted after `BATCH_UPLOAD_RETENTION_HOURS` (default 24) from job completion; `GET /limits` reports it.
- Retention: submitted molecules are not retained beyond serving, and are never used for training; there is no
  retraining opt-in (frontend ADR-034 item 10).

## Module 13 — Auth & Persistence (M3)

| Route | Method | Auth | Request model | Response model |
|---|---|---|---|---|
| `/auth/register` | POST | none (Turnstile-gated) | `RegisterRequest` | `RegisterResponse` (201) |
| `/auth/login` | POST | none | `LoginRequest` | `LoginResponse` (200) + `Set-Cookie: mars_session=<token>` |
| `/auth/me` | GET | session cookie | — | `MeResponse` (200), 401 without a valid session (ADR-022) |
| `/auth/logout` | POST | session cookie | — | 204 |
| `/auth/password-reset/request` | POST | none | `PasswordResetRequestModel` | 202 (always, whether or not the email exists — no account enumeration) |
| `/auth/password-reset/confirm` | POST | none | `PasswordResetConfirmRequest` | 204 |
| `/molecules/save` | POST | session cookie | `SaveMoleculeRequest` | `SavedMoleculeResponse` (201) |
| `/molecules` | GET | session cookie | — | `list[SavedMoleculeResponse]` |
| `/molecules/{id}` | DELETE | session cookie, owner only | — | 204 |
| `/reports/save` | POST | session cookie | `SaveReportRequest` | `SavedReportResponse` (201). Fails with a clear "these results have expired" 410 if the batch job's R2 results were already purged (Module 13 save-vs-purge fix) |
| `/reports` | GET | session cookie | — | `list[SavedReportResponse]` |
| `/reports/{id}` | DELETE | session cookie, owner only | — | 204 |
| `/account` | DELETE | session cookie | `DeleteAccountRequest` | 204 — cascades to delete all `saved_molecules`/`saved_reports`/`batch_jobs` rows for the user (Module 13 retention lever) |

Session cookie: `SESSION_COOKIE_NAME` (default `mars_session`), HttpOnly,
sliding 7-day TTL refreshed on activity. `session:{token} -> user_id` in
Redis; logout/account-deletion deletes the key for instant revocation.

## `/molecule/{id}/explain` (Module 6, ADR-031; background jobs, ADR-040)

The model that serves the value explains it. `ml/serve/routing.json` decides, exactly as for `/predict`:
an XGBoost-served endpoint is explained by exact TreeSHAP over the promoted seeds (`method: "tree_shap"`),
a KERMT-served endpoint by Integrated Gradients on the KERMT service (`method: "integrated_gradients"`).
There is no fallback between the two: if KERMT serves an endpoint and cannot answer, the answer is 503, never an
explanation of a different model. `model_id` equals the `model_id` of the prediction explained (the client checks).

A KERMT-served explanation takes minutes (median 93-193 s warm on 4 CPUs, up to about 18 min for large molecules), so it is a
**background job inside the KERMT service** (ADR-040): `POST` starts or joins it (idempotent), `GET` reads it, `DELETE` cancels it.
An XGBoost-served explanation is instant: `POST` answers 200 with the result. The browser polls `GET` about every 3 s while a job
is queued or running; polling is not rate limited, starting a job is (the `/predict` per-IP bucket, one concurrent job per IP,
a bounded queue of 8). Results are cached 48 h under `explain_cache:<serving version>:<IG parameters digest>:<molecule_id>:<endpoint>`;
a failure is never cached. Job state lives in memory in the service: a restart loses it, reported as a failed job to start again.

| Status | Meaning |
|---|---|
| 200 | `ExplainResponse`; or, from `DELETE`, an `ExplainJobStatus` with state `cancelled` |
| 202 | `ExplainJobStatus`: queued or running, with `Retry-After` |
| 204 | `GET` only: nothing started and nothing cached for this molecule and endpoint |
| 403 | `DELETE` only: another visitor started this job; only the address that started it can cancel it (others may be waiting on it) |
| 404 | unknown or expired `molecule_id` (call `/predict` first) |
| 409 | nothing to explain: the endpoint is stub-served, or is the rule-based `synthetic_accessibility` |
| 422 | unknown `endpoint`, or the molecule cannot be explained |
| 429 | `POST` only: the `/predict` per-IP rate limit, or you already have an explanation running (one per address) |
| 501 | no ml stack in this environment (no RDKit / XGBoost) |
| 503 | the serving model cannot explain right now; the queue is full; or the job was lost to a service restart (start it again) |

`ExplainResponse` is in `mars_contracts/explain.py` (frontend mirror in `contracts.ts`, covered by the drift test).
Every number is signed: positive pushed the model's output UP from its reference, negative DOWN. The contract never
says "risk", "safe" or "favourable" (AGENTS.md rule 1; a test enforces it on the field descriptions).

```
base_value + structure_total + whole_molecule_total + unmapped_total == output_value   (to completeness_error)

structure_total        = sum(atom_attributions)     # one value per atom of smiles_standardized, RDKit order
whole_molecule_*       = RDKit 2D descriptors the model also reads; they cannot be placed on atoms
unmapped_total         = TreeSHAP: fingerprint bits absent from the molecule; IG: the completeness residual
completeness_error     = the method's own identity: IG the integration residual |unmapped_total|, TreeSHAP the additivity error
converged              = IG only: completeness_error met the tolerance after the final step count (false is returned, flagged)
seed_agreement         = median pairwise cosine of the per-seed atom attributions (null for one seed)
fragment_attributions  = sums over named functional groups / ring systems; they overlap and do NOT add up
output_space           = "log_odds" (XGBoost classification), "score" (KERMT classification), "native_unit" (regression)
```

Auth + persistence routes are now modeled above (Module 13 section) rather
than sketched here — `RegisterRequest`/`LoginRequest`/etc. live in
`mars_contracts/auth.py`, `SaveMoleculeRequest`/etc. in
`mars_contracts/persistence.py`. No JWT anywhere (decision confirmed
2026-08-30; `.env.example` and `api/requirements.txt` cleaned up accordingly).
