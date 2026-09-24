# context.md

_Last updated: 2026-09-24 (KERMT Tier-0 GPU runs under way: DILI seeds 0–4, `toxicity__cls` seeds 0–1 done, seeds 2–4 pending; the "no GPU training" statements further down predate 2026-09-22)_

## What MARS is

AI-powered ADMET & drug-safety screening platform. Predicts **14 ADMET
endpoints** (13 ML + 1 rule-based SA score) from a SMILES string. Research
project → target output is a **product + a published paper** (MLSB / AI4Science
venue). Reproducibility, provenance, deterministic evaluation, and auditable
results are first-class, not add-ons.

Modeled after commercial platforms (Insilico, Recursion, Deep Genomics);
benchmarked against SwissADME / ADMETlab / admetSAR / pkCSM (free tier) and
StarDrop (enterprise).

## Where we are

- **Milestone M0 (Contracts & Scaffolding): COMPLETE** as of 2026-08-30.
- **Milestone M1 — Data & Featurization: COMPLETE 2026-08-30.** Delivered in
  4 runs (see `decisions.md` + `status/mars-status_M1.md` + the full
  **`documentation/MARS_M1_TECHNICAL_REFERENCE.md`**).
  Acquisition + lockfile; standardization; per-endpoint EDA; tiered dedup;
  fixed scaffold split + leakage audits; calibration split; DILIst augmentation
  (DILIPredictor MIT gold std, 57 test-set overlaps removed); PPB Option C
  (human primary; all-species pooled = provenance-tracked ablation);
  Module 3 Stages 2–5 (graph w/ explicit chirality, Morgan r2/2048/`useChirality`,
  217 RDKit descriptors w/ SHA drift guard, ETKDGv3+MMFF94/UFF conformers);
  batched `featurize_batch` façade; on-disk `FeatureCache` (config-versioned
  keys, incompatible-config-safe). Blueprint edits: **no paid compute anywhere**
  ($0 budget); **serving → Google Cloud Run** (backend+worker only; Cloud Tasks).
  Processed data at `ml/data/processed/20260830T200000Z/`. **219 ml tests + 12
  M0 green; ruff clean.**
- **Active: M2 — Modeling (Module 4) + calibration/AD (Module 5).**
  Runs 1a (model scaffolding), 1b (XGBoost baseline model + training loop),
  2a (Platt/temperature calibration + k-NN AD), and 2b (5-seed evaluation
  aggregation + 10-check leakage audit + TDC comparability scaffolding) are
  all **COMPLETE** (2026-08-31 to 2026-09-16). Full file-by-file breakdown in
  `next_steps.md` — don't re-derive, cite it.
  **W&B is now wired in** (2026-09-16): `train/run_xgboost_baseline.py` (the
  production CLI) mirrors to W&B by default; `train_one_seed`/
  `train_xgboost_all_seeds` default `use_wandb=False` so ad-hoc/test calls stay
  quiet. `_netrc` auth from M0 verified still valid. See next_steps.md for detail.
  **Tests (2026-09-21, final): ml 633 passed / 15 skipped / 5 failed — the 5 are all in `test_acquisition_lockfile.py`, pre-existing (tracked lockfile is the workstation's `20260918T090143Z` acquisition; this machine's raw data is `20260830T181633Z`, plus 2 stale post-Option-C expectations). Root `contracts/tests api/tests`: 21 passed / 23 skipped (infra-marked, Docker down). Ruff clean repo-wide. No type checker installed.**
  **Production XGBoost sweep COMPLETE 2026-09-17: 70/70 runs, 0 failed.**
  14 endpoints × 5 seeds (`FIXED_SEEDS=(0,1,2,3,4)`), ~172 min total CPU
  wall-clock. Every endpoint: all 5 seeds trained, promoted into
  `ml/artifacts/` (model + AD index + Platt calibrator where applicable),
  `EvaluationReport` built and reloadable, W&B run logged (70/70 real URLs).
  `ml/serve/ModelRegistry.available_endpoints()` now returns all 14 — real,
  non-fabricated inference verified for all 14 in the **live Docker
  container** (was 1/14 — `hia_absorption` only — before this sweep).
  Aggregated 5-seed metrics (mean±std) are in `ml/runs/evaluations/*.json`;
  full table in `decisions.md`'s 2026-09-17 sweep entry. **Two real bugs
  found and fixed during preflight/sweep** (both in new tooling, not
  existing M2 infra — see `mistakes.md`): a preflight script initially
  misclassified 6 endpoints' benign RDKit-vs-TDC scaffold-bucket noise
  (already documented since M1 Run 2) as blocking leakage; the sweep
  driver had the same gap specifically for augmented DILI and was
  corrected post-hoc without re-training. **One statistical anomaly
  flagged, not silently accepted**: `hia_absorption` shows AUROC=1.000
  ± 0.000 across all 5 seeds — plausible given HIA's small, severely
  imbalanced validation folds (410 positive / 51 negative in train_val)
  but flagged for scrutiny before being cited as a strong result.
  KERMT/GNN work is untouched (separate M2 track, not started).
