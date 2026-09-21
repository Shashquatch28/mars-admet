# MARS — Decision Log

Record of decisions that resolve blueprint ambiguities or gate downstream
milestones. Part of `documentation/AIMS/`. Newest first. Each entry = date,
decision, rationale, blueprint tie-in, open follow-ups.

**Provenance note:** this file lived at the repo root as `DECISIONS.md` (tracked)
and was moved into `documentation/AIMS/` (untracked) on 2026-08-30 by the user.
Decision provenance is therefore *not* in git history right now. If that matters
later, options: (a) move a copy back to a tracked path, (b) `git add -f` this
file, or (c) fold the key decisions into the blueprint (which the user edits).
See the 2026-08-30 "documentation stays untracked" entry.

---

## 2026-09-21 (later) — CPU-side evaluation/provenance gaps closed; four new findings, no policy changed

Provisional methodology unchanged: official TDC splits, strict cluster-level leakage
prevention, `metabolism__cls` Option A, `holdout_calibration=True`, no regenerated CYP split,
no Tier-1. No GPU training, no XGBoost retraining, no data regeneration.

### 1. XGBoost held-out TEST evaluation — DONE (14 endpoints x 5 seeds, 0 blocked)

`ml/eval/heldout_evaluation.py` + `ml/train/evaluate_xgboost_test.py`. Loads the 70 promoted
models, scores each endpoint's canonical test split (prep `20260830T200000Z`; DILI on the
augmented variant exactly as the sweep trained it — its test split is bit-identical to the base
split, pinned by a test), and reports raw + calibrated metrics, mean ± std over seeds. Outputs go
to `ml/runs/test_evaluations/` only; the tool refuses to write into `ml/artifacts/` or
`ml/runs/evaluations/`. **Proven non-invasive:** SHA-256 digests of `ml/artifacts/` (178 files)
and `ml/runs/evaluations/` are byte-identical before and after the run. Accuracy is not a MARS
project metric and was not added. No molecule failed featurization (0 unscored).

| Endpoint | VALIDATION (old report) | TEST (raw) | Δ |
|---|---|---|---:|
| ames | AUROC 0.823±0.009 | 0.858±0.005 | +0.035 |
| bbb | 0.684±0.022 | 0.901±0.009 | **+0.217** |
| cyp2c9 | 0.901±0.006 | 0.897±0.001 | −0.003 |
| cyp2d6 | 0.913±0.003 | 0.873±0.002 | −0.040 |
| cyp3a4 | 0.943±0.003 | 0.901±0.001 | −0.042 |
| dili | 0.636±0.034 | 0.898±0.022 | **+0.263** |
| herg | 0.836±0.007 | 0.876±0.005 | +0.040 |
| hia | 1.000±0.000 | 0.972±0.002 | −0.028 |
| pgp | 0.953±0.004 | 0.910±0.005 | −0.043 |
| caco2 | MAE 0.336±0.010 | 0.288±0.012 | −0.048 |
| clearance | 19.212±1.193 | 25.956±0.497 | +6.744 |
| lipophilicity | 0.519±0.010 | 0.544±0.006 | +0.025 |
| ppb | 7.490±0.117 | 7.363±0.122 | −0.127 |
| solubility | 0.726±0.010 | 0.810±0.014 | +0.084 |

**Validation was not a usable proxy for test.** AUROC moved by up to +0.263 (DILI) and +0.217
(BBB); CYP3A4/2D6 fell ~0.04. Every comparison against KERMT must use the TEST column.
HIA's suspicious 1.000 was validation-only (test: 0.972).

