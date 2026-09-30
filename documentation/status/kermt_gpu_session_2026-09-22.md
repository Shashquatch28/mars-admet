# KERMT GPU session 2026-09-22 — reconstruction and next-session checklist

_Written 2026-09-24 from a read-only audit (git, W&B API, repo docs). The lab run's own files
(`runs/`, `finetune.log`, `verify_*.txt`, aggregate JSON, checkpoints, `lab_out_*.tgz`) live on the GPU
workstation `CL502-18` and were **not** available for this audit — everything below is from Git +
W&B, and items only those files can answer are marked UNKNOWN / NEEDS VERIFICATION._

## 1. What was actually trained (W&B `shashquatch/mars-admet`, all `finished`)

The working assumption "5 seeds on one endpoint, 1 seed on DILI" was **inverted**. W&B shows:

| Run (W&B name = id) | Arm | Seed | Duration (`_runtime`) | Git commit / dirty flag | Prep ID |
|---|---|---|---:|---|---|
| `kermt_st_dili_standalone__cls_seed0_20260922T052900Z` | `dili_standalone__cls` | 0 | 234 s | `7475342` / **clean** (`notes`: "first real KERMT run") | `20260918T090433Z` |
| `kermt_st_dili_standalone__cls_seed1_20260922T054638Z` | same | 1 | 237 s | `7475342` / **dirty** | same |
| `kermt_st_dili_standalone__cls_seed2_20260922T055135Z` | same | 2 | 235 s | `7475342` / dirty | same |
| `kermt_st_dili_standalone__cls_seed3_20260922T055629Z` | same | 3 | 235 s | `7475342` / dirty | same |
| `kermt_st_dili_standalone__cls_seed4_20260922T060122Z` | same | 4 | 234 s | `7475342` / dirty | same |
| `kermt_mtsub_toxicity__cls_seed0_20260922T062623Z` | `toxicity__cls` (hERG + AMES, multi-task) | 0 | **5,788 s (≈ 96 min)** | `7475342` / dirty | same |

- **DILI = a complete 5-seed Tier-0 arm (seeds 0–4), ≈ 4 min per seed.** It is *not* the ~1.5 h run.
- **The ~1.5 h run is `toxicity__cls` seed 0.** Seeds 1–4 of `toxicity__cls` have **not** been run.
- Start times (UTC): DILI 05:29–06:05; toxicity 06:26–08:02. Host `CL502-18`, RTX A4000 (16 GiB), Linux 7.0.0-30, Python 3.11.15.
- Nothing else KERMT-related ran after the 2026-09-18 benchmark runs (`kermt_gpu_bench_bs{8..128}`, 5 runs) and the smoke tests. No failed/crashed/killed runs appear in W&B (83 runs total, all `finished`).

## 2. Verified configuration (from W&B `config`)

`model_family` = `kermt_single` (DILI) / `kermt_multitask_subgroup` (toxicity) · `loss_weighting=equal` ·
`holdout_calibration=True` · `calibrate=True` · `use_augmented_dili=False` (base DILI pool) ·
`variant=""` · branch `milestone/m2-kermt`.

- **DILI split (identical across the 5 seeds):** train_val 378, calibration 50 (13 pos / 37 neg), test 96,
  seed-fold val = 41; 0 SMILES overlap, 0 labels sacrificed. Matches the runbook's expected counts.
- **toxicity split:** train_val 16,240 rows, calibration 1,626, test 4,080; AMES retained 5,788 (−14),
  hERG retained 10,493 (−16); calibration held out: AMES 576, hERG 1,056; 0 SMILES overlap; 24 benign
  shared non-acyclic scaffold buckets (documented M1 noise).
- **Hyperparameters: all `null`** (epochs, batch_size, lrs, dropout, …) ⇒ the harness passed **no
  overrides**, i.e. KERMT's own `agent/config/defaults_finetune.json` values applied. The **actual**
  numbers are NOT in W&B or Git — UNKNOWN here; they are in `runs/<run_id>/artifacts/kermt/**/finetune.log`
  and `kermt_defaults_finetune.json` on the workstation.
- **W&B provenance gaps (by construction, not a failure):** `provenance.environment` shows `torch_version`,
  `cuda_available`, `gpu_name` = null because the harness process runs in the host venv and KERMT/CUDA run
  inside the container. GPU identity does exist in W&B run metadata (`gpu_nvidia`). Docker image id, KERMT
  commit and checkpoint sha are not in the W&B config (the checkpoint/KERMT identities are pinned only in
  `ml/data/metadata/kermt_checkpoint.lock.json`) ⇒ record them per session.
- **Dirty flag:** seed-0 DILI ran on a clean tree at `7475342`; DILI seeds 1–4 and toxicity seed 0 were
  launched with a **dirty** tree at the same commit. What was dirty is UNKNOWN. Plausible (unverified)
  explanation: `eval/tier0_artifacts.py` / `tier0_present.py` / `requirements-m2.txt` were written on the
  workstation before being committed as `f51cb8f` (2026-09-22 14:43 IST). That change touches **no
  training/eval-during-training code** (diff is 3 files, all post-hoc), so the training path is byte-identical
  between `7475342` and `f51cb8f`. NEEDS VERIFICATION on the workstation (`git status`, `git stash list`).

