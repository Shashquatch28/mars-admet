# KERMT GPU session — 2026-09-30 (breadth-first Pass 1: seed 0 of the four remaining Tier-0 arms)

_Written 2026-09-30 on the workstation `CL502-18`. Drafted during the session in gitignored `ml/runs/lab_logs/` so the
tree stayed clean for every run; moved here after the last run. Per-run result records:
`kermt_tier0_results/<arm>/seed0/`. Full run directories stay on `CL502-18` (`ml/runs/`, gitignored)._

Strategy: **breadth-first** (`decisions.md` 2026-09-28) — Pass 1 = seed 0 of every Tier-0 arm, Pass 2 = seeds 1–4.
**Every number here is a provisional single-seed result**: no ± std, no KERMT-vs-XGBoost ranking, no seed-to-seed
conclusions.

```text
Pass 1 COMPLETE      (4/4 seed-0 runs this session valid; DILI 0–4 and toxicity 0–1 from earlier sessions)
Seeds 1–4 NOT RUN    (no seed-1+ run launched this session)
Pass 2 BLOCKED       pending maintainer review of §4.4 decisions
```

> **Status update (2026-09-30, after the session):** the §4.4 decisions are now resolved in `AIMS/decisions.md` (2026-09-30) —
> see the addendum in §7. This note's body is the session record as written and is otherwise unchanged.

All four trained models are preserved in W&B as `model` artifacts and verified by full download (§5).

## 1. Session / identities

