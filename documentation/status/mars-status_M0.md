# MARS — Implementation Status & Verification Matrix

**Source of truth:** `mars-blueprint_v4.md`
**Repo SHA at time of audit:** `d3c8fe58c88eb2c6fda73bd9a7fa11c2e6573d79` (`Initial commit`, only `.gitignore` tracked — the entire working tree below is untracked)
**Audit date:** 2026-08-30
**Auditor scope:** full repository read + local smoke tests (contracts import, FastAPI stub end-to-end, docker-compose parse, tracking module import)

---

## 1. Repository state (summary)

The repo is an **M0 scaffold**, partially complete, with a few M1/M2 support modules stubbed ahead of schedule.

| Area | What physically exists | Runs? |
|---|---|---|
| `contracts/` | Installable `mars-contracts` package (Pydantic v2). `Endpoint` enum (15 = 14 ML + SA), `ENDPOINT_METADATA` with task type / category / cluster, `PredictionRequest/Response`, `EndpointPrediction`, `BatchJobStatus`, `ConformerResponse`, `Atom`, `Bond`. | ✅ imports, 15 endpoints, stub produces 14 predictions |
| `api/` | FastAPI app: `/health`, `/predict` (mounted at `/predict`), `stub_predictor` producing contract-shaped deterministic fake predictions + stub standardizer. `Dockerfile`. `requirements.txt` (fastapi, sqlalchemy, asyncpg, redis, boto3, passlib[bcrypt], itsdangerous). | ✅ `/health` 200, `/predict` returns 14 preds, empty-SMILES → 422 |
| `frontend/` | `package.json` (React 18 + Vite + react-router + 3dmol, **no build tooling config, no `index.html`, no `src/main.tsx`**). Hand-mirrored TS `contracts.ts`. Empty `components/ pages/ styles/`. | ❌ not runnable (no vite config / entry) |
| `ml/` | `data/acquire.py` — **stub**, only a `TDC_DATASET_MAP` dict + a print. `tracking/` — `ExperimentRun` (local run dirs, `config.json`/`provenance.json`/`run.json`/`metrics.jsonl`/artifacts), `collect_provenance` (git SHA/branch/dirty + env + pkg versions), `WandbLogger` (mirror). `utils/seed.py` — `set_global_seed` (py/np/torch + deterministic). Empty `configs/`. | ⚠️ `tracking` imports `numpy`/`torch` at module load; **ml deps not installed in `.venv`**, so unrun locally |
| `infra/` | `infra/docker/` — empty. | — |
| `docker-compose.yml` | postgres + redis + minio + api. | ❌ **`api` service block is mis-indented → `docker compose config` fails** ("services.container_name must be a mapping") |
| `.env.example` | All infra/model/W&B/auth/rate-limit vars pre-named. | n/a |
| Tests | **None anywhere.** | — |
| CI/CD | **None** (`.github/` absent). | — |
| `documentation/` | Blueprints v1 → v4. **`documentation/` is in `.gitignore` line 1 → the blueprint is not version-controlled.** | — |

**Stray artifacts:** literal brace directories `api/app/{routers,services,core}/` and `frontend/src/{components,pages,styles}/` (from a `mkdir -p` on a shell without brace expansion). `.gitignore` negates `data/.gitkeep`, `ml/runs/.gitkeep`, `ml/artifacts/.gitkeep` which **do not exist**.

---

## 2. Current milestone

**M0 — Contracts & Scaffolding** (blueprint Module 14 milestone table, target Aug 25–26).

