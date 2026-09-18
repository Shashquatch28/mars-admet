# next_steps.md

_Last updated: 2026-09-17 (M3 Serving/Auth/Batch/Infra session — see below).
Active milestone: M3. M2 status unchanged (still no production training runs)._

## Immediately

- User to review and commit this session's M3 work manually (see
  `context.md`'s git-state note for the full file list). AI does not commit.
- M2's production XGBoost sweep (0/70 runs) and KERMT pre-flight are still
  both outstanding and untouched by M3 — M3 was scoped and executed
  independently per the session's own instructions (don't mix M2 GPU work
  into M3 serving work).
- The full M1 reference is `documentation/MARS_M1_TECHNICAL_REFERENCE.md` —
  cite it, don't re-derive.
- No production XGBoost runs have been fired yet (0 of the planned 70 = 14
  endpoints × 5 seeds). This is the next real decision point, not a code task —
  see "Next" at the bottom of the M2 section.

## M1 — Data & Featurization — ✅ COMPLETE 2026-08-30

All 4 runs done (`status/mars-status_M1.md`, `MARS_M1_TECHNICAL_REFERENCE.md`).
Everything below in this section is kept for reference; nothing here is
outstanding. Deferred-by-design: PPB all-species ablation processing, KERMT
graph-schema adapter (M2 pre-flight), full-scale 3D conformer population
(on-demand).

### 1. Module 1 — Data pipeline (`ml/data/`)

1. ✅ **Acquire (Run 1)** — done as above.
2. ✅ **Standardize (Run 2)** — `ml/featurize/standardize.py`; batched; deterministic; defined stereo preserved; 18 tests. Version `mars-standardizer-v1`.
3. ✅ **EDA pass (Run 2)** — `ml/data/eda.py`; per-endpoint validity/dup/conflict/stereo/scaffold report at `ml/data/eda/…/`.
4. ✅ **Dedup / conflict resolution (Run 2)** — `ml/data/dedup.py`; EDA-gated tiered policy; small-dataset override (DILI); 12 tests.
5. ✅ **Scaffold split (Run 2)** — `ml/data/split.py`; TDC benchmark adopted for 13 endpoints; deterministic Murcko split for hERG_Karim; SMILES-level leakage is a hard failure; adopted-benchmark scaffold overlap surfaced honestly; 5-seed CV utility ready.
6. ✅ **Calibration split (Run 2)** — 10% floor 50, scaffold-aware, seed=42, isolated from test — asserted at prepare-time + in tests.
7. ✅ **DILIst augmentation (Run 2)** — DILIPredictor MIT gold standard; 57 test-set overlaps dropped; 6 tests including a bit-identity test on the test set.
8. ✅ **Self-audit hooks (Run 2)** — `assert_no_leakage` + integration tests in `test_prepare_outputs.py` cover every processed dataset dir.
9. ✅ **Licensing record (Run 1)** — `ml/data/LICENSES.md` written: all 14
   CC BY 4.0 (per-dataset `license_ref` in the lockfile), DILIst public-domain
   17 USC §105, PharmaBench dropped (CC BY-NC-ND). Module 1 §7.

### 2. Module 3 — Featurization pipeline (`ml/featurize/`)

Build as a batched pipeline (vectorized/parallel over a list of molecules — this
is a primary workflow, not an edge case):

1. ✅ Stage 1 standardization (Run 2) — `ml/featurize/standardize.py`.
2. ✅ Stage 2 molecular graph representation (Run 3a) — `ml/featurize/graph.py`.
   Chirality tags EXPLICIT (4-bin one-hot, `CHI_UNSPECIFIED` is bin 0 = never
   fabricated). Portable schema; KERMT adapter deferred to M2 pre-flight per
   the KERMT decision.
3. ✅ Stage 3 ECFP/Morgan (Run 3a) — `ml/featurize/fingerprints.py`. r=2 /
   2048-bit / `useChirality=True`. Enantiomers verified distinguishable
   (Tanimoto 0.71 for L/D-alanine).
