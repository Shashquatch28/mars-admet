# mistakes.md

## Held-out evaluation + readiness (2026-09-21, later) — five traps

- **The served Platt calibrators degrade held-out calibration, and the API applies them.**
  First test-set evaluation of the 70 XGBoost models. Like-for-like on seed 4 (the only seed the
  single per-endpoint `calibrator.json` was fit on — verified empirically, `promote_seed_artifact`
  overwrites it each seed): calibrated ECE is worse on 7/9 classification endpoints and Brier is
  worse on 9/9 (e.g. hia ECE .045→.209, cyp3a4 .025→.046). Cause: calibration-split positive rate
  ≠ test rate (cyp3a4 0.113 vs 0.439). Nothing flagged it because no evaluation had ever looked at
  calibration on held-out data. **Lesson: a calibrator is only validated by held-out calibration
  metrics; "it was fit without error" and "its own split's ECE is 0.0" (in-sample) prove nothing.**
  Not fixed (calibration policy out of scope); tracked in `next_steps.md`.
- **Validation-fold numbers were reported as if they were test numbers.** AUROC moved +0.263
  (dili), +0.217 (bbb), −0.043 (pgp) from validation to test. The old report was internally
  consistent, so it looked fine. **Lesson: label every metric with its split in the artifact
  itself** — `HeldOutEvaluationReport.split == "test"` and a labelled `validation_reference`.
- **The shared cluster fold does not control per-task validation size.** `toxicity__cls`
  validation = 18–24 hERG labels vs ~1,810 AMES (5 seeds); `ppb` 42–50. Only visible by counting
  per-task labels *inside* the fold; the cluster-level counts looked healthy. Epoch selection for
  the small tasks is effectively unmeasured. Not fixed.
- **Two arms silently trained on different data than their baseline.** DILI: XGBoost used the
  augmented pool (979 train), the harness default loads the base pool (287): −71%. Found only by
  putting the two pipelines' training counts side by side. **Lesson: pin `use_augmented_dili` in
  the run config and compare training-pool sizes per endpoint before comparing scores.**
- **My own test-helper bug looked like a product bug.** On Windows `Path.write_text("a\n")` writes
  `\r\n`, so a manifest hash computed from the string didn't match the file — the manifest-integrity
  check (correctly) failed. The check was right; the fixture was wrong. Also: my first readiness
  provenance check looked for `config` inside `provenance.json` (it is in `config.json`) and
  reported a false BLOCKED. **Lesson: when a new check fails, establish which side is wrong
  before touching either.**

## Audit + calibration wiring (2026-09-21) — five traps

- **A preflight that gates on one quantity can "clear" an arm that fails on another.**
  The 2026-09-20 cluster preflight cleared `absorption_distribution__cls` because
  *training-label* loss was only 4.6%. It never measured calibration size. After the same
  union-test removal, `hia_absorption`'s calibration set is **47 molecules, 46 positive and
  1 negative** — below blueprint Module 4's floor of 50. **Lesson: when a gate is named
  "cleared", list every requirement it does and does not test.** `preflight_clusters.py`
  still does not check calibration size; logged in `next_steps.md`, not silently extended.
- **The XGBoost baselines have never been scored on the test set.** Every number in
  `ml/runs/evaluations/*.json` is a 5-seed *validation-fold* metric (per-seed `n_samples`
  equals the val-fold size — CYP3A4 1,229 — and no report carries a test key). Blueprint
  Module 4/11 pick the winner on the held-out test set, and the new KERMT wiring reports
  test metrics, so the two are currently **not comparable**. It went unnoticed because the
  reports are internally consistent and the leakage audit passes. **Lesson: check that the
  quantity you are comparing is the same quantity on both sides before trusting a
  comparison table, not after.**
- **A tracked lockfile can silently describe a different machine than the data beside it.**
  `datasets.lock.json` is the workstation's `20260918T090143Z` acquisition; the raw and
  processed data on the laptop are `20260830T181633Z`. Raw content is identical (15/15
  `snapshot_sha256` match) so nothing is wrong with the science, but `test_acquisition_lockfile.py`
  fails 3 tests looking for a raw directory that only exists elsewhere, plus 2 stale
  Option-C expectations. **Lesson: gitignored data + a tracked lockfile = the lockfile
  outruns the data on any machine that didn't produce it. Compare digests, not IDs.**