| Item | Value |
|---|---|
| Date | 2026-09-30 (runs 06:26 → 09:02 UTC) |
| Workstation | `CL502-18`, NVIDIA RTX A4000 16376 MiB, driver 580.173.02, compute cap 8.6 |
| Branch / SHA | `milestone/m2-kermt` @ `ae5d28d9bd71959708ab2bef310407fad83e324a` (fast-forward `6df4bab` → `ae5d28d`; tree clean before every launch; all 4 runs recorded `git.dirty = false`) |
| `EXPECTED_SHA` | `~/mars-work/lab_env.sh` updated from stale `7475342` → `ae5d28d` (backup `lab_env.sh.bak_20260930`; file is outside the repo) |
| Python / venv | `ml/.venv`, Python 3.11.15; numpy 2.4.6, pandas 2.3.3, sklearn 1.9.1, rdkit 2026.03.6, wandb 0.29.0 |
| Docker | 29.1.3, nvidia runtime, nvidia-ctk 1.20.0; `kermt:latest` = `sha256:2918726c6bd041339ee00534f7b7b9c547466282dc73df71ca365887f3d5d87d` (created 2026-09-18; unchanged since the first real run) |
| KERMT source | `e402473376ace30fa0092dad0578a88bf7f67287`, tag `v2.0.0`, clean |
| Pretrained checkpoint | `kermt_contrastive_v2.0.pt` sha256 `e9e6649bc96503fbdb3023e312764ecbbbafd686d9a62865a1fec9466cea6be3` = lockfile; all 5 lockfile files PASS; re-asserted by `s_run.py` at every launch |
| Prep ID | `20260918T090433Z`. `compare_prep` vs canonical `20260830T200000Z`: 15 × `A_BYTE_IDENTICAL`, 1 × `D` (`dili_liver_injury__augmented` missing on the workstation — known, not used) → overall `D_UNABLE_TO_VERIFY` **for that reason only**; every dataset used this session is `A`; `pipeline_version_mismatch {}` |
| Training config | harness defaults for every run (`KermtConfig()` all-`None`; applied values from `cmd_replay`): 30 epochs, batch 32, lr 1e-4/1e-4 → 2e-5, dropout 0.0, bond_drop 0.1, dist_coff 0.15, `scaffold_balanced`, FFN 700×3, ensemble 1, fold 1, metric `auc` (cls) / `mae` (reg), equal loss weighting, `holdout_calibration=True`, `use_augmented_dili=False`. KERMT defaults copy: `ml/runs/lab_logs/kermt_defaults_finetune_20260930.json` |
| W&B | user `shashquatch28`, entity `shashquatch`, project `mars-admet`; 4/4 runs state `finished`, 0 W&B warnings; 4/4 model artifacts uploaded and download-verified (§5) |
| Git SHA of the training runs | `ae5d28d9bd71959708ab2bef310407fad83e324a` (recorded in every run's provenance). This note and the result records are committed on top of it in the session-finalization commit |

## 2. Preflight (runbook §§1–6)

- GPU idle (652 MiB desktop only, no compute apps, no containers); disk 358 GB free at start, 354 GB at end.
- Harness imports OK; CPU tests **216 passed, 3 skipped** (canonical snapshot laptop-only ×2, xgboost not installed ×1).
- Readiness `--target workstation`: `READY_FOR_GPU_SMOKE_TEST`, 0 smoke blockers (expected WARNs; `eval.xgboost_heldout` FAIL is comparison-gate, laptop-only).
- Cluster preflight identical to runbook §5e (all statuses and row counts).
- Helpers: `s_run.py`, `s_verify.py`, `s_ames.py` byte-identical to the runbook; `s_agg.py` differs only by defensive `.get()` (unused in Pass 1); `s_ckpt.py`, `s_wandb.py` were missing and were installed from runbook text.
- Smoke tests 7a/7b not re-run (§10 gate already passed 2026-09-22).
- Launch pattern for every run (runbook §10, one arm, one seed, detached, VRAM sampled every 2 s):
  `nohup env SUBGROUP=<arm> SEEDS=0 WANDB=1 NOTES="Tier-0 <arm> seed 0" $PY runs/lab_helpers/s_run.py > runs/lab_logs/tier0_<arm>_<TAG>.log`.
  Banner checked against expectations before each run was left to train.

## 3. Pass-1 comparison (all seed 0; test = held-out, never used for selection/calibration)

| # | Arm | Run ID | Task | Train / val | Wall | Peak VRAM | Saved epoch | Verify |
|---:|---|---|---|---|---|---|---|---|
| 1 | `metabolism__reg` | `kermt_st_metabolism__reg_seed0_20260930T062626Z` | reg ×1 | 694 / 99 | 7.1 min | 3869 MiB | 11 | PASS |
| 2 | `absorption_distribution__cls` | `kermt_mtsub_absorption_distribution__cls_seed0_20260930T063831Z` | cls ×3 | 2171 / 310 | 18.2 min | 4153 MiB | 18 † | PASS (1 WARN: HIA cal N=47) |
| 3 | `absorption_distribution__reg` | `kermt_mtsub_absorption_distribution__reg_seed0_20260930T065737Z` | reg ×4 | 9105 / 1301 | 56.7 min | 4053 MiB | 24 | PASS |
| 4 | `metabolism__cls` | `kermt_mtsub_metabolism__cls_seed0_20260930T080420Z` | cls ×3 | 7612 / 1088 | 57.3 min | 3953 MiB | 19 † | PASS |

† `finetune.log` prints a different epoch (29 and 28) — KERMT logging bug, see finding M1. Peak VRAM includes ≈ 620 MiB
desktop baseline. Pass-1 session GPU time ≈ 2.3 h (estimate was 2.5–3 h). ≈ 0.9 GB disk per run.

**Classification — held-out test** (AUROC/AUPRC identical raw vs calibrated, verified):

| Endpoint | Val AUROC (n) | Test n (pos rate) | AUROC | AUPRC | Brier raw → cal | ECE raw → cal | T | Cal N (pos/neg) |
|---|---|---|---|---|---|---|---|---|
| HIA | 0.946 (46) | 117 (0.77) | 0.914 | 0.968 | 0.073 → 0.074 | 0.067 → 0.074 | 0.90 ‡ | 47 (46/1) |
| Pgp | 0.972 (94) | 245 (0.51) | 0.929 | 0.939 | 0.105 → 0.109 | 0.064 → 0.087 | 2.13 | 97 (36/61) |
| BBB | 0.930 (173) | 394 (0.80) | 0.937 | 0.985 | 0.085 → 0.082 | 0.048 → 0.063 | 1.43 | 157 (120/37) |
| CYP3A4 | 0.929 (842) | 2463 (0.44) | 0.896 | 0.875 | 0.132 → 0.130 | 0.042 → 0.025 | 1.39 | 241 (67/174) |
| CYP2D6 | 0.928 (855) | 2621 (0.17) | 0.882 | 0.695 | 0.086 → 0.086 | 0.031 → 0.031 | 1.18 | 833 (110/723) |
| CYP2C9 | 0.908 (837) | 2411 (0.32) | 0.895 | 0.787 | 0.120 → 0.119 | 0.042 → 0.027 | 1.27 | 439 (88/351) |

‡ not interpretable (one negative). All temperatures: `optimizer_success` true, not at the search boundary, NLL improved on
the calibration split.

**Regression — held-out test MAE** (no calibration by design, `status: skipped_regression`):

| Endpoint | Val MAE (n) | Test MAE (n) |
|---|---|---|
| clearance_microsomal | 16.07 (99) | 25.09 (221) |
| solubility (logS) | 0.703 (761) | 0.795 (1960) |
| lipophilicity (logP) | 0.418 (433) | 0.456 (840) |
| Caco-2 | 0.413 (130) | 0.315 (180) |
| PPB (%) | 10.92 (42) | 7.76 (323) |

**Option A (`metabolism__cls`)**, applied exactly as documented, unchanged: labels lost to leakage-safe assembly
CYP3A4 2871/9833 (29.2 %), CYP2D6 2805/10469 (26.8 %), CYP2C9 2762/9640 (28.7 %) — identical to preflight and banner.
Calibration holdout additionally removed 715 / 836 / 803 labels from the training pool.

## 4. Wrap-up for review

### 4.1 Run validity

- **All four Pass-1 runs are valid.** `s_verify.py` VERDICT PASS on each (records: `kermt_tier0_results/<arm>/seed0/verify.txt`);
  `run.json` `completed`; `model.pt` saved; train/val ∩ test = 0 and train/val ∩ calibration = 0 on the CSVs actually handed
  to KERMT; raw AUROC == calibrated AUROC; checkpoint sha and prep ID recorded; git commit `ae5d28d`, clean.
- No NaN/inf loss, no OOM, no traceback, no W&B warning; all 4 W&B runs `finished`. GPU idle and no containers left after the session.
- Only WARN: HIA calibration N=47 < 50 (expected; maintainer gave explicit go for #2 knowing this).
- Known provenance gap unchanged: Docker image recorded by tag only in run provenance (id above is the only record).

### 4.2 Model-performance observations (single seed — descriptive only)

- Classification test AUROC 0.88–0.94 across the six endpoints; AUPRC tracks prevalence (CYP2D6 0.695 at 17 % positives).
- Validation AUROC exceeded test AUROC for 5/6 classification endpoints (by 0.01–0.05); BBB the exception.
- `clearance_microsomal`: test MAE 25.1 vs val 16.1; val MAE bottomed at epoch 11 then drifted up (overfitting after ~11 on 694
  training molecules; epoch selection handled it). Heavy-tailed target, 99 val molecules — do not read further from one seed.
- `absorption_distribution__reg`: test MAE below val for Caco-2 and PPB, above for logS/logP; small val folds for Caco-2 (130) and PPB (42).
- Convergence: training loss fell monotonically-ish in all runs; classification val AUC plateaued by ~epoch 10–19; nothing diverged.
- Runtime scales ≈ linearly with training rows (≈ 0.37–0.50 s per training row incl. overhead: #3 0.37, #4 0.45, #2 0.50).

### 4.3 Methodological issues discovered

- **M1 — KERMT log misreports the best epoch (logging only; saved model is correct).** In KERMT `task/train.py`, `best_epoch`
  is assigned both by the metric-based checkpoint rule (l. 393) and by the val-loss tracker (l. 363, which runs even with
  `select_by_loss=False`). `model.pt` is saved by the metric rule, but the final "best validation … on epoch N" line reports
  whichever updated last. Confirmed on 3 runs: #2 logged 29 / saved 18, #4 logged 28 / saved 19, toxicity seed 1 (2026-09-24)
  logged 26 / saved 21 — in each case the logged best *score* equals the saved epoch's `auc_val`, and matches MARS's own val
  metrics. **Consequence:** the runbook §8 instruction to read "best epoch" from `finetune.log` gives wrong answers; earlier
  session notes that quote a KERMT-logged best epoch should be re-checked. Upstream code; not changed.
- **M2 — Multi-task regression epoch selection is dominated by PPB.** Selection metric = unweighted mean of per-task MAE in
  raw units: (0.703 + 0.418 + 0.413 + 10.92)/4 = 3.113 = logged best. PPB (% scale, MAE ≈ 10) outweighs the log-scale endpoints
  (MAE ≈ 0.4–0.8) by ~15–25×, and PPB has only 42 val molecules — so the saved epoch for all four endpoints is chosen by a
  noisy PPB estimate. **Not fixed, by maintainer instruction** (2026-09-30).
- **M3 — Tiny per-endpoint validation folds** undermine selection in multi-task arms: PPB 42, HIA 46, hERG 18–19 (toxicity).
  Same class as M2.
- **M4 — Calibration split is not label-representative, in inconsistent directions.** Calibration vs test positive rate:
  DILI 0.26 vs 0.52, Pgp 0.37 vs 0.51, CYP3A4 0.28 vs 0.44, CYP2C9 0.20 vs 0.32, CYP2D6 0.13 vs 0.17 (lower); hERG 0.59 vs
  0.54, AMES 0.68 vs 0.60, HIA 0.98 vs 0.77 (higher); BBB 0.76 vs 0.80 (close). Effect on test calibration was mixed:
  temperature scaling **worsened** test ECE for Pgp, BBB, HIA (and Brier for Pgp, HIA), **improved** it for CYP3A4 and CYP2C9,
  neutral for CYP2D6. NLL improved on the calibration split in every case, so the fit itself is sound; the split is the issue.
- **M5 — Regression arms hold out calibration labels they never use.** `holdout_calibration=True` removes 88
  (clearance, 10 % of pool) and 1296 (A/D reg: logS 789, logP 316, Caco-2 77, PPB 114) labels from training for a
  calibration step that is skipped for regression.
- **M6 — Regression reporting is MAE-only** (no RMSE/R²/Spearman) in the harness records.
- **M7 — `aggregate_seed_metrics` returns std = 0.0 for n=1** (`ml/eval/metrics.py:221`, known from 2026-09-28) — no aggregate
  was produced this session; Pass-1 numbers above are read from each `lab_summary.json`.
- **Note N1 (informational, found during the W&B upload; no effect on results).** KERMT re-spells E/Z double-bond notation for a
  few molecules in `out/predictions.csv` (e.g. `C(=C\c1ccccc1)/c1ccccc1` → `C(=C/c1ccccc1)\c1ccccc1`): 13 rows across the four
  runs (A/D-cls test 1, A/D-reg test 4, metabolism-cls test 8). RDKit isomeric canonical SMILES are identical for all 13, and
  row order equals input order in every prediction file checked (10/10). The harness aligns predictions **by row order**
  (`featurize/kermt_adapter.py::read_predictions_csv`), so test metrics are unaffected. Anything that joins KERMT predictions
  back **by SMILES string** would silently drop these rows.

### 4.4 Decisions needed before Pass 2 (seeds 1–4)

Launching Pass 2 needs no code change; these are about whether seeds 1–4 should be run **under the current rules** (fixing any
of them afterwards would invalidate seeds already run, because all 5 seeds of an arm must share one protocol):

1. **M2 / M3 — multi-task epoch-selection metric.** Keep KERMT's raw-unit mean (current), or change selection for
   `absorption_distribution__reg` (and possibly other multi-task arms) to a scale-normalised or per-task rule
   (e.g. `task_wise_checkpoint`, `select_by_loss`, or metric normalisation). Changing it later means re-running seed 0 of that arm.
2. **M5 — `holdout_calibration` for regression arms.** Sign off keeping the unused holdout, or disable it for regression
   (would change training pools → re-run seeds 0 of `metabolism__reg` and `absorption_distribution__reg`). This is part of the
   already-OPEN `holdout_calibration=True` sign-off.
3. **M4 — calibration split representativeness.** Decide whether temperature scaling on the current split is acceptable for
   the final tables, or whether the split construction needs revisiting (affects calibrated metrics only; AUROC/AUPRC and
   regression MAE unaffected).
4. **M6 — regression metrics.** Decide which metrics are required (blueprint) and add them before aggregating — can be
   computed post hoc from saved predictions, so this does not block Pass 2.
5. **M7 — fix single-seed std** before any partial-seed table is produced (not blocking Pass 2 itself).
6. **M1 — runbook correction** (read the saved epoch from the "Saving model at epoch" lines / best score, not the final line).
   Documentation only.
7. **Still OPEN from before:** HIA calibration floor (N=47, 1 negative); Option A for `metabolism__cls` (applied unchanged here);
   DILI base vs augmented pool; `toxicity__cls` seeds 2–4 (≈ 4.75 h) scheduled last in Pass 2.

Pass 2 order if approved (`decisions.md` 2026-09-28), measured cost per seed: `metabolism__reg` ≈ 7 min →
`absorption_distribution__cls` ≈ 18 min → `metabolism__cls` ≈ 57 min → `absorption_distribution__reg` ≈ 57 min →
`toxicity__cls` seeds 2–4 ≈ 95 min each. Seeds 1–4 for the four Pass-1 arms ≈ 9.3 h (4 × 139 min); plus toxicity ≈ 4.8 h.

## 5. Artifacts

| Where | What |
|---|---|
| Git (commit on top of `ae5d28d`) | this note; `kermt_tier0_results/{metabolism__reg,absorption_distribution__cls,absorption_distribution__reg,metabolism__cls}/seed0/` — `lab_summary.json` (val + held-out test + calibration metrics), `config.json`, `run.json`, `provenance.json`, per-endpoint `calibration_diagnostics` / `temperature_scaler` JSON (regression arms have no scaler — none is produced), `verify.txt`, `artifact_metadata.json` (= the `metadata.json` inside the W&B model artifact), `wandb_artifact.json` (references, digests, hashes, record-artifact file list); `kermt_tier0_results/README.md` artifact table extended |
| W&B `shashquatch/mars-admet` | per run: the original training run (config, validation + scalar calibration metrics; **not** test metrics), a **`model` artifact** and a **`run-record` artifact** (below) |
| `CL502-18` only (gitignored) | full run dirs `ml/runs/<run_id>/` (≈ 0.9 GB each incl. `last_checkpoint.pt` and KERMT `.npz` features); session logs, VRAM traces, verify/upload outputs, fingerprint/readiness/preflight reports in `ml/runs/lab_logs/` (`*_20260930*`); upload helpers `ml/runs/lab_helpers/s_upload.py`, `s_wandb_verify.py` |

**W&B entity.** The project lives under the team entity **`shashquatch`** (all 11 model artifacts and all runs); the login is
user `shashquatch28`, and `shashquatch28/mars-admet` does not exist. Artifacts were attached to the real runs under `shashquatch`.

**W&B model artifacts** — convention recovered from `kermt-toxicity-seed1:v0` (2026-09-24) and reproduced exactly: type `model`,
files `model.pt` + `metadata.json` only, aliases `final`, `latest`, logged by resuming the original training run
(`resume="must"`, which sets that run's `job_type` to `model-upload`, as on 2026-09-24). Every run is still `finished`, with the
same number of summary keys as before the upload (12 / 85 / 36 / 85). Each collection has exactly one version (`v0`), and the
seven 2026-09-24 artifacts are unchanged.

| Arm (seed 0) | W&B run (name = id) | Model artifact | `model.pt` bytes | `model.pt` SHA-256 (local = W&B download = metadata) | Artifact digest |
|---|---|---|---:|---|---|
| `metabolism__reg` | `kermt_st_metabolism__reg_seed0_20260930T062626Z` | `shashquatch/mars-admet/kermt-metabolism-reg-seed0:v0` | 203,152,142 | `8ca10190c44f550c3690f9e6f281a43b22583774d6e23b0307bb436c5781dc2a` | `ce579dbeb31c231ac7ca571c550aa855` |
| `absorption_distribution__cls` | `kermt_mtsub_absorption_distribution__cls_seed0_20260930T063831Z` | `shashquatch/mars-admet/kermt-absorption-distribution-cls-seed0:v0` | 203,512,002 | `3b7d2be6f1e8fdd7e82a6c9f6f4c7d81024d7b2663a2f45e887517f8f007abc6` | `8742c20f16d1c9971711d313bece5e6a` |
| `absorption_distribution__reg` | `kermt_mtsub_absorption_distribution__reg_seed0_20260930T065737Z` | `shashquatch/mars-admet/kermt-absorption-distribution-reg-seed0:v0` | 203,514,686 | `10e3553eede7bd187e1bb9c3d258b39d9ec3a62868663a3c10250862cda1c04a` | `5899feb585738eb1770d1def7349fe1c` |
| `metabolism__cls` | `kermt_mtsub_metabolism__cls_seed0_20260930T080420Z` | `shashquatch/mars-admet/kermt-metabolism-cls-seed0:v0` | 203,512,002 | `35ce5318e51fddce72c3061ba6f4b7a9cbc0e2a9e1fa6652203c8b9833caca00` | `b73268596558a303a7bc28cb2365bc09` |

Verification (`s_wandb_verify.py`, per artifact, from W&B rather than local state): run `finished`; artifact `COMMITTED`;
aliases `final`+`latest`; exactly one version; files exactly `model.pt` + `metadata.json`; logged by the training run; **full
download SHA-256 == local `model.pt` SHA-256** (the temporary copy was deleted); `metadata.json` `model_sha256`/`run_id`/`seed`
correct. All PASS for 4/4. Before upload, `s_upload.py` also asserted that `model.pt` is byte-identical to KERMT's
`ckpt/fold_0/model_0/model.pt`, that `verify.txt` says PASS, and that no artifact of that name existed.

**W&B run-record artifacts (new this session, additive).** The 2026-09-24 convention has no place for predictions, training
history or logs, so each run also has a type-`run-record` artifact `kermt-<arm>-seed0-record:v0` (alias `latest`). It holds
`run.json`, `config.json`, `provenance.json`, `lab_summary.json`, `metrics.jsonl`, KERMT `artifacts/kermt/run.json` (applied
args + `cmd_replay`), `finetune.log` (per-epoch train loss / val loss / val metric), `verbose.log`/`quiet.log`, KERMT
`test_result.csv` (validation fold), `prepare_data.json`, the exact `input/train.csv` / `input/val.csv` handed to KERMT, the
calibration JSONs, `predictions/{val,calibration,test}/` (`predictions.csv`, `smiles.csv`, `run.json`, `inference.log`; each
split identified by exact match against the harness's split lists; regression has no calibration inference), `verify.txt`, the
launch/banner log and the VRAM trace. Not included: `last_checkpoint.pt`, KERMT `.npz` feature files.

| Arm | Record artifact | Files | Digest |
|---|---|---:|---|
| `metabolism__reg` | `shashquatch/mars-admet/kermt-metabolism-reg-seed0-record:v0` | 26 | `103c7173159a7fa9a5aa2e757666a0ac` |
| `absorption_distribution__cls` | `shashquatch/mars-admet/kermt-absorption-distribution-cls-seed0-record:v0` | 35 | `d2fee017b758deccfba743d883e09fd6` |
| `absorption_distribution__reg` | `shashquatch/mars-admet/kermt-absorption-distribution-reg-seed0-record:v0` | 29 | `74d48a6566b1164d02df268096d607a0` |
| `metabolism__cls` | `shashquatch/mars-admet/kermt-metabolism-cls-seed0-record:v0` | 35 | `030f0c93dccfb26edc72071132d04c29` |

Upload incident (no effect): the first attempt for `absorption_distribution__cls` stopped at the helper's split-identification
assertion **before** `wandb.init`, so nothing was sent to W&B; the cause is Note N1. The helper was changed to identify splits
from `input/smiles.csv`, and the rerun passed every pre-upload check, including "artifact name not yet used".

## 6. Tier-0 state after this session

| Arm | Seeds done | Status |
|---|---|---|
| `dili_standalone__cls` | 0–4 | complete (aggregate exists) |
| `toxicity__cls` | 0, 1 | seeds 2–4 → Pass 2 |
| `metabolism__reg` | 0 | Pass 1 ✅ — seeds 1–4 → Pass 2 |
| `absorption_distribution__cls` | 0 | Pass 1 ✅ — seeds 1–4 → Pass 2 |
| `absorption_distribution__reg` | 0 | Pass 1 ✅ — seeds 1–4 → Pass 2 |
| `metabolism__cls` | 0 | Pass 1 ✅ — seeds 1–4 → Pass 2 |

**Next action:** maintainer review of §4.4, then Pass 2 one seed at a time with `s_verify.py` PASS between launches.

## 7. Addendum — §4.4 resolved (written after the session, 2026-09-30)

Authoritative text: `documentation/AIMS/decisions.md`, entry "2026-09-30 — Tier-0 Pass-2 protocol frozen". No result record, code, dataset or checkpoint
was changed by it; all four Pass-1 runs remain valid as recorded.

| §4.4 item | Resolution (`decisions.md` 2026-09-30) |
|---|---|
| 1. M2/M3 epoch-selection metric | **D1** — stock KERMT rule kept for all Tier-0 arms; PPB-dominated selection in `absorption_distribution__reg` (and small hERG/HIA/PPB folds) is a stated limitation, not fixed |
| 2. M5 regression `holdout_calibration` | **D2** — kept (`True`) for every arm and seed; regression calibration explicitly unused (`skipped_regression`) |
| 3. M4 calibration split | **D3** — split frozen for Tier 0; raw and calibrated always reported together; prior-shift caveat required |
| 4. M6 regression metrics | deferred (post hoc from saved predictions; does not block Pass 2) |
| 5. M7 single-seed std | deferred; must be fixed before any table (does not block Pass 2) |
| 6. M1 runbook correction | done — runbook now says: report the **saved epoch** (last `Saving model at epoch N` line), never the final `best validation … on epoch N` line (**D1**). The "Saved epoch" column in §3 above is the correct one; footnote † stands |
| 7. HIA calibration floor (N=47, 1 negative) | **D4** — runs valid; HIA calibrated metrics and temperature not reportable; per-launch "explicit go" withdrawn |
| 7. Option A (`metabolism__cls`) | **D5** — confirmed for all of Tier 0 (Option A is the `metabolism__cls` leakage decision, not an HIA item); per-launch "explicit go" withdrawn |
| 7. DILI base vs augmented pool | **D6** — DILI runs kept and labelled "base pool, non-augmented"; pool-match before any KERMT-vs-XGBoost DILI comparison; no DILI run in Pass 2 |
| 7. `toxicity__cls` seeds 2–4 | last in Pass 2 (`lab_session_tasks.md` P-6) |

Pass 2 is therefore **not blocked by decisions**; it proceeds under the drift guard in `decisions.md` D7 and the Pass-2 procedure in
`AIMS/lab_session_tasks.md`.

### Corrections (added 2026-10-01, after the P1 audit)

- **Docker provenance.** Line "Known provenance gap unchanged: Docker image recorded by tag only in run provenance" (§4.1), and the same statement in
  `kermt_gpu_session_2026-09-24.md`, are inaccurate: all 11 committed `provenance.json` files hold only `environment` and `git`. The image tag and id were captured
  separately in the workstation sessions and appear only in `artifact_metadata.json`; no image digest is part of the committed provenance.
- **Saved-epoch wording.** The `Saving model at epoch N` line named in this note and in the §7 table above is not present anywhere in the repo's code; its wording is
  unverified on the laptop. What the repo does show: MARS evaluates the saved `model.pt`, and `ml/eval/tier0_artifacts.py:69` parses the *misleading* `best validation
  auc … on epoch N` line. The 3.1133 recomputation in `decisions.md` D1 uses the committed `lab_summary.json` and the logged score reported in this note — both session
  evidence.
