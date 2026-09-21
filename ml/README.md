# ml/ — data, featurization, models, training, evaluation

Owns blueprint Modules 1, 3, 4, 5 (core), 11 (eval infra), and 6 (post-MVP).
Live status: `../documentation/AIMS/next_steps.md`.

## Layout

```
data/        Module 1 — acquire.py (TDC, runs in an isolated Linux venv),
             dataset_registry, snapshot, eda, dedup, split, prepare,
             dilist_augment. cluster_loaders.py builds the leakage-safe wide
             multi-endpoint table used by multi-task training.
             raw/ + processed/ + cache/ are gitignored; metadata/ is tracked.
featurize/   Module 3 — standardize, scaffold, graph, fingerprints, descriptors,
             conformers, pipeline (featurize_batch), cache (FeatureCache),
             kermt_adapter (SMILES/CSV contract for KERMT),
             ordinal.py (Tier-2 ordinal/CDF codec).
models/      Module 4 — base.py (MARSModel ABC), xgboost_model.py,
             kermt_model.py (stock KERMT CLI path).
train/       Training loops + sweep drivers. train_xgboost, run_xgboost_baseline,
             preflight_sweep, run_production_sweep, verify_sweep,
             train_kermt_cluster (Tier-0 harness), preflight_clusters
             (zero-GPU cluster gate), evaluate_xgboost_test (writes ml/runs/test_evaluations/),
             readiness_report (READY_FOR_GPU_SMOKE_TEST / BLOCKED), kermt_gpu_benchmark.
eval/        Module 11 infra — metrics, calibration (Platt + temperature),
             calibration_diagnostics (fit observability: boundary pinning, NLL/ECE
             before/after), cluster_calibration (the production temperature-scaling
             path for KERMT runs), applicability_domain, evaluate (EvaluationReport),
             leakage_audit (10 checks), tdc_comparison, cluster_eval,
             heldout_evaluation (scores the promoted XGBoost artifacts on the held-out
             TEST split - not the validation fold).
configs/     experiment_config.py (ExperimentConfig, FIXED_SEEDS),
             clusters.py (cluster + type-homogeneous subgroup registry).
serve/       Module 8 — ModelRegistry + predictor, consumed by api/.
utils/       seed.py, rng_state.py (RNG capture/restore for checkpoint/resume; not yet wired
             into training).
tracking/    ExperimentRun (on-disk, source of truth) + WandbLogger (opt-in).
artifacts/   Promoted per-endpoint models (gitignored). runs/ is run output.
```

## Environment

`ml/.venv` is a **separate** environment from the repo-root `.venv` — do not
merge them. It holds numpy, pandas, scikit-learn, rdkit, xgboost, wandb, scipy.
It deliberately has **no torch**: the KERMT backbone runs in its own docker
container, because `cuik_molmaker` is an unconditional import in KERMT's data
layer and cannot be installed CPU-only. Acquisition (`data/acquire.py`) runs in
a third, isolated Linux venv holding `PyTDC` — see `data/acquisition/README.md`.

## Running things

```bash
cd ml && PYTHONPATH=. ./.venv/Scripts/python.exe -m pytest -q
```

Zero-GPU cluster preflight (run this **before** any lab session — it reports what
leakage-safe cluster assembly costs and picks the Tier-2 bin count):

```bash
cd ml && PYTHONPATH=. ./.venv/Scripts/python.exe train/preflight_clusters.py
```

## State

- **M1 complete** — 14 datasets acquired, standardized, deduped, split, cached.
  Full reference: `../documentation/MARS_M1_TECHNICAL_REFERENCE.md` (cite it,
  don't re-derive).
- **XGBoost baseline complete** — 70/70 production runs (14 endpoints × 5 seeds),
  artifacts promoted, evaluation reports in `runs/evaluations/`.
- **KERMT integrated and GPU-validated at smoke-test scale** (tiny AMES fine-tune,
  2026-09-18); the mixed-type cluster limitation is resolved by a three-tier design —
  see `../documentation/AIMS/decisions.md` (2026-09-20). The Tier-0 harness now
  calibrates and scores the test set (2026-09-21, CPU-tested with a test double).
  **No production KERMT training run has happened, and no real KERMT logits have been
  calibrated.**
- **XGBoost test-set evaluation done (2026-09-21):** `runs/test_evaluations/` holds the held-out
  numbers; the old `runs/evaluations/` are validation-fold and differ by up to +0.26 AUROC.
  Compare KERMT to the test set.

The test set is never used for fitting, selection, tuning, or calibration.
