# next_steps.md

_Last updated: 2026-09-24 (GPU training has started: DILI seeds 0–4, `toxicity__cls` seeds 0–1 done; see the
"GPU status" bullet below). Earlier 2026-09-21 content below was written before any GPU training.
Active milestone: M2 (KERMT/GNN track). M3 is locally/container complete.
Branch: `milestone/m2-kermt`. The lab-session checklist is the last section of
"Immediately" below._

## Immediately

- **GPU status (2026-09-24) — supersedes any "no GPU training" wording below.** Real KERMT Tier-0 runs on the
  RTX A4000 workstation, prep `20260918T090433Z`, harness defaults: `dili_standalone__cls` seeds 0–4 complete
  (2026-09-22); `toxicity__cls` seed 0 complete (2026-09-22) and **seed 1 complete + verified PASS
  (2026-09-24)**; `toxicity__cls` **seeds 2–4 pending**, five-seed aggregation pending (toxicity is NOT
  complete until then). Seed-1 record: `documentation/status/kermt_gpu_session_2026-09-24.md` and
  `documentation/status/kermt_tier0_results/toxicity__cls/seed1/`. W&B (`shashquatch/mars-admet`) holds run
  config, validation + calibration metrics (**not test metrics**) and, since 2026-09-24, the final `model.pt` of all 7
  completed runs as hash-verified artifacts `kermt-{dili,toxicity}-seed<N>:v0` (references + retrieval:
  `documentation/status/kermt_tier0_results/README.md`; results for all 7 runs are tracked there too). Git holds
  no model binaries; full run dirs (incl. `last_checkpoint.pt`) stay on `CL502-18` (`ml/runs/` is gitignored). Runs are launched one seed at a time, verified with
  `s_verify.py` before the next.
- **The KERMT mixed-type cluster blocker is RESOLVED as a decision** (see
  `decisions.md`, 2026-09-20). Three-tier ladder approved; stock KERMT is NOT
  forked. Implementation is in progress — see "M2 — mixed-type clusters" below.
- **CPU-side prep is DONE as of 2026-09-20.** Built and tested without a GPU:
  `ml/configs/clusters.py`, `ml/data/cluster_loaders.py` (leakage-safe wide
  table), `ml/eval/cluster_eval.py`, `ml/featurize/ordinal.py` (Tier 2 codec),
  `ml/train/train_kermt_cluster.py` (Tier 0 harness),
  `ml/train/preflight_clusters.py` (the zero-GPU gate, already run), the four
  `kermt_model.py` changes, and 65 new CPU-only tests. Repo is ruff-clean.
  **The next lab session should go straight to GPU work.**
- **Two gate results are already in** (see below and `decisions.md`):
  `absorption_distribution` and `toxicity` arms are cleared to train;
  **`metabolism__cls` is proceeding provisionally under Option A** (2026-09-20
  maintainer call: keep official TDC splits, keep strict cluster-level leakage
  prevention, accept the reduced pool, keep single-task CYP baselines on their
  full original splits); Tier 2's `n_bins=16` is chosen.
- **Calibration (2026-09-21):**
  1. ✅ **WIRED (CPU-verified, GPU-gated).** `fit_temperature_scaler` now has a
     production call site: `eval/cluster_calibration.py::calibrate_endpoints`,
     called from `train/train_kermt_cluster.py::train_one_seed`. Fit on the held-out
     calibration split only; test set scored afterwards, raw and calibrated;
     per-seed diagnostics persisted. 43 new CPU tests (+8 diagnostics tests from
     2026-09-20 = 51 on this path); the isolation property was mutation-tested. **What is NOT verified:** anything about real KERMT logits —
     only a `StubKermt` test double has ever run through this path.
  2. **OPEN — the calibration split is not label-representative** (`mistakes.md`) — a
     pre-existing M1 property affecting all 9 classification endpoints and the
     already-promoted XGBoost calibrators, worst at `cyp3a4_inhibition`
     (train_val 0.4093 vs calibration 0.1129). Changing the split policy is an M1 data
     decision and was **not** taken.
  3. **OPEN — `hia_absorption` calibration is below the floor** after strict union
     removal: N=47, 46 positive / 1 negative (blueprint floor is 50). Its promoted
     XGBoost Platt calibrator was already fit on 49+1. Needs a maintainer call before
     A&D-cls calibration is treated as meaningful. `preflight_clusters.py` did not
     check calibration size when it "cleared" A&D-cls.
  4. **OPEN — `holdout_calibration=True` default needs sign-off.** It removes every
     calibration molecule from the KERMT training pool (`decisions.md` 2026-09-21),
     costing ~10% more labels and making KERMT's pool differ from XGBoost's.