4. ✅ Stage 4 RDKit 2D descriptors (Run 3b) — `ml/featurize/descriptors.py`.
   217 (RDKit 2026.3.5), frozen sorted list + `DESCRIPTOR_SET_SHA` drift guard.
   Non-finite (Ipc overflow etc.) surfaced via `finite_mask` + per-row dict,
   NOT imputed — imputation is a Module 4 decision.
5. ✅ Stage 5 3D conformer (Run 3b) — `ml/featurize/conformers.py`. ETKDGv3 +
   MMFF94 (UFF fallback), lowest-of-10, deterministic `random_seed`, energy +
   force-field recorded, `to_contract_dict()` → `ConformerResponse`. Failure =
   typed record, never a fabricated conformer.
6. ✅ Batched façade (Run 3b) — `ml/featurize/pipeline.py` `featurize_batch()`:
   standardize once, each stage's batch fn once, one provenance bundle.
7. Undefined stereo not fabricated — locked into Stage 2 (test) + Stage 3
   (config default) + Stage 5 (ETKDG is stereo-aware; chiral tag stays unset).
8. Feature/conformer on-disk caching with config-versioned keys — **Run 4**
   (every stage already exposes `cache_key()`).

### 3. Tracking wiring (do alongside, not after)

- Every M1 artifact-producing step logs provenance: input dataset id + version +
  hash, standardization/preprocessing version, code git SHA, package versions,
  seed. Use `ml/tracking/` — extend it, don't add parallel logging.
- Fix **CF-5** (lazy numpy/torch import in `provenance.py`) so CPU-only runs work.
- No W&B runs for debugging iterations — only meaningful records.

### M1 tests to add

- Standardization: known salt → parent; invalid SMILES → clear error;
  stereocenter preserved through normalization.
- ECFP: two enantiomers → **different** fingerprints (useChirality on).
- Split: zero scaffold overlap train vs test; 5 seeds reproducible;
  post-augmentation overlap check catches an injected leak.
- Featurization: batched call over N molecules == N single calls (order + values).
- Conformer output validates against `ConformerResponse`.

## M2 — Modeling (active milestone). Blueprint Module 4 + Module 5.

### Run 1a — COMPLETE 2026-08-31

New files:
- `ml/models/__init__.py`, `ml/train/__init__.py`, `ml/eval/__init__.py`, `ml/configs/__init__.py`
- `ml/models/base.py` — `MARSModel` ABC (fit/predict/save/load + model_id/task_type)
- `ml/eval/metrics.py` — `ClassificationMetrics`, `RegressionMetrics`, `compute_metrics`, `aggregate_seed_metrics`, `expected_calibration_error`
- `ml/configs/experiment_config.py` — `ExperimentConfig` dataclass, `FIXED_SEEDS=(0,1,2,3,4)`, `run_name()`
- `ml/data/loaders.py` — `EndpointData`, `load_endpoint`, `load_manifest`, `list_available_endpoints`; handles augmented DILI, split isolation enforced by tests
- `ml/tracking/experiment.py` — `start(run_tags=...)` extension for M2 metadata

Tests: 69 new (test_metrics, test_loaders, test_experiment_config), 288 total green, 14 skip, ruff clean.

### Run 1b — COMPLETE 2026-08-31

New files:
- `ml/models/xgboost_model.py` — `XGBoostModel` (descriptor 217-D + Morgan 2048-D features;
  `inf`/float32-overflow → nan before XGBoost 3.x QuantileDMatrix; classification →
  `predict_proba`, regression → `predict`; `save`/`load_with_cache`)
- `ml/train/train_xgboost.py` — `train_one_seed`, `train_xgboost_all_seeds`, `aggregate_results`;
  scaffold-based 5-seed CV; calibration split never touched during training; early stopping
  conditional on eval_set presence (XGBoost 3.x requirement)