- **The blueprint's "mandatory" checkpoint + RNG-state discipline is not implemented for
  KERMT runs.** Blueprint Module 10 / `context.md` "Locked facts" require checkpoints to
  carry model + optimizer + LR scheduler + Python/NumPy/PyTorch RNG state, synced to R2.
  A grep of `ml/` for `rng_state` / `set_rng_state` / `resume` finds nothing (only a W&B
  `resume="allow"` flag). KERMT's stock CLI writes its own best-model checkpoint and MARS
  records only the integer seed (`utils/seed.py::set_global_seed`, which also sets
  `PYTHONHASHSEED` at runtime — a no-op for the already-running interpreter). Not a
  correctness blocker for an uninterrupted single-session A4000 run, but bit-exact
  resumption after a preemption is impossible today, and KERMT's own CUDA determinism
  is **not established**. Do not describe seed tracking as full reproducibility.
- **My own audit trap: `None == None` reads as "identical".** The first snapshot-digest
  comparison used a key that does not exist (`snapshot_digest`; the real one is
  `snapshot_sha256`), so every dataset compared `None == None` and printed `True` for
  15/15. Caught because I asserted the values were non-empty before believing the result.
  **Lesson: any "all match" result needs an assertion that the operands exist.**

## Calibration split is NOT label-representative (2026-09-20) — pre-existing, affects shipped artifacts

Found while assessing whether Option A's reduced CYP calibration sets are usable.
The problem is older and wider than that question, and it affects the **already
promoted** XGBoost calibrators, not just future KERMT runs.

- **The calibration split is scaffold-aware but not label-stratified**, so its
  positive rate can differ wildly from the train_val pool it was carved from.
  Measured on `ml/data/processed/20260830T200000Z/` (all 9 classification
  endpoints, `train_val` rate vs `calibration` rate):
  `cyp3a4_inhibition` **0.4093 vs 0.1129 (3.6x)**, `cyp2c9_inhibition`
  0.3393 vs 0.1432 (2.4x), `dili_liver_injury` 0.4921 vs 0.2600 (1.9x),
  `pgp_inhibition` 0.5408 vs 0.3711 (1.5x), `cyp2d6_inhibition` 0.1969 vs 0.1452,
  `bbb_permeability` 0.7519 vs 0.7643, `hia_absorption` 0.8894 vs 0.9800,
  `herg_cardiotoxicity` 0.4899 vs 0.5871, `ames_mutagenicity` 0.5317 vs 0.6759.
  A calibrator fit at an 11% positive rate and then applied to a ~41% positive
  population is being asked to correct a prior shift it never saw.
- **`hia_absorption`'s promoted Platt calibrator was fit on 50 molecules of which
  49 are positive and 1 is negative.** `ml/artifacts/hia_absorption/calibrator.json`
  records `n_fit_samples: 50` with `A=0.318, B=3.578`, which maps essentially
  every input to ~0.97-0.99. `fit_platt_calibrator` only rejects a *strictly*
  single-class split, so 49:1 passed. This is the same endpoint already flagged
  for AUROC = 1.000 ± 0.000 — the two anomalies are probably the same underlying
  data problem, and this calibrator is currently promoted and served.
- **Lesson: "the fitter did not raise" is not evidence the fit is meaningful.**
  Both calibration fitters guard only against empty input, length mismatch and
  strictly-single-class labels. Record `n_positive`/`n_negative` alongside
  `n_fit_samples` for every fit — `eval/calibration_diagnostics.py` now does this.
- Not fixed here: changing the calibration split policy is an M1 data decision
  and was explicitly out of scope for this pass. Logged in `next_steps.md`.

## Temperature scaling has two silent degenerate modes (2026-09-20)

`eval/calibration.py::fit_temperature_scaler` uses
`scipy.optimize.minimize_scalar(..., bounds=(0.05, 10.0), method="bounded")` and
**never checks `result.success`**, and the returned `TemperatureScaler` records
only `(temperature, n_fit_samples)`.

- **Anti-correlated calibration logits pin T to the upper bound.** Verified:
  N=241 synthetic logits with labels anti-correlated to them returns exactly
  `T = 10.0`, no error, no warning. Pinned in
  `ml/tests/test_calibration_diagnostics.py`.
- **Perfectly separable calibration logits drive T toward the lower bound** —
  NLL is monotone in `1/T`, so the fit degenerates into sharpening. Verified at
  N=241: `T = 0.236`.
- Both return an object indistinguishable from a good fit. **Lesson: a bounded
  1-D optimiser that returns a value at its boundary has not found an optimum —
  it has run out of room. Flag it.** `eval/calibration_diagnostics.py::
  is_temperature_at_boundary` exists for exactly this and must be logged per seed.