- **Active: M3 — Serving & Infra (Module 8/13/10), started 2026-09-17.**
  See `module_milestone_map.md` for the authoritative Module↔Milestone audit
  done at kickoff. Real (not stubbed) work landed this session:
  - **Module 8 real serving:** `ml/serve/registry.py` + `predictor.py` — a
    routing table that loads promoted per-endpoint XGBoost artifacts and runs
    real inference (standardize → featurize → predict → Platt-calibrate →
    k-NN AD), falling back to the M0 stub per-endpoint when no artifact is
    promoted. One real artifact promoted as a locally-trained demonstration:
    `hia_absorption` seed 0 (`ml/artifacts/hia_absorption/`) — trained via
    the existing `ml/train/run_xgboost_baseline.py`, not fabricated. Verified
    end-to-end in the **built Docker container** hitting `/predict`, not just
    unit tests. Every other endpoint still correctly serves the stub — this
    is the intended, honest state of the routing table until the real
    70-run sweep (+KERMT) exists. `/predict` also gained Redis caching
    (48h TTL, keyed on smiles+endpoints+`MODEL_VERSION`) and per-IP rate
    limiting (60/min), both fail-open if Redis is down.
  - **Module 13 auth & persistence:** real `users`/`saved_molecules`/
    `saved_reports`/`batch_jobs` Postgres schema (Alembic migration
    `d5be9f4ca6e0`), bcrypt password hashing (direct `bcrypt` lib, NOT
    passlib — see mistakes.md), server-side Redis sessions (opaque
    `secrets.token_urlsafe` tokens, sliding 7d TTL), itsdangerous password-
    reset tokens, Turnstile-gated registration (skips verification when no
    secret key is configured, i.e. local dev), full `/auth/*`,
    `/molecules/*`, `/reports/*`, `DELETE /account` (cascading) routes.
    25 integration tests in `api/tests/` against real Postgres+Redis
    (`requires_infra` marker — skip gracefully, don't fail, when infra isn't
    up; CI now runs real service containers so they execute for real there).
  - **Module 8 batch:** `/batch/predict` (CSV only, SDF returns 415),
    interactive (<=1000, synchronous) and async (enqueued) tiers, SSE
    `/batch/progress/{id}`, `/batch/results/{id}` (410 after the 24h
    retention window). Async queue is `LocalTaskQueue` (in-process
    `asyncio.create_task`) implementing the exact lifecycle contract Cloud
    Tasks will eventually drive — `CloudTasksQueue` exists as a placeholder
    that raises `NotImplementedError` rather than fake success; real GCP
    wiring needs `GCP_SA_KEY_JSON` + a deployed worker endpoint, neither of
    which exist yet.
  - **Module 10 infra:** `api/Dockerfile` now installs
    `ml/requirements-serving.txt` (rdkit, xgboost, numpy,
    **scikit-learn — required even for inference-only use, see mistakes.md**)
    and copies `ml/serve|featurize|models|eval`, so the deployed container
    can actually run real inference, not just the stub. Built and
    container-tested locally via `docker compose up`. Real cloud deploy
    (Cloud Run/Neon/Upstash/R2) has **not** happened — needs explicit
    maintainer approval per the M3 execution rules, tracked in
    `next_steps.md`.
  - **Contracts:** added `mars_contracts/auth.py`, `persistence.py`; added
    `EndpointPrediction.model_id` (additive, defaults `"stub-v0"`) so a
    response can honestly report per-endpoint which artifact actually served
    it. `contracts/API_ROUTES.md` updated with the full Module 13 route
    table.
  - Three real environment/infra bugs hit and fixed this session — see
    `mistakes.md` "M3 start" and "M3 serving container": passlib+bcrypt>=4.1
    incompatibility, two native Windows Postgres services colliding with
    docker-compose's default ports, Docker Hub gating `minio/minio` pulls,
    and `XGBClassifier()` requiring scikit-learn at `__init__` even for
    inference-only use.
  - **Final CPU-side completion pass (same day, after a fresh audit against
    the checklist in the M3 kickoff prompt):**
    - **Module 3 Stage 1 validation is now enforced at the `/predict` /
      `/compare` / `/batch` boundary** when the real ml stack is present —
      `prediction_service.predict()` now raises `ValueError` on a
      chemically-invalid SMILES (real RDKit standardization) instead of
      silently falling back to the stub with the bad input; `/predict` and
      `/compare` turn that into a 422, `/batch`'s per-row handling already
      converted it into a non-blocking `ok=False` row. Container-verified:
      `POST /predict {"smiles":"not a real smiles !!!"}` → `422
      {"detail":"Invalid SMILES (smiles-parse-failed): ..."}`. Only enforced
      where rdkit is actually installed (the container) — root `.venv`
      tests stay lenient by construction (documented, not silently "fixed").
    - **SDF batch upload implemented for real** (`api/app/services/sdf_parser.py`,
      RDKit `ForwardSDMolSupplier`) — was previously a hard 415. Now: real
      parse when rdkit is present (container), 501 (not a fabricated
      rejection) when it isn't (root `.venv`). Container-verified end-to-end:
      uploaded a real ethanol SDF, got back a real 14-endpoint prediction
      (hia_absorption real, rest stub) with `smiles_input: "CCO"` correctly
      extracted.
    - **`/health/ready` readiness endpoint added**, checking real Postgres +
      Redis connectivity — kept separate from `/health` (pure liveness, no
      deps) so the existing CI smoke-predict job and any future Cloud Run
      liveness probe aren't broken by a dependency check. Container-verified:
      `{"status":"ready","checks":{"database":true,"redis":true}}`.
    - **Startup config-safety check**: warns (Python `UserWarning` + log) if
      `SECRET_KEY` is left at its insecure dev default — a concrete,
      discoverable mistake this codebase itself could otherwise ship
      unnoticed. Switched `main.py` to the modern `lifespan` handler while
      at it (was the deprecated `@app.on_event`).
    - **`docker-compose.yml`'s `api` service now has a healthcheck** (hits
      `/health`), matching postgres/redis/minio's existing pattern.
    - **Alembic migration reversibility verified**: `alembic downgrade -1`
      cleanly drops all 4 tables, `alembic upgrade head` cleanly restores
      them — a real ops property, not assumed.
    - Explicitly checked and confirmed NOT overclaiming anywhere: grepped
      for "production ready"/"all 14 endpoints" style claims across
      `api/app`, `contracts/`, and AIMS docs — found none; the `model_id`
      per-endpoint field was already the honest mechanism from the earlier
      pass.
    - **`GET /molecule/{id}/3d` implemented** (was entirely missing —
      found during this audit, not on the original checklist but explicitly
      M3-scoped per `API_ROUTES.md` and CPU-only since Module 3 Stage 5
      conformer generation was already done in M1).
      `api/app/services/{molecule_lookup,conformer_service}.py` +
      `routers/molecule.py`. `/predict` registers `molecule_id -> smiles` in
      Redis (same TTL as the prediction cache); `/molecule/{id}/3d` looks it
      up, real-generates via `ml/featurize/conformers.py` when rdkit is
      present, caches the result, and 404s for an unregistered/expired id
      rather than guessing. **Bug found and fixed while testing this**: the
      original implementation only registered the mapping on a cache
      *miss* — a `/predict` response served from cache (including one cached
      *before* this feature existed) never got registered, permanently
      404ing `/molecule/{id}/3d` for that molecule. Fixed by registering on
      both cache hit and miss. Container-verified end-to-end: real ETKDGv3 +
      MMFF94 coordinates and Gasteiger partial charges returned for ethanol;
      unknown id → 404.