- `ml/train/run_xgboost_baseline.py` — CLI entry point (one endpoint × one seed)
- `ml/requirements-m2.txt` + `requirements-m2.lock.txt` (xgboost==3.2.0)

Tests: 20 new (test_xgboost_model.py), 308 total green, 14 skip, ruff clean.

### Run 2a — COMPLETE 2026-09-16

New files:
- `ml/eval/calibration.py` — `PlattCalibrator` + `fit_platt_calibrator` (XGBoost;
  1-D logistic regression on calibration-split predictions, per blueprint's
  Platt-over-isotonic preference for tabular models); `TemperatureScaler` +
  `fit_temperature_scaler` (KERMT stub — interface-complete, validated with
  synthetic logits only since KERMT doesn't exist yet; scalar T fit via
  `scipy.optimize.minimize_scalar` on NLL, no torch dependency)
- `ml/eval/applicability_domain.py` — `ADIndex`, `build_ad_index`, `query_ad`,
  `bulk_tanimoto_distance` (vectorized popcount-via-matmul Tanimoto distance
  matrix); 5-NN Tanimoto/ECFP4, threshold = 90th percentile of the training
  set's own leave-one-out 5-NN distances, per-endpoint, no calibration split
  needed (blueprint Module 5 CORE)

Tests: 32 new (test_calibration.py incl. a calibration-split-isolation
integration test against real trained XGBoost + M1 AMES data;
test_applicability_domain.py incl. integration test against real DILI data).
340 total green, 14 skip, ruff clean.

### W&B wiring — COMPLETE 2026-09-16

`_netrc` credentials from M0 setup (2026-08-30) still valid — verified via a
read-only `wandb.Api().viewer` call (no run created). `wandb==0.29.0` installed
into `ml/.venv` (was root-venv-only before). Nothing further needed from the
user; production runs will show up in the `mars-admet` W&B project automatically.

- `ml/tracking/experiment.py` — `ExperimentRun.provenance` now stored as an
  attribute (was a local var in `start()`), so callers can reuse it for W&B init
- `ml/train/train_xgboost.py` — `train_one_seed`/`train_xgboost_all_seeds` gained
  `use_wandb: bool = False` (opt-in at this layer — keeps ad-hoc/test calls from
  creating dashboard noise). A W&B init/auth failure is caught, warned, and never
  fails the underlying training run (local ExperimentRun stays authoritative).
  `SeedResult.wandb_url` added.
- `ml/train/run_xgboost_baseline.py` — the actual production CLI entry point
  defaults W&B **ON**; `--no-wandb` opts out. This is the answer to "don't
  accidentally miss a production run."
- `ml/requirements-m2.txt` + lock — added `wandb==0.29.0`

Tests: 4 new (`test_train_xgboost_wandb.py`), all mock `wandb.init` — no real
network calls or dashboard runs created by the test suite (project convention:
"no W&B runs for debugging iterations").

### Run 2b — COMPLETE 2026-09-16

New files:
- `ml/eval/evaluate.py` — `EvaluationReport` + `build_evaluation_report`; turns
  `eval.metrics.aggregate_seed_metrics`'s in-memory dict into a durable,
  reloadable artifact tied to endpoint/model_family/prep_id/seeds/run_ids
- `ml/eval/leakage_audit.py` — 10 `LeakageCheckResult` functions (6 always-run
  split checks + 2 always-run per-seed-CV-fold checks + 2 optional checks for
  AD index / calibrator isolation) + `run_leakage_audit` orchestrator +
  `assert_no_leakage`. Each check verified to both pass on clean data AND fail
  on deliberately injected leakage (not just trivially green)
