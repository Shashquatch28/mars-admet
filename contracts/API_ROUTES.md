# MARS API Route Contract (Phase 0)

Blueprint Module 8's endpoint table, pinned to concrete request/response field
names. This is one of the three Phase 0 contracts (with the prediction-response
shape in `mars_contracts/prediction.py` and the conformer shape in
`mars_contracts/conformer.py`).

**Status:** field names below are locked for MVP. `/predict` is implemented
(stub predictor). Everything else is defined here so ml/, api/, and frontend/
build against a fixed surface; implementation lands in M3 (Module 8) / M4
(Module 6/7 lazy routes).

Base URL (local): `http://localhost:8000`

| Route | Method | Auth | Request model | Response model | Milestone |
|---|---|---|---|---|---|
| `/health` | GET | none | — | `{"status": "ok"}` | M0 ✅ |
| `/predict` | POST | none (IP rate-limited) | `PredictionRequest` | `PredictionResponse` | M0 ✅ (stub) |
| `/batch/predict` | POST | account | multipart file + `BatchPredictOptions` | `BatchPredictResponse` | M3 |
| `/batch/progress/{job_id}` | GET (SSE) | account | — | `text/event-stream` of `BatchJobStatus` | M3 |
| `/batch/results/{job_id}` | GET | account | — | `BatchPredictResponse` (results populated) | M3 |
| `/compare` | POST | none | `CompareRequest` | `CompareResponse` | M3 |
| `/molecule/{id}/3d` | GET | none | — | `ConformerResponse` | M3 (lazy) |
| `/molecule/{id}/explain?endpoint=<Endpoint>` | GET | none | query param `endpoint` | `ExplainResponse` (see below — not yet modelled) | M4 / Post-MVP |
| `/molecule/{id}/report` | GET | none | — | `application/pdf` (binary; no JSON model) | M4 |

`{id}` = `PredictionResponse.molecule_id` (16-hex truncated SHA-256 of standardized SMILES).

## Cross-cutting (Module 8)

- **Every** JSON response that carries predictions includes `model_version`
  (routing-table version tag). It is also part of the Redis cache key:
  `key = (standardized_smiles, sorted(endpoint_set), model_version)`, TTL 48h.
- Rate limits: anonymous 60 `/predict`/min per IP; per-account 5 concurrent
  batch jobs, 50,000-molecule cap, interactive threshold 1,000.
- Batch uploads (R2) auto-deleted 24h after job completion.
- Retention: `retrain_opt_in` defaults `false`; opted-in data stored separately
  from the serving cache/upload bucket.

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

### Auth stub (M3, Module 8/13)
```
POST /auth/register  { email, password, turnstile_token }  -> 201 { user_id }
POST /auth/login     { email, password }                    -> 200 + Set-Cookie: session=<token>
POST /auth/logout                                           -> 204
POST /auth/password-reset/request  { email }                -> 202
POST /auth/password-reset/confirm  { token, new_password }  -> 204
```
Session strategy is **server-side Redis sessions, not JWT** (Module 13):
`session:{token} -> user_id`, sliding 7-day TTL refreshed on activity. `token` is
an opaque `secrets.token_urlsafe` value returned in an HttpOnly cookie
(`SESSION_COOKIE_NAME`); logout / account-suspension deletes the Redis key for
instant revocation. Password-reset tokens are `itsdangerous`-signed, time-limited,
emailed via Resend. No JWT anywhere (decision confirmed 2026-08-30; `.env.example`
and `api/requirements.txt` cleaned up accordingly).