## 3. Logged metrics — read with care

W&B `summary` contains, per endpoint: `auroc`, `auprc`, `brier_score`, `ece`, and calibration diagnostics
(`temperature`, `ece_before/after`, `nll_before/after`, `at_boundary`, `optimizer_success`, class counts).
The block is tagged **`split: val`** with `n_samples` = the seed-fold validation size (DILI 41; AMES 1,809;
hERG 19). **These are validation-fold numbers, not held-out test numbers.** The runbook already
recorded that W&B carries no test-metric dicts (`lab_session_tasks.md` App. B.8). Test metrics (raw and
calibrated) live only in the workstation's `lab_summary.json` / `kermt_tier0_<arm>_aggregate.json`.

Validation-fold values (for orientation only — do **not** compare these to the XGBoost *test* numbers):

| Arm | seed | val AUROC | val AUPRC | temperature | ECE before → after | `optimizer_success` |
|---|---:|---:|---:|---:|---|---|
| DILI | 0 | 0.9077 | 0.9063 | 2.540 | 0.170 → 0.132 | True |
| DILI | 1 | 0.8995 | 0.8927 | 2.660 | 0.184 → 0.169 | True |
| DILI | 2 | 0.8975 | 0.8997 | 2.750 | 0.196 → 0.192 | True |
| DILI | 3 | 0.8804 | 0.8897 | 2.899 | 0.188 → 0.149 | True |
| DILI | 4 | 0.9240 | 0.9406 | 2.418 | 0.199 → 0.155 | True |
| tox / AMES | 0 | 0.8532 | 0.8339 | 1.185 | 0.079 → **0.095 (worse)** | True (`nll_improved` True, `ece_improved` **False**) |
| tox / hERG | 0 | 0.9118 | 0.7000 | 1.329 | 0.069 → 0.057 | True (val n = 19 only) |

Observations (record, don't fix): DILI temperatures 2.4–2.9 (raw KERMT logits over-confident on a 50-molecule
calibration set); no `at_boundary`; hERG validation is 19 labels so its epoch selection is effectively
unmeasured (already a known OPEN item).

## 4. Discrepancies found

1. **User/handoff belief vs W&B:** the 5-seed arm is DILI, the single seed is `toxicity__cls` (see §1).
2. **Docs stale:** `next_steps.md`, `context.md` and `lab_session_tasks.md` were last updated 2026-09-21 and still say "no GPU training". Updated 2026-09-24.
3. **No GitHub-side "DILI training results".** GitHub had exactly one new commit, `f51cb8f` (post-hoc scripts).
   Run outputs are gitignored by design (`ml/runs/`); the DILI/toxicity results were never pushed and cannot
   be pulled — they must be carried from the workstation (`lab_out_*.tgz`, runbook §13 end-of-session).
4. **`f51cb8f` breaks the repo's "ruff clean" invariant:** 12 findings in `ml/eval/tier0_artifacts.py` /
   `tier0_present.py` (I001, B905 ×4, F841, B007 ×4, UP017 ×2). Not fixed here (source-code change out of
   audit scope).
