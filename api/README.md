# api/ — MARS serving layer

FastAPI service for prediction, batch, molecule detail, auth and persistence.
Owns blueprint Modules 8 and 13. The route table and field names are in
[`../contracts/API_ROUTES.md`](../contracts/API_ROUTES.md); this file covers how
the service is put together and how to run and test it.

## Layout

```
app/
  main.py          app factory, CORS policy, startup warnings, router mounts
  core/config.py   Settings (env / .env); every key is documented in ../.env.example
  deps.py          auth dependency (session cookie -> user)
  db/              SQLAlchemy models, async session; Alembic migrations in alembic/
  routers/         health, predict, compare, molecule (3D), batch, auth,
                   molecules, reports, account
  services/
    prediction_service.py  routing: real model per endpoint, stub fallback
    stub_predictor.py      deterministic fake values (model_id "stub-v0")
    prediction_cache.py    Redis cache, key = smiles + endpoints + MODEL_VERSION
    rate_limit.py          anonymous per-IP limit on /predict (fails open)
    sessions.py            server-side sessions in Redis (not JWT)
    task_queue.py          batch queue: in-process LocalTaskQueue; Cloud Tasks is a
                           placeholder that raises NotImplementedError
    sdf_parser.py, batch_results.py, conformer_service.py, molecule_lookup.py,
    security.py, turnstile.py, redis_client.py
tests/             API tests; Postgres/Redis-backed ones skip when infra is down
```

## How a prediction is served

1. `routers/predict.py` rate-limits, then calls `prediction_service.predict`.
2. With the ml stack installed (the Docker image has it), the SMILES is
   standardized (a chemically invalid SMILES is a 422) and each requested
   endpoint is routed to its promoted artifact in `ml/artifacts/` via
   `ml/serve/registry.py`: featurize, predict, calibrate, applicability domain.
3. An endpoint with no promoted artifact, or any request when the ml stack is not
   importable, is served by the stub, and its row says so (`model_id: "stub-v0"`).
   The startup log warns when the ml stack is missing.
4. The synthetic-accessibility score is rule-based (`ml/serve/rule_based.py`) and
   is added as its own row when rdkit is present.
5. Top-level `model_version` is `MODEL_VERSION`. **Bump it whenever the response
   shape or routing changes**: it is part of the 48 h cache key, and an old key
   will otherwise keep serving the old shape.

## Run

From the repo root:

```bash
cp .env.example .env
docker compose up -d --build         # postgres, redis, minio, api on :8000
curl localhost:8000/health
```

Or without Docker, against a running Postgres and Redis:

```bash
pip install -e ./contracts
pip install -r api/requirements.txt
cd api && alembic upgrade head && uvicorn app.main:app --reload
```

Docs: `http://localhost:8000/docs`. The Docker image copies `ml/serve`,
`ml/featurize`, `ml/models` and `ml/eval` and mounts `ml/artifacts/` and
`ml/data/cache/` as volumes, so trained artifacts change independently of code.

## Test

```bash
pytest contracts/tests api/tests -q      # root .venv
ruff check contracts api ml
```

Without Postgres and Redis the integration tier skips rather than fails (see
`tests/conftest.py`, `requires_infra`); CI runs it against real service
containers. Real inference is only exercised where rdkit is installed (the
built image), so root-`.venv` runs are stub-only for `/predict` by design.

## Known limits

- Cloud Tasks is not wired; async batch runs in-process.
- The anonymous rate limiter keys on `request.client.host`. Behind Cloud Run
  that address is unverified (frontend ADR-025 item 5).
- CORS is an explicit origin list with credentials (`CORS_ALLOW_ORIGINS`). The
  session cookie is `SameSite=Lax`, so SPA and API must be same-site.
- No `/molecule/{id}/explain` or `/report` yet (see `contracts/API_ROUTES.md`).
