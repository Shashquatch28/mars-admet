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

## Quick start

Three separate Python environments are used on purpose; do not merge them.

| Environment | For |
|---|---|
| root `.venv` | `contracts/` and `api/` tests |
| `ml/.venv` | all `ml/` work (rdkit, xgboost, wandb) |
| isolated acquisition env | PyTDC only (`ml/data/acquisition/README.md`) |

```bash
# 1. Environment file
cp .env.example .env

# 2. Contracts first; ml/, api/ and the drift test import them
pip install -e ./contracts

# 3. Local infra and the API (http://localhost:8000/docs)
docker compose up -d --build

# 4. Frontend (http://localhost:5173)
cd frontend
npm install
cp .env.example .env.local     # then set VITE_API_BASE=/api
npm run dev
```

The API image installs the inference subset of `ml/` and mounts
`ml/artifacts/` as a volume. **`ml/artifacts/` is git-ignored.** Without
promoted artifacts the API serves the deterministic stub for every endpoint
(`model_id: "stub-v0"`), which the UI marks with a diagonal hatch.

Smoke check:

```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"smiles": "CCO", "endpoints": null}'
```

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
  batch-upload retention; retraining use is opt-in only.
- No paid compute. Serving target is Google Cloud Run.