**Calibration finding — the served Platt calibrators make held-out calibration WORSE.**
Only ONE `calibrator.json` exists per endpoint: `serve.registry.promote_seed_artifact`
overwrites it on every seed. Re-deriving it in memory from each seed's calibration-split
predictions shows **only seed 4 reproduces it, for all 9 classification endpoints.** Like-for-like
on seed 4 (the calibrator's own model), test ECE raw → calibrated: ames .026→.098, bbb .113→.156,
cyp2c9 .019→.037, cyp2d6 .020→.023, cyp3a4 .025→.046, hia .045→**.209**, pgp .102→.123;
improved only for dili (.199→.053) and herg (.075→.074, negligible). **Calibrated ECE is worse on
7/9 endpoints and Brier is worse on 9/9.** The cause is the prior shift already recorded: the
calibration-split positive rate is far from the test rate (cyp3a4 0.113 vs 0.439; cyp2c9 0.143 vs
0.319; hia 0.980 vs 0.769). These calibrators are what `ml/serve/` applies to the API's
classification probabilities. **Not fixed** — the calibration policy is out of scope — but this
is a defect in served predictions, not a hypothetical. For seeds 0–3 the "calibrated" numbers use
a calibrator not fit on those models; each per-seed record carries `calibrator_is_seed_matched`.

### 2. Workstation data provenance — raw: byte-identical; processed: **D, UNABLE TO VERIFY**

Established from repository evidence only (no workstation processed data exists in the repo):
- **Raw acquisition — A, byte-identical.** All 15 `snapshot_sha256` match between
  `ml/data/metadata/history/datasets.lock.20260830T181633Z.json` and the tracked
  `datasets.lock.json` (acq `20260918T090143Z`); 56 of 58 file-level SHA-256 entries match. The 2
  that don't are `ppb_binding`'s benchmark-split files, dropped by the Option-C registry policy
  (`in_admet_benchmark_group` True→False). PyTDC 1.1.15 on both.
- **Processed splits (`20260918T090433Z`) — D.** Corroborating but not sufficient: the counts
  quoted from the workstation (AMES 7,278→7,255, train_val 5,802, test 1,453; CYP3A4 12,328→
  12,295) equal this machine's `manifest.json`. Counts are not hashes.
- **Note:** `manifest.json` embeds absolute paths, so two machines' manifests can never be
  byte-identical; comparison must hash the split files.
- **Tooling to close it in one command each side:** `ml/data/compare_prep.py` (read-only;
  classifies A byte-identical / B content-identical / C materially different / D unable to
  verify, overall = worst dataset). Canonical fingerprint committed at
  `ml/data/metadata/prep_fingerprint.20260830T200000Z.json` (16 datasets; 60 files cross-checked
  against the manifest's recorded hashes). Workstation: `python data/compare_prep.py
  fingerprint --prep-dir data/processed/<id> --out ws.json`, then `compare --a <canonical> --b
  ws.json`.

### 3. Calibration holdout — exact data flow, and its consequences (behaviour unchanged)

```
train_val (wide, union-test already removed)
  └─ minus EVERY calibration molecule of ANY member endpoint   <- ClusterData.train_pool
       └─ five_seed_train_val_folds(pool, seed)  ->  train | validation
            ├─ KermtModel.fit(train, val)         val selects the epoch; calibration molecules absent from BOTH
            ├─ predict_logits(calibration split)  ->  fit_temperature_scaler  (calibration arrays only)
            └─ predict_logits(TEST split)         ->  fitted scaler  ->  final metrics
```
Calibration molecules are excluded from **both training and epoch-selection validation**
(pinned by `test_calibration_molecules_never_reach_fit`); the test set touches only the final
transform-and-score step. **Consequence — KERMT's effective training pool differs from the
XGBoost pipeline's.** Seed-0 labelled training molecules, XGBoost train vs KERMT Tier-0 defaults:
cyp3a4 8,604 vs 5,405 (−37%); cyp2d6 9,160 vs 5,973 (−35%); cyp2c9 8,435 vs 5,238 (−38%);
ames 5,077 vs 3,403 (−33%); herg 9,195 vs 9,418 (+2%); hia 403 vs 329; pgp 846 vs 748;
bbb 1,376 vs 1,206; solubility 6,578 vs 5,937; lipophilicity 2,940 vs 2,361; caco2 634 vs 478;
ppb 1,130 vs 947; clearance 771 vs 694. This is intentional leakage prevention (union-test removal
plus calibration holdout), not an accident, and it makes the comparison conservative *against*
KERMT for the CYPs. Two further facts surfaced while measuring it:
- **DILI −71% (979 → 287) is a configuration mismatch, not a leakage effect:** XGBoost trained on
  the DILIst-augmented pool; the harness default loads the base pool (`use_augmented_dili=False`).
- **The shared cluster fold does not control per-task validation size.** `toxicity__cls`
  validation holds only **18–24 hERG labels vs ~1,810 AMES labels** across all 5 seeds (hERG and
  AMES cover largely disjoint compounds, so the scaffold groups that fill the validation fold are
  AMES-heavy); `ppb_binding` gets 42–50, `hia` 46. Epoch selection for hERG is effectively
  unmeasured. Recorded, **not fixed** (fold construction is a design decision).

### 4. RNG-state checkpoint/resume — utility DONE, integration NOT done

`ml/utils/rng_state.py` (stdlib-only at import; numpy/torch optional; stageable into the KERMT
container): captures Python, NumPy legacy-global, optional named NumPy `Generator`s, torch CPU and
every CUDA device; deterministic compact-sorted JSON + SHA-256 digest; versioned
`mars-rng-state-v1`; strict/non-strict restore that validates everything *before* mutating (an
all-or-nothing refusal). 23 CPU tests via a fake torch (real-torch test skips — torch absent).
**Not integrated into any training path.** Future integration points: (1) the stock path cannot be
checkpointed from MARS (the loop is in the container) — at most capture host RNG after
`set_global_seed` in `train_kermt_cluster.train_one_seed`; (2) the real point is the Tier-1
trainer's epoch loop (`ml/train/kermt_mixed/train_mixed.py`, runs in-container). Still true:
`PYTHONHASHSEED` cannot be restored in-process, and KERMT CUDA determinism is not established.

### 5. Readiness — `ml/train/readiness_report.py`

Verdict on this machine: **`READY_FOR_GPU_SMOKE_TEST` — CPU-side scope only.** 15 PASS, 5 WARN, 0
FAIL, 4 NOT_EVALUATED (checkpoint binary, KERMT checkout, Docker image, GPU — workstation-only;
re-run with `--target workstation`). Smoke-test blockers: none. Comparison-gate concern: workstation
processed-data identity not established. WARNs: tracked-lockfile acquisition ≠ snapshot (raw
content identical); HIA calibration N=47 with 1 negative; **dozens of uncommitted changes (43 when
measured), so a run's recorded git SHA would not describe the code that ran**. Every check exercises substance
(re-hashes files, loads clusters, runs a calibration micro-run, round-trips RNG state, starts a real
`ExperimentRun`); 28 tests prove it fails on tampered-but-present files. It found and I fixed two
bugs **in my own checks** (looked for `config` inside `provenance.json`; it lives in `config.json`).

### Remaining GPU-dependent gates
Real KERMT logits calibration (unknown at N=241/47); full-endpoint and multi-task KERMT training;
G1–G3 (need the not-yet-built Tier-1 trainer); KERMT CUDA determinism; Docker image identity
(no pinned digest exists); workstation processed-data identity (needs one command on the
workstation).

---

## 2026-09-21 — KERMT calibration path wired; three audit findings recorded (nothing about policy changed)

**Provisional methodology unchanged:** official TDC endpoint splits, strict cluster-level
leakage prevention, Option A for `metabolism__cls`. No split, dataset, cluster definition
or calibration-sizing rule was altered. Real KERMT calibration behaviour is to be evaluated
later on actual logits.

### What was wired (CPU-only, unit-tested; the logit-producing step is GPU-gated)

`fit_temperature_scaler` previously had **zero production call sites** — the KERMT path
never calibrated anything. It now has one:

- `ml/eval/cluster_calibration.py` — `calibrate_endpoints(...)`: per classification
  endpoint, fit on the **calibration split only** via
  `eval.calibration_diagnostics.diagnose_temperature_fit`, then transform + score the
  **untouched test set** (raw and calibrated metrics). The fit function takes only
  calibration arrays *by signature*; test arrays are read after the scaler exists.
  Regression columns never reach the fitter. A single-class or unlabelled calibration
  set is reported as `skipped_invalid_calibration_data` with the reason — no scaler is
  fabricated and the other endpoints proceed. A fit pinned to a search boundary is
  reported as `fitted_at_boundary`, not silently accepted or rejected (no project
  document defines an acceptable temperature range).
- `ml/train/train_kermt_cluster.py` — `train_one_seed(..., holdout_calibration=True,
  calibrate=True)` now: build pool → fit → **calibrate** → **test-score** → persist →
  log. Per-endpoint per-seed records carry every field the maintainer specified
  (`endpoint_key, seed, n_fit_samples, n_positive, n_negative, positive_rate, temperature,
  at_boundary, optimizer_success, nll/ece before/after, nll/ece_improved,
  train_val_positive_rate, calibration_positive_rate`) plus `prep_id`, `model_id` and the
  pretrained-checkpoint SHA-256 from `kermt_checkpoint.lock.json`.
- `ml/data/cluster_loaders.py` — `ClusterData.train_pool(holdout_calibration)`,
  `.positive_rates()`, `.calibration_molecules()`.
- Persisted per endpoint under the run's artifacts: `calibration/<endpoint>/
  temperature_scaler.json` (deliberately **not** `calibrator.json` — that is the XGBoost
  registry's `PlattCalibrator` filename and a `TemperatureScaler` there would fail to load)
  and `calibration_diagnostics.json`.

### Decision made inside the wiring, flagged for sign-off: `holdout_calibration=True` by default

The required data flow says the calibrator is fit on a *held-out* calibration split. The
data did not make that true by itself:

- `train_val.csv` **contains** the calibration molecules (`calibration ⊂ train_val`; M1's
  `assignments.csv` only labels them).
- KERMT selects its best epoch on the validation fold. On this snapshot the calibration
  split is most of the XGBoost validation fold (CYP3A4: val n=1,229, calibration n=983).
  Leaving it in would fit the scaler on molecules the model was *selected* on.
- So `train_pool()` removes every calibration molecule, from **all** columns, before the
  fold is built. Stricter than per-column masking on purpose: a calibration molecule for
  CYP3A4 may carry a CYP2D6 label, and CYP labels are strongly correlated across the Veith
  screens, so keeping it via that label would still expose the shared encoder to it.
- `calibrate=True` with `holdout_calibration=False` raises `ValueError` — that
  combination produces a calibration that looks fine and means nothing.

**Measured cost, real M1 snapshot `20260830T200000Z`** (extra training labels lost,
*on top of* the union-test removal): metabolism__cls cyp3a4 −715 / cyp2d6 −836 /
cyp2c9 −803 (pool 9,720 → 8,700); toxicity__cls herg −1,056 / ames −576; A&D cls
hia −65 / pgp −105 / bbb −163; A&D reg solubility −789 / lipophilicity −316 /
caco2 −77 / ppb −114; metabolism__reg clearance −88; dili −50.

**Consequence to weigh:** KERMT's training pool now differs from the pool XGBoost trained
on. XGBoost's CV folds were built over all of `train_val`. The KERMT-vs-XGBoost comparison
therefore must be made on the **test** set, not the validation fold (see finding 2 below).
Setting `holdout_calibration=False, calibrate=False` restores the full pool for a run that
does not calibrate.

### Finding 1 — CORRECTION: `absorption_distribution__cls` is not "cleared" on calibration grounds

The 2026-09-20 preflight marked A&D-cls cleared on *training-label* loss (4.6%). It never
checked calibration size. After strict union-test removal the calibration sets are:

| Arm | Endpoint | N | pos / neg | rate | vs blueprint floor of 50 |
|---|---|---:|---|---:|---|
| A&D cls | **hia_absorption** | **47** | **46 / 1** | 0.979 | **below the floor** |
| A&D cls | pgp_inhibition | 97 | 36 / 61 | 0.371 | above |
| A&D cls | bbb_permeability | 157 | 120 / 37 | 0.764 | above |
| dili | dili_liver_injury | 50 | 13 / 37 | 0.260 | at the floor |
| metabolism cls | cyp3a4 / cyp2d6 / cyp2c9 | 241 / 833 / 439 | 67/174, 110/723, 88/351 | 0.278/0.132/0.200 | above (miss the 10% target — see 2026-09-20) |
| toxicity cls | herg / ames | 1,050 / 576 | 616/434, 392/184 | 0.587 / 0.681 | above |

HIA falls from 50 to 47 — **below Module 4's floor** — with a single negative example, and
its promoted XGBoost Platt calibrator was already fit on 49 positives + 1 negative. Not
fixed (policy is out of scope); the wiring will record it as a fit on 47 rows with
`n_negative=1`, or skip it if the negative is lost. Needs a maintainer call before A&D-cls
calibration is treated as meaningful.

### Finding 2 — no code path evaluates the held-out test set; XGBoost baselines are validation-fold numbers

Verified from `ml/runs/evaluations/*.json` (no key or metric refers to test; per-seed
`n_samples` equals the validation-fold size, e.g. CYP3A4 1,229) and by grep (the only
reference to `.test` in `train/` is `preflight_sweep.py`'s row count). The 70-run XGBoost
sweep reports **5-seed validation-fold metrics only.** Blueprint Module 4/11 select the
winner "on held-out scaffold-split **test** set". So the KERMT-vs-XGBoost comparison
cannot be made yet: KERMT (new wiring) reports test metrics, XGBoost reports none. This
is CPU-doable (evaluate the 70 existing artifacts on test; no retraining) but was **not
done here** and is now an explicit prerequisite in `next_steps.md`.

### Finding 3 — the tracked lockfile and this machine's data are different acquisitions

`ml/data/metadata/datasets.lock.json` is acquisition `20260918T090143Z` (written by the
workstation re-acquisition, commit `64e1054`); this machine's raw + processed data and all
70 XGBoost runs are acquisition `20260830T181633Z`. **Verified content-identical:** all 15
`snapshot_sha256` values match between the old and new lockfiles; the only field that
changed is `ppb_binding.in_admet_benchmark_group` True→False (the documented Option-C
registry policy). This explains the 5 pre-existing failures in
`test_acquisition_lockfile.py`: 3 look for `raw/*/20260918T090143Z/` (absent here), 2 are
stale expectations after Option C. What is **not** established from repository evidence:
that the workstation's processed splits (`prep_id 20260918T090433Z`, gitignored) are
byte-identical to `20260830T200000Z` — only that the raw inputs are and that the counts
quoted on 2026-09-18 match. Verify on the workstation before comparing KERMT to XGBoost.

---

## 2026-09-20 — RESOLVED: KERMT mixed-type cluster limitation. Three-tier ladder approved; option (b) fork rejected

**This closes the 2026-09-18 "Not decided" item.** Literature review + a direct read of
KERMT's own source settled it. Maintainer decision taken on two axes: **build the full
ladder (Tier 0 + Tier 1 + Tier 2), and correctness comes ahead of the Sep 30 date.**

### What the literature settled

- **Type-homogeneous grouping is the published SOTA path, not a compromise.** ADMET-AI
  (Swanson et al., *Bioinformatics* 2024) trains exactly two Chemprop-RDKit multitask
  models over its 41 TDC datasets — one over all 10 regression sets, one over all 31
  classification sets. Chemprop itself ties loss choice to a single dataset type, so
  **KERMT inherits this constraint by lineage, not by oversight.** Our logged option (a)
  is what the field's leading ADMET platform actually does.
- **Multi-task frequently loses at our data sizes.** Negative transfer is well documented
  (one benchmark: single-task KPGT wins 3/5 tasks, multitask 1/5). The Oct-2025 KERMT
  multitask paper (arXiv 2510.12719) — which finetunes *this exact backbone* — finds gains
  concentrated **>60K datapoints**. MARS's endpoints are 910–13,445. This tempers
  expectations for every tier and is why the blueprint's "empirical winner selection"
  language is load-bearing: **a result where multi-task loses is a publishable finding,
  not a failure.**
- **Regression-as-classification is sound** (Tier 2's basis): "Stop Regressing"
  (Farebrother et al. 2024) shows binned cross-entropy beating MSE with the largest
  margins (1.8–2.1x) in *multi-task* settings; ordinal binary decomposition
  (Frank & Hall 2001; Li & Lin 2007) turns a continuous target into K-1 binary
  `y > t_k` tasks with the CDF recovered by summation. Frank-Hall does **not** guarantee
  monotonicity when the binary models are learned independently — must be enforced post-hoc.
- **Kendall, Gal & Cipolla 2018** confirms the blueprint's Module 4 formula: `1/(2σ²)`
  for regression, `1/σ²` for classification. The blueprint already mandates exactly this.

### Four findings from reading KERMT's source (these changed the problem)

1. **Cross-endpoint split leakage — highest-risk item, previously unconsidered anywhere
   in MARS.** Twelve endpoints adopt their *own* TDC benchmark split. A molecule can be
   `train_val` for `solubility_logs` and `test` for `hia_absorption`. **Any shared-encoder
   cluster run therefore leaks through the encoder** and would silently inflate every
   cluster number against the 70 completed XGBoost baselines. This is a correctness
   precondition for Tier 0, Tier 1 **and** Tier 2 — not a Tier-1 concern. Fixed in the
   loader (see `next_steps.md`), never discovered downstream.
2. **Kendall weighting is UNREACHABLE through MARS's current KERMT path — and cannot be
   reached by adding a flag.** Two layers, verified separately against the pinned commit
   `e402473`:
   - `task/train.py` builds `MTLLoss` only under `if args.use_mtl_loss:`, and `log_sigma`
     *is* genuinely optimized when that is set
     (`optimizer.param_groups[1]['params'].append(mtl_loss.log_sigma)`). So `main.py
     finetune` itself can do Kendall weighting.
   - **But MARS never calls `main.py` directly.** It calls
     `agent/scripts/run_finetune_local.py`, and that wrapper **never forwards
     `use_mtl_loss`** — it is absent from all three of its passthrough tuples
     (`TRAINING_FLAGS`, `TASK_FLAGS`, `FFN_FLAGS`) and is never appended to the argv it
     builds for `main.py`. It also uses strict `p.parse_args(argv)`, so passing
     `--use-mtl-loss` to it would be an **unrecognized-argument hard failure (exit 2)**,
     not a silent no-op.

   **Consequence, and it is structural rather than a missing flag:** the stock-CLI path
   (a) can only ever do **equal weighting**. That is fine — equal weighting is exactly
   blueprint Module 4's *mandatory baseline comparison*. But it means **all three
   loss-balancing arms (fixed / Kendall / GradNorm) are delivered by Tier 1**, for pure-type
   clusters as well as mixed ones. The `toxicity` cluster's Kendall arm therefore also needs
   Tier 1; it is not obtainable from the stock CLI. This also sharpens G3: stock KERMT *is*
   fixed weighting, which is precisely why the Tier-1 trainer is run in `mode="fixed"` for
   that parity gate.

   **An earlier draft of this entry said the fix was to emit `--use-mtl-loss` from
   `_hyperparam_flags()`. That is wrong and would have failed every Tier-0 run at the next
   GPU session.** Caught during CPU-side prep by reading the wrapper script rather than
   trusting the layer below it. No such flag is added to `KermtConfig`.
3. **KERMT is usable as a library — no fork is needed to do mixed-type training.**
   `KermtFinetuneTask` exposes `self.kermt` (the `KERMTEmbedding` encoder) plus dual
   `mol_atom_from_atom_ffn` / `mol_atom_from_bond_ffn` heads, already builds
   `nn.ModuleList` per-target heads under `ffn_num_task_specific_layers`, and `forward()`
   returns **logits** in training mode — sigmoid is applied only in eval, gated by a
   single `self.classification` bool. `kermt_container.sh run -- "<cmd>"` runs any
   command inside the container. Mixed-type training is therefore a **MARS-owned training
   loop that imports KERMT**, not a patch to it. `KermtFpGeneration` also exists, so
   frozen-encoder embedding extraction is natively available if ever needed.
4. **CORRECTION — KERMT's uniform `MTLLoss` is NOT buggy for pure-type clusters.**
   It uses `precision = 0.5*exp(-2logσ)` for every task, which looks like the regression
   form applied to classification. It is not a bug: substituting `σ_k = σ_c/√2` gives
   `1/(2σ_k²) = 1/σ_c²` and `log σ_k = log σ_c − ½log2`, so the classification objective
   differs by a **per-task additive constant** — identical gradients, identical optimum,
   identical effective weights. It is an exact reparameterization. **It only bites when
   classification and regression coexist in one run**, which is precisely the mixed
   clusters. When reporting `log σ` for a pure-classification cluster, apply the offset
   `log σ_compliant = log σ_kermt + ½log2`. **Do not "fix" this upstream** — an earlier
   draft of this analysis wrongly called it non-compliant.

### The approved architecture — three tiers, kept strictly distinct

The three training paths must never be conflated in code, run names, or results tables:

| | Path | What trains it | `model_family` |
|---|---|---|---|
| **(a)** | Stock KERMT, type-homogeneous | KERMT's own CLI, unmodified | `kermt_multitask_subgroup` / `kermt_single` |
| **(b)** | MARS-owned mixed-type training | MARS trainer importing KERMT as a library, in-container | `kermt_mixed` |
| **(c)** | Ordinalized all-classification | KERMT's own CLI, unmodified, on encoded targets | `kermt_ordinal` |

**Tier 0 (path a)** — type-homogeneous subgroups. **Introduces MARS-side harness and CLI
code only; it introduces no new KERMT optimization or model logic whatsoever.** The
training step is the existing `KermtModel` shelling out to the stock CLI exactly as it does
today. What is new is MARS-side plumbing: cluster registry, leakage-safe cluster loader,
per-endpoint result decomposition, a sweep driver.

**Tier 1 (path b)** — MARS-owned mixed-type trainer, staged into the container's `/data`
bind mount and run with `import kermt`. Per-column type-correct losses (BCEWithLogits vs
MSE/L1 on standardized targets), type-correct Kendall precisions, masked per-task loss,
stratified batch composition, per-task logσ logging, fixed-weight escape hatch, and
selectable `fixed | kendall | gradnorm` weighting. Emits true pre-sigmoid logits.

**Tier 2 (path c)** — ordinal-CDF homogenization: each regression endpoint encoded as M
binary `y > quantile_m` columns so a mixed cluster becomes one all-classification stock-CLI
run with zero patching; scalar decoded from the survival function with monotonicity enforced
(`np.minimum.accumulate`). **Investigated only after Tier 1**, and gated first by a
zero-GPU discretization-ceiling test.

### Clarifications that the plan document got loose and are corrected here

- **`kermt_model.py` takes FOUR changes, not "three small things"** as an earlier draft
  said: (1) the homogeneity guard the docstring already claims but does not implement,
  (2) `target_names` / `target_task_types` properties, (3) an explicit
  `supports_loss_weighting = False` marker plus documentation that the stock path is
  equal-weighting-only — **not** a `--use-mtl-loss` flag, see finding 2,
  (4) `predict_logits()`.
- **`metabolism__reg` = `{clearance_microsomal}` is a single-task run, not a homogeneous
  multi-task subgroup.** It is the **mandatory single-task KERMT baseline already owed**
  for that endpoint under Module 4's "mandatory baselines per endpoint". It runs once under
  `model_family="kermt_single"` and is cited in both roles. It must not be counted as, or
  reported as, a multi-task cluster arm — doing so would fabricate a multi-task result out
  of a single-task run. Tier 0 therefore yields **three** genuinely new multi-task
  subgroups: `metabolism__cls` (3 tasks), `absorption_distribution__cls` (3),
  `absorption_distribution__reg` (4). `toxicity__cls` is already covered by the existing
  pure-cluster path. All Tier-0 runs are equal-weighting by construction (finding 2).
- **G3 defined precisely.** G3 compares the MARS-owned Tier-1 trainer (path b) against the
  stock KERMT CLI (path a) on **classification-only data, where both paths are legitimately
  capable of running the identical job** — that is the whole point of the gate: it isolates
  trainer-implementation differences from mixed-type effects. Datasets: `ames_mutagenicity`
  (single-task) and `toxicity__cls` (hERG + AMES, 2-task). Seeds: `FIXED_SEEDS` = 0,1,2,3,4,
  identical folds from `five_seed_train_val_folds`, identical hyperparameters, Tier-1 run in
  `mode="fixed"` with all weights 1.0 (so it is imitating stock equal weighting, not Kendall).
  Quantity compared: **validation-fold AUROC** from `ml/eval/metrics.py::compute_metrics`,
  computed host-side by MARS for both paths (KERMT's own `test_result.csv` is never read —
  standing rule). Pass iff `|mean_A − mean_B| <= 0.5 * max(std_A, std_B)` **and** paired
  per-seed `|ΔAUROC| <= 0.02` on at least 4 of the 5 seeds.

### Rejected, with reasons

1. **Patching KERMT's `get_loss_func` / `task/train.py` (logged option b) — REJECTED.**
   The checkout lives at `~/mars-work/kermt-src/`, **outside the MARS git tree**, so
   `tracking/provenance.py` cannot see it, `ExperimentRun` cannot record it, and the patch
   dies on any re-clone or image rebuild — every mixed-cluster number would be
   unreproducible by construction. It also alters the `run_finetune_local.py` /
   `check_checkpoint.py` contracts that `KermtModel` depends on, putting the comparability
   of the 70 completed XGBoost runs at risk. **Import-as-library (Tier 1) gives identical
   capability with provenance MARS actually controls.** Stock KERMT stays an untouched,
   pinned dependency.
2. **Deferring mixed-type training entirely (logged option c) — REJECTED.** It kills a
   mandatory Module 11 ablation axis ("fixed vs. uncertainty-weighted vs. GradNorm" for
   Metabolism and A&D) and leaves Module 4's clustering decision untested.
3. **Widening `MARSModel.task_type` to a list — REJECTED.** It breaks `XGBoostModel`,
   `compute_metrics`, `evaluate.py`, `serve/registry.py` and `serve/predictor.py` at once.
   Use additive `target_names` / `target_task_types` properties with single-task defaults.
4. **GradNorm as the default — REJECTED.** Cost (one extra partial backward per task), an
   extra hyperparameter (α), no ADMET precedent. It is the mandated ablation arm, not the
   shipped method. Kendall stays the default per blueprint Module 4.

### MEASURED 2026-09-20 — the leakage fix is cheap everywhere except Metabolism

`ml/train/preflight_clusters.py` run on the real M1 snapshot `20260830T200000Z`
(zero GPU, full output in `ml/runs/cluster_preflight.json`):

| Cluster arm | train_val rows | dropped | worst per-endpoint label loss |
|---|---:|---:|---:|
| `toxicity__cls` | 16,240 | 30 | **0.2%** |
| `dili_standalone__cls` | 378 | 0 | 0.0% |
| `metabolism__reg` (clearance) | 881 | 0 | 0.0% |
| `absorption_distribution__cls` | 2,765 | 56 | 4.6% |
| `absorption_distribution__reg` | 11,570 | 446 | 14.6% |
| `absorption_distribution` (whole) | 13,724 | 684 | 16.1% |
| **`metabolism__cls`** | 9,720 | **5,625** | **29.2%** |
| **`metabolism` (whole)** | 10,568 | **5,629** | **29.2%** |

**Metabolism is the problem, and the cause is structural, not a bug.** CYP3A4 /
CYP2D6 / CYP2C9 are the Veith screens of substantially the *same compound library*
against three enzymes, and each adopted its own independent TDC test split. So a
molecule that is test for CYP3A4 is very often train for CYP2D6 — removing the union
of the three test sets costs each CYP roughly 29% of its training labels
(cyp3a4 −2,871 of 9,833; cyp2d6 −2,805 of 10,469; cyp2c9 −2,762 of 9,640).

This is not an argument against the leakage fix — without it those numbers would
simply have been wrong. It is a real cost that has to be weighed, and it is exactly
why the measurement was made before spending GPU time. **Not decided here; flagged
for the maintainer** — full analysis in the 2026-09-20 memo section below.

#### Deeper measurement, 2026-09-20 (read-only analysis, no data changed)

- **The structural cause is confirmed with numbers, not assumed.** Pairwise Jaccard
  overlap of the full compound sets: CYP3A4↔CYP2D6 **0.641** (9,912 shared),
  CYP3A4↔CYP2C9 **0.612** (9,242), CYP2D6↔CYP2C9 **0.631** (9,723). Against
  `clearance_microsomal` the Jaccard is **0.002** — clearance is essentially
  disjoint from the CYPs and contributes almost nothing to the loss (it sacrifices
  8 of 881 labels, 0.9%). The damage is entirely internal to the three Veith screens.
- The three CYP test sets themselves overlap: 7,495 summed → **6,330 unique** in the
  union (1,165 collapse).
- **Calibration split damage is worse than train_val damage and was not previously
  recorded.** CYP3A4 loses **75.5%** of its calibration split (983 → 241), CYP2C9
  **54.5%** (964 → 439), CYP2D6 **20.4%** (1,047 → 833). All three still clear
  blueprint Module 4's absolute floor of 50 compounds, but all three fall well short
  of that rule's *10%-of-train_val* target (CYP3A4 241 vs a 696 target; CYP2C9 439 vs
  687; CYP2D6 833 vs 766 — only CYP2D6 clears it). Temperature scaling is a
  1-parameter fit, which is the regime the blueprint explicitly chose *because* it
  tolerates small calibration sets — so this is a tension to record, not an automatic
  failure.
- **Class balance shifts slightly but measurably:** CYP3A4 positive rate 0.4093 →
  0.4384 (**+2.90 pp**), CYP2C9 0.3393 → 0.3518 (+1.25 pp), CYP2D6 0.1969 → 0.1900
  (−0.69 pp). Non-random with respect to the label, so it is worth reporting, though
  no project rule defines a threshold for acceptable drift.
- **Multi-task label density is genuinely high**, which is the argument *for* the
  cluster: of the 9,720 surviving cluster molecules, 39.0% carry all three CYP
  labels, 43.2% carry two, 17.8% carry one.
- **By the blueprint's own stated evidence base, `metabolism__cls` sits below the
  regime where MT benefit is expected — before and after the loss.** Module 4 records
  that pretrained MT outperforms specifically with ">5 correlated tasks and >50,000
  combined datapoints; below that, benefit is marginal or reverses."
  `metabolism__cls` is **3 tasks / 29,942 labels before removal, 21,504 after** —
  under both criteria either way. The Oct-2025 KERMT multitask paper's >60K threshold
  points the same direction. This reframes the decision: the 29% loss is not the only
  reason to doubt this arm.
- All four metabolism endpoints are `in_admet_benchmark_group=True` in
  `ml/data/metadata/datasets.lock.json` and `split_method="adopt_benchmark"` in their
  `provenance.json` — so unlike the hERG and PPB exceptions, an official TDC split
  **does** exist here and regenerating one would discard it.

The A&D and Toxicity arms need no such decision.

### MEASURED 2026-09-20 — Tier 2 is viable at 16 bins

Discretization-ceiling test (`featurize.ordinal.discretization_ceiling_mae`, no
training at all) against the completed XGBoost baseline MAE, per regression endpoint:

| Endpoint | XGBoost MAE | ceiling @8 bins | ceiling @16 | ceiling @32 |
|---|---:|---:|---:|---:|
| caco2_permeability | 0.336 | 35.0% | **17.6%** | 9.7% |
| lipophilicity_logp | 0.519 | 33.4% | **17.3%** | 8.6% |
| ppb_binding | 7.49 | 34.0% | **18.5%** | 9.0% |
| clearance_microsomal | 19.21 | **24.3%** | 17.6% | 6.8% |
| solubility_logs | 0.726 | 44.2% | **23.3%** | 12.3% |

**16 bins clears the ≤25%-of-baseline gate for all five**, so Tier 2 is not blocked
by discretization loss. `solubility_logs` is the tightest at 23.3% and is the one to
watch; 32 bins halves every ceiling if headroom is wanted, at the cost of more heads
(A&D at 32 bins would be 4×31 + 3 = 127 targets, which is likely impractical — 16 is
the working default).

### Open follow-ups

- **Metabolism cluster scope** — the 29% decision above. Blocks the `metabolism__cls`
  arm only; `absorption_distribution` and `toxicity` are unaffected and can proceed.
- DILI-into-toxicity joint training (blueprint Module 4's flagged empirical question) is
  still untested and is now cheap to test once the cluster substrate exists.
- `ppb_binding` acquisition/test drift and the missing external DILIst file (both from the
  2026-09-18 entry) remain open and are unrelated to this decision.

---

## 2026-09-18 (cont'd) — Smoke tests 1-6 PASSED on real AMES data; M1 re-acquired on this workstation

**M1 data re-acquired on this workstation** via the existing isolated-venv mechanism (`ml/data/acquisition/README.md`), native Linux instead of WSL (`python3.12 -m venv --without-pip` + `get-pip.py`, since `python3.12-venv` apt package wasn't installed and neither system Python nor MARS's own `.venv`/`ml/.venv` were touched). All 15 canonical dataset_keys acquired (excluding `ppb_binding__all_species`, a documented deferred ablation — see below); dedup/split numbers match the original 2026-08-30 audit exactly (e.g. AMES 7278→7255, CYP3A4 12328→12295), confirming the pipeline's own determinism claim. `ml/data/prepare.py` run afterward — all 15 processed successfully.

**Two dataset-registry findings surfaced, NOT modified (flagged only):**
1. `ppb_binding` and `ppb_binding__all_species` share `tdc_name="PPBR_AZ"` in `dataset_registry.py`, so both can't be acquired in one `acquire.py` pass (second one hits `FileExistsError` on the shared raw path). Excluded the deferred ablation variant via `--only` (matching the original, already-audited 15-dataset M1 baseline) — did not touch the registry or acquire.py's collision handling.
2. `test_acquisition_lockfile.py::test_benchmark_split_partitions_the_full_set_except_ppbr` and `::test_blueprint_n_flags_recorded` now fail against the fresh lockfile — traced to a real, already-resolved-elsewhere code change: `ppb_binding`'s `in_admet_benchmark_group` flag was flipped to `False` in the registry sometime after 2026-08-30 (the "Option C" fix mentioned in `mars-status_M1.md`'s "Registry–vs–lockfile divergence" note), so a fresh acquisition correctly no longer attaches a `benchmark_split` to it — the two tests were written against the old lockfile's now-superseded quirk and haven't been re-run since that registry fix landed (this session is the first re-acquisition since). Not fixed here — outside this session's KERMT-integration scope; flagged for whoever next touches `ml/data/`.
3. `test_dilist_augmentation.py` + 3 `test_loaders.py` tests still fail — DILIst augmentation needs the external FDA/NCTR DILIst file (not a TDC dataset, not part of `acquire.py`), which this session did not obtain (external-source acquisition, out of scope; flagged per the session's own stop-at-external-source instruction).

**Two real bugs found and fixed in `ml/models/kermt_model.py` during the actual smoke run (not in KERMT's code):**
1. `_parse_json_stdout` couldn't parse `check_checkpoint.py`'s real output — it's pretty-printed JSON (`indent=2`) prefixed by container/CUDA banner text on stdout; the original whole-string-then-single-line fallback handled neither. Fixed to scan backward for a line starting `{` and parse from there to EOF. Regression test added.
2. `KermtConfig.metric` defaulting to nothing let `run_finetune_local.py` fall back to `defaults_finetune.json`'s unconditional `"mae"` — invalid for `dataset_type=classification` (`kermt/util/parsing.py`'s own validation caught it: `ValueError: Metric "mae" invalid for dataset type "classification"`). Fixed: wrapper now always resolves an explicit, task_type-correct metric (`auc` / `mae`) rather than relying on the config file's regression-oriented default. Regression tests added.
3. `fit()`/`predict()` read `run_manifest["save_dir"]` / `["output_csv"]` as host paths — they're CONTAINER paths (`/runs/...`, since we pass `--out /runs`), so the check for the finetuned checkpoint failed with "not found" even though finetune had genuinely already succeeded. Fixed to always construct the host path from the known `run_dir` bind-mount instead of trusting the container-side string. Two regression tests added (mocking `_run_container`, no docker needed to run them).

All 35 `ml/tests/test_kermt_{model,adapter}.py` unit tests pass; full `ml/tests/` suite: 375 passed (the pre-existing 6 explained above; none newly broken).

**Real smoke-test results (endpoint: `ames_mutagenicity`, classification, 300 real train / 80 real val molecules — genuine scaffold-fold subset of the real 5,802-compound train_val pool, never touching the 1,453-compound held-out test set):**

| Smoke | Result |
|---|---|
| 1 — container import | PASS: `cuda_available=True`, `device_count=1`, `torch==2.9.1`, CUDA 12.8 runtime, `kermt`/`cuik_molmaker` import clean |
| 2 — checkpoint load | PASS: `check_checkpoint.py --mode finetune_init` → `ok:true`, `model_type=hybrid`, arch matches HF card exactly |
| 3 — forward (real data) | PASS: real graph conversion + forward, `loss_train=1.3317` epoch 0, no NaNs |
| 4 — backward | PASS (inferred from real training dynamics, not an isolated hook — KERMT's CLI exposes no standalone forward/backward entry point): `loss_train` 1.3317→1.0341→0.8531 and `auc_val` 0.6575→0.6756→0.7244 monotonically improve across 3 epochs — proof gradients are flowing and the optimizer is updating real weights, not a static/no-op pass |
| 5 — tiny finetune + ckpt save/reload | PASS: 3 epochs, batch_size=16, wall time 50.2s (includes container/prepare overhead; pure train loop ≈13.5s); reload-then-repredict bit-identical (`RELOAD_PREDS_MATCH=True`) |
| 6 — MARS eval integration | PASS: `ml/eval/metrics.py::compute_metrics` → AUROC 0.7244 (matches KERMT's own `auc_val` exactly), AUPRC 0.8457, Brier 0.1920, ECE 0.1395; `tracking.experiment.ExperimentRun` logs the run + metrics cleanly |

Peak GPU memory across the whole fit+predict: 1,909 MiB (of 16,376 MiB) including a ~412 MiB desktop-process baseline — KERMT's own delta ≈1.5 GB at batch_size 16 on this tiny run. Comfortable headroom; no OOM, no attempt yet at a larger-batch ceiling (out of this session's scope per the user's explicit stop instruction).

**Confirmed by source inspection, not assumed:** KERMT's finetune CLI (`kermt/util/parsing.py`) has no `--fp16`/`--bf16`/`--amp`, no gradient-accumulation flag, and no gradient-checkpointing flag. Precision is fp32-only; the only VRAM lever exposed is `--batch_size` itself.

**Mixed classification+regression multi-task limitation (Metabolism, Absorption & Distribution clusters): still open, per explicit instruction not to solve it this session.** Nothing new to add beyond the entry above — flagged, not touched.

---

## 2026-09-18 — KERMT integration (Phase 3+): GPU workstation, container isolation, wrapper built

**Workstation.** RTX A4000, 16 GB VRAM, driver 580.173.02 (CUDA 13.0), nvcc 13.2,
Python 3.11.15 in `.venv`. Docker 29.1.3 + nvidia-container-toolkit 1.20.0
present and verified (`docker run --gpus all ... nvidia-smi` succeeds).

**RDKit compatibility — resolved empirically, not assumed.** Cloned
`github.com/NVIDIA-BioNeMo/KERMT` @ v2.0.0 (commit `e402473`) and read the
actual source (not guessed): `kermt/data/molgraph.py`, `kermt/data/kermtdataset.py`,
and `kermt/util/features.py` all have an **unconditional, top-level `import
cuik_molmaker`** — not gated behind `args.use_cuikmolmaker_featurization`
(that flag only gates which *codepath* runs once the module is already
imported). This contradicts the 2026-09-17 pre-flight's open question ("a
CPU-only attempt... skipping the cuik_molmaker conda pins... is plausible but
genuinely untested") — it is not plausible. You cannot `import kermt.data.*`
at all without `cuik_molmaker` built, regardless of rdkit version or CUDA
usage intent. `cuik_molmaker` is a source-only PyPI sdist (no wheel) that
compiles CUDA extensions against a specific torch+CUDA build.

**Decision: isolate via KERMT's own official Docker container, do not
hand-install into `ml/.venv`.** KERMT's repo is container-first by design
(`agent/README.md`) and ships a Dockerfile (`nvidia/cuda:12.6.3-cudnn-devel-ubuntu22.04`
base) that already builds `cuik_molmaker` + pins `rdkit==2025.9.1` in a conda
env named `kermt`, completely isolated from `ml/.venv`'s `rdkit==2026.3.6`.
This makes the RDKit-version question moot rather than answered — there is no
shared environment for the two pins to conflict in. `ml/.venv` is untouched;
no `transformers` or PyTorch Geometric were installed anywhere (KERMT uses
neither — it's a from-scratch GROVER-style message-passing implementation,
confirmed by reading `kermt/model/models.py` and `kermt/model/layers.py`; the
`transformers>=4.40` line in `ml/requirements.txt` is a stale placeholder
from before the backbone was chosen and should be removed in a future pass).

Built `kermt:latest` via `agent/scripts/kermt_container.sh ensure_image`
(the repo's own bootstrap helper, not a hand-rolled `docker build`). Vendored
the KERMT checkout **outside** the mars-admet git tree, at
`~/mars-work/kermt-src/` (sibling checkout, referenced via `MARS_KERMT_REPO`
env var) — it's a third-party tool dependency, not MARS source.

**Checkpoint downloaded and hashed.** `nvidia/NV-KERMT-70M-v2` ->
`kermt_contrastive_v2.0.pt` (282,379,314 bytes) + its three vocab files,
into `ml/data/checkpoints/kermt/NV-KERMT-70M-v2/` (gitignored, mirrors the
`ml/data/raw/` convention). SHA256 provenance recorded in the newly-added,
tracked `ml/data/metadata/kermt_checkpoint.lock.json`. Not yet loaded with
`torch.load` inside the container (Smoke 2) as of this entry — see
`next_steps.md` for exact status.

**Genuine, verified architectural incompatibility — NOT worked around,
flagged for a maintainer decision:** KERMT's own `main.py finetune` takes
ONE `--dataset_type` value for the whole run (`kermt/util/parsing.py` L598
`assert args.dataset_type is not None`; `task/train.py` picks one
`loss_func` from it via `get_loss_func(args, model)`). MARS's blueprint
Metabolism cluster (3 classification + 1 regression) and Absorption &
Distribution cluster (4 regression + 3 classification) are **mixed-type**
and cannot be finetuned as a single heterogeneous KERMT run against the
stock CLI. Same-type multi-task clusters (Toxicity: hERG + AMES, both
classification) work fine via KERMT's native `ffn_num_task_specific_layers`
per-target heads. KERMT's own `kermt/util/loss.py::MTLLoss` **is** Kendall/
Gal-Cipolla homoscedastic uncertainty weighting natively (`precision =
0.5*exp(-2*log_sigma)`, applied on top of a per-task masked loss in
`task/train.py`) — good news for same-type clusters, doesn't resolve the
mixed-type problem. Options for the maintainer to choose from (none applied
yet): (a) split each mixed cluster into a same-type sub-group per run
(e.g. Metabolism -> {CYP3A4,CYP2D6,CYP2C9} classification run +
{Clearance} single-task regression run) — cheapest, but weakens the
cluster's intended joint-training rationale; (b) patch `task/train.py`'s
`get_loss_func` to accept a per-task loss-type list (KERMT's code is
Apache-2.0; a real change to code MARS doesn't own, needs its own review);
(c) defer mixed-type joint training entirely and rely on single-task KERMT
per endpoint (already required anyway as the XGBoost comparison baseline)
until this is resolved. **Not decided — this entry exists so it isn't
re-discovered from scratch next session.**

**Adapter is a SMILES/CSV contract, not a graph-tensor transform.** KERMT's
CLI has no entry point that accepts a precomputed atom/bond graph tensor in
place of a SMILES column — every `kermt-*` workflow takes `--csv` with a
`smiles` column and KERMT re-featurizes internally via `kermt/data/molgraph.py`.
`ml/featurize/kermt_adapter.py` therefore hands KERMT MARS's already-
standardized SMILES verbatim rather than translating `mars-graph-v1` tensors.
Chirality preservation is verified as a vocabulary-equivalence claim (both
MARS's `CHIRAL_TAGS` and KERMT's `ATOM_FEATURES['chiral_tag']` one-hot the
same four `Chem.ChiralType` members in the same order — see
`ml/tests/test_kermt_adapter.py::test_chiral_tag_vocab_matches_kermt`), not
a tensor-diff, since no tensor ever crosses the boundary.

**`ml/models/kermt_model.py`** implements `MARSModel` (single-task:
`mars-kermt-single-v1`; same-type multi-task: `mars-kermt-multitask-v1`) by
shelling out to `agent/scripts/kermt_container.sh run -- "python ... "`
inside the container for every actual model operation — KERMT is never
imported in-process. `fit()` passes MARS's val fold as both KERMT's
`--val-csv` and `--test-csv` (the finetune CLI requires both-or-neither);
KERMT's own resulting `test_result.csv` is therefore NOT MARS's real test
metric — MARS computes that separately via `predict()` on the actual held-out
test set, same as the XGBoost baseline already does.

**Open follow-ups (see `next_steps.md` for the live checklist):** Smoke
tests 2-6 not yet run as of this entry; M1 raw/processed data does not exist
on this workstation (gitignored by design, acquired on a different machine)
— acquisition needs to be re-run here before any real finetune can use real
MARS data; mixed-type cluster decision above; `transformers` line removal
from `ml/requirements.txt`.

---

## 2026-09-17 — KERMT pre-flight (Phase 1-2): identity resolved, GPU still required

**No code/training executed — this is the read-only feasibility audit.**
Full report given to the user directly; key facts worth persisting here
since they resolve previously-open follow-ups (CF-8, B-7 from
`next_steps.md`):

**CF-8 (exact checkpoint identity) — RESOLVED.** Confirmed directly from
the model's own Hugging Face repo (`nvidia/NV-KERMT-70M-v2`, fetched via
its public API — not downloaded) and its README: the hosted checkpoint
file is `kermt_contrastive_v2.0.pt` — the **contrastive variant**, not a
base masked-pretrain checkpoint (no base variant is hosted at this repo at
all). Architecture: graph-transformer (GROVER extension), hidden size 800,
6 message-passing+attention layers, 4 heads/layer, latent dim 512, 70.6M
params. Source code is NOT bundled in the HF repo — it lives separately at
`github.com/NVIDIA-BioNeMo/KERMT` (v2.0.0 release tag), with real CLI
entry points already built (`main.py {finetune,predict,fingerprint,eval}`).

**New finding, not previously known:** the official `environment.yml`
pins `pytorch-gpu=2.9.1` and `cuik_molmaker>=0.2,<0.3` (a CUDA-native
featurization accelerator), and the Dockerfile bases on
`nvidia/cuda:12.6.3-cudnn-devel-ubuntu22.04` — i.e. **the officially
documented environment has a hard GPU dependency at setup time**, not
just at training time. Partially offset by a second finding: the CLI
itself exposes `--no_cuda` (forces CPU) and `--use_cuikmolmaker_featurization`
(opt-in, default `False`) — so the *application* doesn't strictly require
CUDA to be exercised, only the *conda environment as officially
documented* does. Whether a CPU-only `torch` build + the plain Python
`kermt`/`task` packages (skipping the `pytorch-gpu`/`cuik_molmaker` conda
pins) actually imports and runs is **untested** — genuinely unknown until
attempted, not assumed either way.

**B-7 (CPU inference for Cloud Run serving) — still open, refined.** Not
resolved by this audit: NVIDIA's own model card states only a GPU-based
"Test Hardware" section (A100/L4, ≥32GB VRAM recommended) with zero
mention of CPU inference anywhere in either the model card or the source
repo's README. This is a real, first-party confirmation that CPU-serving
latency for KERMT is genuinely unvalidated by NVIDIA — Module 10's
CPU-only Cloud Run serving assumption for KERMT remains an open risk,
not newly resolved.

**Environment audit (this machine, 2026-09-17):** Python 3.11.9 (both
venvs); **no `torch` or `transformers` installed anywhere**; **no NVIDIA
GPU** (only Intel Arc integrated graphics — no CUDA path, matches the
blueprint's own stated laptop spec); 15.5GB total RAM (~5GB free at audit
time); Intel Core Ultra 5 125H, 14 cores/18 threads; 139GB free disk
(comfortably enough for the ~282MB checkpoint if downloaded).

**Decision: stopped before installing anything**, per the explicit
instruction to report required installs before making them. Phases 3
(CPU smoke test), 4 (GPU smoke test), 5 (fine-tune smoke test) not
attempted this session — see the full report given to the user for the
exact classification of what's CPU-feasible-to-attempt vs. GPU-required.

---

## 2026-09-17 — M2 production XGBoost sweep: 70/70 complete

**Result: 70/70 runs completed, 0 failed, 0 skipped.** 14 endpoints (the
authoritative `mars_contracts.endpoints.ML_ENDPOINTS`) × 5 seeds
(`FIXED_SEEDS=(0,1,2,3,4)`, unchanged from the existing config — no new
seed list invented). ~172 minutes total CPU wall-clock, zero GPU. DILI
used the augmented (DILIst) dataset per the already-adopted Module 1 §6
decision — not an ablation choice made here.

**Process:** Phase 0 audit (confirmed endpoint/seed/split/config identity
against `mars_contracts`, `ExperimentConfig`, `ml/data/dataset_registry.py`
— nothing inferred from memory) → Phase 1 preflight (`ml/train/
preflight_sweep.py`, all 14 endpoints loaded, class-balance/label-range
sanity, 8-check leakage audit, write-access + W&B connectivity checks) →
Phase 2 pilot (`solubility_logs` seed 0 via the real production CLI path,
W&B on, verified artifact/provenance/promotion/registry-discovery) →
Phase 3 full sweep (`ml/train/run_production_sweep.py`, in-process driver
over the same `train_one_seed` function the CLI uses, one JSONL record per
run written incrementally) → Phase 4/5 verification (`ml/train/
verify_sweep.py`: all 5 seeds present per endpoint, no duplicate
seeds/run_ids, every artifact reload-tested with a live smoke prediction,
registry AD/calibrator presence matches task type exactly).

**Preflight finding, not a blocker:** 6/14 endpoints (`solubility_logs`,
`bbb_permeability`, `cyp3a4/2d6/2c9_inhibition`, `dili_liver_injury`)
show small RDKit-vs-TDC Murcko-scaffold-bucket overlaps on their adopted
TDC benchmark splits — zero actual duplicate compounds (exact-SMILES
check clean), exactly the effect already documented in M1 Run 2 for
BBB/CYPs, now confirmed to also affect `solubility_logs` and augmented
DILI. Not routed around — logged, classified as non-blocking per the
established M1 policy ("do NOT try to fix the overlap... log it and move
on"), and the sweep proceeded. Two tooling bugs from mis-implementing this
classification were found and fixed (see `mistakes.md`); no retraining was
needed for the fix.

**Aggregated 5-seed metrics (mean ± std), from `ml/runs/evaluations/*.json`:**

| Endpoint | Task | Metric | Value |
|---|---|---|---|
| solubility_logs | regression | MAE | 0.726 ± 0.010 |
| lipophilicity_logp | regression | MAE | 0.519 ± 0.010 |
| caco2_permeability | regression | MAE | 0.336 ± 0.010 |
| hia_absorption | classification | AUROC / AUPRC | 1.000 ± 0.000 / 1.000 ± 0.000 — **flagged anomaly, see below** |
| pgp_inhibition | classification | AUROC / AUPRC | 0.953 ± 0.004 / 0.969 ± 0.004 |
| bbb_permeability | classification | AUROC / AUPRC | 0.684 ± 0.022 / 0.828 ± 0.026 |
| ppb_binding | regression | MAE | 7.490 ± 0.117 |
| cyp3a4_inhibition | classification | AUROC / AUPRC | 0.943 ± 0.003 / 0.847 ± 0.004 |
| cyp2d6_inhibition | classification | AUROC / AUPRC | 0.913 ± 0.003 / 0.737 ± 0.007 |
| cyp2c9_inhibition | classification | AUROC / AUPRC | 0.901 ± 0.006 / 0.689 ± 0.012 |
| clearance_microsomal | regression | MAE | 19.212 ± 1.193 |
| herg_cardiotoxicity | classification | AUROC / AUPRC | 0.836 ± 0.007 / 0.870 ± 0.007 |
| ames_mutagenicity | classification | AUROC / AUPRC | 0.823 ± 0.009 / 0.915 ± 0.004 |
| dili_liver_injury | classification | AUROC / AUPRC | 0.636 ± 0.034 / 0.626 ± 0.021 |

**Flagged, not silently accepted: HIA's AUROC = 1.000 ± 0.000 across all 5
seeds.** Plausible given HIA's small, severely imbalanced validation folds
(410 positive / 51 negative in train_val — a val fold can be trivially
separable), but a perfect, zero-variance result across 5 independent seeds
is exactly the kind of number that should be treated with suspicion, not
cited as "our best endpoint," until scrutinized further (e.g. against the
verified-reproducible TDC leaderboard comparison, Module 11 §4). No ranking
of endpoints is implied by this table (per the task's own instruction not
to rank unless the blueprint requires it).

**No blueprint/ranking claims made.** This is the mandatory baseline
(XGBoost/ECFP+descriptors) only — Module 4's single-task GNN and
multi-task cluster models (KERMT) remain entirely unbuilt; Module 11's
full ablation matrix, significance testing, and TDC leaderboard comparison
are M5 scope, not run here.

**Model registry handoff.** All 70 artifacts conform to the existing
`ml/serve/registry.py` contract without any change to that module —
`promote_seed_artifact` (already built for the earlier 1-artifact demo)
scaled to all 14 endpoints × 5 seeds unmodified. `ModelRegistry.
available_endpoints()` now returns all 14; the live Docker container
(unchanged code, artifacts mounted via the existing `docker-compose.yml`
volume) was hit with a real `/predict` request and confirmed 14/14 real
(`model_id != "stub-v0"`) — up from 1/14 before this sweep. Known,
pre-existing, documented limitation unchanged by this sweep: each
`promote_seed_artifact` call refits and overwrites the endpoint-level
Platt calibrator from that call's own seed, so the calibrator saved after
promoting seeds 0→4 in order is fit on seed 4's raw output distribution
only, not an ensemble fit — a minor approximation, not a correctness bug
(Platt scaling parameters are typically stable across similar models from
the same architecture/hyperparameters), documented rather than silently
accepted.

---

## 2026-09-17 — M3 final CPU-side completion pass (same day, second session)

**Audit method.** Re-reviewed the blueprint, `module_milestone_map.md`,
`context.md`, `next_steps.md`, `decisions.md`, and current code against an
explicit checklist (SDF, Cloud Tasks, Cloud Run, Module 3 Stage 1 validation,
registry behavior, batch behavior, compare, caching, rate limiting,
auth/session, account isolation/deletion, migrations, config, health checks,
Docker/Compose) before writing any code, per instruction.

**Classification of every checklist item:**
| Item | Classification | Action |
|---|---|---|
| SDF batch upload | Required for M3, CPU-only, was missing | **Implemented** — real RDKit parse in-container, 501 (not fake success) outside it |
| Module 3 Stage 1 SMILES validation at API boundary | Required for M3, CPU-only, was missing | **Implemented** — 422 on invalid SMILES when ml stack present |
| Model registry behavior | Required, already done | Verified, no change |
| Batch behavior (interactive/async/SSE/results) | Required, already done | Verified, no change |
| Compare endpoint | Required, already done — but didn't handle the new validation error | **Fixed** — catches `ValueError` → 422 |
| Prediction caching | Required, already done | Verified, no change |
| Rate limiting | Required, already done | Verified, no change |
| Auth/session behavior | Required, already done | Verified, no change |
| Account isolation | Required, already done + tested | Verified, no change |
| Account deletion | Required, already done + tested | Verified, no change |
| Database migrations | Required, existed but reversibility unverified | **Verified** — `downgrade -1` / `upgrade head` both clean |
| Environment/configuration handling | Required — insecure default was silent | **Implemented** — startup warning for default `SECRET_KEY` |
| Health checks | Required — only liveness existed | **Implemented** — `/health/ready` (DB+Redis), kept separate from `/health` so CI's dependency-free smoke test still works |
| Docker/Compose behavior | Required — api service had no healthcheck | **Implemented** — added, matching postgres/redis/minio's pattern |
| `GET /molecule/{id}/3d` | Required for M3 (blueprint-scoped, CPU-only, data dependency already complete since M1) — found missing during this audit, not on the original checklist | **Implemented** — real ETKDGv3+MMFF94 conformers via `ml/featurize/conformers.py`, id->smiles registered by `/predict` in Redis, cached, 404 for unknown/expired id. Bug found+fixed: registration only fired on cache miss, so cached predictions never got registered — fixed to register on hit and miss too |
| Cloud Tasks | Requires GCP credentials/approval | Left as documented `NotImplementedError` placeholder — correct, not a gap |
| Cloud Run deployment | Requires GCP credentials/approval | Not started, per explicit instruction |
| KERMT / 70-run sweep | Blocked by / IS the M2 scope | Not touched, per explicit instruction |
| R2/MinIO wiring for batch results | Requires Cloudflare credentials for the real target; CPU-feasible for the MinIO stand-in but judged not required (Redis stand-in already proves the contract) | Deferred, documented |
| `BatchPredictOptions` as query params vs. form-field group | Not actually required for M3 completion — a contract-polish item for M4 frontend integration | Deferred, documented |

**No milestone-structure changes.** `module_milestone_map.md`'s table and
the M0–M5 mapping are unchanged — this pass only affects M3's own internal
completion status, not the audit's structure.

**Verdict: M3 is now locally/container complete** for every item that is
(a) blueprint-required, (b) CPU-only, and (c) doesn't depend on GCP
credentials, paid infrastructure, or M2's production model artifacts. The
remaining open items are all correctly classified as external-dependency or
explicitly-deferred, not missing local work.

---

## 2026-09-17 — M3 kickoff: Module↔Milestone mapping audit + serving/auth/batch build

**Mapping audit (done first, per instruction, before any code).** Full
authoritative table now lives in `documentation/AIMS/module_milestone_map.md`
— 14 blueprint modules, 6 milestone rows (M0–M5; blueprint's own prose says
"five" but the table has six — flagged as a blueprint inconsistency, not
resolved). Key finding: Module 8 and Module 10 both span M0 (contracts/stub,
skeleton) + M3 (real build); Module 11's MVP infra (metrics/evaluate/leakage-
audit/tdc-comparison) shipped *inside* M2, ahead of its nominal M5 slot.

**Model serving (Module 8) — real registry, honest partial coverage.**
`ml/serve/registry.py` (`ModelRegistry`, `promote_seed_artifact`) +
`predictor.py` implement the routing table: per-endpoint promoted XGBoost
artifacts (`ml/artifacts/<endpoint>/seed_<n>/` + AD index + Platt calibrator)
served for real; every uncovered endpoint falls back to the M0 stub
per-endpoint (not per-response) via `EndpointPrediction.model_id` (new,
additive contract field). One artifact promoted as a locally-trained
demonstration (`hia_absorption` seed 0, real training run via the existing
`ml/train/run_xgboost_baseline.py`) — this is explicitly the "locally
trained artifact" verification tier, not the production 70-run sweep, which
has not been executed. Verified against the **built Docker container**
hitting a live `/predict`, not just unit tests.

**Session/DB architecture decisions:**
- **`get_redis()` is deliberately NOT a cached singleton.** redis-py's async
  connection pool binds to whichever event loop is active when a connection
  first opens; a cached client survives across `TestClient` instances (each
  with its own loop) and raises "Event loop is closed" on the next command.
  Matches the blueprint's own Upstash/serverless-Redis assumption (frequent
  reconnects already expected) rather than fighting it.
- **SQLAlchemy async engine uses `NullPool`**, same root cause/fix as above —
  no connection is held across requests. Matches Cloud Run's `min-instances=0`
  short-lived-instance target; a long-lived pool has little to reuse there
  anyway.
- **Rate limiting and prediction caching fail OPEN, not closed, when Redis is
  unreachable.** A down cache/limiter must not take `/predict` itself down;
  local dev/tests without `docker compose up -d redis` correctly degrade
  rather than erroring.
- **Password hashing uses the `bcrypt` library directly, not passlib** —
  passlib 1.7.4 is broken against bcrypt>=4.1 (see mistakes.md).

**Batch/async architecture (Module 8).** `LocalTaskQueue` (in-process
`asyncio.create_task`) implements the exact job lifecycle (`batch_jobs` row +
Redis progress + Redis-stored results, 24h TTL) that Cloud Tasks will
eventually drive; `CloudTasksQueue` exists as an explicit `NotImplementedError`
placeholder rather than a fake success path — real GCP wiring needs
`GCP_SA_KEY_JSON` + a deployed Cloud Run worker endpoint, neither of which
exist. No Celery/RQ introduced, per the blueprint's locked architecture.

**Auth & persistence (Module 13).** Full schema (`users`, `saved_molecules`,
`saved_reports`, `batch_jobs`) via one Alembic migration (`d5be9f4ca6e0`);
snapshot-on-save implemented as "client re-POSTs the result it already has"
rather than a server-side re-fetch-from-R2-at-save-time — this sidesteps the
blueprint's "save-vs-purge race condition" by construction (no re-fetch step
to race against the purge) instead of by the countdown-UI mitigation the
blueprint describes; documented in `api/app/routers/reports.py`.

**Deployment (Module 10).** `api/Dockerfile` now installs
`ml/requirements-serving.txt` (rdkit, xgboost, numpy, **scikit-learn — a real
inference-time dependency of `XGBClassifier()`/`XGBRegressor()`'s own
`__init__`, not just training**, discovered by testing the built image, not
just grepping imports) and copies `ml/serve|featurize|models|eval`. Real
Cloud Run/Neon/Upstash/R2 deployment has **not** happened — explicit
maintainer approval required first, per the M3 execution rules.

**Four real environment bugs hit and fixed this session** (full detail in
`mistakes.md`): passlib+bcrypt incompatibility; two native Windows Postgres
services colliding with docker-compose's default host ports (remapped to
55432); Docker Hub gating anonymous `minio/minio` pulls (repointed to
`quay.io/minio/minio`); `XGBClassifier()` needing scikit-learn even for
pure inference.

---

## 2026-08-30 — PPB Option C locked; Run 3 split into 3a + 3b

**PPB Option C (maintainer decision).**
- **Primary MARS PPB endpoint** = human only. Source dataset = TDC `PPBR_AZ`;
  loader = `tdc.single_pred.ADME(name='PPBR_AZ')` (filters to `Species == "Homo
  sapiens"`); N = 1,614 compounds. Split = independent deterministic Murcko
  scaffold split (same policy shape as `hERG_Karim`), NOT the TDC benchmark
  split (which pools 5 species and does not partition the human subset).
  Reported as **not directly leaderboard-comparable** — same trade-off shape as
  hERG. Full derivation recipe + hashes live in `dataset_registry.py` and in
  each run's `provenance.json`.
- **Secondary all-species pooled dataset** = retained as a comparability
  ablation only. Provenance-tracked (registry declares
  `ppb_binding__all_species`, raw files on disk from Run 1); NOT on the M2
  critical path; only executed once M2's training architecture and compute cost
  are confirmed (specifically: whether re-training the multi-task cluster for
  each seed is required, or just PPB-specific runs).
- **Blueprint edits applied:** Module 1 §4 (PPB exception paragraph parallel to
  hERG); Module 2 row (`1,614 (human) / 1,797 compounds pooled`).
- **Code:** [ml/data/dataset_registry.py](ml/data/dataset_registry.py) declares
  both variants; [ml/data/prepare.py](ml/data/prepare.py) sources split method
  from the registry (not the stale lockfile). PPB primary processed 2026-08-30
  at `prep_id=20260830T200000Z`: 1,614 → 1,614 (0% conflict) → tv 1,291 / test
  323 / cal 129, method=scaffold, seed=0. Test set is fixed forever.

**Run 3 split — 3a + 3b (maintainer instruction 2026-08-30). Both done.**
- **Run 3a** — molecular graph representation (chirality-aware) + Morgan/ECFP
  fingerprints + PPB Option C landing.
- **Run 3b** — RDKit 2D descriptors (`ml/featurize/descriptors.py`, 217 frozen +
  `DESCRIPTOR_SET_SHA` drift guard, non-finite surfaced via `finite_mask` not
  imputed — imputation is a Module 4 call), batched façade
  (`ml/featurize/pipeline.py` `featurize_batch` — standardizes ONCE, one
  provenance bundle), ETKDGv3 + MMFF94/UFF 3D conformers
  (`ml/featurize/conformers.py`, deterministic seed, lowest-of-10,
  `to_contract_dict` → `ConformerResponse`, typed failure not fabrication).
  All stage configs expose `cache_key()` so Run 4's cache is a thin wrap.

---

## 2026-08-30 — No paid compute anywhere (maintainer directive)

**Decision.** "Nothing in this project utilizes anything paid even as a
fallback." The GPU compute path is now $0: lab A100s primary, **free-tier cloud
notebooks (Kaggle 30 GPU-hr/wk P100/T4; Colab free T4) as the fallback** —
the prior RunPod RTX 4090 paid fallback is removed. Whole training + full-ablation
budget: ~185 GPU-hr / **$0**.

**Blueprint edits applied** (`mars-blueprint_v4.md`): Module 10 hosting-stack
training-compute row; new "No-paid-compute constraint" box; GPU-strategy section
(renamed from "Hybrid strategy … + RunPod"); all three cost-ceiling lines → "$0";
Module 11 §compute-budget line; Module 14 M2 note.

**Consequence flagged:** 16 GB free-tier VRAM < KERMT's recommended 32 GB →
grad-checkpointing + small batch + gradient accumulation on the free tier;
multi-task cluster runs that still OOM wait for a lab A100 session, not a paid
card. This is the residual M2 schedule risk.

**Serving hosting → Google Cloud Run (maintainer decision, follow-up 2026-08-30).**
Scope: **backend + async worker only** move to Cloud Run; everything else stays
on its current free tier (Neon Postgres, Upstash Redis, Vercel frontend,
Cloudflare R2 storage, Resend email).
- Backend = Cloud Run service, `min-instances=0`, ~1–3 s cold start accepted
  (vs Render free's 30–50 s, which is why Render free was originally rejected).
- Async batch = **Cloud Tasks → a dedicated Cloud Run worker endpoint** (no
  Celery broker, no always-on worker). SSE progress served from the backend
  reading job state in Redis.
- $0 at demo scale (Cloud Run + Cloud Tasks always-free tiers); pay-per-use only
  under sustained real traffic, no always-on instance charge.
- Blueprint edits: Module 10 Direction + hosting table (backend row, new worker
  row) + serving-cost line + Domain/SSL + Supporting-infra CI/CD line; Module 8
  batch-handling + Module 12 batch-upload row; Module 13 session-strategy
  rationale (persistent-Render → Upstash-GET-is-cold-safe) + `batch_jobs` note;
  Module 14 M3 milestone row. `.env.example` — `RENDER_API_KEY` → `GCP_*` /
  `CLOUD_RUN_*` / `CLOUD_TASKS_QUEUE` / `GCP_SA_KEY_JSON`.
- `api/requirements.txt` had no celery/rq deps → nothing to change there.

**hERG endpoint kept as `hERG_Karim` (maintainer confirmed).** Rationale in
Run-2 EDA + KERMT decision.

---

## 2026-08-30 — M1 Run 2 completed; blueprint edits applied

**Blueprint edits** (per maintainer approval 2026-08-30):
- **Module 1 §4** — added an hERG exception paragraph. Direct TDC leaderboard
  comparability is claimed only for endpoints with an official benchmark split;
  hERG uses an independent Murcko scaffold split and is not directly comparable.
  Merged multi-source hERG superset noted as citable future work (UnihERG_DB,
  Zhang/Chen series, Feb 2025 preprint — see `FUTURE_SCOPE.md`).
- **Module 1 §6** — DILIst augmentation source clarified. FDA LTKB DILIst is
  the label source of truth (public-domain, 17 U.S.C. § 105); structures come
  from the DILIPredictor DILI gold standard (MIT-licensed, 1,111 rows). No
  name→SMILES resolution step to build ourselves.
- **Module 2** — DILI N updated from `~1,303 (augmented)` to
  `1,111 (augmented, post SMILES resolution)`.

**DILIst source decision.** DILIPredictor gold standard (Seal et al., bioRxiv 2024).
Verified as of 2026-08-30: repo `github.com/srijitseal/DILI` MIT-licensed;
`data/DILI_Goldstandard_1111.csv` sha256 `a86fd3a71c…`; 716+/395- balance;
downstream provenance recorded in `ml/data/augmentation/dilipredictor_v1/PROVENANCE.md`.

**PPBR_AZ investigation, no authoritative decision yet.** PPBR_AZ is
multi-species (5) in the raw TDC file. `tdc.single_pred` filters to human only
(1,614); `tdc.benchmark_group` pools all species (2,790 measurements over 1,797
unique compounds, species column dropped). Investigation and options recorded
in `status/ppbr_az_investigation.md`; PPB split is deferred until Option A / B / C
is chosen. Nothing else in M1 is blocked.

**Dedup / split / calibration + DILIst augmentation are all landed** —
processed outputs at `ml/data/processed/20260830T192126Z/`; 124 ml tests + 12 M0
tests all pass; the non-negotiable "DILIst rows can never reach the fixed TDC
DILI test set" rule fired on 57 compounds (all removed from the augmentation
stream). Full evidence in `status/mars-status_M1.md`.

---

## 2026-08-30 — M1 execution split into 4 runs

**Decision.** M1 is delivered in four reviewed passes, each with its own report:
1. env/dependency audit, storage & provenance architecture, TDC acquisition + lockfile;
2. standardization, EDA, dedup/conflict resolution, fixed scaffold split + leakage
   tests, calibration split, DILIst augmentation;
3. graph representation, Morgan FP, RDKit descriptors, batch pipeline, 3D conformers;
4. caching, comprehensive deterministic tests, status finalization.
Blueprint v4 stays source of truth; major decisions surfaced to the maintainer
before proceeding. **Run 1 complete 2026-08-30** — see
`status/mars-status_M1.md`.

---

## 2026-08-30 — M1 environment: two isolated venvs

**Decision.**
- **Acquisition env** — isolated (WSL Ubuntu 24.04), `PyTDC==1.1.15` installed
  `--no-deps` + a pinned minimal runtime (numpy<2, pandas, scikit-learn,
  tqdm, fuzzywuzzy, requests, packaging, setuptools<81, huggingface_hub, openpyxl).
  Frozen in `ml/data/requirements-acquire.lock.txt`. Runs `ml/data/acquire.py`
  only; produces raw snapshots + the lockfile. Reproduce: `ml/data/acquisition/README.md`.
- **M1 working env** — dedicated `ml/.venv` (Python 3.11.9): numpy 2.4.6,
  pandas 2.3.3, scikit-learn 1.9.0, **rdkit 2026.3.5**, joblib 1.5.3, pytest,
  `-e ../contracts`. No torch (M1 is CPU-only). Pins: `ml/requirements-m1.txt`
  (+ `.lock.txt`). `ml/requirements.txt` kept as the loose milestone-tagged superset.

**Rationale.** Modern PyTDC force-pins `numpy<2` and `rdkit<2024.3.1` and needs
`tiledbsoma`, which has **no Windows wheel**. Co-installing it would drag the whole
M1/M2 stack back to NumPy 1.x / RDKit 2023.09 and pull a large multi-omics stack
the ADMET code path never imports. Isolating it keeps `ml/.venv` current. The
omitted PyTDC deps are only used by TDC's multi-omics / model-server modules.

**Open follow-up.** If the M2 KERMT/BioNeMo stack itself pins `numpy<2`, `ml/.venv`
gets rebuilt on numpy 1.x at M2 start. Cost is low (pure re-install).

---

## 2026-08-30 — hERG: acquire both datasets, decide after EDA

**Decision.** `hERG_Karim` (13,445; blueprint Module 2 primary) **and** the TDC
ADMET Benchmark Group `hERG` (655) are both acquired in M1. The
`herg_cardiotoxicity` endpoint→dataset choice is deferred to Run 2 EDA (dataset
sizes, overlap, scaffold diversity in hand).

**Rationale / finding.** `hERG_Karim` is absent from the ADMET Benchmark Group —
no official fixed split, and the published TDC hERG leaderboard is on the small
`hERG` (Wang). Blueprint Module 1 §4's "the specific split required to make our
results directly comparable to published TDC leaderboard numbers" over-claims for
hERG. **Wording fix proposed in `status/mars-status_M1.md` §4 — not applied,
awaiting maintainer.** Not routing around `hERG_Karim`: 2025–2026 frontier work
(UnihERG_DB; Zhang/Chen series) *pools* `hERG_Karim` with ChEMBL/PubChem/BindingDB
rather than replacing it — Karim stays the credible backbone. A MARS-built merged
`ChEMBL+PubChem+hERG_Karim` superset (cf. the Feb 2025 preprint) is logged as
citable future work in `documentation/FUTURE_SCOPE.md`.

---

## 2026-08-30 — M0 declared complete; proceed to M1

**Decision.** All M0 deliverables done or resolved (see
`status/mars-status_M0.md` matrix rows M0-1…M0-11). Remaining flagged items
(TDC lockfile B-6, KERMT pre-flight CF-8/B-7, provenance lazy-import CF-5) are
M1/M2 scope, not M0 blockers. Next milestone: **M1 — Data & Featurization**.

**What shipped in M0:** contracts package + `API_ROUTES.md` + batch/compare
models; FastAPI `/health` + `/predict` (stub); ML tracking scaffold; fixed
`docker-compose`; CI (`ruff` + `pytest` + image build + `/predict` smoke); 12
tests; `ruff.toml`; auth scaffold aligned to Redis sessions; repo hygiene.

---

## 2026-08-30 — GNN backbone: KERMT (`nvidia/NV-KERMT-70M-v2`)

**Decision.** Shared pretrained graph encoder for all Module 4 clusters =
**KERMT**, checkpoint `nvidia/NV-KERMT-70M-v2` (NVIDIA BioNeMo release, NVIDIA
Open Model License). Not vanilla GROVER, not a "manuscript-in-prep" contrastive
variant.

**Rationale.**
- Blueprint Module 4 already names "GROVER/KERMT-style checkpoint, publicly
  available" and its evidence base explicitly cites the KERMT study
  (Adrian et al., Merck/NVIDIA, Oct 2025) — this is the in-spec choice, not a
  deviation.
- KERMT is a purpose-built GROVER successor whose headline result *is*
  multi-task ADMET finetuning of a pretrained graph encoder — exactly MARS's
  cluster design. Reported to beat Chemprop and KPGT, strongest for tasks
  >10K samples (MARS's Metabolism + Toxicity clusters: CYP3A4/2D6/2C9, hERG,
  AMES all 7K–13K).
- Public, pinnable checkpoint → hashable into the Module 1-style lockfile.
- NVIDIA Open Model License: commercial use OK, derivatives OK, no attribution
  requirement, no NC/ND — clears Module 1 §7 (unlike the dropped PharmaBench).
- GROVER lineage means the atom/bond feature schema doesn't fully reset if we
  fall back to GROVER (MIT) mid-M2.

**Pre-vetted fallbacks** (if KERMT tooling causes real M2 integration friction):
GROVER (MIT, battle-tested, shared featurization lineage) → KPGT (Nat Commun,
63-dataset validation) as the more-mature alternative.

**Open follow-ups — resolve before/at M2 start, not now:**
1. **Exact checkpoint identity.** Confirm from the HF model card whether
   `NV-KERMT-70M-v2` is the base masked-pretrain checkpoint or the
   contrastive-hybrid one; we want the variant with a published comparison
   behind it. Pin the resolved file + vocab/featurizer files by hash.
2. **CPU inference for serving — potential blueprint conflict.** Module 10 plans
   CPU-only serving on Render ("inference doesn't need GPU at our model scale").
   Must verify KERMT + its featurizer (cuik-molmaker / BioNeMo stack) can run a
   forward pass on CPU at acceptable latency. If it can't, either Module 10's
   serving tier changes (GPU serving) or we distill/export (ONNX) — flag to
   maintainer before committing the serving design.
3. **Free-tier fallback VRAM.** KERMT docs recommend ≥32 GB VRAM for
   pretraining/finetuning. Lab A100 (40/80 GB) clears it; the free-tier
   fallback (Kaggle P100/T4, Colab T4 — all **16 GB**, no paid card anywhere
   per the 2026-08-30 no-paid-compute directive) does not. Run a smoke finetune
   on a free-tier card early with gradient checkpointing + small batch +
   gradient accumulation; if the multi-task cluster runs still OOM, those runs
   wait for a lab A100 session (they are not moved to a paid card). Single-task
   fine-tunes on small/medium endpoints are expected to fit the free tier.
4. Add the KERMT featurizer to `ml/requirements.txt` once its package name +
   version are known; it defines Module 3 Stage 2's graph schema.

**Blueprint impact:** none required to the spec text. Follow-up #2 may force a
Module 10 serving-tier revision — that would come back here + to the maintainer
as its own decision.

---

## 2026-08-30 — Auth: server-side Redis sessions, not JWT

**Decision.** Confirmed Module 13's locked choice. Opaque
`secrets.token_urlsafe` tokens, `session:{token} -> user_id` in Redis, sliding
7-day TTL, HttpOnly cookie. Logout / suspension deletes the key (instant
revocation). Password-reset tokens: `itsdangerous`-signed, time-limited, emailed
via Resend.

**Rationale.** Redis already deployed; persistent (non-serverless) backend makes
per-request lookup cheap; instant revocation of abuse-prone accounts matters
more here than JWT's statelessness (Module 8 gates batch upload behind accounts).

**Changes made.** `.env.example` — `JWT_*` → `SESSION_*` / `PASSWORD_HASH_SCHEME`
/ `RESEND_API_KEY`. `api/requirements.txt` — dropped `python-jose[cryptography]`,
added `itsdangerous`. `contracts/API_ROUTES.md` — auth-stub note updated.

---

## 2026-08-30 — `documentation/` reorganized; AIMS added

**Decision.** Restructured `documentation/`:
- `mars-blueprint_v4.md` stays at the top level (it's attached by path into
  every chat — do not move it).
- `archive/` — superseded blueprint drafts v1 / v1.2 / v2 / v3.
- `status/mars-status_M0.md` — the M0 audit doc (README references updated).
- `AIMS/` — AI Memory System: `README.md`, `context.md`, `decisions.md` (this
  file), `next_steps.md`, `mistakes.md`, `glossary.md`. Paste-in bootstrap for a
  fresh chat.

---

## 2026-08-30 — Blueprint stays out of version control

**Decision.** `documentation/` remains git-ignored (blueprint, status docs, and
now AIMS). Originally the compensating control was a tracked `DECISIONS.md` at
the repo root; the user then moved that into `documentation/AIMS/`, so decision
provenance is currently outside git. Accepted for now; recovery options listed in
this file's header. The versioned blueprint filenames (`_v1…_v4`) plus `archive/`
give a coarse revision trail.

---

## 2026-08-30 — Training compute: lab A100s primary; NO paid compute anywhere

**Decision (updated 2026-08-30 by maintainer directive).** The college lab
permits personal-research (non-coursework) GPU use — lab A100s are the primary
M2 training resource. **Nothing in the project uses paid compute, even as a
fallback.** The prior "RunPod RTX 4090 paid fallback" is removed. New fallback
= free-tier cloud notebooks (Kaggle Notebooks: P100 16 GB / 2×T4, 30 GPU-hr/wk
quota; Colab free: T4-class, session-limited). Whole training + full-ablation
budget is ~185 GPU-hr at **$0**.

**Consequences.** (a) 16 GB free-tier VRAM < KERMT's recommended 32 GB →
memory-optimised finetuning (grad-checkpointing, small batch, gradient
accumulation) on the free tier; (b) multi-task cluster runs that need a single
uninterrupted multi-hour block wait for a lab A100 session rather than moving to
a paid card — this is the residual M2 schedule risk; (c) free-tier sessions are
pre-emptible, so the checkpoint + RNG-state restore discipline is doubly
load-bearing.

**Blueprint edits applied 2026-08-30:** Module 10 hosting-stack row, "no-paid-
compute constraint" box, GPU-strategy section, all three cost-ceiling lines
(now "$0"), Module 11 §compute-budget line, Module 14 M2 note.

**Still paid in the blueprint (NOT changed — M3 scope, flagged to maintainer):**
the serving hosting stack still names Render Starter (~$7/mo) + "~$15-20/mo"
for the always-on demo. That is a deliberate M3 cold-start-avoidance choice, not
a compute fallback; left as-is pending a separate maintainer call.

**Correction, 2026-09-16 (M3 mapping audit):** this note is stale. The current
`mars-blueprint_v4.md` Module 10 already fully describes Cloud Run (backend +
worker, `min-instances=0`) with no Render mention anywhere in that module —
see the "Serving hosting → Google Cloud Run" follow-up decision immediately
below this entry, which *did* apply the edit. Nothing outstanding here; do not
treat Render as a live M3 blocker.

---

## 2026-08-30 — W&B project

**Decision.** Experiment tracking project created: project `mars-admet`, entity
`shashquatch`. Auth via `wandb login` (`_netrc`), so `WANDB_API_KEY` stays empty
in `.env`. `WandbLogger` smoke-tested green.