- Existing `test_calibration.py` coverage is N=300-4000 well-behaved synthetic
  logits only; neither degenerate mode nor any small-N case was covered before.

## KERMT mixed-type resolution (2026-09-20) — three traps, two of them latent for days

- **"Kendall weighting" was never reachable — and the first proposed fix would
  have broken every run.** Two layers, and checking only the first gives the
  wrong answer. Layer 1: `task/train.py` builds `MTLLoss` only under
  `if args.use_mtl_loss:`, so `main.py finetune` *can* do Kendall weighting —
  which made "just pass `--use-mtl-loss` from `_hyperparam_flags()`" look like
  the fix. Layer 2, and the one that matters: **MARS never calls `main.py`.** It
  calls `agent/scripts/run_finetune_local.py`, which never forwards
  `use_mtl_loss` (absent from `TRAINING_FLAGS` / `TASK_FLAGS` / `FFN_FLAGS`, never
  appended to the argv it builds) **and uses strict `p.parse_args(argv)`** — so
  the "fix" would have been an unrecognized-argument hard failure, exit 2, on
  every Tier-0 run at the next lab session. Caught during CPU-side prep by
  reading the wrapper script instead of the engine underneath it.
  **Lesson: when shelling out through someone else's convenience wrapper, the
  wrapper's passthrough list is the real API — not the underlying tool's.** Read
  the argv the wrapper actually constructs before adding a flag to it. Corollary
  now standard here: after any multi-task run, assert `log σ` is non-zero before
  claiming the run used Kendall weighting at all.
- **DO NOT "fix" KERMT's uniform `MTLLoss` precision — it is an exact
  reparameterization, not a bug.** `kermt/util/loss.py` uses
  `precision = 0.5*exp(-2logσ)` for every task, which looks like Kendall's
  *regression* form wrongly applied to classification (the blueprint asks for
  `1/σ²` on classification). It is not wrong: substituting `σ_k = σ_c/√2` gives
  `1/(2σ_k²) = 1/σ_c²` and `log σ_k = log σ_c − ½log2`, so the two objectives
  differ by a per-task **additive constant** — identical gradients, identical
  optimum, identical effective weights. An earlier draft of the 2026-09-20
  analysis called this non-compliant and was wrong. It only matters when
  classification and regression coexist in one run. When reporting `log σ` for a
  pure-classification cluster, apply `log σ_compliant = log σ_kermt + ½log2`.
  **Lesson: before filing a third-party "bug", check whether the difference is
  absorbable into a reparameterization of the learnable parameter.**
- **Cross-endpoint split leakage is invisible to every existing leakage check.**
  All of `ml/eval/leakage_audit.py`'s 10 checks are *within* one endpoint. But 12
  endpoints adopt their own TDC benchmark split, so a molecule can legitimately
  be `train_val` for `solubility_logs` and `test` for `hia_absorption`. The
  moment a cluster shares one encoder across those endpoints, training on the
  first leaks into the second's test set — and every existing check still passes.
  This would have silently inflated every cluster number against the 70
  completed XGBoost baselines. **Lesson: a leakage audit written for single-task
  training does not transfer to multi-task training. Re-derive the audit when the
  unit of training changes**, and run it *before* spending GPU hours, not after
  the numbers look good.

## M2 production sweep — driver script (2026-09-17, same day as preflight)

- **`run_production_sweep.py`'s own leakage-check classification didn't
  reuse `preflight_sweep.py`'s augmented-DILI `split_method` fallback**,
  so the sweep summary initially reported `dili_liver_injury:
  leakage_audit_ok=False` — a false alarm from the exact same reporting
  gap already found and fixed in preflight (augmented DILI's
  `provenance.json` has no `split_method` field). Direct re-check
  confirmed DILI's only failing check is the same documented, benign
  `test_disjoint_from_train_val_scaffolds` (19 buckets, zero real
  duplication) — every other check, including the two checks only
  possible once a real AD index + calibrator exist
  (`ad_index_disjoint_from_test`, `calibrator_fit_sample_count`), passed.
  Fixed the driver to use the same fallback and patched the already-written
  `production_sweep_summary.json` with a corrective note rather than
  re-running the (unaffected) training. **Lesson: when the same
  classification logic is needed in two scripts, either share one
  function or expect to fix both — this is the second time this exact
  gap bit a script in the same session.**

## M2 production sweep preflight (2026-09-17)

