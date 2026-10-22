# MARS — Molecular ADMET Rapid Screening

A desktop scientific workstation that predicts ADMET endpoints for drug
molecules from a SMILES string: **14 ML endpoints** across five ADMET
categories, plus a rule-based synthetic-accessibility score shown in its own
group. Every value is served with an applicability-domain check and a note of
which model produced it.

`documentation/mars-blueprint_v4.md` is the locked design spec and the source
of truth; this repository is its execution, not a restatement of it.

## Where the project stands

| Area | State |
|---|---|
| Contracts (`contracts/`) | Done. Pydantic models, route table, frontend drift test. |
| Data and featurization (`ml/data`, `ml/featurize`) | Done. Locked acquisition, scaffold split, leakage audits, feature cache. |
| Modelling (`ml/models`, `ml/train`, `ml/eval`) | XGBoost baseline done: 14 endpoints x 5 seeds promoted to `ml/artifacts/`. KERMT (GNN) training lives on `milestone/m2-kermt`; the product ships on its Tier 0 (`documentation/FUTURE_SCOPE.md`). |
| Serving (`api/`, `ml/serve/`) | Done locally. `/predict`, `/compare`, `/batch/*`, `/molecule/{id}/3d`, auth and persistence. Cloud deploy has not happened. |
| Frontend (`frontend/`) | In progress (M4). Predict is live against the API; Batch is on a fixture; Compare and Library are placeholders. |

Current frontend state and next steps: `documentation/frontend/HANDOFF.md`.
Project memory, decisions and the ML track log: `documentation/AIMS/`.

## Repository layout

```
contracts/    Shared Pydantic contracts and the route table (API_ROUTES.md).
              Source of truth for field names used by ml/, api/ and frontend/.
ml/           Data, featurization, models, training, evaluation, serving
              registry. Run as scripts, not installed. See ml/README.md.
api/          FastAPI service: prediction, batch, auth, persistence.
              See api/README.md.
frontend/     Vite + React + TypeScript SPA. See frontend/README.md.
infra/        Reserved for deployment config (Module 10); empty today.
documentation/
  mars-blueprint_v4.md   the locked spec
  frontend/              design system, ADRs, handoff
  AIMS/                  project memory, decision log, lab runbooks
  status/                point-in-time status notes
  FUTURE_SCOPE.md        deliberately deferred work
docker-compose.yml       Local stack: Postgres, Redis, MinIO (R2 stand-in), API.
.env.example             Every backend environment variable, with defaults.
.github/workflows/ci.yml Lint, test, API image build, /predict smoke test.
AGENTS.md                Non-negotiable rules for any coding agent.
```

## Running MARS

The app is two parts: the **API stack** (Docker: Postgres, Redis, MinIO and the
FastAPI service on port 8000) and the **frontend** (Vite dev server on port
5173). Commands below are PowerShell, run from the repo root unless a `cd` says
otherwise.

### Prerequisites

- **Docker Desktop**, running. Its daemon is not started by default: open it and
  wait 30-60 s until `docker ps` works. An immediate "pipe not found" error just
  means it is still starting.
- **Node 20+** and npm (the frontend).
- **Python 3.11** with the root `.venv` (only for the database migration and the
  tests; the API itself runs inside Docker).
- **`ml/artifacts/`** with the promoted models. It is git-ignored, so it exists
  only on a machine that trained or copied it. Without it the API still runs, but
  every value is a stub (`model_id: "stub-v0"`, drawn with the diagonal hatch).

### First time only

```powershell
# Environment file (the defaults work for local development)
Copy-Item .env.example .env

# Root venv: contracts + API dependencies (provides Alembic and pytest)
python -m venv .venv
.venv\Scripts\pip install -e ./contracts -r api/requirements.txt

# Frontend dependencies and env file
cd frontend
npm ci
Copy-Item .env.example .env.local
```

Then open `frontend/.env.local` and **uncomment `VITE_API_BASE=/api`**. Without
it the UI has no API: it says so, shows no values, and Run, Save and Batch
upload are off.

### Every time you run it

**1. Check what is already running.** Other sessions may share this machine.

```powershell
docker ps
Get-NetTCPConnection -State Listen -LocalPort 5173,8000
```

**2. Start the API stack.** Docker Desktop must be up first.

```powershell
docker compose up -d --build
docker compose ps
```

Wait until `postgres`, `redis`, `minio` and `api` all show `healthy` (the API
needs a few seconds after the others). Add `--build` only when `api/` or
`frontend/` changed; otherwise plain `docker compose up -d` is faster.