- **Active: M2 KERMT/GNN track — mixed-type cluster blocker RESOLVED 2026-09-20.**
  KERMT's stock CLI takes one `--dataset_type` per run, so the two mixed-type
  clusters (`metabolism`, `absorption_distribution`) can't be jointly finetuned
  against it. Decision: a three-tier ladder — (a) stock KERMT on type-homogeneous
  subgroups, (b) a MARS-owned mixed-type trainer that **imports KERMT as a
  library** inside its own container, (c) ordinalized all-classification runs —
  with **stock KERMT left unforked and pinned** in every tier. Full rationale
  and the rejected options in `decisions.md`'s 2026-09-20 entry; live work
  breakdown in `next_steps.md`. Three findings from that pass matter beyond this
  decision: **cross-endpoint split leakage** (a molecule can be `train_val` for
  one endpoint and `test` for another, so any shared-encoder cluster run leaks
  through the encoder — a correctness precondition for all three tiers);
  **Kendall weighting is unreachable through the stock path** — KERMT's
  `run_finetune_local.py` never forwards `--use_mtl_loss` and parses strictly, so
  the stock CLI is equal-weighting only and all three loss-balancing arms must
  come from the MARS-owned trainer; and KERMT's uniform `MTLLoss` precision is an **exact
  reparameterization**, not a bug, for pure-type clusters — do not "fix" it.
