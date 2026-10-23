# MARS cloud deploy runbook

Written 2026-10-23 on branch `deploy/cloud-run`. Ship checklist items C6-C9 and D14. Target: one Cloud Run
service serving the site and the API under `/api` (ADR-025), Neon Postgres, Upstash Redis, Cloudflare R2, Cloud
Tasks for the batch worker, a separate KERMT CPU service, Sentry and UptimeRobot.

**Status of this document.** Everything below is *prepared*, not *observed*. The code paths (model delivery,
Neon URL handling, the worker endpoint) are tested locally; no step has been run against GCP, Neon, Upstash or R2.
"Verify" lines say what to look at; the ship checklist is ticked only for what was actually seen on the deployed
service (see "Ticking the checklist" at the end).

## How to read the steps

Each step has **Who** (`you / console` = a provider's web page; `you / terminal` = your own PowerShell; `me / repo`
= done in this repository), **Do**, **Verify**, **Undo**, and **Costs** where there is one.

**Secrets rule.** You type or paste every secret yourself, into a provider console or into your own terminal. They
never go into this repository, a commit, a log, or a chat message. Secrets live in Google Secret Manager and reach
Cloud Run as secret-backed environment variables; this document names variables, never values. A secret must have no
trailing newline (paste in the console, or use the helper in step 7).

**Phase 2 rule.** Every command that creates, changes or deletes a cloud resource, or costs money, is shown to you
first and run only after you say so. Read-only commands (`list`, `describe`, `curl`) run freely once you are logged in.

PowerShell variables used throughout (set once per terminal):

```powershell
$PROJECT = "<gcp-project-id>"
$REGION  = "us-central1"
$AR      = "mars"                                   # Artifact Registry repository
$IMAGE   = "$REGION-docker.pkg.dev/$PROJECT/$AR/mars-api"
$KIMAGE  = "$REGION-docker.pkg.dev/$PROJECT/$AR/mars-kermt"
$TAG     = (git rev-parse --short HEAD)
$SVC     = "mars-api"
$KSVC    = "mars-kermt"
$SA      = "mars-runtime@$PROJECT.iam.gserviceaccount.com"
```

## 0. What runs where

| Piece | Service | What it holds | Free-tier note |
|---|---|---|---|
| Site + API + worker endpoint | Cloud Run `mars-api` (one image, `api/Dockerfile`) | bundle, FastAPI, 70 XGBoost models in RAM | Cloud Run free tier, request-based billing |
| Trained XGBoost models | R2 bucket `mars-models` | one immutable release, ~209 MB, 184 files | R2 free 10 GB |
| Batch bytes | R2 bucket `mars-batch-uploads` | `batch/<job>/...`, 24 h | R2 free tier |
| Accounts, saved items, jobs | Neon Postgres | 4 tables (Alembic) | Neon free plan |
| Sessions, cache, rate limit, progress | Upstash Redis | `session:*`, prediction cache, `ratelimit:*`, `batch_progress:*` | 500K commands/month |
| Batch slices | Cloud Tasks queue `mars-batch` | one task per 250 molecules | ~1M operations/month free (from memory; the pricing page did not load, confirm) |
| KERMT predictions | Cloud Run `mars-kermt` (`ml/serve/kermt_service`) | 15 checkpoints from a Cloud Storage volume | not free past ~10k predictions/month, see step 13 |
| Errors / uptime | Sentry, UptimeRobot | | free plans |

## 1. Accounts and values to bring (do these first, in this order)

Free-tier limits were read from each provider's pricing page on 2026-10-23 unless marked "unverified". Prices change; check the page before relying on a number.

| # | Account | You create | You bring back (keep in your password manager) | Limit that could bite |
|---|---|---|---|---|
| 1 | **Google Cloud** | Project + billing account (a card is required even for the free tier). Budget alert: Billing > Budgets, $5 with 50/90/100 % thresholds. | Project ID, region (`us-central1`) | Cloud Run free: 2M requests, 180,000 vCPU-s, 360,000 GiB-s per month, *request-based billing only*. Artifact Registry free 0.5 GB then ~$0.10/GB-month (image 1.11 GB, so cents). Cloud Build 120 build-minutes/day free. Secret Manager: ~6 free versions, then ~$0.06 each per month (this deploy uses ~10; unverified figures). **The KERMT service is the one component that can cost real money** (step 13). |
| 2 | **Neon** | Project `mars`, Postgres 16 or newer, region near `us-central1` (AWS `us-east-2` is the closest) | the **direct** (non-pooled) connection string | Free plan: 100 CU-hours/project/month, 1 GB storage, compute **suspends after 5 minutes idle** (the first query after idle waits for it to wake), 5 GB transfer. `/api/health` deliberately does not touch the database. |
| 3 | **Upstash** | Redis database `mars`, GCP `us-central1` if offered, TLS on | the `rediss://default:<password>@<host>:<port>` URL (TCP, not the REST URL) | Free: 500K commands/month, 256 MB, 10 MB per request. A watched batch polls Redis twice a second (about 7,200 commands per hour per open progress stream); each uncached prediction costs a handful (rate limit, cache get/set); each signed-in request one session read. Watch the usage graph in the first week. |
| 4 | **Cloudflare R2** | Cloudflare account, enable R2 (it may ask for a card even on the free tier: check at sign-up), buckets `mars-models` and `mars-batch-uploads`, three API tokens (step 3) | account ID, three key pairs | Free: 10 GB storage, 1M Class A (write/list), 10M Class B (read) per month, no egress fee. Each release is ~209 MB, so ten kept releases fill the free storage: delete old ones. |
| 5 | **Sentry** | Organization + project (Python / FastAPI) | the project DSN | Free: 5,000 errors/month, 1 user, 30 days. A crash loop spends the quota in minutes. |
| 6 | **UptimeRobot** | Account, alert email | none | Free: 50 monitors, 5-minute interval; the page calls it "hobby and non-profit" and does not say whether commercial use is allowed. |
| 7 | **Tools on your machine** | `gcloud` CLI, Docker Desktop (only for local builds), the repo's root `.venv` | | |
| 8 | **Domain** | *Not needed.* The `*.run.app` URL is HTTPS and same-origin. A custom domain is a later choice. | | Turnstile (D14) needs a hostname it accepts: confirm `run.app` is allowed when you reach that step (unverified). |
| 9 | **Not used** | Resend (password reset is off, ADR-022 item 7), Vercel (frontend ships in the API image, ADR-025), W&B login (KERMT checkpoints are already on this machine in `ml/artifacts_kermt/`, 5.7 GB). | | |

