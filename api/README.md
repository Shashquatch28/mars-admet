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
curl localhost:8000/api/health
```

Or without Docker, against a running Postgres and Redis:

```bash
pip install -e ./contracts
pip install -r api/requirements.txt
cd api && alembic upgrade head && uvicorn app.main:app --reload
```

Every route is under `/api` (ADR-025). Docs: `http://localhost:8000/api/docs`. The Docker image copies `ml/serve`,
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

## Batch worker deploy (not yet run against GCP)

One Cloud Run service serves the site, the API and the worker endpoint. Set on that service:
`BATCH_QUEUE_BACKEND=cloud_tasks`, `BATCH_BLOB_BACKEND=s3`, `BATCH_WORKER_SECRET` (long random),
`WORKER_BASE_URL` (its own URL), `GCP_PROJECT_ID`, `GCP_REGION`, `CLOUD_TASKS_QUEUE`, the R2 `S3_*`
values with `S3_REGION=auto`, and `MAX_CONCURRENT_PREDICTIONS` = its vCPU count. The service account
needs `roles/cloudtasks.enqueuer`. Create the queue with the same attempt count the app expects:

```bash
gcloud tasks queues create mars-batch --location=us-central1   --max-attempts=5 --min-backoff=10s --max-backoff=300s --max-concurrent-dispatches=2
```

After the first deploy, check: (1) a 300-row upload reaches `done` and `/api/batch/progress` advances
slice by slice; (2) `POST /api/internal/batch/run` without the secret answers 403; (3) stop the service
mid-job and confirm Cloud Tasks retries the slice and the job still finishes; (4) the result is an object
under `batch/<job>/results.json` and expires after 24 h.

## Known limits

- Async batch: by default (`BATCH_QUEUE_BACKEND=local`) a queued job runs inside this process and dies with
  it. `BATCH_QUEUE_BACKEND=cloud_tasks` enqueues one Cloud Task per slice of `BATCH_SLICE_ROWS` molecules,
  aimed at `POST /api/internal/batch/run` on this same service (guarded by `BATCH_WORKER_SECRET`; absent
  unless that backend is on). That path is unit-tested against a fake Cloud Tasks client and has not run
  against a real project: do the checks under "Batch worker deploy" after the first deploy.
- Batch bytes (the uploaded molecules, slice results, the final result) go through `BATCH_BLOB_BACKEND`.
  `redis` is for development only: a result is about 2.5 KB per molecule and Upstash's free plan allows
  10 MB per request and 100 MB per record, so Redis holds a few thousand rows at most and the
  50,000-molecule cap cannot fit. Production uses `s3` (Cloudflare R2). Each object carries an expiry
  stamp that reads enforce, so the 24 h retention holds without a lifecycle rule; add one as well
  (delete `batch/` objects after 1 day) so expired objects are removed.
- The anonymous rate limiter counts per client address. By default that is the socket peer
  (`request.client.host`), which behind a proxy is the proxy: everyone would share one bucket.
  Set `TRUSTED_PROXY_HOPS=1` behind Cloud Run to read the entry Google's front end appended to
  `X-Forwarded-For` (entries to its left are client-supplied and are never read; uvicorn's own
  `--forwarded-allow-ips` is not used because it only trusts `127.0.0.1` by default and `*` would
  trust a forgeable leftmost entry). That Cloud Run appends exactly one entry is the documented
  load-balancer behaviour but has not been observed on a deployed service: after the first deploy,
  send two requests with different forged `X-Forwarded-For` values and confirm they share a bucket.
- Predictions run on a pool capped at one per CPU (`MAX_CONCURRENT_PREDICTIONS`, default the CPUs
  this process may use). Cloud Run may not report its vCPU limit to the process, so set it there.
- Batch files up to `BATCH_INTERACTIVE_THRESHOLD` (100) are answered in the upload request; larger
  files are queued and report progress.
- CORS is an explicit origin list with credentials (`CORS_ALLOW_ORIGINS`). The
  session cookie is `SameSite=Lax`, so SPA and API must be same-site.
- No `/molecule/{id}/explain` or `/report` yet (see `contracts/API_ROUTES.md`).