- **KERMT calibration (2026-09-21):** `fit_temperature_scaler` had no production call
  site; it now does (`ml/eval/cluster_calibration.py`, called from
  `ml/train/train_kermt_cluster.py`). Fit on the held-out calibration split only, test
  set scored afterwards (raw + calibrated), per-seed diagnostics persisted. CPU-verified
  with a labelled test double only — **no real KERMT logits have ever been calibrated.**
  Findings recorded in `decisions.md` 2026-09-21: `hia_absorption`'s calibration set is
  N=47 (46 pos / 1 neg, below the floor of 50) after strict union removal; the calibration
  split is not label-representative; `holdout_calibration=True` (default) is a decision
  awaiting sign-off; and **the XGBoost baselines are validation-fold metrics with no
  test-set evaluation anywhere**, so KERMT-vs-XGBoost is not yet comparable.
- **Held-out evaluation + readiness (2026-09-21, later):** the 70 XGBoost models have now been scored on the
  untouched TEST split (`ml/runs/test_evaluations/`, 14 endpoints x 5 seeds; `artifacts/` byte-unchanged). Test
  differs from the old validation-fold reports by up to +0.263 AUROC, so **compare KERMT against the test
  numbers**. It also showed the served Platt calibrators worsen held-out calibration (ECE worse 7/9, Brier 9/9,
  seed-4 like-for-like). Workstation processed data: raw is byte-identical, processed identity **unable to
  verify** (`ml/data/compare_prep.py`, fingerprint `ml/data/metadata/prep_fingerprint.20260830T200000Z.json`).
  RNG capture/restore utility exists (`ml/utils/rng_state.py`) but is **not integrated** into training.
  `ml/train/readiness_report.py`: `READY_FOR_GPU_SMOKE_TEST` (CPU-side scope; 4 workstation checks pending).
- Solo build, dependency-ordered, targeting Sep 30 2026 (blueprint Module 14).
  Maintainer call 2026-09-20: **correctness ahead of the date** for the KERMT
  mixed-type work.
- Git: M0=`daddcf7`, M1 Run 1=`ec9c604`, Run 2=`c86a956`, Run 3=`77aab38`
  (+`b072865` CI fix), Run 4=`f679e71`, M2 Runs 1a+1b=`141415b`,
  M2 Runs 2a+2b+W&B=`a1f6b69`, M2 production-sweep tooling=`d67463f`,
  M3 serving/auth/infra=`bad0b02`, documentation now git-TRACKED=`1c252ac`,
  KERMT v2 integration + GPU validation=`64e1054`, KERMT GPU benchmark=`e2f45c7`.
  Current branch **`milestone/m2-kermt`**. Note `documentation/` became
  git-tracked at `1c252ac` (2026-09-18) — the older "documentation stays
  untracked" note below is superseded. The user commits manually. **The AI must
  not run git write commands.**

