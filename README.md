# MARS — Molecular ADMET Rapid Screening

Drug safety/viability screening platform predicting 14 clinically relevant ADMET
endpoints from molecular structure. `documentation/mars-blueprint_v4.md` is the
full locked design spec and the source of truth — this repo is the execution of
that blueprint, not a restatement of it. Current implementation status and the
verification matrix live in `documentation/mars-status_M0.md`.

Build is **solo, sequenced by dependency order** (blueprint Module 14, revised
from the earlier 3-person A/B/C split). The `ml/` / `api/` / `frontend/` READMEs
still say "Person A/B/C" in places — that framing is retired; treat them as
module groupings, not people.

## Repo layout

```
contracts/    Shared Pydantic contracts (Phase 0) — source of truth for
              field names used by ml/, api/, and frontend/. See API_ROUTES.md.
ml/           Modules 1/3/4/5/6/11 — data, featurization, models, training, eval.
api/          Module 8 — FastAPI serving, routing table, batch queue.
frontend/     Modules 9/7/12/13 UI — React.
infra/        Module 10 — deployment/config.
docker-compose.yml   Local dev stack: Postgres, Redis, MinIO (R2 stand-in), API.
.env.example  All required env vars, pre-named.
.github/workflows/ci.yml   Lint + test + API image build + /predict smoke test.
```

## Day 1 setup

```bash
# 1. Environment
cp .env.example .env

# 2. Contracts (install first — both ml/ and api/ depend on this)
pip install -e ./contracts

# 3. Bring up local infra
docker compose up -d postgres redis minio

# 4. API (stub predictor wired in — /predict returns contract-shaped fake
#    data until Person A's trained models land)
cd api && pip install -r requirements.txt
uvicorn app.main:app --reload
# -> http://localhost:8000/docs

# 5. ML deps (heavy — torch/rdkit/PyTDC; GNN training needs a CUDA box)
cd ml && pip install -r requirements.txt
python data/acquire.py   # STUB today — see documentation/mars-status_M0.md (M1)
```

> Frontend (`frontend/`) is **not runnable yet** — `package.json` exists but the
> Vite entry (`index.html`, `src/main.tsx`, `vite.config.ts`, `tsconfig.json`)
> is M4 work. `npm install` works; `npm run dev` does not.

## Verify it's working

```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"smiles": "CCO", "endpoints": null}'
```

Should return 14 endpoint predictions (fake values from the stub predictor, but
contract-shaped — this is what B and C build against until A's real models land).

## Build order (Module 14, solo)

Dependency chain, not a team split:
`contracts → data/featurize/models/AD → API+auth → frontend+3D → infra deploy →
eval/explainability/novelty`. Milestones M0–M5 target Sep 30, 2026. See
`documentation/mars-status_M0.md` for where each module actually stands.

## Key locked decisions (see blueprint for full reasoning)

- 14 endpoints, TDC-sourced, all CC BY 4.0 (PharmaBench dropped — NC-ND conflict)
- Scaffold split (80/20, 5-seed CV), matches TDC's official benchmark protocol
- Multi-task clusters: Absorption/Distribution, Metabolism (+Clearance), Toxicity, DILI standalone
- k-NN applicability domain (5-NN Tanimoto/ECFP4) is core MVP, not deferred
- Checkpointing + RNG-state restoration is mandatory (lab A100 sessions aren't guaranteed length)
- `/predict` is fast/cheap; 3D conformers + explainability are lazy/on-demand
- 48h Redis cache TTL, 24h batch upload retention, opt-in-only retraining use