- **6/14 endpoints "fail" `check_test_disjoint_from_train_val_scaffolds`
  (solubility_logs, bbb_permeability, cyp3a4/2d6/2c9_inhibition,
  dili_liver_injury) — all benign, none are real leakage.** Every one of
  them passes the exact-SMILES disjointness check with zero overlap (no
  duplicate compounds) and every other leakage check; only the
  RDKit-vs-TDC Murcko-scaffold-bucket assignment differs slightly for a
  handful of molecules — exactly the effect already documented in M1 Run 2
  ("BBB and several CYPs"), now also observed on `solubility_logs` (14
  overlapping buckets) and augmented DILI (19). First preflight attempt
  wrongly treated this as a hard STOP; fixed `ml/train/preflight_sweep.py`
  to only block on this specific check when the exact-SMILES check has
  ALSO failed, or when the split is one of MARS's own self-generated
  scaffold splits (`ppb_binding`, `herg_cardiotoxicity`) where zero overlap
  is a hard construction guarantee, not adopted-benchmark noise.
- **The augmented DILI variant's `provenance.json` has no `split_method`
  field** — `dilist_augment.py`'s provenance writer never recorded it
  (a real gap, not fixed here since it's a documentation/completeness
  issue, not a data-correctness one: augmentation only ever adds to
  train_val, so the augmented variant's test set is provably the
  unmodified base adopted-benchmark test set regardless). Preflight now
  falls back to the base (non-augmented) dataset's `split_method` for
  this classification. Worth adding the field for real the next time
  `dilist_augment.py` is touched.


Things that were broken, went wrong, or are traps. Read before repeating a class
of action. Newest first.

## M3 final CPU-side pass (2026-09-17, later same day)

- **Two overlapping `docker compose build api` invocations against the same
  image tag corrupted/contended for BuildKit's cache and lock state**,
  making both hang indefinitely with near-zero CPU usage and no output —
  looked identical to a genuine build hang (which is what buffered-until-exit
  output from a SLOW-but-healthy build also looks like, so the two are easy
  to confuse). Diagnosed via `Get-Process -Name docker-compose,docker-buildx`
  showing alive processes with ~0 total CPU time after several minutes
  (a genuinely working build keeps accumulating CPU; a stuck one doesn't).
  → `Stop-Process -Force` on the stray PIDs, `docker buildx prune -f`, retry
  as a single build. **Lesson: never start a second `docker compose build`
  for the same image while an earlier one might still be running** — check
  `Get-Process -Name docker-compose,docker-buildx` first, and judge
  "hung vs. slow" by CPU accumulation over time, not by output silence alone
  (large layers like `nvidia-nccl-cu12`'s 342MB genuinely produce zero
  intermediate output for a while on a slow link).

## M3 serving container (2026-09-17)

- **`xgb.XGBClassifier()`/`XGBRegressor()` require scikit-learn importable at
  `__init__`, even if you never call any sklearn API** — discovered by
  actually running the built `api` Docker image against a real promoted
  artifact (`hia_absorption`) rather than trusting the static import-grep
  audit alone: `ImportError: sklearn needs to be installed in order to use
  this module`, raised inside `XGBoostModel.load_with_cache` →
  `xgb.XGBClassifier()`, well before `.predict()`. `ml/requirements-serving.txt`
  originally omitted scikit-learn on the theory that only `fit_platt_calibrator`
  (a training-time function, already lazy-imported per `eval/calibration.py`)
  needed it. That theory was correct for `eval/calibration.py` but wrong for
  `models/xgboost_model.py`'s own sklearn-wrapper classes — fixed by adding
  `scikit-learn>=1.5,<2` to `ml/requirements-serving.txt`. **Lesson: a clean
  `grep` for module-level heavy imports is necessary but not sufficient** —
  a library's own `__init__` can pull in a "training-only" dependency that
  never appears in this codebase's own import lines. Always smoke-test the
  actual built artifact end-to-end (container + real model file), not just
  the source-level dependency audit.

## M3 start (2026-09-16)

- **This machine has TWO native Windows Postgres services already installed
  and running** (`postgresql-x64-16` on port 5432, `postgresql-x64-18` on
  port 5433 — `Get-Service -Name '*postgres*'`), both pre-dating this
  project. Symptom: `asyncpg.exceptions.InvalidPasswordError: password
  authentication failed for user "mars"` even though `docker exec
  mars_postgres psql -U mars` (Unix socket, inside the container) worked
  fine — remapping docker-compose's postgres to 5433 "fixed" nothing because
  5433 was ALSO already claimed by the native `postgresql-x64-18` service;
  `netstat -ano | grep 543` + `Get-CimInstance Win32_Process -Filter
  "ProcessId=<pid>"` confirmed both `postgres.exe` owners. TCP connections
  to `localhost:<port>` were landing on whichever native service claimed
  that port first, never reaching the container, so of course the "mars"
  role didn't exist there. → Remapped docker-compose's postgres to **host
  port 55432** (confirmed free via `netstat`); `DATABASE_URL` in
  `.env`/`.env.example`/`Settings` default all updated to `localhost:55432`.
  The `api` service's own `DATABASE_URL` (docker-compose internal network,
  `postgres:5432`) is unaffected — only host-side connections needed the
  port change. **Lesson: on this machine, always verify a docker-compose
  host port is actually free** (`netstat -ano | findstr :<port>` /
  `Get-NetTCPConnection -LocalPort <port>`) before assuming a connection
  failure is a credentials/container problem — don't stop at the first
  remap either; check the NEW port too.
