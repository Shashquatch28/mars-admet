# MARS — Molecular ADMET Rapid Screening

Drug safety/viability screening platform predicting 14 clinically relevant ADMET
endpoints from molecular structure. `documentation/mars-blueprint_v4.md` is the
full locked design spec and the source of truth — this repo is the execution of
that blueprint, not a restatement of it.

**Where the project actually stands is `documentation/AIMS/next_steps.md`**
(live work breakdown) and `documentation/AIMS/module_milestone_map.md`
(authoritative Module ↔ Milestone matrix). Per-milestone verification matrices
are in `documentation/status/`.

Build is **solo, sequenced by dependency order** (blueprint Module 14, revised
from an earlier 3-person A/B/C split — that framing is retired; treat `ml/`,
`api/`, `frontend/` as module groupings, not people).

## Status (2026-09-20)

| Milestone | Scope | State |
|---|---|---|
| M0 | Contracts & scaffolding | ✅ complete |
| M1 | Data (Module 1) + featurization (Module 3) | ✅ complete — 14 datasets acquired, standardized, split, cached |
| M2 | Modeling (Module 4) + calibration/AD (Module 5) | 🟡 **current** — XGBoost baseline sweep complete (70/70 runs, all 14 endpoints, validation-fold metrics); KERMT integrated and GPU-validated at smoke-test scale; **no production GNN training run yet** |
| M3 | Serving (Module 8) + auth/DB (Module 13) + infra (Module 10) | 🟢 locally/container complete — real inference for all 14 endpoints; cloud deploy not started (needs GCP credentials) |
| M4 | Frontend, 3D, explainability | ⬜ not started |
| M5 | Full eval matrix (Module 11), polish, launch | ⬜ not started |

## Repo layout

```
contracts/    Shared Pydantic contracts — source of truth for field names used
              by ml/, api/, and frontend/. See contracts/API_ROUTES.md.
ml/           Modules 1/3/4/5/11 — data, featurization, models, training, eval.
api/          Module 8 + 13 — FastAPI serving, auth, persistence, batch queue.
frontend/     Modules 9/7/12 UI — React + Vite. NOT runnable yet (M4).
infra/        Module 10 — deployment/config.
documentation/  Blueprint, AIMS memory, status matrices, technical reference.
docker-compose.yml   Local dev stack: Postgres, Redis, MinIO (R2 stand-in), API.
.env.example  All required env vars, pre-named.
.github/workflows/ci.yml   Lint + tests (with real Postgres/Redis) + image build
              + /predict smoke test.
```

## Environments — three, deliberately not merged

1. **root `.venv/`** — API + tooling only (fastapi, pydantic, ruff, pytest,
   mars-contracts). No ML stack. Runs the API and `pytest contracts/tests api/tests`.
2. **`ml/.venv/`** — the ML working env: numpy, pandas, scikit-learn, rdkit,
   xgboost, wandb, scipy. No torch.
3. **KERMT's own docker container** (`kermt:latest`) — the GNN backbone. `ml/.venv`
   is never given torch or `cuik_molmaker`; see `documentation/AIMS/decisions.md`.
   A separate WSL/Linux venv holds `PyTDC` for acquisition only.

## Setup

```bash
cp .env.example .env
pip install -e ./contracts        # install first — ml/ and api/ both depend on it
docker compose up -d postgres redis minio
```

Run the API with **real** inference (the container has the ml serving stack baked in):

```bash
docker compose up -d api
```

```bash
curl -X POST http://localhost:8000/predict -H "Content-Type: application/json" -d "{\"smiles\": \"CCO\"}"
```

Returns real predictions for all 14 endpoints — each carries a `model_id`, so a
stub response (`"stub-v0"`) is always distinguishable from a trained one.

A **native** uvicorn (root `.venv`, stub-only, no ml stack) must use port 8080 —
port 8000 is reserved by Hyper-V/Docker on the dev machine:

```bash
.venv/Scripts/uvicorn.exe app.main:app --app-dir api --port 8080
```

## Tests and lint

```bash
.venv/Scripts/python.exe -m pytest contracts/tests api/tests -q
```

```bash
cd ml && PYTHONPATH=. ./.venv/Scripts/python.exe -m pytest -q
```

```bash
.venv/Scripts/python.exe -m ruff check contracts api ml
```

> `frontend/` is **not runnable** — `package.json` exists but the Vite entry
> (`index.html`, `src/main.tsx`, `vite.config.ts`) is M4 work.

## Key locked decisions (blueprint has the full reasoning)

- 14 endpoints, TDC-sourced, all CC BY 4.0 (PharmaBench dropped — NC-ND conflict)
- Scaffold split (80/20, 5-seed CV) matching TDC's official benchmark protocol;
  hERG and PPB are documented exceptions with self-generated splits, reported as
  not leaderboard-comparable
- Multi-task clusters: Absorption/Distribution, Metabolism (+Clearance), Toxicity,
  DILI standalone
- k-NN applicability domain (5-NN Tanimoto/ECFP4) is core MVP, not deferred
- Checkpointing + RNG-state restoration is mandatory
- `/predict` is fast/cheap; 3D conformers + explainability are lazy/on-demand
- 48h Redis cache TTL, 24h batch upload retention, opt-in-only retraining use
- Server-side Redis sessions, not JWT
- **No paid compute anywhere**, even as a fallback — $0 budget
