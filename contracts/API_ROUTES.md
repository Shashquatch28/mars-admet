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
in Module 8's original table. `/molecule/{id}/explain` and `/molecule/{id}/report`
remain M4/Post-MVP, undefined here beyond the sketch below.

Base URL (local): `http://localhost:8000`

| Route | Method | Auth | Request model | Response model | Milestone |
|---|---|---|---|---|---|
| `/health` | GET | none | — | `{"status": "ok"}` | M0 ✅ |
| `/health/ready` | GET | none | — | `{"status", "checks": {"database", "redis"}}` | M3 ✅ (not in original Module 8 table; readiness vs. liveness split) |
| `/predict` | POST | none (IP rate-limited) | `PredictionRequest` | `PredictionResponse` | M3 ✅ (real per-endpoint routing + stub fallback; M0 shipped the stub-only version) |
| `/batch/predict` | POST | account | multipart file (CSV or SDF) + `smiles_column`/`endpoints` query params | `BatchPredictResponse` | M3 ✅ |
| `/batch/progress/{job_id}` | GET (SSE) | account | — | `text/event-stream` of `BatchJobStatus`-shaped JSON | M3 ✅ |
| `/batch/results/{job_id}` | GET | account | — | `BatchPredictResponse` (results populated) | M3 ✅ |
| `/compare` | POST | none | `CompareRequest` | `CompareResponse` | M3 ✅ |
| `/molecule/{id}/3d` | GET | none | — | `ConformerResponse` | M3 ✅ — `{id}` must have been seen by `/predict` in the current cache window (see below) |
| `/molecule/{id}/explain?endpoint=<Endpoint>` | GET | none | query param `endpoint` | `ExplainResponse` (see below — not yet modelled) | M4 / Post-MVP |
| `/molecule/{id}/report` | GET | none | — | `application/pdf` (binary; no JSON model) | M4 |

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
  coverage for some endpoints and none for others at the same time (e.g. as of
  2026-09-16, `hia_absorption` has one promoted local XGBoost seed;
  every other endpoint still falls back to the stub within the same response).
- Rate limits: anonymous 60 `/predict`/min per IP; per-account 5 concurrent
  batch jobs, 50,000-molecule cap, interactive threshold 1,000.
- Batch uploads (R2) auto-deleted 24h after job completion.
- Retention: `retrain_opt_in` defaults `false`; opted-in data stored separately
  from the serving cache/upload bucket.

## Module 13 — Auth & Persistence (M3)

| Route | Method | Auth | Request model | Response model |
|---|---|---|---|---|
| `/auth/register` | POST | none (Turnstile-gated) | `RegisterRequest` | `RegisterResponse` (201) |
| `/auth/login` | POST | none | `LoginRequest` | `LoginResponse` (200) + `Set-Cookie: mars_session=<token>` |
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

## Not yet modelled in `mars_contracts` (documented target shapes)

### `ExplainResponse` (M4, depends on Module 6)
```
molecule_id: str
endpoint: Endpoint
method: str                       # "integrated_gradients"
atom_attributions: list[float]    # per-atom signed importance, len == n_atoms
fragment_attributions: list[{     # aggregated to functional-group level (Module 6)
    smarts: str
    atom_indices: list[int]
    score: float                  # signed: + increases predicted risk, - decreases
}]
baseline: str                     # attribution baseline used
```

Auth + persistence routes are now modeled above (Module 13 section) rather
than sketched here — `RegisterRequest`/`LoginRequest`/etc. live in
`mars_contracts/auth.py`, `SaveMoleculeRequest`/etc. in
`mars_contracts/persistence.py`. No JWT anywhere (decision confirmed
2026-08-30; `.env.example` and `api/requirements.txt` cleaned up accordingly).