- `ml/eval/tdc_comparison.py` — `TDCComparisonResult` + `build_tdc_comparison`;
  comparability flag is fully data-driven from each dataset's own
  `provenance["split_method"]` (`adopt_benchmark` vs `scaffold`) — no hardcoded
  endpoint names. Does NOT fetch or hardcode live TDC leaderboard numbers
  (external, changing resource) — `TDCBenchmarkEntry` is a manual-lookup record

Tests: 46 new (test_evaluate.py, test_leakage_audit.py, test_tdc_comparison.py),
incl. integration tests against real AMES (comparable) and hERG_Karim
(NOT comparable, self-generated split — confirmed against real provenance.json).

**Full suite after Run 2b + W&B wiring: 386 passed, 14 skipped, 0 failed, ruff
clean.** Root-venv contracts/api suite unaffected (12/12 still passing).

### Production XGBoost sweep — ✅ COMPLETE 2026-09-17

**70/70 runs completed, 0 failed.** 14 endpoints × `FIXED_SEEDS=(0,1,2,3,4)`,
~172 min total CPU wall-clock (largest endpoints — hERG/CYP series/AMES/
solubility, 5.8k–10.5k compounds — ran several minutes each; smaller
endpoints tens of seconds). Preflight (`ml/train/preflight_sweep.py`) →
pilot (`solubility_logs` seed 0) → full sweep
(`ml/train/run_production_sweep.py`) → verification
(`ml/train/verify_sweep.py`), all per the M2 execution rules (CPU-only,
no KERMT, exact `FIXED_SEEDS`, no fabricated results).

**Outputs, all real and verified:**
- `ml/artifacts/<endpoint>/seed_{0..4}/` — 70 real XGBoost model dirs,
  every one reload-tested (`XGBoostModel.load_with_cache` + a smoke
  prediction on "CCO", finite output) via `verify_sweep.py`
- `ml/artifacts/<endpoint>/ad_index/` + `calibrator.json` (classification
  endpoints only) — built from real training data, not placeholders
- `ml/runs/evaluations/<endpoint>.json` — 14 `EvaluationReport`s, all
  reload correctly, 5 unique seeds/run_ids each
- 70/70 real W&B run URLs logged to project `mars-admet`
- `ml/serve/ModelRegistry.available_endpoints()` → all 14 (was 1 —
  `hia_absorption` only). **Container-verified**: `POST /predict {"smiles":
  "CCO"}` against the live `docker compose` `api` service returns real
  (`model_id != "stub-v0"`) predictions for all 14/14 endpoints.

**Aggregated 5-seed metrics (mean ± std)** — full table in `decisions.md`'s
2026-09-17 sweep entry. Headline: CYP3A4 AUROC 0.943±0.003, Pgp 0.953±0.004,
CYP2D6 0.913±0.003, CYP2C9 0.901±0.006, hERG 0.836±0.007, AMES 0.823±0.009,
BBB 0.684±0.022, DILI 0.636±0.034; regressions solubility MAE 0.726±0.010,
lipophilicity 0.519±0.010, caco2 0.336±0.010, clearance 19.2±1.2, PPB
7.49±0.12. **Flagged anomaly, not silently accepted**: HIA AUROC = 1.000 ±
0.000 across all 5 seeds — plausible (HIA's val folds are small and
severely imbalanced, 410:51) but suspiciously perfect; treat with caution
before citing, don't assume it's simply "the best endpoint."

**Two real bugs found in NEW tooling during this pass** (not pre-existing
M2 infra — see `mistakes.md` for full detail): the preflight script
initially misclassified 6 endpoints' benign, already-documented (M1 Run 2)
RDKit-vs-TDC scaffold-bucket noise as blocking leakage; the sweep driver
had the identical gap specifically for augmented DILI's missing
`split_method` provenance field. Both fixed; the DILI sweep summary entry
was corrected post-hoc (no re-training needed — the underlying leakage
audit was already clean apart from the same documented benign check).

### KERMT integration — Phase 3+ underway (2026-09-18, RTX A4000 workstation)