5. **`matplotlib>=3.10` added to `requirements-m2.txt` but not to `requirements-m2.lock.txt`**, and it is not
   installed in the laptop `ml/.venv`. Whether the workstation venv has it is NEEDS VERIFICATION (the scripts
   evidently ran there: `tier0_dili_standalone__cls/` package is referenced by the script's text).
6. W&B config carries no `KermtConfig` values, Docker image id, KERMT commit or checkpoint sha (§2).

## 5. State after this session

| Arm | Status |
|---|---|
| `dili_standalone__cls` | trained ×5 seeds (0–4); W&B complete; post-hoc package apparently generated on workstation; test aggregate **not verified here** |
| `toxicity__cls` | **1/5 seeds trained** (seed 0); seeds 1–4 untrained; `s_agg.py` will refuse to aggregate |
| `metabolism__reg`, `absorption_distribution__reg`, `absorption_distribution__cls`, `metabolism__cls` | untrained |
| Held-out KERMT-vs-XGBoost comparison | not done — needs the workstation's aggregate JSONs (test metrics) on the laptop next to `ml/runs/test_evaluations/*.json` |
| Tier-1 (mixed-type trainer), G1–G4, Tier-2, CYP single-task baselines, KERMT sweep CLI | not started (unchanged) |

## 6. Next GPU session — checklist

> **SUPERSEDED 2026-09-28:** the plan below ("`toxicity__cls` seeds 1,2,3,4") is replaced by the breadth-first
> Pass 1 / Pass 2 plan in `AIMS/decisions.md` 2026-09-28 and `AIMS/lab_session_tasks.md` §10. Also stale: origin
> `6df4bab` records that `toxicity__cls` **seed 1 was run on 2026-09-24**. Items 1–2 and 5–10 (commit/dirty-tree, preflight,
> W&B, capture, do-not, post-run) still apply to every launch; items 3–4 (arm/seeds/runtime) do not.

Plan source: `lab_session_tasks.md` §10 table (row 2 continues; rows 3–6 follow). **Undecided:** whether to run
`toxicity__cls` seeds 1–4 only or also start row 3+ in the same session (maintainer's call — the runbook says
not to launch an arm that can't finish, and `absorption_distribution__cls` / `metabolism__cls` need an explicit go).

1. **Branch/commit:** `milestone/m2-kermt`, fast-forward the workstation to `f51cb8f`
   (`git pull --ff-only origin milestone/m2-kermt`). Training code is identical to `7475342`, the commit the
   six W&B runs cite. Set `EXPECTED_SHA` to the full SHA (`git rev-parse origin/milestone/m2-kermt`).
2. **MUST first (workstation):** `git status --short` and `git stash list` — explain the "dirty" flag on the
   runs before launching anything; a non-empty tracked diff is a runbook STOP. Save any workstation-only
   files (`ml/runs/lab_helpers/*`, `lab_out_*.tgz`) before pulling; `ml/runs/` is gitignored so the pull won't touch it.
3. **Arm / seeds:** `ARM=toxicity__cls SEEDS=1,2,3,4` (seed 0 exists — do not repeat, same rule the runbook
   used for DILI). Same config as seed 0: `holdout_calibration=True`, equal weighting, `variant=""`, no
   hyperparameter overrides, `NOTES="Tier-0 toxicity seed N"` (follow the existing note pattern).
4. **Expected runtime:** ≈ 5,800 s (≈ 1.6 h) per seed ⇒ **≈ 6.4 h for four seeds** (seed-to-seed variation
   unmeasured; only one toxicity run exists). Launch detached (`nohup`), poll. DILI-class arms cost ≈ 4 min/seed.
5. **Preflight (runbook §3–6):** `nvidia-smi`; container CUDA check; `s_ckpt.py` (sha256 `e9e6649b…6be3`);
   KERMT HEAD `e402473…` clean; `compare_prep.py` vs `prep_fingerprint.20260830T200000Z.json` with
   `PREP_ID=20260918T090433Z` (last session's fingerprint verdict is NOT recorded anywhere I can see — record
   it this time); `readiness_report.py --prep-id 20260918T090433Z`; `df -h .` — toxicity checkpoints have
   never been sized: run `du -sh runs/<toxicity seed0 run_id>` first and budget ×4.
6. **W&B:** export `WANDB_ENTITY=shashquatch WANDB_PROJECT=mars-admet` (nothing loads `.env`); `WANDB=1`;
   run name = `kermt_mtsub_toxicity__cls_seed<N>_<UTC>` (auto). No W&B `group` is set on any KERMT run today
   (all `group=None`); if grouping is wanted it needs a code change — undecided, don't improvise.
7. **Capture (small files only, no `*.pt`):** per run `config.json`, `provenance.json`, `run.json`,
   `metrics.jsonl`, `lab_summary.json`, `verify_<run_id>.txt`, `finetune.log`; per arm
   `kermt_tier0_toxicity__cls_aggregate.json`; session identities (git SHA, Docker image id, KERMT commit,
   checkpoint sha, GPU/driver, `kermt_defaults_finetune.json` copy, peak VRAM, `wall_seconds`, `du -sh`).
   Record the **actual KERMT hyperparameters** (epochs, batch size, lr…) from `finetune.log` — they are currently
   recorded nowhere durable.
8. **Metrics to confirm recorded:** per endpoint, raw **and** calibrated **test** AUROC/AUPRC/Brier/ECE,
   temperature + `at_boundary`/`optimizer_success`/`nll_improved`, class counts; per-seed and 5-seed mean ± std
   via `s_agg.py`. Note the AMES `ece_improved=False` at seed 0 and watch whether it repeats.
9. **Do NOT:** commit anything from `ml/runs/`; download datasets/checkpoints (all already on the workstation;
   the laptop has none); re-run DILI seeds or `toxicity` seed 0; overwrite an existing run directory; lower batch
   size silently on OOM; change split/calibration policy; run `kermt_gpu_benchmark.py` (hard-coded `/tmp` paths).
10. **Post-run:** `s_verify.py` PASS per run → `s_agg.py` → optionally `eval/tier0_artifacts.py --run-id …` per
    seed and `eval/tier0_present.py` per arm → runbook §13 end-of-session (`git status` empty, W&B count =
    completed runs, no run stuck "running", tar without `*.pt`) → copy the tgz to the laptop.

## 7. Open items carried forward

Unchanged from `next_steps.md` (holdout_calibration sign-off; HIA calibration floor; DILI augmented-vs-base pool
— note the 5 DILI runs used the **base 287-train pool**, so the comparison to XGBoost's 979-molecule augmented
pool is currently apples-to-oranges; calibration split not label-representative; XGBoost served calibrators; tiny
per-task validation sets) plus the new ones in §4 (ruff findings, lock file, missing hyperparameters/image-id in
run provenance, W&B logs validation-only metrics, unexplained dirty flag).