**Why M0 and not M1:**
- M0's deliverables are the only ones with *any* substantive implementation (contracts package, monorepo skeleton, docker-compose, `.env` template, W&B code scaffold).
- M0 is **not complete**: `docker-compose` is broken, there is **no CI/CD skeleton** (explicit M0 line item), and the **API route contract** (one of the three Phase 0 contracts) is only partially written (only `/predict` + conformer shapes exist; Module 8's other 6 routes are unmodelled and undocumented).
- M1 proper is essentially unstarted: `acquire.py` performs no acquisition, there is no standardization / dedup / scaffold-split / lockfile code, and `ml/featurize/`, `ml/models/`, `ml/train/`, `ml/eval/` do not exist.
- The M1/M2 support code that *does* exist (`tracking/`, `utils/seed.py`) is infrastructure that can be built before its milestone without violating dependency order; it does not make M1 "in progress".

**Conclusion:** finish M0 before starting M1. M0's gaps (broken compose, no CI smoke test, incomplete route contract) are exactly the "keep model/API/frontend from drifting" guarantees M0 exists to provide, so they block clean M1+ work.

**Update (2026-08-30):** M0 is now **complete** — all matrix rows M0-1…M0-11 COMPLETE or RESOLVED. Open items are M1/M2 work, not M0: the TDC lockfile (B-6) and the two KERMT pre-flight checks (CF-8). **Next milestone: M1 — Data & Featurization.**

---

## 3. Verification matrix

Status definitions per task instructions: **COMPLETE** = implemented + evidenced; **PARTIAL** = some behavior exists but incomplete/untested/incorrect; **MISSING** = not implemented; **CONFLICTING** = implementation violates blueprint, needs a decision.

### 3.1 Milestone M0 — Contracts & Scaffolding (CURRENT)

| # | Item (blueprint ref) | Status | Remaining work |
|---|---|---|---|
| M0-1 | Phase 0 **prediction response contract** (M14 Phase 0; Module 5 CI fields, Module 8 model-version) | **COMPLETE** | Values present: per-endpoint `value`, `unit`, `confidence_low/high`, `in_domain`, `knn_distance`, `model_version`, `molecule_id`, `served_at`, `cache_hit`. Matches Module 5 CORE + Module 8 versioning. |
| M0-2 | Phase 0 **conformer / 3D data contract** (M14 Phase 0; Module 3 Stage 5 → Module 7) | **COMPLETE** | `ConformerResponse` = atoms (element, xyz, Gasteiger `partial_charge`), bonds (order incl. 1.5 aromatic), `energy_kcal_mol`, `sdf_block`. Coordinate format + units + energy covered. |
| M0-3 | Phase 0 **API route contract** (M14 Phase 0 — "Module 8's endpoint table, concrete request/response field names") | **COMPLETE** *(this pass)* | Added `contracts/API_ROUTES.md` (all 8 routes: method/auth/models/milestone + cross-cutting cache/rate-limit/retention rules) and `mars_contracts/api.py` (`BatchPredictOptions`, `BatchRowResult`, `BatchPredictResponse`, `CompareRequest`, `CompareResponse`). `ExplainResponse` / report shapes documented as targets, modelled at M4. |
| M0-4 | Monorepo skeleton | **COMPLETE** | `contracts/ ml/ api/ frontend/ infra/` present; README documents layout (stale, see M0-9). |
| M0-5 | `docker-compose` local stack (Module 10 topology: PG + Redis + R2 stand-in + API) | **CONFLICTING / broken** → *fixed this pass* | `api` service keys indented at the same level as `api:` → invalid compose. `docker compose config` errors out. Service topology otherwise matches Module 10 (Neon→postgres, Upstash→redis, R2→minio). |
| M0-6 | **CI/CD skeleton** (Module 10: GH Actions — lint/test on PR, build image, smoke-test prediction) | **MISSING** → *added this pass* | No `.github/`. |
| M0-7 | `.env` template (Module 8/10/13 vars) | **COMPLETE** *(this pass)* | CF-4 resolved 2026-08-30: JWT dropped for server-side Redis sessions. `.env.example` now has `SESSION_TTL_DAYS`/`SESSION_COOKIE_*`/`PASSWORD_HASH_SCHEME`/`RESEND_API_KEY`; `api/requirements.txt` drops `python-jose`, adds `itsdangerous`. See `DECISIONS.md`. |
| M0-8 | **W&B project set up** (M14 M0) | **COMPLETE** *(confirmed 2026-08-30)* | Remote project `mars-admet` / entity `shashquatch` created; `wandb` 0.29.0 in `.venv`; auth via `wandb login` (`_netrc`), so `WANDB_API_KEY` stays empty. `WandbLogger` smoke-tested green by the user. `.env.example` `WANDB_ENTITY=shashquatch`. |
| M0-9 | Repo README accuracy | **CONFLICTING** → *fixed this pass* | References `mars-blueprint_v3.md` and the abandoned 3-person A/B/C split; v4 is solo. |
| M0-10 | Repo hygiene | **COMPLETE** *(this pass)* | Removed stray `{...}` brace dirs; added the negated `.gitkeep`s; fixed over-broad `data/` ignore (was hiding `ml/data/` source); ignore `*.egg-info/` + root `test_*.py`. |
| M0-11 | Blueprint under version control | **RESOLVED — won't fix (deliberate, 2026-08-30)** | User decision: `documentation/` stays untracked. Compensating control: tracked `DECISIONS.md` at repo root is the version-controlled home for decision provenance. CF-1 closed on that basis. |

### 3.2 Module 1 — Data (milestone M1, NOT CURRENT)

| # | Requirement | Status | Remaining work |
|---|---|---|---|
| 1-1 | TDC acquisition of all 14 datasets via PyTDC | **MISSING** | `acquire.py` has the name map only; no PyTDC calls, no download, no raw persistence. |
| 1-2 | Standardization of all 14 sets through Module 3 Stage 1 **before** dedup/split | **MISSING** | No standardization code. |
| 1-3 | EDA-gated tiered dedup / conflict resolution (drop vs average/majority-vote vs tie-drop) | **MISSING** | — |
| 1-4 | Scaffold split 80/20 (Murcko, no shared scaffolds) + 5-seed train/val CV within train_val | **MISSING** | — |
| 1-5 | Data versioning lockfile (PyTDC version + per-dataset snapshot hashes) | **MISSING** | `Module 1 §5` — no lockfile. |
| 1-6 | DILIst augmentation (train/val pool only; dedup vs TDC test set; scaffold-overlap re-check) | **MISSING** | `acquire.py` comment references it only. |
| 1-7 | Held-out calibration split carved from train_val (Module 4; 10% or 50-floor) | **MISSING** | — |
| 1-8 | Licensing check recorded (all 14 CC BY 4.0; PharmaBench dropped) | **PARTIAL** | Decision captured in blueprint + README bullet; no `LICENSES.md` / per-dataset provenance file in repo. |

### 3.3 Module 2 — Endpoint Selection

| # | Requirement | Status | Remaining work |
|---|---|---|---|
| 2-1 | 14 endpoints (13 ML + SA rule-based) enumerated | **COMPLETE** | `Endpoint` enum + `ENDPOINT_METADATA`; `ML_ENDPOINTS` excludes SA. Names/datasets match Module 2 table. |
| 2-2 | Task type per endpoint | **COMPLETE** | Matches blueprint (SA = `RULE_BASED`). |
| 2-3 | SA score category | **PARTIAL / minor** | Blueprint = "N/A"; code assigns `EndpointCategory.ABSORPTION` (enum has no N/A member). Cosmetic; document or add `OTHER`. |

### 3.4 Module 3 — Featurization (milestone M1, NOT CURRENT)

| # | Requirement | Status | Remaining work |
|---|---|---|---|
| 3-1 | Stage 1 standardization (canonicalize, salt strip, tautomer/charge normalize, reject invalid SMILES) | **MISSING** | Only `standardize_stub()` = `smiles.strip()` in the API. |
| 3-2 | Stage 2 molecular graph repr (atom/bond features for backbone) | **MISSING** | — |
| 3-3 | Stage 3 ECFP/Morgan r=2, 2048-bit, **`useChirality=True`** | **MISSING** | — |
| 3-4 | Stage 4 ~200 RDKit 2D descriptors | **MISSING** | — |
| 3-5 | Stage 5 3D conformer (ETKDG + MMFF94, lowest-energy, cached per molecule) | **MISSING** | Contract shape only. |
| 3-6 | Batch/vectorized execution across stages 1–4 (non-negotiable) | **MISSING** | — |
| 3-7 | Stereochemistry: preserve defined centers, chirality in graph feats, `useChirality` in ECFP, don't fabricate undefined, EDA-log stereo-defined ratio per endpoint | **MISSING** | — |
| 3-8 | Expensive-feature caching (conformers, descriptors) | **MISSING** | — |

### 3.5 Module 4 — Models (milestone M2, NOT CURRENT)

| # | Requirement | Status | Remaining work |
|---|---|---|---|
| 4-1 | XGBoost / RF baseline on ECFP, per endpoint × 5 seeds | **MISSING** | — |
| 4-2 | Shared pretrained GNN backbone (GROVER/KERMT-style public checkpoint) | **MISSING** (backbone chosen 2026-08-30) | Decision: **KERMT `nvidia/NV-KERMT-70M-v2`** (see `DECISIONS.md`). Still to do: pin exact checkpoint+featurizer files by hash; add KERMT featurizer to `ml/requirements.txt`; **verify CPU inference feasibility for Module 10 serving** (open risk); smoke-finetune on a 24 GB card before relying on the RunPod fallback. |
| 4-3 | Single-task fine-tune per endpoint × 5 seeds | **MISSING** | — |
| 4-4 | Multi-task clusters: Metabolism / Absorption+Distribution / Toxicity + DILI standalone, masked loss | **PARTIAL** | Cluster *assignments* are encoded in `ENDPOINT_METADATA` (`metabolism`, `absorption_distribution`, `toxicity`, `dili_standalone`) and match Module 4. No model code. |
| 4-5 | Kendall homoscedastic uncertainty weighting for mixed-type clusters | **MISSING** | — |
| 4-6 | Sparse-task mitigation: log σₜ trajectory monitoring (mandatory) + stratified batch composition + fixed-weight fallback | **MISSING** | — |
| 4-7 | Probability calibration — temperature scaling (GNN) / Platt (XGBoost), per calibration split | **MISSING** | — |
| 4-8 | Empirical winner selection on held-out scaffold test set | **MISSING** | — |
| 4-9 | Checkpoint = model + optimizer + LR scheduler + **Python/NumPy/PyTorch RNG state**, synced to R2 | **PARTIAL** | `set_global_seed()` seeds all three RNGs at start. **No checkpoint save/restore, no RNG-state capture/restore, no R2 sync** anywhere. This is the highest-risk M2 gap (blueprint calls it "mandatory"). |
| 4-10 | Model artifact/version provenance | **PARTIAL** | `WandbLogger.log_artifact()` exists; no caller, no version registry, no routing-table artifact. |

### 3.6 Module 5 — Uncertainty & Applicability Domain (milestone M2, NOT CURRENT)

| # | Requirement | Status | Remaining work |
|---|---|---|---|
| 5-1 | CORE: 5-seed ensemble confidence bands (mean ± std / entropy) | **MISSING** (contract-ready) | `confidence_low/high` fields exist; no computation. |
| 5-2 | CORE: k-NN applicability domain (5-NN Tanimoto ECFP4, per-endpoint 90th-pctile self-calibrating threshold, cached index) | **MISSING** (contract-ready) | `in_domain` + `knn_distance` fields exist; no index, no threshold calc. |
| 5-3 | DEFERRED: conformal prediction | **MISSING (Post-MVP, out of M0/M1/M2 scope)** | Not required now. |

### 3.7 Module 6 — Explainability (Post-MVP, milestone M4)

| # | Requirement | Status |
|---|---|---|
| 6-1 | Integrated Gradients, atom-level → functional-group aggregation | **MISSING (Post-MVP)** |
| 6-2 | Dual validation (structural-alert cross-check + perturbation) | **MISSING (Post-MVP)** |

### 3.8 Module 7 — 3D Rendering (milestone M4)

| # | Requirement | Status |
|---|---|---|
| 7-1 | 3Dmol.js viewer, single shared component, Track 1 hero + Track 2 analysis | **MISSING** (`3dmol` dep declared; no component) |
| 7-2 | Conformer data contract consumed | **COMPLETE (contract side)** — see M0-2 |

### 3.9 Module 8 — API / Serving (milestone M3)

| # | Requirement | Status | Remaining work |
|---|---|---|---|
| 8-1 | `POST /predict` (SMILES → 14 endpoints + basic uncertainty), IP rate-limited, no auth | **PARTIAL** | Route + stub work; no rate limiting; stub not real inference (expected pre-M2). |
| 8-2 | `POST /batch/predict` (CSV/SDF, ≤1000 sync else job_id), account required | **MISSING** | — |
| 8-3 | `GET /batch/progress/{job_id}` SSE | **MISSING** | — |
| 8-4 | `GET /batch/results/{job_id}` | **MISSING** | — |
| 8-5 | `GET /molecule/{id}/3d` lazy | **MISSING** | — |
| 8-6 | `GET /molecule/{id}/explain?endpoint=` lazy | **MISSING (Post-MVP feature)** | — |
| 8-7 | `POST /compare` (2–3 molecules) | **MISSING** | — |
| 8-8 | `GET /molecule/{id}/report` PDF | **MISSING** | — |
| 8-9 | Redis cache keyed on (std SMILES + endpoint set + **model version**), 48h TTL | **MISSING** | `PREDICTION_CACHE_TTL_SECONDS=172800` env only. |
| 8-10 | Model routing table (endpoint → cluster model + empirical winner variant), one inference per overlapping cluster | **PARTIAL** | Cluster grouping in `ENDPOINT_METADATA`; no routing/serving layer. |
| 8-11 | Auth stub (email/password), Turnstile on registration, rate limits | **MISSING** | env vars only; scaffold now session-based (CF-4 resolved). |
| 8-12 | Retention enforcement (48h cache / 24h batch / opt-in retrain) | **MISSING** | env vars only. |
| 8-13 | `model_version` in every response | **COMPLETE (contract)** / PARTIAL (value is `stub-v0`) | — |

### 3.10 Module 9 — Frontend (milestone M4)

| # | Requirement | Status |
|---|---|---|
| 9-1 | Design system / `style-guide.html` (lab-instrument vernacular, token system) | **MISSING** |
| 9-2 | Runnable app shell (Vite entry, router) | **MISSING** (`package.json` only; no `index.html`/`main.tsx`/`vite.config`) |
| 9-3 | TS contract types mirrored from Pydantic | **PARTIAL / drift risk** | `contracts.ts` hand-mirrors `EndpointPrediction`/`PredictionResponse` correctly today; no codegen, no drift guard. |
| 9-4..9-13 | Prediction panel, CI bars, batch upload, toasts, comparison, radar, ultra-wide, motion tiering, editor panel, explainability scale | **MISSING** |

### 3.11 Module 10 — Infra / Deployment (milestone M3, skeleton in M0)

| # | Requirement | Status | Remaining work |
|---|---|---|---|
| 10-1 | `docker-compose` local = prod topology | **CONFLICTING → fixed this pass** | See M0-5. |
| 10-2 | API `Dockerfile` | **COMPLETE** | `python:3.11-slim`, installs reqs, copies `app/`, runs uvicorn. Builds `contracts` via `-e ../contracts` in reqs — **note:** Dockerfile `COPY contracts /contracts` but `WORKDIR /app`; `-e ../contracts` resolves to `/contracts` ✅. |
| 10-3 | Worker (Celery/RQ) service | **MISSING** | Blueprint Module 8/10 both reference it; no worker in compose. |
| 10-4 | CI/CD (GH Actions) | **MISSING → added this pass** | — |
| 10-5 | Monitoring (Sentry, UptimeRobot) | **MISSING** | `SENTRY_DSN` env only. |
| 10-6 | Secrets via platform/Actions, never committed | **COMPLETE** | `.gitignore` covers `.env*` except `.env.example`; `.env.example` holds no real secrets. |
| 10-7 | Training checkpoint → R2 sync | **MISSING** | `S3_BUCKET_CHECKPOINTS` env only. |

### 3.12 Module 11 — Evaluation & Benchmarking (milestone M5, infra usable earlier)

| # | Requirement | Status | Remaining work |
|---|---|---|---|
| 11-1 | Metrics: MAE (reg); AUROC + AUPRC (clf); ECE + Brier (calibration) | **MISSING** | No `ml/eval/`. |
| 11-2 | 5-seed mean ± std reporting, fixed test set, never single-run | **PARTIAL** | `metrics.jsonl` per-run logging exists; no seed-aggregation layer. |
| 11-3 | Nemenyi post-hoc significance testing | **MISSING** | — |
| 11-4 | Reproducibility-gated leaderboard comparison (CaliciBoost / MapLight / MapLight+GNN) | **MISSING** | — |
| 11-5 | Self-audit protocol (scaffold-overlap check pre-report, esp. post-augmentation; HP-tuning disclosure; env repro) | **MISSING** | — |
| 11-6 | Provenance capture (§5 field list) | **PARTIAL** | `collect_provenance()` captures git SHA/branch/dirty + python/OS/CPU + numpy/torch/cuda/cudnn/rdkit/sklearn/xgboost/pytdc versions. **Missing:** GPU device name (`torch.cuda.get_device_name`), automatic seed capture (only if placed in `config`), dataset id/version/hash (config-dependent, no enforced schema), preprocessing/featurization version, checkpoint id, W&B run URL back-link. `torch`/`numpy` imported at module top → provenance unusable without full ML stack even for CPU-only XGBoost runs (Module 10 wants those on the laptop). |
| 11-7 | W&B as the tracking system | **PARTIAL** | `WandbLogger` wrapper (init with config+provenance, `log`, `log_artifact`, `finish`, `resume="allow"`). No run naming convention tied to endpoint/seed/cluster, no guard against logging debug/no-op runs (task §5 concern). |
| 11-8 | §5.5 structural-frontier robustness check (Lo-Hi / DataSAIL) | **MISSING (Post-MVP-parallel)** | — |
| 11-9 | §6 ablation matrix | **MISSING (Post-MVP-parallel)** | — |

### 3.13 Module 12 — Feature Catalog (spec; features land in owning milestones)

| # | Requirement | Status |
|---|---|---|
| 12-1..core | Single/batch input, prediction panel, uncertainty, AD flag, radar, drug-likeness + alerts, SA score, approved-drug percentile | **MISSING** (contracts partially anticipate AD flag + CI) |
| 12-2..novelty | Explainability heatmap, conformal, chemical-space map, `mmpdb` MMP suggestions | **MISSING (Post-MVP)** — `mmpdb>=3.1` declared in `ml/requirements.txt` |

### 3.14 Module 13 — Auth & Persistence (milestone M3)

| # | Requirement | Status | Remaining work |
|---|---|---|---|
| 13-1 | Server-side Redis sessions (`session:{token}→user_id`, sliding 7d TTL), **not JWT** | **MISSING** (scaffold aligned) | CF-4 resolved: `.env.example` + `api/requirements.txt` now session-based, no JWT. Implementation is M3. |
| 13-2 | Registration/login/password-reset (bcrypt/argon2, Resend email) | **MISSING** | `passlib[bcrypt]` + `itsdangerous` in `api/requirements.txt`; `RESEND_API_KEY` in `.env.example`. |
| 13-3 | Postgres schema: `users`, `saved_molecules`, `saved_reports`, `batch_jobs` | **MISSING** | `sqlalchemy`/`asyncpg` declared; no models, no migrations (no Alembic). |
| 13-4 | Snapshot-on-save (predictions/results frozen at save time) | **MISSING** | — |
| 13-5 | Account deletion cascades | **MISSING** | — |

---

## 4. Critical findings

**CF-1 — Blueprint is git-excluded.** `.gitignore:1` ignores `documentation/`. **RESOLVED 2026-08-30 — won't fix, deliberate.** User keeps `documentation/` (blueprint + status docs) untracked. Compensating control adopted: a tracked `DECISIONS.md` at repo root records every decision that resolves a blueprint ambiguity or gates a milestone, so decision provenance is version-controlled even though the spec is not. Residual risk accepted: blueprint *revisions* themselves aren't diffable in git history — mitigated by the versioned filenames (`mars-blueprint_v1…v4.md`) the user already maintains.

**CF-2 — `docker-compose.yml` is non-functional.** The `api:` service's keys (`build`, `container_name`, `env_file`, `environment`, `ports`, `volumes`, `depends_on`, `command`) are indented at the same column as `api:` itself, so YAML parses them as sibling top-level services. `docker compose config` fails outright. `docker compose up` (README "Day 1 setup" step 3, blueprint M0) cannot have worked. *Fixed this pass.*

**CF-3 — No CI, no automated smoke test.** Blueprint Module 10 mandates a GH Actions pipeline that runs a "smoke-test prediction against a known molecule to catch silent regressions" and "ties into Module 11's reproducibility discipline". Nothing exists. Without it, contract drift between `contracts/` (Pydantic) and `frontend/src/types/contracts.ts` (hand-mirrored) — an explicitly acknowledged risk in that file's own header — is undetected. *Skeleton added this pass.*

**CF-4 — Auth scaffold contradicted the locked session strategy.** `.env.example` shipped `JWT_*` vars and `api/requirements.txt` pulled `python-jose`, against Module 13's "Server-side sessions in Redis, not JWT". **RESOLVED 2026-08-30.** `.env.example` → `SESSION_TTL_DAYS` / `SESSION_COOKIE_NAME` / `SESSION_COOKIE_SECURE` / `PASSWORD_HASH_SCHEME` / `RESEND_API_KEY` (+ Turnstile kept). `api/requirements.txt` → dropped `python-jose[cryptography]`, added `itsdangerous` (signed reset tokens), kept `passlib[bcrypt]`. `contracts/API_ROUTES.md` auth-stub note updated. Logged in `DECISIONS.md`.

**CF-5 — Provenance module hard-depends on the full ML stack.** `ml/tracking/provenance.py` does `import numpy` / `import torch` at module top. Module 10 states XGBoost baselines run **locally on the laptop** (no CUDA). Provenance/experiment tracking for those runs will `ImportError` unless the whole GNN stack is installed on the laptop too. Recommend lazy/guarded imports so `ExperimentRun` works in a CPU-only env. (M2 refinement — noted, not fixed this pass to keep M0 scope tight.)

**CF-6 — Frontend cannot start.** `package.json` declares Vite but there is no `index.html`, `src/main.tsx`, `vite.config.ts`, or `tsconfig.json`. README claims `npm run dev` is a Day-1 step. Not an M0 blocker per the milestone table (frontend shell is M4) but the README overstates readiness. *README corrected this pass; shell build deferred to M4.*

**CF-7 — Contract coverage gap for Phase 0.** Two of three Phase 0 contracts (prediction response, conformer) are solid; the **API route contract** is effectively absent. *Added `contracts/API_ROUTES.md` + batch/compare request-response models this pass* so M1/M3 build against a fixed surface.

**CF-8 — KERMT backbone: two open risks that could touch the blueprint (M2, flagged now).** Backbone decision = KERMT `nvidia/NV-KERMT-70M-v2` (in-spec — Module 4 names KERMT; full rationale in `DECISIONS.md`). Two items to verify before M2 commits:
1. *CPU inference for serving.* Module 10 assumes CPU-only serving on Render. If KERMT + its featurizer (cuik-molmaker / BioNeMo stack) can't do an acceptable-latency CPU forward pass, Module 10's serving tier has to change (GPU serving, or ONNX export/distillation). Verify with a CPU smoke inference on the pretrained checkpoint early in M2.
2. *RunPod fallback VRAM.* KERMT recommends ≥32 GB VRAM for finetuning; the blueprint's RunPod **RTX 4090 (24 GB)** fallback is under that. Lab A100 is fine. Smoke-finetune on a 24 GB card before depending on the fallback; if it OOMs, bump the fallback to RunPod A40 (48 GB) and revise the Module 10 budget rate.

**No data-leakage findings yet** — Module 1 (splitting, augmentation, test-set isolation) is entirely unimplemented, so there is nothing to leak *from*. The leakage-prevention requirements (1-4, 1-6, 11-5) become live at M1 and must be built in from the first commit of the split code, not retrofitted.

---

## 5. M0 completion — done this pass

1. ✅ **`docker-compose.yml`** re-indented; `docker compose config` validates. (`worker` service = M3, noted not added.)
2. ✅ **`.github/workflows/ci.yml`** — `ruff` + `pytest` (contracts, api) + API image build + boot-and-`/predict`-smoke on `CCO` (asserts 14 preds + `model_version`).
3. ✅ **`contracts/API_ROUTES.md`** + `mars_contracts/api.py` (`BatchPredictOptions`, `BatchRowResult`, `BatchPredictResponse`, `CompareRequest`, `CompareResponse`); `/molecule/{id}/{3d,explain,report}` documented, modelled at M4.
4. ✅ **Tests** — `contracts/tests/test_contracts.py` (7), `api/tests/test_predict.py` (5) + `api/conftest.py`. All green locally.
5. ✅ **Repo hygiene** — brace-dir removal; `.gitkeep`s; `data/` ignore scoped so `ml/data/` source isn't hidden; `*.egg-info/` + root `test_*.py` ignored.
6. ✅ **README** — v4 reference, solo framing, frontend "not runnable yet" note.
7. ✅ **`ml/pyproject.toml`** (pytest rootdir/pythonpath) + repo-wide **`ruff.toml`**.
8. ✅ **Auth scaffold** aligned to Redis sessions (CF-4).
9. ✅ **`DECISIONS.md`** created (tracked decision log; CF-1 compensating control).

**Deferred (correctly out of M0):** all Module 1/3/4/5 implementation, auth logic, DB schema, frontend shell, monitoring wiring, KERMT M2 pre-flight checks (CF-8), TDC lockfile (B-6).

---

## 6. Risks / blockers requiring your input

| ID | Blocker | Status |
|---|---|---|
| B-1 | W&B remote project + entity | ✅ RESOLVED — project `mars-admet` / entity `shashquatch`, `_netrc` auth, smoke-tested. |
| B-2 | CF-1 — blueprint in VCS | ✅ RESOLVED — won't fix; `DECISIONS.md` is the compensating tracked record. |
| B-3 | CF-4 — JWT → Redis-session cleanup | ✅ RESOLVED — applied to `.env.example`, `api/requirements.txt`, `API_ROUTES.md`. |
| B-4 | Lab A100 personal-research use | ✅ RESOLVED — permitted; A100 is primary M2 resource. |
| B-5 | GNN backbone choice | ✅ RESOLVED — KERMT `nvidia/NV-KERMT-70M-v2` (`DECISIONS.md`). Sub-tasks now tracked under CF-8 + row 4-2, not blockers. |
| B-6 | TDC version + dataset hashes for the Module 1 §5 lockfile | ⏳ OPEN — needs `python ml/data/acquire.py` run with `PyTDC` installed. Genuinely M1 work, not M0. |
| B-7 | KERMT CPU-inference feasibility for Module 10 serving (CF-8 item 1) | ⏳ OPEN — M2 pre-flight; may force a Module 10 serving-tier revision. |