GPU workstation available now (RTX A4000 16GB) — the 2026-09-17 GPU blocker
is lifted. See `decisions.md`'s 2026-09-18 entry for full detail; summary:

- `kermt:latest` docker image build in progress/complete via
  `~/mars-work/kermt-src/agent/scripts/kermt_container.sh ensure_image`
  (KERMT vendored outside the mars-admet repo, referenced via
  `MARS_KERMT_REPO` env var — see decisions.md for why: container isolation,
  not a hand-installed venv, because `cuik_molmaker` is an unconditional
  import in `kermt/data/molgraph.py` — genuinely required, not opt-in).
- Checkpoint + vocab files downloaded and SHA256-hashed:
  `ml/data/metadata/kermt_checkpoint.lock.json` (tracked),
  binaries at `ml/data/checkpoints/kermt/NV-KERMT-70M-v2/` (gitignored).
- `ml/featurize/kermt_adapter.py` + `ml/models/kermt_model.py` implemented;
  13 adapter unit tests passing (`ml/tests/test_kermt_adapter.py`); full
  `ml/tests/` suite re-run — 283 passed, 4 pre-existing failures unrelated
  to KERMT (missing `ml/data/raw/` on this machine, same as before this
  session), 50 skipped (torch-gated tests, no regression).
- Smoke tests 2-6 (checkpoint load, forward, backward, tiny finetune, MARS
  eval integration) **not yet run** as of this update — blocked on the
  docker image finishing its build, then blocked on real M1 data existing
  on this machine (`ml/data/raw/` and `ml/data/processed/` are both empty
  here — M1 was acquired on a different machine and the directories are
  gitignored by design; acquisition needs to be re-run on this workstation
  before a real-data finetune, per `ml/data/acquisition/README.md`).
- **New, verified blocker for mixed-type clusters** (Metabolism,
  Absorption & Distribution): KERMT's stock CLI takes one `--dataset_type`
  per run, so a single call can't jointly finetune classification +
  regression targets. Not resolved — three options logged in decisions.md,
  needs a maintainer call. Same-type clusters (Toxicity: hERG+AMES) and
  all 14 single-task runs are unaffected.

<details><summary>Original 2026-09-17 Phase 1-2 audit (superseded above, kept for history)</summary>

Read-only audit only — no training, no installs. Gates single-task/
multi-task GNN work (Run 3+); independent of the complete XGBoost sweep.
Full report given to the user; key resolved/open items below. See
`decisions.md`'s 2026-09-17 KERMT pre-flight entry for the full detail.

**Resolved this pass:**
- Checkpoint identity (item 1 below) — it's the **contrastive v2.0**
  variant (`kermt_contrastive_v2.0.pt`), confirmed via the HF repo's own
  file listing; no base variant is hosted there at all.
- Source code location: separate repo, `github.com/NVIDIA-BioNeMo/KERMT`
  (v2.0.0 tag) — real CLI already exists (`main.py {finetune,predict,
  fingerprint,eval}`), so MARS would integrate against that CLI/package
  rather than writing model code from scratch.
- Official env (`environment.yml`) hard-pins `pytorch-gpu=2.9.1` +
  `cuik_molmaker` (CUDA-native) + a CUDA 12.6 Docker base — GPU-required
  **as officially documented**. Partially offset: the CLI itself exposes
  `--no_cuda` and makes `--use_cuikmolmaker_featurization` opt-in
  (default off), so a CPU-only attempt (non-GPU `torch` + the plain
  `kermt`/`task` Python packages) is plausible but **genuinely untested**.

**Still open, unresolved:**
- Item 2 below (CPU inference latency) — NVIDIA's own model card documents
  zero CPU test hardware or latency numbers; still an open risk for
  Module 10's CPU-only Cloud Run serving assumption.
- Items 3-4 below — untouched; require either installing a CPU-only torch
  build on this laptop (a real environment change, not done without
  explicit go-ahead) or lab A100 / free-tier GPU notebook access.

