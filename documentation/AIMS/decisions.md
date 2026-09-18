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