## Repo map

```
contracts/   mars-contracts (Pydantic v2, pip-installed editable). SOURCE OF
             TRUTH for field names. endpoints.py (Endpoint enum + ENDPOINT_METADATA
             with task_type/category/cluster), prediction.py, conformer.py,
             api.py (batch/compare models), API_ROUTES.md (all 8 Module 8 routes).
api/         FastAPI. app/main.py, routers/{health,predict,compare,batch,
             auth,molecules,reports,account}.py. app/core/config.py
             (pydantic-settings Settings). app/db/{base,models,session}.py
             (SQLAlchemy async, NullPool — see mistakes.md re: event-loop-
             per-TestClient). app/services/{stub_predictor (M0 fake data),
             prediction_service (real ml/serve/ routing + stub fallback),
             prediction_cache, rate_limit, security (bcrypt+itsdangerous),
             sessions (Redis), redis_client (deliberately uncached, see its
             own docstring), task_queue (LocalTaskQueue real /
             CloudTasksQueue placeholder), batch_results, turnstile}.py.
             alembic/ (migration `d5be9f4ca6e0` = initial schema). tests/
             (30: 5 stub-only fast tier + 25 real-Postgres/Redis integration,
             `requires_infra`-marked). conftest.py puts api/ on path.
ml/          data/ — acquire.py, dataset_registry.py, snapshot.py, eda.py,
             dedup.py, split.py, prepare.py, dilist_augment.py; raw/ (git-ignored,
             immutable, ~22MB), metadata/datasets.lock.json (git-TRACKED) +
             acquisition_report.md, eda/<eda_id>/, processed/<prep_id>/ (15 datasets
             + __augmented, git-ignored), cache/ (git-ignored), LICENSES.md,
             augmentation/dilipredictor_v1/ (CSV git-TRACKED + PROVENANCE.md).
             featurize/ — standardize, scaffold, graph, fingerprints, descriptors,
             conformers, pipeline (featurize_batch), cache (FeatureCache),
             build_cache. tracking/ — experiment.py (ExperimentRun, now exposes
             .provenance), wandb_logger.py (WandbLogger, wired into train/),
             utils/seed.py (torch lazy). configs/ — experiment_config.py
             (ExperimentConfig, FIXED_SEEDS). models/ — base.py (MARSModel ABC),
             xgboost_model.py. train/ — train_xgboost.py (use_wandb=False
             default), run_xgboost_baseline.py (CLI, W&B ON by default,
             --no-wandb to opt out). eval/ — metrics.py, calibration.py
             (Platt/TemperatureScaler), applicability_domain.py (ADIndex/5-NN
             Tanimoto), evaluate.py (EvaluationReport), leakage_audit.py
             (10-check audit), tdc_comparison.py (comparability flags, data-
             driven from provenance.json, no hardcoded leaderboard numbers).
             runs/ (git-ignored, ExperimentRun output; evaluations/*.json =
             one EvaluationReport per endpoint; production_sweep_summary.json
             + production_sweep_results.jsonl = the 70-run sweep record).
             serve/ (M3, Module 8) — registry.py (ModelRegistry,
             promote_seed_artifact) + predictor.py (real per-molecule
             inference against promoted artifacts). train/preflight_sweep.py,
             run_production_sweep.py, verify_sweep.py (M2 production-sweep
             tooling, 2026-09-17). artifacts/ (git-ignored except .gitkeep) —
             **all 14 endpoints promoted**, 5 seeds each, real XGBoost models
             + AD indices + Platt calibrators (classification endpoints).
             requirements-serving.txt (rdkit+xgboost+numpy+**scikit-learn**,
             installed into api/Dockerfile — NOT root .venv). tests/ (653
             collected, 633 pass, incl. test_serve_registry.py, run in ml/.venv). **Production
             XGBoost sweep COMPLETE (70/70) as of 2026-09-17** — see the
             bullet above for the full rundown; KERMT/GNN training is a
             separate, not-yet-started M2 track.
             KERMT cluster track (2026-09-20/21): configs/clusters.py,
             data/cluster_loaders.py, eval/cluster_eval.py,
             eval/calibration_diagnostics.py, eval/cluster_calibration.py,
             featurize/ordinal.py, train/train_kermt_cluster.py,
             train/preflight_clusters.py, eval/heldout_evaluation.py, train/evaluate_xgboost_test.py,
             data/compare_prep.py, utils/rng_state.py, train/readiness_report.py. Tier-1 trainer (ml/train/kermt_mixed/,
             models/kermt_mixed_model.py) does NOT exist yet.
frontend/    package.json + src/types/contracts.ts ONLY. NOT runnable (no Vite
             entry). React 18 + Vite + 3dmol planned. M4.
infra/       empty (infra/docker/.gitkeep). M3/M10.
docker-compose.yml   postgres + redis + minio(R2 stand-in) + api. Valid.
.github/workflows/ci.yml   ruff + pytest + docker build + /predict smoke on CCO.
ruff.toml    repo-wide lint (E,F,I,B,UP; ignore E501, UP042).
documentation/   git-TRACKED since 1c252ac. blueprint v4 + archive + status + AIMS.
```