**This machine (2026-09-17): no GPU, no torch, no transformers installed
anywhere.** Only Intel Arc integrated graphics (no CUDA path) — matches
the blueprint's own stated laptop spec. 15.5GB RAM, 14-core CPU, 139GB
free disk (enough for the ~282MB checkpoint if/when downloaded).

Featurization is DONE — consume `ml/data/processed/<prep_id>/` +
`ml/featurize/featurize_batch` / `FeatureCache`. Do NOT re-standardize processed
SMILES (they are canonical fixed-points).

</details>

### M2 pre-flight (live checklist, updated 2026-09-18 — see decisions.md)

1. ✅ Confirm exact identity of `nvidia/NV-KERMT-70M-v2` (base vs contrastive)
   — **RESOLVED 2026-09-17: contrastive v2.0.** ✅ Checkpoint + 3 vocab files
   downloaded and SHA256-hashed 2026-09-18 into
   `ml/data/metadata/kermt_checkpoint.lock.json`.
2. Verify KERMT **CPU inference** latency — **still open**, now moot for the
   GPU-workstation smoke tests but still gates Module 10's CPU-only Cloud
   Run serving assumption. Resolve **B-7 / CF-8** separately from this GPU work.
3. Smoke-finetune KERMT on the RTX A4000 (16 GB) with gradient checkpointing +
   small batch + gradient accumulation. **In progress 2026-09-18** — wrapper
   (`ml/models/kermt_model.py`) built and unit-tested; Smoke tests 2-6 (ckpt
   load, forward, backward, tiny finetune, eval integration) blocked on (a)
   the `kermt:latest` image finishing its build and (b) real M1 data existing
   on this machine (currently absent — see decisions.md 2026-09-18 entry).
4. ~~Add KERMT's featurizer package to `ml/requirements.txt`~~ — **superseded**:
   KERMT is NOT added to `ml/.venv`/`ml/requirements.txt` at all (container
   isolation instead, see decisions.md). The Stage 2 graph schema
   (`mars-graph-v1`) stays portable/unlocked; the "adapter" that exists is a
   SMILES/CSV contract (`ml/featurize/kermt_adapter.py`), not a schema lock,
   since KERMT re-derives its own graph internally from SMILES.
5. **New:** decide how to handle KERMT's mixed-classification/regression
   multi-task limitation for the Metabolism and Absorption & Distribution
   clusters (decisions.md 2026-09-18 entry has 3 options) — needs a
   maintainer call, not resolvable by further inspection alone.
6. **New:** re-run M1 acquisition (`ml/data/acquire.py`) on this workstation
   — `ml/data/raw/` and `ml/data/processed/` are empty here (gitignored by
   design; M1 was originally run on a different machine). Needed before any
   KERMT finetune can use real MARS endpoint data rather than synthetic
   smoke-test data.

## M3 — Serving & Infra (active milestone, started 2026-09-17)

Blueprint Module 8 (API/Serving) + Module 13 (Auth & Persistence) +
Module 10 (Infra/Deployment). Full audit at kickoff:
`documentation/AIMS/module_milestone_map.md`. Real work landed, not stubs —
see `context.md`'s M3 bullet for the full rundown. Summary of what's done:

- Module 8: real per-endpoint model registry (`ml/serve/`) wired into
  `/predict` with honest per-endpoint stub fallback; `/compare`; `/batch/predict`
  (CSV, interactive + async tiers) + `/batch/progress` (SSE) + `/batch/results`;
  Redis caching (48h) + per-IP rate limiting (60/min), both fail-open.
- Module 13: full Postgres schema + migration, bcrypt auth, Redis sessions,
  password reset, saved molecules/reports (snapshot-on-save), cascading
  account deletion. 25 integration tests against real Postgres+Redis.