- ✅ **DONE 2026-09-21 — XGBoost held-out TEST evaluation** (`ml/eval/heldout_evaluation.py`,
  `ml/train/evaluate_xgboost_test.py`; reports in `ml/runs/test_evaluations/`, 14 endpoints x 5
  seeds, 0 blocked; `artifacts/` and `runs/evaluations/` proven byte-unchanged). The KERMT
  comparison must use these **test** numbers, not the old validation-fold reports — they differ by
  up to +0.263 AUROC. Table in `decisions.md` 2026-09-21 (later).
- **OPEN — served XGBoost Platt calibrators degrade held-out calibration** (like-for-like on the
  calibrator's own seed 4: ECE worse on 7/9 endpoints, Brier worse on 9/9; worst hia .045→.209).
  They are what the API applies. Cause: calibration-split prior ≠ test prior. Also only ONE
  calibrator exists per endpoint (fit on seed 4). Calibration policy is out of scope so **not
  fixed** — needs a maintainer call (the API is serving these).
- **OPEN — shared cluster fold leaves tiny per-task validation sets.** `toxicity__cls` val =
  18–24 hERG labels vs ~1,810 AMES; `ppb` 42–50; `hia` 46. Epoch selection for those tasks is
  effectively unmeasured. Design decision; not changed.
- **OPEN — KERMT harness trains DILI on the base pool** (287 train) while XGBoost used the
  DILIst-augmented pool (979): −71%. Configuration mismatch; decide which the comparison uses and
  pin `use_augmented_dili` in the run config.
- ✅ **DONE 2026-09-21 — RNG capture/restore utility** (`ml/utils/rng_state.py`, 23 tests).
  **Not integrated** into any training path — see the integration points in its docstring.
- ✅ **DONE 2026-09-21 — readiness report** (`ml/train/readiness_report.py`): verdict
  `READY_FOR_GPU_SMOKE_TEST` (CPU-side scope; 4 workstation checks NOT_EVALUATED).
- **OPEN — workstation processed-data identity is UNABLE TO VERIFY (D).** Raw acquisition is
  byte-identical (15/15). Run `data/compare_prep.py fingerprint` on the workstation and
  `compare` against `ml/data/metadata/prep_fingerprint.20260830T200000Z.json`.
- **OPEN — no KERMT sweep CLI driver exists.** `train_subgroup_all_seeds` does; the
  lab snippets below call it directly. A thin CLI (subgroup, seeds, W&B on by default)
  is a small implementation gap, not a blocker.
- **Leakage first, before any GPU spend.** Cross-endpoint split leakage
  (`decisions.md` 2026-09-20, finding 1) is a correctness precondition for all
  three tiers. A cluster run that cannot prove zero train/test overlap does not
  get trained.
- The full M1 reference is `documentation/MARS_M1_TECHNICAL_REFERENCE.md` —
  cite it, don't re-derive.
- M2's production **XGBoost** sweep is COMPLETE (70/70, 2026-09-17). The
  remaining M2 scope is the KERMT/GNN track only.
- The user commits manually. **The AI must not run git write commands.**

### GPU lab session — ordered checklist (2026-09-21)

> **For the lab itself, follow `lab_session_tasks.md`** (added 2026-09-21): every command there was
> checked against the code, and it corrects two points below — on the workstation pass
> `--prep-id 20260918T090433Z` to `readiness_report.py` and do **not** pass `--workstation-fingerprint`
> (the report derives the canonical fingerprint's filename from `--prep-id`), and export
> `WANDB_ENTITY`/`WANDB_PROJECT` (nothing loads `.env`). This section is kept as the record of intent.

Verification tags: **[ran here]** executed on this laptop against the repo (with a
`StubKermt` test double where KERMT is needed — real code, real data, fake model
scores); **[recorded 9-18]** executed on the workstation on 2026-09-18 per
`status/kermt_integration_status.md`, not re-run since; **[sig-checked]** matches the
current function signatures but has not run against real KERMT. Workstation paths
(`~/mars-work/...`, `../.venv/bin/python`) are as recorded 2026-09-18.

**0. Before leaving the laptop (CPU, this machine)**
- `git status --short` — expect the M2-kermt working tree; the user commits manually
  **[ran here]**. Nothing below works on the workstation until the new modules
  (`ml/eval/cluster_calibration.py`, `ml/train/train_kermt_cluster.py`, ...) are there.
- Decide the OPEN items above (esp. HIA floor, `holdout_calibration` default, DILI pool, and what
  to do about the served calibrators). The XGBoost test evaluation is already done.
- **Commit first.** The readiness report WARNs that a dirty tree makes each run's recorded git SHA
  not describe the code that ran.
- `cd ml && PYTHONPATH=. ./.venv/Scripts/python.exe train/readiness_report.py` — expect
  `READY_FOR_GPU_SMOKE_TEST` with 4 pending workstation checks **[ran here]**.

**1. Environment on the workstation**
- `nvidia-smi` — expect RTX A4000, 16376 MiB **[recorded 9-18]**.
- `export MARS_KERMT_REPO=~/mars-work/kermt-src MARS_KERMT_IMAGE=kermt:latest`, then
  `docker image ls kermt:latest` **[recorded 9-18]**.
- `cd ~/mars-work/mars-admet/ml && PYTHONPATH=. ../.venv/bin/python -m pytest -q`
  **[recorded 9-18 for the older suite]** — expect only the 5 known
  `test_acquisition_lockfile.py` failures (3 of which should now *pass* on the
  workstation, where `raw/*/20260918T090143Z/` exists).
- `../.venv/bin/python -c "import wandb"` and confirm `wandb login` state without printing
  the key — **not established** that wandb is installed in the workstation venv.

**2. Data + checkpoint verification**
- `ls data/processed/` — expect `20260918T090433Z` **[recorded 9-18]**. **Not
  established:** that its splits are byte-identical to the laptop's `20260830T200000Z`
  (raw inputs are; 15/15 `snapshot_sha256`). Close it: `PYTHONPATH=. ../.venv/bin/python
  data/compare_prep.py fingerprint --prep-dir data/processed/20260918T090433Z --out ws.json`
  then `... compare --a data/metadata/prep_fingerprint.20260830T200000Z.json --b ws.json`;
  expect `A_BYTE_IDENTICAL` (or `B_...` if only formatting differs) **[ran here on both local
  snapshots; not yet on the workstation]**. Manifests can't be diffed — they embed absolute paths.
- `PYTHONPATH=. ../.venv/bin/python train/readiness_report.py --target workstation
  --workstation-fingerprint ws.json` — evaluates the 4 workstation-only checks for real
  (checkpoint sha, KERMT commit, Docker image id, GPU/VRAM) **[ran here with `--target laptop`;
  the workstation branch is unit-tested with mocks only]**. Record the printed Docker image id: no
  pinned expected id exists anywhere in the repo.
- `sha256sum data/checkpoints/kermt/NV-KERMT-70M-v2/kermt_contrastive_v2.0.pt` — expect
  `e9e6649bc96503fbdb3023e312764ecbbbafd686d9a62865a1fec9466cea6be3`
  (`ml/data/metadata/kermt_checkpoint.lock.json`) **[recorded 9-18]**.
- `PYTHONPATH=. ../.venv/bin/python train/preflight_clusters.py --prep-dir
  data/processed/20260918T090433Z` **[ran here on the laptop's snapshot]** — re-confirms
  the leakage cost and the Tier-2 bin choice on the workstation's snapshot. The
  `xgb_mae` columns will read `n/a` unless `runs/evaluations/` was copied over.

**3. KERMT smoke test (unchanged from 9-18)**
- Re-run the tiny AMES fine-tune in `status/kermt_integration_status.md` §11
  **[recorded 9-18]**: expect 3 epochs, `loss_train` falling, `auc_val` ≈ 0.72, reload
  bit-identical.

**4. Calibration smoke test + first real run — `dili_standalone__cls`**
Smallest classification arm (328-molecule training pool after the calibration holdout,
of which the fold splits train/val; 50-row calibration set with 13 positives), so it exercises train → calibrate → test →
persist in minutes. **[sig-checked and executed here with `StubKermt`]**:

```python
from pathlib import Path
from configs.clusters import all_subgroups
from configs.experiment_config import ExperimentConfig
from data.cluster_loaders import load_cluster
from models.kermt_model import KermtConfig
from train.train_kermt_cluster import train_one_seed

PREP = Path("data/processed/20260918T090433Z")
CKPT = Path("data/checkpoints/kermt/NV-KERMT-70M-v2/kermt_contrastive_v2.0.pt")
key = "dili_standalone__cls"
spec = all_subgroups()[key]
cd = load_cluster(PREP, list(spec.endpoints), cluster_key=key)
cfg = ExperimentConfig(endpoint=key, model_family=spec.model_family, seed=0, prep_id=cd.prep_id)
res = train_one_seed(cd, spec, cfg, 0, checkpoint=CKPT,
                     kermt_config=KermtConfig(epochs=3, batch_size=16),
                     runs_dir=Path("runs"), use_wandb=False)
print(res.calibration)
```

Expected outputs under `runs/<run_id>/`: `artifacts/kermt/` (KERMT work dir),
`artifacts/model/kermt/`, `artifacts/calibration/dili_liver_injury/{temperature_scaler,
calibration_diagnostics}.json`, `metrics.jsonl` with a `val` and a `calibration+test`
record. **Inspect** `at_boundary`, `optimizer_success`, `n_negative` (expect 37 of 50),
and that `test_metrics_calibrated.auroc == test_metrics_raw.auroc`.

**5. Tier-0 runs** (`use_wandb=True` for these; every run is equal-weighted). Same snippet
with `train_subgroup_all_seeds`, then the aggregators **[sig-checked and executed here
with `StubKermt`, 5 seeds, on `dili_standalone__cls`]**:

```python
from eval.cluster_calibration import (aggregate_calibration_across_seeds,
                                      aggregate_test_metrics_across_seeds)
from eval.cluster_eval import cluster_results_to_endpoint_reports
from train.train_kermt_cluster import train_subgroup_all_seeds

results = train_subgroup_all_seeds(cd, spec, cfg, checkpoint=CKPT, runs_dir=Path("runs"),
                                   use_wandb=True)
records = [r for res in results for r in res.calibration.values()]
test_agg = aggregate_test_metrics_across_seeds(records)      # <- final numbers
cal_agg = aggregate_calibration_across_seeds(records)        # <- stability diagnostics
val_reports = cluster_results_to_endpoint_reports(
    results, cluster_key=key, model_family=spec.model_family,
    prep_id=cd.prep_id, task_types=cd.task_types)            # val-fold only
```

Arms, in suggested order (`all_subgroups()` keys): `metabolism__reg` (clearance, the
single-task baseline, no calibration), `dili_standalone__cls`, `toxicity__cls`,
`absorption_distribution__reg`, `absorption_distribution__cls` (**HIA calibration is
N=47, 1 negative — see OPEN item 3**), `metabolism__cls` (**provisional Option A**).
Each x 5 seeds. **Also required, not in that list:** the single-task KERMT baselines for
the 3 CYPs on their full original splits (Option A) — `KermtModel` supports them but no
harness path builds them yet.

**6. Equivalence gates G1-G4** — all need the Tier-1 trainer (`ml/train/kermt_mixed/`,
`models/kermt_mixed_model.py`), which **does not exist yet**. G1/G2/G3 are GPU-dependent;
G4 (Kendall math) is CPU-only and can be written first. Tier 1 becomes executable only
after Tier 0 completes and G1-G4 pass.

**7. Tier 2** — codec and zero-GPU ceiling gate are done (`n_bins=16`). Remaining, all
GPU: the ordinal-encoded stock-CLI runs and the decoded-MAE-within-15% gate. Postpone
until Tier 1 lands.

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
5. ✅ **RESOLVED 2026-09-20.** KERMT's mixed-classification/regression multi-task
   limitation for the Metabolism and Absorption & Distribution clusters —
   three-tier ladder approved, option (b) fork rejected. Full rationale in
   `decisions.md`'s 2026-09-20 entry; live work breakdown in
   "M2 — mixed-type clusters" below.
6. **New:** re-run M1 acquisition (`ml/data/acquire.py`) on this workstation
   — `ml/data/raw/` and `ml/data/processed/` are empty here (gitignored by
   design; M1 was originally run on a different machine). Needed before any
   KERMT finetune can use real MARS endpoint data rather than synthetic
   smoke-test data.

### M2 — mixed-type clusters (live work breakdown, opened 2026-09-20)

Decision + rationale: `decisions.md` 2026-09-20. **Three paths, kept strictly
distinct in code, run names and results tables — never conflate them:**

| | Path | Trained by | `model_family` |
|---|---|---|---|
| **(a)** | Stock KERMT, type-homogeneous | KERMT's own CLI, unmodified | `kermt_multitask_subgroup` / `kermt_single` |
| **(b)** | MARS-owned mixed-type training | MARS trainer importing KERMT as a library, in-container | `kermt_mixed` |
| **(c)** | Ordinalized all-classification | KERMT's own CLI, unmodified, on encoded targets | `kermt_ordinal` |

**Stock KERMT stays an untouched, pinned dependency in every tier.**

#### Shared substrate — CPU-only, blocks all three tiers

- `ml/configs/clusters.py` — cluster + type-homogeneous subgroup registry,
  **derived** from `ENDPOINT_METADATA`, never re-listed (drift-proof by test).
  Subgroup keys: `metabolism__cls`, `metabolism__reg`,
  `absorption_distribution__cls`, `absorption_distribution__reg`, `toxicity__cls`.
  Lives in `ml/configs/`, NOT `contracts/` — subgroups are a training-time
  artifact of a third-party CLI limit and must not leak into the serving contract.
- `ml/data/cluster_loaders.py` — `load_cluster(...)`: wide multi-endpoint label
  table (one NaN-able column per endpoint) over the existing `load_endpoint`,
  **plus the mandatory leakage fix**: `cluster_test = ∪ members' test rows`, then
  every `cluster_test` molecule is removed from the wide `train_val` **in all
  columns**; emits `ClusterSplitReport` quantifying the labels sacrificed; asserts
  zero SMILES and zero scaffold overlap. One **shared** fold per seed for all
  tasks (per-task folds would leak across tasks).
- `ml/eval/cluster_eval.py` — per-column decomposition of 2-D cluster predictions
  into per-endpoint metrics and per-endpoint `EvaluationReport`s, so cluster
  results stay directly comparable with the 70 completed XGBoost runs.
- `ml/configs/experiment_config.py` — new families/prefixes
  `kermt_multitask_subgroup`→`kermt_mtsub`, `kermt_mixed`→`kermt_mx`,
  `kermt_ordinal`→`kermt_ord`, plus a `variant` field so the three weighting arms
  don't collide on one run name.
- `ml/models/kermt_model.py` — **four** changes (an earlier draft said "three"):
  (1) the endpoint-homogeneity guard the docstring already claims but does not
  implement; (2) `target_names` / `target_task_types` properties;
  (3) an explicit `supports_loss_weighting = False` marker + docs recording that
  this path is **equal-weighting only** — KERMT's `run_finetune_local.py` never
  forwards `use_mtl_loss` and parses strictly, so there is no flag to add and
  asking for Kendall here must fail loudly rather than silently do nothing
  (see `decisions.md` finding 2); (4) `predict_logits()`, which unblocks
  temperature scaling for **every** KERMT classification run and does **not**
  require Tier 1.
- `ml/models/base.py` — additive `target_names` / `target_task_types` only.
  Do NOT widen `task_type` to a list.

#### Tier 0 (path a) — type-homogeneous subgroups

**Introduces MARS-side harness and CLI code only. It introduces NO new KERMT
optimization or model logic** — the training step is the existing `KermtModel`
shelling out to the stock CLI exactly as it already does.

New: `ml/train/train_kermt_cluster.py` (mirrors `train_xgboost.py`'s harness) and
`ml/train/run_kermt_subgroup_sweep.py` (production CLI, W&B on by default).

**`metabolism__reg` = `{clearance_microsomal}` is a SINGLE-TASK run, not a
homogeneous multi-task subgroup.** It is the mandatory single-task KERMT baseline
already owed for that endpoint under Module 4. It runs once under
`model_family="kermt_single"` and is cited in both roles; it must never be
reported as a multi-task cluster arm. Tier 0 therefore yields **three** genuinely
new multi-task subgroups — `metabolism__cls` (3), `absorption_distribution__cls`
(3), `absorption_distribution__reg` (4). `toxicity__cls` is already covered by the
existing pure-cluster path.

**All Tier-0 runs are equal-weighting by construction** — that is the blueprint's
mandatory fixed/equal baseline arm, and it is the only arm the stock CLI can
produce. Kendall and GradNorm for *every* cluster, pure or mixed, come from Tier 1.

**Gate to Tier 1:** subgroups complete; per-endpoint `EvaluationReport`s written;
`ClusterSplitReport` label sacrifice judged acceptable.

**✅ The sacrifice is now MEASURED (2026-09-20, zero GPU)** — run
`cd ml && PYTHONPATH=. python train/preflight_clusters.py`; results in
`ml/runs/cluster_preflight.json` and tabulated in `decisions.md`. Headline:
`toxicity__cls` 0.2%, `absorption_distribution__cls` 4.6%,
`absorption_distribution__reg` 14.6% — all fine and **cleared to train**. But
**`metabolism__cls` loses 29% of each CYP's training labels** (5,625 rows dropped),
because the three Veith CYP screens cover largely the same compound library with
three independent TDC test splits. **That one arm is blocked on a maintainer
decision** (accept the loss / keep CYPs single-task / regenerate a cluster-level
split and forfeit leaderboard comparability). Do not start `metabolism__cls` on
the GPU until that is decided; the other arms need no such call.

#### Tier 1 (path b) — MARS-owned mixed-type trainer, KERMT as a library

Staged into the run's `--data` bind mount (`/data/_mars_trainer/`) and run with
`import kermt` inside the container. **Do not extend `kermt_container.sh`** — it
lives in the un-MARS-versioned checkout, the same provenance hole that rules out
forking. Provenance: sha256 of every staged file + MARS git commit +
`KERMT_COMMIT` + in-container `pip freeze` → `trainer_provenance.json`.

`ml/train/kermt_mixed/`: `train_mixed.py`, `losses.py` (per-column BCEWithLogits
vs MSE/L1 on standardized targets; type-correct Kendall precisions `0.5*exp(-2logσ)`
regression / `exp(-2logσ)` classification; **a task with zero labeled rows in a
batch drops its entire term including `log σ_t`**), `sampler.py` (stratified
batches — the blueprint's mandated preventive fix; identical sampler across all
three weighting arms so the ablation isolates weighting), `scaling.py` (NaN-aware
per-column, train-fold only), `gradnorm.py` (ablation arm only),
`metrics_hooks.py` (JSONL → `ExperimentRun` + W&B host-side; no second tracking
system). Host side: `ml/models/kermt_mixed_model.py` — a **separate**
`KermtMixedModel`, so the stock path stays un-regressed.

**Equivalence gates — all four must pass before any mixed run is believed:**

- **G1 forward/inference parity** (~30s, no training). A Tier-0 finetuned AMES
  checkpoint loaded through `KermtMixedModel`'s inference path must reproduce the
  stock `predictions.csv` on 64 fixed molecules to 1e-5. Isolates model
  construction, featurization, two-view averaging and sigmoid placement from
  optimizer noise.
- **G2 one-epoch loss parity** (~15s). Same argv-derived args, seed 0,
  `mode="fixed"`, all weights 1.0; epoch-1 train loss within 5% of stock.
- **G3 multi-seed AUROC parity — precisely:** compares path (b) against path (a)
  on **classification-only data, where both paths can legitimately run the
  identical job** — that is the point of the gate, isolating trainer
  implementation from mixed-type effects. Datasets: `ames_mutagenicity`
  (single-task) and `toxicity__cls` (hERG + AMES). Seeds: `FIXED_SEEDS` 0–4,
  identical folds from `five_seed_train_val_folds`, identical hyperparameters,
  Tier 1 in `mode="fixed"` with all weights 1.0. Quantity: **validation-fold
  AUROC** from `ml/eval/metrics.py::compute_metrics`, computed host-side by MARS
  for both paths (KERMT's own `test_result.csv` is never read — standing rule).
  Pass iff `|mean_A − mean_B| <= 0.5*max(std_A, std_B)` **and** paired per-seed
  `|ΔAUROC| <= 0.02` on ≥4/5 seeds.
- **G4 Kendall-loss mathematical unit test** (CPU). `mode="kendall"` with
  `log_sigma` frozen at 0 must equal the fixed-weight loss ×0.5 per regression
  term and ×1.0 per classification term, exactly.

Then: `fixed` / `kendall` / `gradnorm` arms on both mixed clusters — the Module 11
mandated ablation axis.

#### Tier 2 (path c) — ordinal-CDF homogenization

**Investigated only after Tier 1.** `ml/featurize/ordinal.py` — `OrdinalCdfCodec`
(quantile thresholds fit on the train fold only); `encode` → M binary
`<endpoint>__gt<m>` columns, which keeps `kermt_adapter.py`'s
`write_finetune_csv` / `read_predictions_csv` **unchanged**; `decode` enforces
the monotonicity Frank-Hall does not guarantee (`np.minimum.accumulate`) and
recovers the scalar from the survival function using train-fold in-bin means.

**Zero-GPU discretization-ceiling test first, before any GPU training:** encode
true `y`, decode the exact binary labels, measure the pure discretization-floor
MAE; require ≤25% of the direct-regression baseline MAE, and use it to choose
`n_bins`.

**✅ DONE 2026-09-20 — `n_bins=16` is the working default.** Ceilings at 16 bins:
caco2 17.6%, lipophilicity 17.3%, ppb 18.5%, clearance 17.6%, solubility 23.3% of
their XGBoost baseline MAE. All five clear the gate; solubility is tightest and is
the one to watch. 32 bins roughly halves every ceiling but would make A&D 127
targets, which is impractical. Full table in `decisions.md`; raw numbers in
`ml/runs/cluster_preflight.json`.

Only then the remaining (GPU) gate: val-fold decoded MAE within 15% of the direct
single-task regression MAE for the same endpoint and seed.

#### Final comparison (all tiers)

Per endpoint, on the held-out scaffold test set, against **both** mandatory
baselines: the completed XGBoost runs and single-task KERMT. **XGBoost's side of this table is
`ml/runs/test_evaluations/<endpoint>.json` (`aggregated_test_raw`), never `ml/runs/evaluations/`**
(validation fold). KERMT's side is `aggregate_test_metrics_across_seeds`. Compare RAW to RAW for
ranking metrics; treat calibrated numbers with the served-calibrator caveat above. Mean ± std over the
5 fixed seeds, never a single run. **Multi-task is an empirical experiment — a
result where it loses is a publishable finding, not a failure**; the Oct-2025
KERMT multitask paper puts the gains above 60K datapoints and MARS's endpoints
are 910–13,445.

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