## Environment (this machine)

- Windows 11, **PowerShell** primary shell. Bash tool also available.
- **Three environments now:**
  1. **root `.venv/`** (Python 3.11.9) — API + tooling. pydantic, mars-contracts,
     wandb 0.29.0, fastapi, uvicorn, httpx, ruff, pytest. No ML stack. Used to run
     the API + contracts/api tests + repo-wide `ruff`.
  2. **`ml/.venv/`** (Python 3.11.9) — M1+M2 working env. numpy 2.4.6, pandas 2.3.3,
     scikit-learn 1.9.0, **rdkit 2026.3.5**, joblib 1.5.3, pytest, `-e ../contracts`,
     plus M2: **xgboost 3.2.0**, **wandb 0.29.0**, scipy 1.17.1. No torch yet
     (KERMT is M2 Run 3+). Pins: `ml/requirements-m1.txt` + `-m2.txt` / `.lock.txt`.
     Run ml tests: `cd ml && ../ml/.venv/Scripts/python.exe -m pytest -q` (633 pass, 15 skip, 5 pre-existing failures).
  3. **WSL Ubuntu `~/mars-acq-venv`** — isolated acquisition env, `PyTDC==1.1.15`
     `--no-deps` + pinned minimal runtime. Only runs `ml/data/acquire.py`.
     `ml/data/requirements-acquire.lock.txt`. Reproduce: `ml/data/acquisition/README.md`.
- Still NOT installed anywhere: torch, transformers, mmpdb, sqlalchemy, asyncpg,
  redis, boto3 (KERMT belongs on the CUDA box; the rest is M3/M4).
- **WSL↔Windows quoting trap:** `wsl -d Ubuntu -- bash -lc '…'` with a
  space-containing path (the repo path has a space) mangles quotes. Pipe the
  script via stdin instead: `wsl -d Ubuntu -- bash -s <<'EOF' … EOF`.
- Docker Desktop is installed but its daemon was **not running** (used WSL instead).
- **W&B live and wired into training** (2026-09-16): project `mars-admet`,
  entity `shashquatch`. Auth via `wandb login` (`_netrc`) → `WANDB_API_KEY`
  stays empty in `.env`. `_netrc` re-verified valid via read-only
  `wandb.Api().viewer` call. `train/run_xgboost_baseline.py` mirrors every
  production run by default (`--no-wandb` to opt out); `train_one_seed()`
  itself defaults `use_wandb=False` so tests/ad-hoc calls stay off the dashboard.
- `.env` exists (copied from `.env.example`).
- **Port 8000 is blocked for a directly-bound native process on this machine**
  (WinError 10013 — Hyper-V/Docker reserved range); a **native** `uvicorn`
  needs **8080** instead. Docker's own port-proxy is unaffected — the `api`
  container publishes 8000 fine via `docker compose up api`.
- **Ports 5432 AND 5433 are both taken by native Windows Postgres services**
  (`postgresql-x64-16`, `postgresql-x64-18`) on this machine — docker-compose's
  `postgres` service is remapped to host port **55432** (`docker-compose.yml`
  + `.env`/`.env.example` `DATABASE_URL`). See mistakes.md before assuming a
  DB auth failure is a credentials problem.