- Module 10: `api/Dockerfile` extended with the real ml inference stack;
  container-tested locally (`docker compose up`) with a real prediction
  from a real trained artifact. Cloud deploy NOT done (needs GCP creds +
  explicit approval).

### Resolved in the 2026-09-17 final CPU-side pass (were open, now done)

- ~~SDF batch upload~~ — implemented for real (`api/app/services/sdf_parser.py`,
  RDKit `ForwardSDMolSupplier`); 501 (not a fabricated success) when rdkit
  isn't installed in the running process. Container-verified with a real
  ethanol SDF end-to-end.
- ~~Module 3 Stage 1 SMILES validation not enforced at the API boundary~~ —
  now enforced (422) via `prediction_service.predict()` raising `ValueError`
  on invalid SMILES, when the real ml stack is present. Container-verified.
- ~~`GET /molecule/{id}/3d` not implemented~~ — found during this audit
  (M3-scoped, CPU-only, data dependency already complete since M1); now
  real, cached, container-verified end-to-end (real ETKDG+MMFF94 conformer
  for ethanol). Fixed a real bug found while testing it: the id->smiles
  registration only fired on a prediction-cache miss, so cached predictions
  (including pre-existing ones) permanently 404'd — fixed to register on
  both hit and miss.
- Added along the way (not originally tracked as gaps, found during the
  audit): `/health/ready` readiness check (DB+Redis), a startup warning for
  an insecure default `SECRET_KEY`, `docker-compose.yml` `api` healthcheck,
  and a verified-reversible Alembic migration (`downgrade -1` / `upgrade head`).

### Still open within M3 — all require external credentials/approval, or are explicitly out of CPU-only local scope

1. **`CloudTasksQueue` is a documented placeholder, not wired up** —
   `LocalTaskQueue` (in-process asyncio) implements the identical job
   lifecycle contract for local dev/single-instance use; swapping in real
   Cloud Tasks needs `GCP_SA_KEY_JSON` + a deployed Cloud Run worker
   endpoint (both M3/M10 deployment items, not code-side gaps).
2. **Batch result storage uses Redis, not R2/MinIO** — MinIO now starts
   cleanly in docker-compose (`quay.io/minio/minio`, see mistakes.md) but
   isn't wired to any code path; `api/app/services/batch_results.py`
   documents this as a deliberate local-dev simplification. Real R2 wiring
   is a Cloudflare-credential item, not CPU/GPU-gated, but wasn't judged
   "required for M3 local completion" — the Redis stand-in already proves
   the batch lifecycle contract end-to-end.
3. **`BatchPredictOptions` fields are passed as query params, not a
   multipart form-field group** — `retrain_opt_in` is accepted nowhere yet
   (no separate opt-in storage pipeline exists); `smiles_column`/`endpoints`
   work as query params today, not matching the contract's original
   form-field sketch exactly. Worth reconciling before frontend (M4) build
   against this route. Not blueprint-mandatory infrastructure — a contract
   polish item.
4. **Real cloud deployment (Cloud Run/Neon/Upstash/R2) not started** —
   needs `GCP_PROJECT_ID`/`GCP_SA_KEY_JSON`/Neon+Upstash credentials and
   explicit maintainer go-ahead before anything is actually deployed
   (M3 execution rules: no paid-service surprise).
5. **CI now runs real Postgres/Redis service containers** for the
   auth/persistence/batch integration tests (`.github/workflows/ci.yml`) —
   not yet actually exercised on a real PR/push since this branch's changes
   are uncommitted; worth confirming once committed and pushed.

**M3 is now locally/container complete for everything that doesn't need
GCP credentials, paid infra, or M2's production model artifacts.** See
`decisions.md`'s 2026-09-17 "final pass" entry for the full classification.

## Not now (later milestones — do not start)

M4 frontend/3D/explainability/MMP, M5 eval matrix. Listed only so they're
not mistaken for M3 work.