- **`docker-compose.yml`'s `minio/minio:latest` image pull fails**
  ("pull access denied … may require 'docker login'") — Docker Hub has
  throttled/gated that image for anonymous pulls as of this date. `postgres`
  and `redis` pull fine; only `minio` is affected. **Fixed**: repointed to
  `quay.io/minio/minio:latest`, which pulls fine anonymously — same image
  content, different registry. Batch result storage still uses a
  Redis-based stand-in for this session's scope regardless (see
  `api/app/services/batch_results.py`); MinIO now starts cleanly but isn't
  wired to any code path yet.
- **`passlib[bcrypt]` is broken with `bcrypt>=4.1`.** passlib 1.7.4 probes the
  backend via `_bcrypt.__about__.__version__`; that attribute was removed from
  the `bcrypt` package in 4.1+, so every `CryptContext(schemes=["bcrypt"]).hash()`
  call raises `AttributeError`/`ValueError` immediately. passlib is effectively
  unmaintained (no fix upstream as of this date). → Use the `bcrypt` library
  directly (`bcrypt.hashpw`/`bcrypt.checkpw`), no passlib. `.env.example`'s
  `PASSWORD_HASH_SCHEME` comment updated accordingly. If a future dependency
  bump reintroduces passlib transitively, re-check this before trusting any
  password hash it produces.
- **Docker Desktop's daemon is not running by default on this machine** (same
  note as the M0 audit, still true) — `docker ps` fails with
  `open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file
  specified`. Launch `Docker Desktop.exe` and wait ~30-60s before any
  `docker compose`/`docker build` command; don't treat the immediate failure
  as "docker is broken."

## M1 Run 4 (2026-08-30)

- **`build_cache.py` writes `build_report.json` only at the very end** (after
  morgan → descriptors → graph → conformer, all sequential in one process). Don't
  wait on the report file mid-run to judge progress — check the sharded entry
  counts under `ml/data/cache/<stage>/` instead. Real timing: morgan 3572 in 9s,
  graph 3572 in 11s, descriptors 3572 in **104s** (the bottleneck, ~34/s),
  conformers 150 in **535s** (~3.6s/mol — genuinely expensive, correctly lazy).
- **Conformers: 1 of 150 real DILI/HIA/Caco2/Pgp molecules failed** to
  embed/optimize — stored as `ConformerResult(ok=False)`, not fabricated. UFF
  fallback wired but not needed on that sample (149/149 MMFF94). The graceful-
  failure path works on real data, not just the invalid-SMILES unit test.
- **Serving → Cloud Run (not Render).** Blueprint Modules 8/10/12/13/14 +
  `.env.example` updated. Backend + async worker only; async batch = Cloud Tasks
  → Cloud Run worker endpoint (no Celery). $0 at demo scale. If M2 finds KERMT
  CPU inference too slow for Cloud Run, a GPU tier reintroduces cost → flag.
- **`documentation/MARS_M1_TECHNICAL_REFERENCE.md` is now the canonical M1
  reference.** Cite it; don't re-derive numbers.

## M1 Run 3b (2026-08-30)

- **RDKit `Descriptors._descList` is 217 in 2026.3.5, not "~200".** Took the
  whole set (frozen sorted + SHA-hashed) rather than a curated subset — a subset
  needs its own justification and drifts silently. `assert_descriptor_set_matches`
  raises on any RDKit descriptor-set change; bump `DESCRIPTOR_VERSION` + re-featurize.
- **Descriptor non-finite values (Ipc overflow) are NOT imputed in featurization.**
  The layer returns the raw matrix + `finite_mask` + per-row `{name: value}`.
  Imputation strategy is a Module 4 (modelling) decision — don't bury it in Stage 4.