- Docker Desktop present; `docker compose` works (daemon needs manually
  launching via the Start Menu / `Docker Desktop.exe` — it is not running by
  default). `docker-compose.yml`'s `minio` image is `quay.io/minio/minio`
  (Docker Hub's `minio/minio` now gates anonymous pulls).

## How to run things

```bash
# API + Swagger UI, NATIVE uvicorn (NOTE port 8080, not 8000; stub-only —
# no ml stack in root .venv, so /predict always falls back to the stub here)
.venv\Scripts\uvicorn.exe app.main:app --app-dir api --port 8080
#   -> http://localhost:8080/docs

# API with REAL inference: the docker-compose api container (has the ml
# serving stack baked in via api/Dockerfile). Uses host port 8000 (fine via
# Docker's port-proxy even though a native bind to 8000 is blocked).
docker compose up -d postgres redis minio api
curl -X POST http://localhost:8000/predict -d '{"smiles":"CCO"}' -H "Content-Type: application/json"
#   -> hia_absorption comes back model_id="mars-xgboost-ecfp-desc-v1" (real);
#      every other endpoint is still "stub-v0" (honest — no artifact yet)

# DB migrations (from api/, needs postgres running — see port note above)
cd api && ..\.venv\Scripts\python.exe -m alembic upgrade head

# Tests — API/contracts (root .venv). 5 stub-only + 25 real-Postgres/Redis
# integration tests + 1 SDF-real test (env-gated, only runs where rdkit is
# installed — skips here by construction, see api/tests/test_batch.py)
.venv\Scripts\python.exe -m pytest contracts/tests api/tests -q      # 21 pass, 23 skip when Postgres/Redis are down (2026-09-21)
# Tests — ml track (ml/.venv), run FROM ml/
cd ml && PYTHONPATH=. ..\ml\.venv\Scripts\python.exe -m pytest -q    # 633 pass, 15 skip, 5 pre-existing lockfile failures (2026-09-21)

# Lint
.venv\Scripts\python.exe -m ruff check contracts api ml

# Local infra
docker compose up -d postgres redis minio

# Frontend: NOT runnable yet (M4)
```

## Locked facts (do not re-litigate — see decisions.md + blueprint for why)

- 14 endpoints, all TDC-sourced, all CC BY 4.0. PharmaBench dropped (NC-ND).
- Split: scaffold (Murcko), 80/20 train_val/test, 5-seed CV within train_val,
  fixed held-out test set. 12 endpoints adopt the TDC benchmark split verbatim;
  **hERG_Karim + PPB (human-only, Option C)** self-generate a deterministic
  Murcko split (no official split exists) → not directly leaderboard-comparable.
- Calibration split: carved from train_val before CV; 10% or 50-compound floor.
- DILIst augments DILI (train/val pool only; dedup vs TDC test; re-check scaffold
  overlap post-merge).
- Clusters (multi-task, masked loss): `absorption_distribution` (logS, logP,
  Caco2, HIA, Pgp, BBB, PPB), `metabolism` (CYP3A4, CYP2D6, CYP2C9, Clearance),
  `toxicity` (hERG, AMES), `dili_standalone` (DILI).
- Backbone: **KERMT `nvidia/NV-KERMT-70M-v2`** (NVIDIA Open Model License).
  GROVER (MIT) is the pre-vetted fallback.
- Loss balancing for mixed clusters: Kendall homoscedastic uncertainty weighting.
  Mandatory: log per-task logσ_t trajectory. Preventive: stratified batches.
  Fallback: fixed weight for a persistently unstable task.
- Calibration: temperature scaling (GNN), Platt (XGBoost baseline).
- Uncertainty CORE: 5-seed ensemble bands + k-NN AD (5-NN Tanimoto ECFP4,
  per-endpoint 90th-pctile threshold). Conformal prediction = Post-MVP.
- Featurization (`ml/featurize/`, all built Run 3, all batched + deterministic +
  `cache_key()`-tagged): `standardize` (`mars-standardizer-v1`) → `graph`
  (`mars-graph-v1`, atom 42-D / bond 10-D, chirality = explicit 4-bin one-hot) →
  `fingerprints` Morgan (`mars-morgan-r2-2048-chirality-v1`, **useChirality=True**)
  → `descriptors` (`mars-rdkit2d-v1`, 217 RDKit 2D, frozen list + SHA drift guard,
  non-finite surfaced not imputed) → `conformers` (`mars-etkdgv3-mmff94-...-v1`,
  ETKDGv3 + MMFF94/UFF fallback, lowest-of-10, deterministic seed, maps to
  `ConformerResponse`). Single batch entry: `featurize_batch()` in
  `ml/featurize/pipeline.py` — standardizes ONCE, one provenance bundle per call.
  On-disk `FeatureCache` (`ml/featurize/cache.py`): key = `sha256(stage ␟
  stage.cache_key() ␟ std_smiles)`; `<stage>/_config.json` records every config
  + lib versions; incompatible config → recompute, never silent reuse.
- **Serving: Google Cloud Run** (backend + async worker; `min-instances=0`).
  Async batch = **Cloud Tasks → Cloud Run worker endpoint** (no Celery).
  Everything else free-tier (Neon, Upstash, Vercel, R2, Resend). $0 at demo scale.
- Auth: **server-side Redis sessions, NOT JWT** (`session:{token}->user_id`,
  sliding 7d TTL). Turnstile on registration only.
- Checkpoint = model + optimizer + LR scheduler + **Python/NumPy/PyTorch RNG
  state**, synced to Cloudflare R2. Mandatory (lab A100 sessions get preempted).
- `/predict` fast/cheap; 3D conformers + explainability computed lazily.
- Redis cache key includes **serving model version**. 48h TTL. 24h batch upload
  retention. Retraining use = per-upload opt-in only.
- Explainability (Module 6) = Post-MVP: Integrated Gradients, atom-level →
  functional-group aggregation, dual validation.
- Training: lab A100s primary (personal research permitted). **No paid compute
  anywhere, even as a fallback** (maintainer directive 2026-08-30). Fallback =
  free-tier cloud notebooks (Kaggle 30 GPU-hr/wk P100/T4; Colab free T4). 16 GB
  free-tier VRAM < KERMT's recommended 32 GB → grad-checkpointing + small batch;
  multi-task cluster runs may have to wait for a lab A100 session. Whole
  training + ablation budget is ~185 GPU-hr / **$0**.
- ~~`documentation/` stays git-untracked~~ — **superseded 2026-09-18 (`1c252ac`)**:
  the whole `documentation/` tree (AIMS, blueprint + archive, status, technical
  reference) is now git-TRACKED. AIMS files are therefore part of review and
  should be updated in the same session as the work they describe.

## Open pre-flight items before/within M1–M2

- **B-6:** ✅ RESOLVED 2026-08-30 (M1 Run 1). `ml/data/acquire.py` implemented;
  all 15 datasets acquired via PyTDC 1.1.15; `ml/data/metadata/datasets.lock.json`
  written + verified (re-hash + cross-run determinism).
- **CF-M1-1:** hERG endpoint→dataset choice deferred to Run 2 EDA; blueprint
  Module 1 §4 wording fix proposed (`status/mars-status_M1.md` §4), not applied.
- **CF-M1-2:** PPBR_AZ `single_pred` N (1,614) ≠ its TDC benchmark split N (2,790);
  resolve before PPB standardization/splitting in Run 2.
- **DILIst:** not a TDC dataset — Run 2 needs the FDA/NCTR DILIst file + its own
  provenance record.
- **B-7 / CF-8:** verify KERMT can do acceptable-latency **CPU inference** (Module
  10 assumes CPU-only serving); if not, Module 10 serving tier changes.
- **CF-8:** confirm which checkpoint `NV-KERMT-70M-v2` actually is (base
  masked-pretrain vs contrastive-hybrid); smoke-finetune on a 16 GB free-tier
  card (Kaggle P100/T4) with grad-checkpointing to confirm the memory-optimised
  path works before depending on it for anything time-critical.
- **CF-5:** ✅ RESOLVED 2026-08-30 (M1 Run 1). `provenance.py` + `utils/seed.py`
  torch imports made lazy; guard test `ml/tests/test_provenance_cpu_only.py`.
  `set_global_seed()` now returns a small record and no longer needs torch.