**Region choice.** Keep Cloud Run, Cloud Tasks, Artifact Registry, the Cloud Storage bucket and (if offered) Upstash
in `us-central1`; Neon in `us-east-2`. Round trips between them are per-request cost.

## 2. Environment variables, from `api/app/core/config.py`

The API reads these (field name upper-cased). **Secret** = Secret Manager. **Plain** = `--set-env-vars`. **Leave** = keep the code default.

### API service (`mars-api`)

| Variable | Code default | Production value | Kind | Notes |
|---|---|---|---|---|
| `DATABASE_URL` | local compose DSN | Neon *direct* URL, pasted as Neon shows it | Secret | `postgresql://...?sslmode=require&channel_binding=require` is rewritten to `postgresql+asyncpg://...?ssl=require` by `normalize_database_url`. Use the direct host, not `-pooler`: the app opens a connection per request and the pooled endpoint needs asyncpg statement-cache changes that are not made. |
| `REDIS_URL` | `redis://localhost:6379/0` | Upstash `rediss://` URL | Secret | `rediss` = TLS. |
| `SECRET_KEY` | `mars-dev-secret-change-me` | 48 random bytes, hex | Secret | Signs password-reset tokens. The app warns at start-up if left at the default. |
| `SESSION_COOKIE_SECURE` | `false` | `true` | Plain | The app logs a warning at start-up if the bundle is served without it. |
| `CORS_ALLOW_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | the service's own `https://...run.app` URL | Plain | Same-origin never needs CORS. ADR-025 says "empty"; the code default is *not* empty, so set it explicitly (after the first deploy, step 11). |
| `TRUSTED_PROXY_HOPS` | `0` | `1` | Plain | Cloud Run appends one `X-Forwarded-For` entry. Unverified until check C-4. |
| `RATE_LIMIT_ANON_PER_MINUTE` | `60` | leave | Plain | Per client address, `/predict` only. |
| `MAX_CONCURRENT_PREDICTIONS` | `0` (= CPUs the process sees) | the service's vCPU count, `2` | Plain | Cloud Run may not report its CPU limit. |
| `STATIC_DIR` | empty | set by the Dockerfile (`/app/static`) | image | Do not set. |
| `PORT` | | supplied by Cloud Run | platform | The Dockerfile's `CMD` reads it. |
| `MODEL_ARTIFACT_BUCKET` | empty | `mars-models` | Plain | Turns on download + verification at start-up. |
| `MODEL_ARTIFACT_PREFIX` | `models` | leave | Plain | |
| `MODEL_ARTIFACT_RELEASE` | empty | the 64-hex id printed by the publish script | Plain | Pins the exact bytes. Rolling back = the previous id. |
| `MODEL_ARTIFACT_ACCESS_KEY_ID` / `MODEL_ARTIFACT_SECRET_ACCESS_KEY` | empty (falls back to `S3_*`) | read-only token on `mars-models` | Secret | The write token never leaves your machine. |
| `MODEL_ARTIFACT_DIR` | `./ml/artifacts` | leave (`/app/ml/artifacts`, the container's memory-backed disk) | | The directory must start empty. |
| `REQUIRE_REAL_MODELS` | `false` | `true` | Plain | Refuse to start rather than serve a stub for any of the 14 endpoints (implied when the bucket is set). |
| `MODEL_VERSION` | `v0.2.0-dev` | leave, or `v0.2.0` | Plain | Part of the 48 h prediction-cache key. |
| `MARS_APPLY_PLATT` | unset | leave unset | | Raw scores (C0, decisions.md 2026-10-08). Read by `ml/serve/predictor.py`, not by `Settings`. |
| `ML_DATA_CACHE_DIR` | `./ml/data/cache` | leave | | Featurization cache, written per new molecule (~4.4 KB: 2.2 KB Morgan + 2.3 KB descriptors) onto the memory-backed disk. See "Memory" below. |
| `PREDICTION_CACHE_TTL_SECONDS` | `172800` | leave | | |
| `S3_ENDPOINT_URL` | `http://localhost:9000` | `https://<account-id>.r2.cloudflarestorage.com` | Plain | |
| `S3_REGION` | `us-east-1` | `auto` | Plain | R2 wants `auto`. |
| `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` | MinIO dev keys | read-write token on `mars-batch-uploads` | Secret | |
| `S3_BUCKET_UPLOADS` | `mars-batch-uploads` | leave, or your bucket name | Plain | |
| `BATCH_BLOB_BACKEND` | `redis` | `s3` | Plain | Redis cannot hold a large batch on Upstash. |
| `BATCH_QUEUE_BACKEND` | `local` | `cloud_tasks` | Plain | |
| `BATCH_WORKER_SECRET` | empty | 48 random bytes, hex | Secret | Sent as `X-MARS-Worker-Secret`; empty disables the worker endpoint. |
| `WORKER_BASE_URL` | empty | the service's own URL | Plain | Known only after the first deploy (step 11). |
| `GCP_PROJECT_ID` | empty | project ID | Plain | |
| `GCP_REGION` | `us-central1` | leave | Plain | |
| `CLOUD_TASKS_QUEUE` | `mars-batch` | leave | Plain | |
| `BATCH_SLICE_ROWS` | `250` | leave | Plain | About two minutes of work per slice. |
| `BATCH_TASK_DEADLINE_SECONDS` | `900` | leave | Plain | Max 1800. |
| `BATCH_TASK_MAX_ATTEMPTS` | `5` | `5` | Plain | **Must equal the queue's `--max-attempts`** (step 10). |
| `BATCH_SIZE_CAP` | `50000` | `50000`; **lower it if KERMT is on** (step 13) | Plain | |
| `BATCH_INTERACTIVE_THRESHOLD` | `100` | `100` without KERMT, `20` with KERMT | Plain | Larger files are queued. |
| `BATCH_UPLOAD_RETENTION_HOURS` | `24` | leave | Plain | Reported by `GET /api/limits`. |
| `KERMT_SERVICE_URL` | empty (KERMT off) | the `mars-kermt` URL, once it is ready | Plain | |
| `KERMT_SERVICE_TOKEN` | empty | same value as the KERMT service's `KERMT_TOKEN` | Secret | |
| `KERMT_TIMEOUT_SECONDS` | `30` | leave | Plain | After it, KERMT-routed endpoints fall back to XGBoost (dagger shown), uncached. |
| `KERMT_ROUTING_PATH` | empty (packaged `routing.json`) | leave | | |
| `SENTRY_DSN` | empty (off) | the DSN | Secret | |
| `SENTRY_ENVIRONMENT` | `development` | `production` | Plain | |
| `SENTRY_RELEASE` | empty | the git short sha (`$TAG`) | Plain | |
| `SENTRY_TRACES_SAMPLE_RATE` | `0` | leave | Plain | |
| `CLOUDFLARE_TURNSTILE_SECRET_KEY` | empty (verification skipped) | **leave unset until D14's widget exists** | Secret | If set before the client sends real tokens, nobody can register (the client sends a placeholder, ADR-022 item 6). |
| `RESEND_API_KEY` | empty | leave unset | | Unused: no password-reset email. |
| `SESSION_TTL_DAYS`, `SESSION_COOKIE_NAME`, `PASSWORD_HASH_SCHEME` | 7, `mars_session`, `bcrypt` | leave | | |

### KERMT service (`mars-kermt`, `ml/serve/kermt_service/app.py` and `engine.py`)

| Variable | Default | Production value | Kind | Notes |
|---|---|---|---|---|
| `KERMT_MODELS_DIR` | `/models` (image `ENV`) | leave; the volume mounts here | | Layout `<arm>/seed_<n>/model.pt` + `metadata.json`. |
| `KERMT_ARMS` | every arm found | `toxicity__cls,metabolism__cls,metabolism__reg,absorption_distribution__cls,absorption_distribution__reg` | Plain | DILI is not routed to KERMT (`ml/serve/routing.json`). |
| `KERMT_SEEDS` | every seed found | `0,1,2` | Plain | 3 of 5 seeds: 15 checkpoints. |
| `KERMT_THREADS` | the container's cgroup CPU limit | `4` | Plain | Cloud Run's sandbox may not expose the cgroup file, so set it. |
| `KERMT_BATCH_SIZE` | `32` | leave | Plain | |
| `KERMT_TOKEN` | unset (no auth) | same value as the API's `KERMT_SERVICE_TOKEN` | Secret | The URL is public, so the token is the only guard; `/health` is open. |
| `PORT` | | **not read**: the image listens on `8100` | | Deploy with `--port 8100`. |

### Publish script (your terminal only, never on a server)

| Variable | Notes |
|---|---|
| `S3_ENDPOINT_URL`, `S3_REGION` | as above |
| `MODEL_PUBLISH_ACCESS_KEY_ID`, `MODEL_PUBLISH_SECRET_ACCESS_KEY` | the write-capable token on `mars-models` |
| `MODEL_ARTIFACT_BUCKET`, `MODEL_ARTIFACT_PREFIX` | optional; `--bucket` / `--prefix` override |

### Migration (your terminal only)

| Variable | Notes |
|---|---|
| `DATABASE_URL` | the Neon direct URL; `alembic/env.py` reads it through `Settings`. |

## 3. How the trained models get to Cloud Run (the known gap, closed)

`ml/artifacts/` (209 MB, 14 endpoints x 5 seeds x model + AD index + calibrator or error band, 184 files) is
gitignored and not in the image. The route:

1. **You publish** with `infra/scripts/publish_model_artifacts.py`. It hashes every file, builds a manifest, and
   uploads `models/<release>/files/...` then `models/<release>/manifest.json` last. The release id is the SHA-256
   of the manifest, so the id pins the exact bytes. It refuses a tree that does not cover all 14 endpoints (a
   model, its AD index, and a calibrator or error band) and verifies the upload afterwards.
2. **Each API instance** (`app/services/model_artifacts.py`, called first in the app's lifespan) downloads that
   release into its empty `MODEL_ARTIFACT_DIR`, streams each file through SHA-256, checks size and digest against
   the manifest, and checks the 14-endpoint roster. **Any** failure (unreachable bucket, wrong release id, altered
   manifest, corrupted or missing object, an endpoint without a model, a directory that already holds other
   files) raises; the process exits before opening its port; Cloud Run never routes traffic to that revision and
   the previous revision keeps serving. It never falls back to the stub, and the error names the object or endpoint.
3. Regression endpoints must ship `error_band.json` (without it a row prints no interval), classification
   endpoints `calibrator.json`; with KERMT on, the regression endpoints routed to KERMT must also ship
   `kermt_error_band.json`. Because bands travel inside the release, **a missing band cannot reach production**.
   They need rebuilding only when the tree you publish lacks them or after a retrain, and only on a machine with
   `ml/data/processed` (your development machine, not Cloud Run):
   `cd ml; $env:PYTHONPATH="."; .\.venv\Scripts\python train\build_error_bands.py` (about 6 minutes). The KERMT
   bands: `train/build_kermt_error_bands.py` against a service that loaded all five seeds.

Cost of the route: R2 storage ~209 MB per release (free tier 10 GB), ~184 Class A operations per publish, ~185
Class B per instance start (free tiers 1M and 10M), no egress fee. **Start-up cost:** every new instance
downloads ~209 MB before it listens (8 s from a local MinIO; from R2 over the internet expect 10-30 s, unmeasured),
then loads 70 models in the background (~12 s, measured earlier on a laptop). Cloud Run's container disk is
memory, so the 209 MB also counts against the instance's memory.

**Rejected alternative: baking `ml/artifacts` into the image.** Simpler at run time, but CI and Cloud Build cannot
see the gitignored directory, so the image would have to be built on your machine and pushed over your uplink, and
every model change would be an image rebuild. The release pins the bytes and decouples models from code.

## 4. Steps

### Step 0. Tools, login, project, APIs

- **Who:** you / console, then you / terminal.
- **Do:** (console) create the project, attach billing, create the $5 budget alert. (terminal)
  ```powershell
  gcloud auth login
  gcloud config set project $PROJECT
  gcloud config set run/region $REGION
  gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com cloudtasks.googleapis.com storage.googleapis.com
  ```
- **Verify:** `gcloud config list`; `gcloud services list --enabled` shows the six.
- **Undo:** `gcloud services disable <api>`; `gcloud auth revoke`.
- **Costs:** nothing; enabling APIs is free.

### Step 1. Neon

- **Who:** you / console. **Do:** create the project; open *Connect*, switch **Pooled connection off**, copy the connection string. Keep it for steps 6 and 7.
- **Verify:** step 6 (migration) is the check. **Undo:** delete the Neon project. **Costs:** free plan.

### Step 2. Upstash

- **Who:** you / console. **Do:** create the database (TLS on). Decide eviction: with it off, a full database (256 MB) makes writes fail; with it on, old keys, including sessions, can be dropped. Copy the Redis (TCP) URL.
- **Verify** (your terminal, URL typed in your shell only):
  ```powershell
  $env:REDIS_URL = Read-Host "REDIS_URL"
  .\.venv\Scripts\python -c "import os, redis; print(redis.from_url(os.environ['REDIS_URL']).ping())"   # True
  Remove-Item Env:REDIS_URL
  ```
- **Undo:** delete the database. **Costs:** free plan.

### Step 3. Cloudflare R2

- **Who:** you / console. **Do:** enable R2; create buckets `mars-models` and `mars-batch-uploads` (private; do **not** enable the public `r2.dev` URL). On `mars-batch-uploads` add a lifecycle rule: delete objects with prefix `batch/` after 1 day (the app also refuses expired objects on read). Create three tokens (R2 > Manage API tokens), each scoped to the bucket(s) named:

  | Token | Permission | Bucket | Used by |
  |---|---|---|---|
  | `mars-publish` | Object Read & Write | `mars-models` | your terminal, step 4 |
  | `mars-models-ro` | Object Read only | `mars-models` | Cloud Run (`MODEL_ARTIFACT_*`) |
  | `mars-runtime` | Object Read & Write | `mars-batch-uploads` | Cloud Run (`S3_*`) |

  Note the account ID (endpoint `https://<account-id>.r2.cloudflarestorage.com`).
- **Verify:** step 4. **Undo:** delete the tokens and buckets (empty a bucket first). **Costs:** free tier.

### Step 4. Publish the models

- **Who:** you / terminal (the write key is yours), run from the repository root.
- **Do:**
  ```powershell
  .\.venv\Scripts\python infra\scripts\publish_model_artifacts.py --dry-run          # hashes only: prints the release id, touches no network
  $env:S3_ENDPOINT_URL = "https://<account-id>.r2.cloudflarestorage.com"; $env:S3_REGION = "auto"
  $env:MODEL_PUBLISH_ACCESS_KEY_ID = Read-Host "write key id"
  $s = Read-Host "write secret" -AsSecureString; $env:MODEL_PUBLISH_SECRET_ACCESS_KEY = [System.Net.NetworkCredential]::new("", $s).Password
  .\.venv\Scripts\python infra\scripts\publish_model_artifacts.py --bucket mars-models
  ```
  The last line printed is `MODEL_ARTIFACT_RELEASE=<64 hex>`. Keep it.
- **Verify:** the script ends with "verified in the bucket". Independently:
  `... publish_model_artifacts.py --bucket mars-models --verify <release>` prints "release intact"; the R2 console shows `models/<release>/manifest.json` and 184 objects under `files/`. On the current tree the dry run printed
  `8342d9816e7e8df3e4c2a2f1e44e13de5c382ccb2408e3a7ec7f7425b3f7d93c` (184 files, 209.3 MB); the same tree gives the same id.
- **Undo:** delete the `models/<release>/` objects in the console. Nothing uses a release until a service names it. Close the terminal (it holds the key in its environment) or `Remove-Item Env:MODEL_PUBLISH_*`.
- **Costs:** free tier.

### Step 5. (Only if the script says a band is missing) rebuild error bands

See section 3, item 3. After it, re-run step 4: the new tree has a new release id.

### Step 6. Database migration

- **Who:** you / terminal. **Do:** from `api\`, with the Neon direct URL in your shell only:
  ```powershell
  cd api
  $env:DATABASE_URL = Read-Host "Neon direct URL"
  ..\.venv\Scripts\alembic heads            # exactly one head
  ..\.venv\Scripts\alembic upgrade head
  ..\.venv\Scripts\alembic current          # prints that head
  Remove-Item Env:DATABASE_URL; cd ..
  ```
- **Verify:** `alembic current` shows the head; the Neon console's table view lists `users`, `batch_jobs`, `saved_molecules`, `saved_reports` and `alembic_version`. The first run also proves the URL rewrite works against real Neon (unobserved until then).
- **Undo:** `alembic downgrade base` (drops the tables), or delete the Neon branch. **Costs:** a few seconds of compute.

### Step 7. Secrets in Secret Manager

- **Who:** you. Names to create (values are yours): `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`*, `BATCH_WORKER_SECRET`*, `KERMT_SERVICE_TOKEN`*, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `MODEL_ARTIFACT_ACCESS_KEY_ID`, `MODEL_ARTIFACT_SECRET_ACCESS_KEY`, later `SENTRY_DSN`. The three starred are random: generate them without ever seeing them.
- **Do (console, simplest):** Secret Manager > Create secret > paste the value (no newline). **Or (terminal)** with this helper, which never echoes a value and writes no newline:
  ```powershell
  function New-MarsSecret([string]$Name, [switch]$Random) {
    if ($Random) { $b = New-Object byte[] 48; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); $v = ($b | ForEach-Object { $_.ToString("x2") }) -join "" }
    else { $v = [System.Net.NetworkCredential]::new("", (Read-Host $Name -AsSecureString)).Password }
    $f = Join-Path $env:TEMP "mars_secret.tmp"; [IO.File]::WriteAllText($f, $v)
    gcloud secrets create $Name --data-file=$f; Remove-Item $f
  }
  New-MarsSecret DATABASE_URL; New-MarsSecret SECRET_KEY -Random   # and so on
  ```
  Then the runtime service account (next) needs `roles/secretmanager.secretAccessor` on each.
- **Verify:** `gcloud secrets list`; `gcloud secrets versions list DATABASE_URL`. (Do not run `versions access`: it prints the value.)
- **Undo:** `gcloud secrets delete <name>`. **Costs:** ~10 versions; the free allowance is ~6 (unverified), the rest cents per month.

### Step 8. Runtime service account

- **Who:** you / terminal. **Do:**
  ```powershell
  gcloud iam service-accounts create mars-runtime --display-name "MARS Cloud Run runtime"
  gcloud projects add-iam-policy-binding $PROJECT --member "serviceAccount:$SA" --role roles/cloudtasks.enqueuer
  foreach ($s in "DATABASE_URL","REDIS_URL","SECRET_KEY","BATCH_WORKER_SECRET","KERMT_SERVICE_TOKEN","S3_ACCESS_KEY_ID","S3_SECRET_ACCESS_KEY","MODEL_ARTIFACT_ACCESS_KEY_ID","MODEL_ARTIFACT_SECRET_ACCESS_KEY") {
    gcloud secrets add-iam-policy-binding $s --member "serviceAccount:$SA" --role roles/secretmanager.secretAccessor
  }
  ```
- **Verify:** `gcloud iam service-accounts list`; `gcloud secrets get-iam-policy DATABASE_URL`. **Undo:** `remove-iam-policy-binding` / `service-accounts delete`. **Costs:** none.

### Step 9. Build and push the image

- **Who:** you / terminal (me for the files, already in `infra/`).
- **Do:**
  ```powershell
  gcloud artifacts repositories create $AR --repository-format docker --location $REGION
  gcloud builds submit --config infra/cloudbuild.api.yaml --substitutions "_IMAGE=$IMAGE,_TAG=$TAG" .
  ```
  The build is the Dockerfile in `api/` (Node builds the bundle, then Python). CI's `build-api-image` job runs the same Dockerfile.
- **Verify:** `gcloud artifacts docker images list "$REGION-docker.pkg.dev/$PROJECT/$AR"` shows `mars-api:$TAG`. The image is 1.11 GB (see section 6).
- **Undo:** `gcloud artifacts docker images delete "$IMAGE`:$TAG"`; `gcloud artifacts repositories delete $AR --location $REGION`.
- **Costs:** Cloud Build 120 min/day free (this build is ~10 min); storage ~$0.10/GB-month past 0.5 GB.

### Step 10. Cloud Tasks queue

- **Who:** you / terminal. **Do:**
  ```powershell
  gcloud tasks queues create mars-batch --location $REGION --max-attempts 5 --min-backoff 10s --max-backoff 300s --max-concurrent-dispatches 2
  ```
  `--max-attempts` must equal `BATCH_TASK_MAX_ATTEMPTS`.
- **Verify:** `gcloud tasks queues describe mars-batch --location $REGION` shows `maxAttempts: 5`. **Undo:** `gcloud tasks queues delete mars-batch --location $REGION`; Cloud Tasks does not let you reuse a deleted queue name for about a week (documented behaviour; unverified for this project). **Costs:** 1M operations/month free.

### Step 11. Deploy the API

- **Who:** you / terminal; I show the exact command first. **Do:**
  ```powershell
  gcloud run deploy $SVC `
    --image "$IMAGE`:$TAG" --region $REGION --service-account $SA `
    --allow-unauthenticated `
    --cpu 2 --memory 2Gi --cpu-boost --min-instances 0 --max-instances 3 --concurrency 8 --timeout 900 `
    --set-env-vars "SESSION_COOKIE_SECURE=true,TRUSTED_PROXY_HOPS=1,REQUIRE_REAL_MODELS=true,MAX_CONCURRENT_PREDICTIONS=2,MODEL_ARTIFACT_BUCKET=mars-models,MODEL_ARTIFACT_RELEASE=<release>,S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com,S3_REGION=auto,BATCH_BLOB_BACKEND=s3,BATCH_QUEUE_BACKEND=cloud_tasks,GCP_PROJECT_ID=$PROJECT,GCP_REGION=$REGION,CLOUD_TASKS_QUEUE=mars-batch,SENTRY_ENVIRONMENT=production,SENTRY_RELEASE=$TAG" `
    --set-secrets "DATABASE_URL=DATABASE_URL:latest,REDIS_URL=REDIS_URL:latest,SECRET_KEY=SECRET_KEY:latest,BATCH_WORKER_SECRET=BATCH_WORKER_SECRET:latest,S3_ACCESS_KEY_ID=S3_ACCESS_KEY_ID:latest,S3_SECRET_ACCESS_KEY=S3_SECRET_ACCESS_KEY:latest,MODEL_ARTIFACT_ACCESS_KEY_ID=MODEL_ARTIFACT_ACCESS_KEY_ID:latest,MODEL_ARTIFACT_SECRET_ACCESS_KEY=MODEL_ARTIFACT_SECRET_ACCESS_KEY:latest"
  ```
  Then, because the service URL exists only now:
  ```powershell
  $URL = gcloud run services describe $SVC --region $REGION --format "value(status.url)"
  gcloud run services update $SVC --region $REGION --update-env-vars "WORKER_BASE_URL=$URL,CORS_ALLOW_ORIGINS=$URL"
  ```
  Sizing is measured, not guessed: the warmed API container held 441 MiB with all 70 models loaded; add the 209 MB
  of artifacts on the memory-backed disk and the featurization cache (below) and 2 GiB leaves headroom; 1 GiB does not.
  `--allow-unauthenticated` makes the site public: see "Decisions that are yours" before running it.
- **Verify:** `gcloud run services describe $SVC --region $REGION` shows the revision `Ready`; logs (`gcloud run services logs read $SVC --region $REGION --limit 50`) show "Fetching model release ..." then "ready in ..."; then the post-deploy checks in section 5.
- **Undo:** `gcloud run services delete $SVC --region $REGION`; to roll back one revision: `gcloud run services update-traffic $SVC --to-revisions <old>=100`. **Costs:** request-based billing; scale to zero.

### Step 12. Post-deploy checks

Section 5.

### Step 13. KERMT service

**Decision (item 2 of the brief): the checkpoints live in a Cloud Storage bucket mounted read-only at `/models`.**

| Route | Image size | Cold-start cost | Memory | Verdict |
|---|---|---|---|---|
| A. Bake into the image | image ~6 GB+ (base ~3 GB + 2.85 GB checkpoints) | image pull grows | none extra | Rejected: Cloud Build and CI cannot see `ml/artifacts_kermt` (gitignored, 5.7 GB), so the image would be built and pushed from your machine; every checkpoint change is a rebuild. |
| B. Fetch to disk at start (like the XGBoost route) | image ~3 GB | download 2.85 GB before listening | **+2.85 GB**, because the disk is memory | Rejected: the extra RAM would push the service to 8 GiB+ for no gain. |
| **C. Cloud Storage volume mount** | image ~3 GB | files read on demand through FUSE | only what torch loads (~0.8 GB + 0.19 GB per checkpoint); FUSE cache also counts against memory | **Chosen.** No copy step, checkpoints versioned apart from code, `engine.py` already verifies each checkpoint's SHA-256 against its `metadata.json` at load (`verify_hash=True`), 2.85 GB sits inside the 5 GB Cloud Storage free allowance (unverified for this account). |

Costs and limits of route C: Cloud Run documents that a volume mount which fails or takes more than 30 s makes the
service fail to start, that FUSE caches count against memory, and that reads are limited by network bandwidth.
Load time is the dominant cost either way: ~10-12 s per checkpoint measured locally, so **15 checkpoints = 150-180 s
plus read time, unmeasured on Cloud Run**. Use a startup probe on `/health` (503 until all are loaded); Cloud Run
allows `failureThreshold x periodSeconds` up to 600 s. While it loads, the API serves KERMT-routed endpoints from
XGBoost with the dagger and does not cache those responses (by design, ADR-033).

**Scale-to-zero or one warm instance.** Rates below are request-based billing, Tier 1, from Google's pricing table
as relayed by a search summary (the pricing page itself did not load): $0.000024 per vCPU-second, $0.0000025 per
GiB-second, idle minimum instance $0.0000025 per vCPU-second and GiB-second. Confirm in the pricing calculator.
At 4 vCPU / 8 GiB:

- *Scale to zero (recommended).* A cold start is ~200-300 s of 4 vCPU/8 GiB ~ 1,000 vCPU-s: about 180 cold starts fit the 180,000 vCPU-s free tier. After 15 idle minutes the next KERMT-routed request meets a cold service, the API times out at 30 s, answers from XGBoost (dagger visible), and the instance finishes loading in the background (**whether a client timeout still lets the instance finish starting is not verified: check C-9**).
- *One warm instance (`--min-instances 1`).* Idle charge ~ (4+8) x 2,592,000 s x $0.0000025 ~ **$78/month**, before any request time. Not free; the blueprint's "$0 serving" no longer holds.
- *Serving cost.* A KERMT-routed molecule costs ~4.5 s of 4 vCPU (measured locally with 15 checkpoints): ~18 vCPU-s. The free tier is therefore ~10,000 uncached single-molecule predictions per month; beyond it ~$0.0005 each. **Batch calls the service one molecule at a time**, so a 1,000-row batch is ~75 minutes and ~$0.5 past the free tier, and a 50,000-row batch is ~62 hours and ~$26. **If KERMT is on, lower `BATCH_SIZE_CAP`** (for example 2,000) or accept those numbers. The threshold change to 20 is in the brief; the cap is the matching decision.

- **Who:** you / terminal (me for `infra/cloudbuild.kermt.yaml`).
- **Do:**
  ```powershell
  # 1. checkpoints: the 5 routed arms x seeds 0,1,2 only (about 2.85 GB of the 5.7 GB on disk)
  $KBUCKET = "$PROJECT-mars-kermt-models"
  gcloud storage buckets create "gs://$KBUCKET" --location $REGION --uniform-bucket-level-access
  foreach ($arm in "toxicity__cls","metabolism__cls","metabolism__reg","absorption_distribution__cls","absorption_distribution__reg") {
    foreach ($seed in 0,1,2) { gcloud storage cp -r "ml\artifacts_kermt\$arm\seed_$seed" "gs://$KBUCKET/$arm/" }
  }
  # 2. image
  gcloud builds submit --config infra/cloudbuild.kermt.yaml --substitutions "_IMAGE=$KIMAGE,_TAG=$TAG" .
  # 3. service account access to the bucket (reuse mars-runtime or create mars-kermt-sa)
  gcloud storage buckets add-iam-policy-binding "gs://$KBUCKET" --member "serviceAccount:$SA" --role roles/storage.objectViewer
  # 4. deploy
  gcloud run deploy $KSVC --image "$KIMAGE`:$TAG" --region $REGION --service-account $SA --allow-unauthenticated `
    --port 8100 --cpu 4 --memory 8Gi --cpu-boost --min-instances 0 --max-instances 1 --concurrency 8 --timeout 120 `
    --add-volume "name=models,type=cloud-storage,bucket=$KBUCKET,readonly=true" --add-volume-mount "volume=models,mount-path=/models" `
    --set-env-vars "KERMT_ARMS=toxicity__cls,metabolism__cls,metabolism__reg,absorption_distribution__cls,absorption_distribution__reg,KERMT_SEEDS=0,1,2,KERMT_THREADS=4" `
    --set-secrets "KERMT_TOKEN=KERMT_SERVICE_TOKEN:latest" `
    --startup-probe "httpGet.path=/health,httpGet.port=8100,periodSeconds=10,timeoutSeconds=5,failureThreshold=60"
  # 5. point the API at it
  $KURL = gcloud run services describe $KSVC --region $REGION --format "value(status.url)"
  gcloud run services update $SVC --region $REGION --update-env-vars "KERMT_SERVICE_URL=$KURL,BATCH_INTERACTIVE_THRESHOLD=20" --update-secrets "KERMT_SERVICE_TOKEN=KERMT_SERVICE_TOKEN:latest"
  ```
  The `--startup-probe` and `--add-volume` flag syntax is taken from Google's docs (volume flags confirmed 2026-10-23; the probe flag form is **unconfirmed**): check `gcloud run deploy --help` before running. `--max-instances 1` is deliberate: a second instance is another 3-minute cold start, and the engine answers one request at a time anyway. The `mars-kermt` URL is public and guarded by the token alone; `/health` is open and reports load progress.
- **Verify:** `curl.exe -s "$KURL/health"` returns `{"ready":true,"loaded":15,"expected":15,...}` (503 with progress while loading); a prediction through the API (check C-2) shows `model_id` starting `mars-kermt` for the routed endpoints and `model_version` ending `+kermt.<digest>`; the frontend shows `KERMT` with no dagger (ADR-033). The API refuses to start if a KERMT-routed regression endpoint's `kermt_error_band.json` is not in the model release.
- **Undo:** `gcloud run services update $SVC --region $REGION --remove-env-vars KERMT_SERVICE_URL,BATCH_INTERACTIVE_THRESHOLD` (back to XGBoost only); `gcloud run services delete $KSVC --region $REGION`; delete the bucket. **Costs:** above.

### Step 14. Sentry and UptimeRobot

- **Who:** you / console, then terminal for the secret. **Do:** follow `documentation/MONITORING.md`: create the Sentry project, store its DSN as secret `SENTRY_DSN`, grant the runtime account access, then
  `gcloud run services update $SVC --region $REGION --update-secrets "SENTRY_DSN=SENTRY_DSN:latest"`; create the Sentry alert (email on a new issue in `production`); create the two UptimeRobot monitors on `/api/health` (keyword `"status":"ok"`) and `/`, and make sure its timeout and "alert after N failures" tolerate a cold start (a cold API start is now ~20-60 s, not the blueprint's 1-3 s).
- **Verify:** Sentry's "waiting for first event" becomes an event (check C-11); both monitors show Up. (The app's "Sentry error reporting is on" line is logged on a logger that uvicorn does not print, so it will not appear in Cloud Run logs.)
- **Undo:** `--remove-secrets SENTRY_DSN`; pause the monitors. **Costs:** free plans.

### Step 15. D14: Turnstile (only after the public deploy is approved)

Honeypot field and a registration rate limit first, then the widget with the site key served from `/api/limits`,
then set `CLOUDFLARE_TURNSTILE_SECRET_KEY` (secret). Until then registration is open to anyone who finds the URL
(the secret must stay unset, or the placeholder token the client sends fails verification and **nobody** can register).
Confirm Turnstile accepts a `run.app` hostname when you add the widget.

## 5. Post-deploy checks (documented before, never observed until you run them)

Set `$URL` to the service URL. Every check says what a pass looks like and what a fail means. Record the actual
output in `documentation/status/` (or the checklist note) when you run it.

**PowerShell quoting.** Windows PowerShell 5.1 drops the double quotes inside a string passed to a native program,
so every JSON body below is piped in (`... | curl.exe ... --data-binary "@-"`) instead of passed with `-d`. Use
`curl.exe`, not `curl` (an alias for `Invoke-WebRequest`).

**C-1. The site and the API answer.** `curl.exe -s "$URL/api/health"` is `{"status":"ok"}`. Open `$URL/` in a browser: the app loads. Open `$URL/batch` directly: the app loads (client-route fallback), not a 404. `curl.exe -s "$URL/api/limits"` reports the cap, threshold (100, or 20 with KERMT) and 24 h.

**C-2. Real models, not the stub.**
```powershell
'{"smiles":"CC(=O)OC1=CC=CC=C1C(=O)O"}' | curl.exe -s -X POST "$URL/api/predict" -H "Content-Type: application/json" --data-binary "@-"
```
Pass: 15 rows (14 + synthetic accessibility); no `model_id` equals `stub-v0`; `model_version` is `MODEL_VERSION`
(plus `+kermt.<digest>` with KERMT). Logs show the release fetch. **Also prove it fails loudly:**
```powershell
gcloud run deploy $SVC --region $REGION --image "$IMAGE`:$TAG" --no-traffic --tag canary --update-env-vars "MODEL_ARTIFACT_RELEASE=$('0'*64)"
```
Pass: the deploy reports the revision failed to become ready, the log names "cannot read release 000000000000", and `$URL` still answers from the old revision. Undo: nothing to undo (the failed revision takes no traffic); delete it with `gcloud run revisions delete`.

**C-3. Regression rows carry a band.** In the C-2 response the five regression endpoints (`solubility_logs`, `lipophilicity_logp`, `caco2_permeability`, `ppb_binding`, `clearance_microsomal`) have non-null `heldout_error_halfwidth`. A null means the release lacked `error_band.json` (the roster check should have refused to start, so a null here is a bug worth reporting).

**C-4. The client address the rate limiter sees (C2, ADR-025 item 5).** Send requests whose `X-Forwarded-For` you forge, and look at which Redis key they land on:
```powershell
1..3 | ForEach-Object { '{"smiles":"CCO"}' | curl.exe -s -o NUL -w "%{http_code}`n" -X POST "$URL/api/predict" -H "Content-Type: application/json" -H "X-Forwarded-For: 9.9.9.$_" --data-binary "@-" }
curl.exe -s https://api.ipify.org     # your public address
```
In the Upstash console (Data Browser), look for keys `ratelimit:predict:*`. Pass: one key named with **your public address** and a count of 3, none containing `9.9.9.x`. Fail A: keys `ratelimit:predict:9.9.9.1:...` (the hop count is wrong, forged values are read: set `TRUSTED_PROXY_HOPS` lower or raise it). Fail B: a Google-looking address shared by everyone (the header carries more or fewer entries than assumed). Then the behaviour: 65 requests inside a minute with different forged values must return `200` x60 then `429`:
```powershell
1..65 | ForEach-Object { '{"smiles":"CCO"}' | curl.exe -s -o NUL -w "%{http_code} " -X POST "$URL/api/predict" -H "Content-Type: application/json" -H "X-Forwarded-For: 8.8.8.$_" --data-binary "@-" }
```

**C-5. The `Secure` cookie.** Register and sign in with a throwaway address (your terminal prompts for the password; the client sends `turnstile_token` as a placeholder while the secret is unset):
```powershell
$pw = Read-Host "password (8+ chars)"
"{`"email`":`"deploycheck@example.com`",`"password`":`"$pw`",`"turnstile_token`":`"x`"}" | curl.exe -s -X POST "$URL/api/auth/register" -H "Content-Type: application/json" --data-binary "@-"
"{`"email`":`"deploycheck@example.com`",`"password`":`"$pw`"}" | curl.exe -s -i -c cookies.txt -X POST "$URL/api/auth/login" -H "Content-Type: application/json" --data-binary "@-" | Select-String -Pattern "set-cookie"
```
Pass: the header reads `mars_session=...; HttpOnly; Max-Age=604800; Path=/; SameSite=lax; Secure`. Then `curl.exe -s -b cookies.txt "$URL/api/auth/me"` returns the user. Delete the account afterwards (`DELETE /api/account`, or the Settings pane). `cookies.txt` is a session token: delete it.

**C-6. The worker endpoint refuses strangers.** Without the secret, and with a wrong one, `POST $URL/api/internal/batch/run` must answer **403** (404 if `BATCH_QUEUE_BACKEND` is not `cloud_tasks`; 503 if the secret is unset):
```powershell
$body = '{"job_id":"00000000-0000-0000-0000-000000000000","index":0}'
$body | curl.exe -s -o NUL -w "%{http_code}`n" -X POST "$URL/api/internal/batch/run" -H "Content-Type: application/json" --data-binary "@-"
$body | curl.exe -s -o NUL -w "%{http_code}`n" -X POST "$URL/api/internal/batch/run" -H "Content-Type: application/json" -H "X-MARS-Worker-Secret: wrong" --data-binary "@-"
```

**C-7. A queued batch end to end (the Cloud Tasks call).** Make 300 distinct molecules, upload as the signed-in user, watch progress, fetch results:
```powershell
.\.venv\Scripts\python infra\scripts\make_check_batch.py 300 check_batch_300.csv
curl.exe -s -b cookies.txt -F "file=@check_batch_300.csv" "$URL/api/batch/predict?smiles_column=smiles"     # status "queued"; note job_id
curl.exe -s -N -b cookies.txt "$URL/api/batch/progress/<job_id>"                                              # completed: 0 -> 250 -> 300, then status done
curl.exe -s -b cookies.txt "$URL/api/batch/results/<job_id>"                                                  # 300 rows
```
(A 300-row file is above the interactive threshold of 100 or 20, so it is queued.) Pass, all of: progress advances slice by slice (250 then 50); results hold 300 rows; Cloud Run request logs show `POST /api/internal/batch/run` with status 200 and a `Google-Cloud-Tasks` user agent (`gcloud run services logs read $SVC --region $REGION --limit 100`); `gcloud tasks queues describe mars-batch --location $REGION` shows no stuck tasks; R2 holds `batch/<job_id>/results.json`. For the retry behaviour, repeat with 1,500 rows and, while it runs, change any env var (`gcloud run services update $SVC --region $REGION --update-env-vars X=1`) so a revision swaps mid-job: the job must still finish, and a non-2xx followed by a retry (header `X-CloudTasks-TaskRetryCount` above 0) may appear in the logs. **Not guaranteed to trigger**; if no slice was in flight it proves nothing, say so.

**C-8. Retention.** The next day, `GET /api/batch/results/<job_id>` no longer returns the result and the R2 object is gone.

**C-9. Cold start, measured.** After 20 minutes with no traffic (stop the UptimeRobot monitors first, or they keep it warm):
```powershell
curl.exe -s -o NUL -w "API cold: %{time_total}s`n" "$URL/api/health"
curl.exe -s -o NUL -w "KERMT cold: %{time_total}s`n" "$KURL/health"
```
Expect the API in tens of seconds (download + start), KERMT in minutes, and check whether a request that the client abandons still lets the KERMT instance finish loading (look at its logs for "KERMT engine ready"). Record both numbers; they replace the blueprint's 1-3 s.

**C-10. Memory.** Cloud Run console > `mars-api` > Metrics > Memory utilisation after C-7: it should stay well under 100 %. The cache writes ~4.4 KB per new molecule to the memory-backed disk; a 50,000-molecule batch is ~220 MB of data (more with filesystem overhead).

**C-11. Sentry receives an event.** The app has no crash route and none should be added. Verify the project and DSN from your terminal with a one-off event (the DSN typed into your shell only):
```powershell
$env:SENTRY_DSN = Read-Host "DSN"; .\.venv\Scripts\python -c "import os, sentry_sdk; sentry_sdk.init(os.environ['SENTRY_DSN']); sentry_sdk.capture_message('mars deploy check'); sentry_sdk.flush()"; Remove-Item Env:SENTRY_DSN
```
That proves the DSN and the project, **not** the app's own capture and scrubbing on the deployed service (`tests/test_observability.py` covers the wire payload locally). The first real exception is the first observation of that path.

**C-12. UptimeRobot.** Both monitors Up for 24 hours; after a week compare Cloud Run's billing page with the expectation that pings are billed as milliseconds of request time (unverified).

## 6. Image size and build (measured 2026-10-23, Windows, Docker Desktop)

- The full `api/Dockerfile` **built to completion locally** (the pip layer that failed once on a slow link took
  ~10 minutes and finished; total ~13 minutes). CI's `build-api-image` runs the same Dockerfile.
- **Image size.** As the Dockerfile stood, the image was 2.3 GB: the `xgboost` wheel on Linux x86_64 depends on
  `nvidia-nccl-cu12` (~350 MB download), which this CPU-only service never uses. `ml/requirements-serving.txt` now
  asks for `xgboost-cpu` (same `xgboost` module, same version 3.2.0, no NVIDIA wheel): the image is **1.11 GB**.
  Predictions were compared between the two images on 31 molecules x 15 endpoints (3,255 values: value, interval,
  domain flag, kNN distance, error band, model id): **0 differ**. This is a change to a served dependency; it is
  on this branch, not in `main`.
- The trained models are not in the image (section 3). Run from an empty `ml/artifacts`, the built image fetched
  the release from a local MinIO and answered with real models and all five regression bands; with a wrong release
  id it exited with code 3 and "cannot read release 000000000000". Neither was run on Cloud Run or against R2.

## 7. Decisions that are yours

1. **Public or private first.** `--allow-unauthenticated` exposes the site, and registration has no bot gate until D14. Safer: deploy with `--no-allow-unauthenticated` and use `gcloud run services proxy` / an IAM-restricted invoker until D14 is done.
2. **KERMT cost model** (step 13): scale to zero (recommended) versus ~$78/month warm, and the `BATCH_SIZE_CAP` to set with it.
3. **Upstash eviction** (step 2).
4. **Custom domain**: not required.
5. **Pin `rdkit`.** `ml/requirements-serving.txt` says `rdkit>=2026.3.1`; the image resolves 2026.9.1 while the models were trained under 2026.3.5. A 31-molecule check on 2026-10-23 found the 217 descriptors identical to 6e-14 and Morgan bits identical, so nothing is wrong today, but it floats with every rebuild (the KERMT image pins for exactly this reason).

## 8. Teardown (everything created above, in reverse)

`gcloud run services delete` for both services; `gcloud tasks queues delete mars-batch`; `gcloud artifacts repositories delete`; delete the Cloud Storage bucket; `gcloud secrets delete` each secret; `gcloud iam service-accounts delete`; delete the Neon project, Upstash database, R2 buckets and tokens, Sentry project, UptimeRobot monitors. Or delete the GCP project, which removes everything in it at once.

## 9. Ticking the checklist

Tick only what you saw on the deployed service, and write what was not seen next to it.

- **C6** (approve the deploy and supply credentials): yours to tick.
- **C7** (Cloud Run, Neon, Upstash, R2): after C-1, C-2, C-3 and the migration. Say whether the error bands came with the release.
- **C8** (Cloud Tasks worker; already ticked for the code): add the observed result of C-6, C-7 (and C-8 the next day). Note if the retry test did not trigger.
- **C9** (Sentry and UptimeRobot): after step 14 and C-11/C-12, naming whether the app's own capture was observed.
- **C2** (client address): add C-4's observation.
- **D14**: only after step 15.