- **Conformer `_optimise` UFF fallback is wired but untested on real data** —
  MMFF94 covered every smoke molecule. When Run 4 runs conformers at dataset
  scale, check `rejection_summary`'s UFF + `optimization-failed` counts.
- **`ConformerResult.to_contract_dict()` RAISES on a failed result** — there is
  no `ConformerResponse` shape for "no conformer" (by contract design; Module 8
  returns an error status). Callers must check `.ok` first.
- **`generate_conformer` had an ugly try/except/finally hack** from a first draft
  (ternary + `dir()` probe). Cleaned to a plain `except Exception: return
  _fail(smiles, "unexpected-error")`. If you see that pattern again, it's wrong.
- **Blueprint no-paid-compute edit (2026-08-30):** RunPod paid fallback removed
  everywhere; free-tier notebooks (Kaggle/Colab) are the fallback; budget is $0.
  The serving hosting stack (Render Starter ~$7/mo) was NOT changed — flagged to
  the maintainer as a separate M3-scope call.

## M1 Run 3a (2026-08-30)

- **Registry–vs–lockfile can diverge across policy changes.** The Run-1 lockfile
  recorded PPB's `in_admet_benchmark_group=True` (because the acquisition
  attached the all-species benchmark_split). The Option C decision two runs
  later changed that to `False` at the registry level. Prepare.py now consults
  the REGISTRY (not the lockfile) for split method, and records both values in
  provenance so the divergence is auditable and version-controlled. Rule of
  thumb: the lockfile is the acquisition FACT; the registry is the current
  POLICY. Prepare-time policy changes need to check the registry.
- **Second registry entry with the same `tdc_name` requires acquisition
  redesign** if you want it acquired at the same acq_id (`ppb_binding` +
  `ppb_binding__all_species` both point at `PPBR_AZ`; acquire.py currently
  writes to `raw/<tdc_name>/<acq_id>/` which would collide). Not a live bug
  today because the all-species files are already on disk from Run 1 and we
  read them directly when the ablation is scheduled; if we ever add
  `--only ppb_binding__all_species` re-acquisition, `acquire.py`'s raw path
  layout will need to key on dataset_key rather than tdc_name.
- **`ATOM_FEATURE_DIM = 42`, not 44.** I miscounted in the graph.py docstring;
  the code was right, the doc was wrong. Fixed. Categorical bin counts:
  11 + 7 + 6 + 4 + 6 + 6 + 2 = 42.
- **`rdFingerprintGenerator` is the modern API.** `AllChem.GetMorganFingerprintAsBitVect`
  still exists but is being phased out; the generator API is what RDKit
  documents in 2026 and it returns a plain NumPy array without an intermediate
  BitVect conversion.
- **Enantiomer verification test is worth its weight in gold.** Both the graph
  and Morgan modules include an explicit "L != D" chirality test AND its dual
  "with chirality off, L == D" — so any future refactor that silently flips the
  useChirality default (or drops the chirality atom features) fails a targeted
  test, not a vague accuracy regression at M2.

## M1 Run 2 (2026-08-30)

- **PPBR_AZ has 5 species pooled in the TDC benchmark split**, but the species
  column is dropped by the loader. `single_pred` returns human only (1,614);
  `benchmark_group` returns all species (2,790 measurements over 1,797 compounds).
  The compound-level 80/20 partition is clean, but the label the model sees is
  a scalar mixture of human + rat + dog + mouse + guinea pig with no covariate
  telling it which. Do NOT silently pick one; the choice is a scientific one.
- **RDKit's `MurckoScaffold.GetScaffoldForMol` output can differ from TDC's own
  scaffold assignment** even on the same molecule — small non-empty-scaffold
  overlaps show up in adopted benchmark splits (BBB, several CYPs) after our
  Module 3 Stage 1 standardization. This is real but expected; do NOT try to
  "fix" the overlap by regenerating the split — it would forfeit leaderboard
  comparability. Log it in the split report notes and move on.
- **Post-standardization SMILES collision** can move a compound from `train_val`
  to `test` in adopted TDC benchmark splits (BBB had 1). Rule of thumb: the
  fixed test set is authoritative; drop the compound from train_val, log it in
  `post_standardization_leaks_removed_from_train_val`.