**3. Create or update the database tables.** Compose does not run migrations. It
is safe to repeat and is a no-op when the schema is current. Skip it only if you
never sign in, save or use Batch.

```powershell
cd api
..\.venv\Scripts\alembic upgrade head
cd ..
```

**4. Start the frontend.**

```powershell
cd frontend
npm run dev
```

**5. Open http://localhost:5173.** The first prediction after the API starts takes
about 15 s because it loads the models; later ones take about a second.

Verify the stack from another terminal:

```powershell
curl.exe http://localhost:8000/api/health
curl.exe -X POST http://localhost:8000/api/predict -H "Content-Type: application/json" -d '{\"smiles\": \"CCO\", \"endpoints\": null}'
```

API docs are at http://localhost:8000/api/docs. The Docker image also serves the
built UI, so http://localhost:8000 works without the Vite server (it reflects the
last `docker compose up -d --build`, not live edits).

KERMT (GNN) serving is optional and off by default: the stack above serves every
endpoint from XGBoost. To enable it, see `ml/serve/kermt_service/README.md` and the
KERMT block in `.env.example` (`docker compose --profile kermt up -d kermt`).

### Stopping

Press `Ctrl+C` in the frontend terminal, then:

```powershell
docker compose down      # keeps your data
```

Never add `-v` unless you want the Postgres and MinIO volumes deleted: that
erases accounts, saved molecules and reports.

### If something is off

| Symptom | Cause and fix |
|---|---|
| `docker compose` fails with "pipe ... not found" | Docker Desktop is not running yet. Start it and wait. |
| Sign-up, Save or Library says "relation does not exist" | Step 3 was skipped. Run the Alembic upgrade. |
| Every value has the diagonal hatch | `ml/artifacts/` is missing or empty, so the API is serving the stub. |
| UI says it has no API, Run disabled | `VITE_API_BASE=/api` is not set in `frontend/.env.local`. Restart `npm run dev` after editing it. |
| UI results disagree with `curl localhost:8000` | The Vite proxy is aimed at a different API. POST the same SMILES to `:8000/api/predict` and `:5173/api/predict` and compare `model_version` and `served_at`. |
| Port 8000 refused (`WinError 10013`) for a native uvicorn | Hyper-V/Docker reserves ranges on this machine. Use 8080 for a native uvicorn; the Docker API on 8000 is fine. |
| Port 5173 or 8000 already in use | Another session owns it. Use your own ports; see `AGENTS.md`, "Shared dev environment". |

### Python environments

Three separate Python environments are used on purpose; do not merge them.

| Environment | For |
|---|---|
| root `.venv` | `contracts/` and `api/` tests, Alembic |
| `ml/.venv` | all `ml/` work (rdkit, xgboost, wandb) |
| isolated acquisition env | PyTDC only (`ml/data/acquisition/README.md`) |

## Tests

```bash
# contracts + API (root .venv). DB/Redis-backed tests skip when the stack is down.
pytest contracts/tests api/tests -q

# ml (ml/.venv; the full suite takes several minutes)
ml/.venv/Scripts/python -m pytest ml/tests -q

# lint (CI runs the same command)
ruff check contracts api ml

# frontend
cd frontend && npm test && npm run lint && npx tsc --noEmit
```

A native uvicorn from the root `.venv` (stub only, no ml stack) must use port
8080: port 8000 is reserved by Hyper-V/Docker on the dev machine.

CI (`.github/workflows/ci.yml`) runs ruff, the contract and API tests against
real Postgres and Redis service containers, a `/predict` smoke test, and a
Docker build of the API image. It does not deploy.

## Working agreements

- Several sessions may share one checkout, one Docker daemon and the same
  untracked config. Read `AGENTS.md` ("Shared dev environment") before starting
  a server or a container.
- The UI must never imply a capability the model does not have: no value is
  coloured, ranked or called good or safe by its magnitude. The full list of
  rules is in `AGENTS.md`.

## Key locked decisions

Full reasoning is in the blueprint; the log of changes is in
`documentation/AIMS/decisions.md`.

- 14 TDC-sourced endpoints, all CC BY 4.0 (PharmaBench dropped: NC-ND conflict).
- Scaffold split (80/20, 5-seed CV), matching TDC's benchmark protocol.
- k-NN applicability domain (5-NN Tanimoto on ECFP4) is core, not deferred.
- `/predict` is fast and cheap; 3D conformers and explainability are lazy.
- 48 h Redis cache keyed on SMILES, endpoint set and `MODEL_VERSION`; 24 h
  batch-upload retention; submitted molecules are never used for training.
- No paid compute. Serving target is Google Cloud Run.