- **DILI compounds have zero stereo annotations** — expected (names→structures
  didn't resolve stereo). Blueprint's `useChirality=True` fix (Run 3) won't help
  DILI. Not a bug; just a fact about the data.
- **DILIPredictor's `DILI_Goldstandard_1111.csv` has 15 rows with invalid
  phosphate SMILES** (`[P](=O)(=O)O` — valence 6, illegal). Our standardizer
  correctly rejects them with `sanitize-failed`. Keep the raw rows in the
  augmentation report's `rejection_samples[]` for auditability rather than
  silently swallowing them.
- **`select_policy` chose `majority_vote` for hERG_Karim (5.6% conflict rate)**
  — that's the conservative side of the low-vs-moderate threshold (5%). If
  Run 3+ evidence says `drop_conflicting` is actually cleaner for that dataset,
  the policy record + the tests make the swap safe (the rationale string
  already documents the borderline).

## M1 Run 1 (2026-08-30)

- **`wsl -d Ubuntu -- bash -lc '…$VAR…'` mangles quoting** when the script or a
  path contains spaces (the MARS repo path has one). Symptom: `$VAR` comes back
  empty, `cd` fails. → Pipe the script via **stdin**: `wsl -d Ubuntu -- bash -s
  <<'EOF' … EOF`. bash parses the file text internally; no wsl.exe quote handling.
- **First acquisition run wrote to `ml/data/ml/data/…`** — `acquire.py --repo-root`
  defaulted to `.` while cwd was `ml/data`. → Added a guard: the script rejects a
  `--repo-root` that has no `ml/data/acquire.py` under it. Always pass an absolute
  repo root.
- **Snapshot digest drifted between acquisition and verification** for
  regression datasets. Cause: acquisition hashed pandas floats (`-4.0` →
  canonical `"-4"`) while verification read the CSV as strings (`"-4.0"` →
  `"-4.0"`). → `canonical_label` now numerically coerces strings so `1`, `1.0`,
  `"1.0"` all collapse identically; the acquisition digest is computed by
  **reading back the persisted CSV** (`canonical_csv_digest`), the exact code
  path verification uses. Never hash the in-memory DataFrame for provenance.
- **`pip install PyTDC` (any 0.4.17–1.1.15) fails on Windows** — declares
  `tiledbsoma`, which ships **no Windows wheel**, and force-pins `numpy<2` /
  `rdkit<2024.3.1`. Those heavy deps (`tiledbsoma`, `cellxgene-census`, `gget`,
  `biopython`, `transformers`…) are only used by TDC's multi-omics / model-server
  code, not `tdc.single_pred` / `tdc.benchmark_group`. → PyTDC lives in an
  isolated Linux env, installed `--no-deps` + a pinned minimal runtime.
- **PyTDC 1.1.15 on Python 3.12 also needs**, beyond its `--no-deps` set:
  `packaging`, `setuptools<81` (for `pkg_resources`; 81 removed it),
  `huggingface_hub` (imported eagerly by `tdc/__init__.py` via `model_server`).

## Data traps found in M1 Run 1 (not yet acted on — Run 2)

- **PPBR_AZ: `single_pred` N (1,614) ≠ benchmark-group split N (2,231+559=2,790).**
  The only dataset where the TDC benchmark split is NOT a partition of the
  `single_pred` full set. Also ~10% below the blueprint's 1,797. Resolve which
  set is authoritative before touching PPB in Run 2. Pinned by
  `test_benchmark_split_partitions_the_full_set_except_ppbr`.
- **`hERG_Karim` is not in the TDC ADMET Benchmark Group** — needs a
  self-generated Murcko scaffold split in Run 2 and is not leaderboard-comparable.
  Blueprint Module 1 §4 over-claims comparability; wording fix proposed, not applied.
- **Minor N drift from the blueprint** (TDC revised datasets): BBB +2.8%, AMES,
  Pgp, Caco2, hERG(bench) all a few compounds off. Lockfile records exact N.

## Found broken during the M0 audit (2026-08-30)

- **`docker-compose.yml` `api` service was mis-indented** — its keys sat at the
  same column as `api:`, so YAML parsed them as sibling top-level services;
  `docker compose config` failed outright. → After ANY compose edit, run
  `docker compose config` to validate. Fixed.
- **`.gitignore` had a bare `data/`** — that pattern matches `ml/data/` too,
  which holds pipeline **source code** (`acquire.py`, future `standardize.py`…).
  A naive `git add ml/` would have silently dropped it. → Anchor repo-root-only
  dirs as `/data/`; ignore dataset dirs specifically (`ml/data/raw/*` with a
  `!…/.gitkeep`). Fixed.
- **Brace-literal directories** `api/app/{routers,services,core}/` and
  `frontend/src/{components,pages,styles}/` existed on disk — created by running
  `mkdir -p a/{b,c}` in a shell **without brace expansion** (PowerShell / cmd).
  → In PowerShell, don't use bash brace expansion; make dirs explicitly or use
  the Bash tool. Removed.
- **`ml/tracking/provenance.py` hard-imports `numpy` and `torch` at module top.**
  Module 10 says XGBoost baselines run on the laptop (CPU, no CUDA). Provenance
  for those runs would `ImportError`. → Make those imports lazy/guarded when M2
  touches tracking. **Still open (CF-5).**
- **README was stale** — referenced `mars-blueprint_v3.md` and the abandoned
  3-person A/B/C split; claimed `npm run dev` works. Frontend has no Vite entry
  and is not runnable (M4). Fixed README; frontend left for M4.
- **No CI, no tests** existed at all. Added `.github/workflows/ci.yml` + 12
  tests. Blueprint Module 10 mandates a known-molecule `/predict` smoke test.
- **`.env.example` shipped `JWT_*` vars + `python-jose`** against Module 13's
  locked "server-side Redis sessions, not JWT". → Aligned to sessions. When
  building M3 auth: opaque `secrets.token_urlsafe` tokens in Redis, never JWT.

## Environment traps (this machine)

- **Port 8000 → `WinError 10013`** (socket access forbidden). Hyper-V / Docker
  reserves port ranges on this Windows box. → Use **8080** for uvicorn. Check
  reserved ranges with `netsh interface ipv4 show excludedportrange protocol=tcp`.
- **`.venv` has API + tooling deps only, not the ML stack.** `import
  ml.tracking.experiment` fails on `numpy`. Expected — don't "fix" it by
  installing torch/rdkit locally unless doing CPU work that needs them; the ML
  stack belongs on the CUDA box.
- **Swagger "Example Value" is not a response.** The `/docs` UI shows
  `{"value": 0, "smiles_input": "string", …}` as a schema placeholder before you
  Execute. Not a bug, not a real result. "Failed to fetch" on Execute = server
  unreachable (wrong port / not running / wrong scheme), not CORS (`main.py`
  allows `*`).
- **ruff `I001` import-sort failed on pre-existing files** and would have broken
  CI on first run. → `ruff.toml` added (E,F,I,B,UP; ignore E501, UP042 — the
  latter because `class X(str, Enum)` → `StrEnum` changes serialization on the
  locked contract enums). Ran `ruff check --fix` once across the tree.
- **Throwaway `test_wandb.py` at repo root** would have been committed. → Added
  `/test_*.py` + `/scratch_*.py` to `.gitignore`. Keep debug scripts out of the
  repo; they also risk polluting W&B with junk runs (Module 11 §5 — only
  meaningful records).

## M1/M2 traps to not walk into (from the blueprint, not yet hit)

- **RDKit ECFP `useChirality` defaults to OFF.** Two enantiomers → identical
  ECFP4 unless you pass `useChirality=True`. CYP2C9 is in-scope and shows the
  effect. Same silent-default risk exists at the graph-feature level (Stage 2).
- **Standardize BEFORE dedup/split**, not after. All 14 sets, identical pipeline.
- **Augmentation (DILIst) must be deduped against the TDC held-out TEST set**,
  and scaffold-overlap re-checked AFTER merging. Skipping this = leakage that
  invalidates every leaderboard comparison.
- **Test set is off-limits** for model selection, hyperparameter tuning,
  calibration, and iterative development. Calibration uses its own split carved
  from train_val.
- **Scaffold split must reproduce TDC ADMET Benchmark Group's exact protocol** —
  it's a comparability commitment, not a free choice.
- **Checkpoints must include RNG state** (Python/NumPy/PyTorch), not just
  weights + optimizer. A resumed run without restored RNG state silently
  diverges from what "seed 5" is supposed to mean. Push checkpoints to R2, not
  lab disk (shared machines wipe home dirs).
- **KERMT recommends ≥32 GB VRAM for finetuning.** The free-tier fallback
  (Kaggle/Colab, 16 GB — no paid card anywhere per the 2026-08-30 directive) is
  well under that. Free-tier GNN training needs grad-checkpointing + small batch
  + gradient accumulation; multi-task cluster runs that still OOM wait for a lab
  A100 session, they do NOT get a paid card.
- **Don't burn GPU hours on unvalidated code.** Tiny data (a few dozen mols, 1–2
  epochs) → verify logging + checkpoint save + checkpoint restore + RNG restore
  → then the real run.
