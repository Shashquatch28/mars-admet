# KERMT GPU session — 2026-09-24 (`toxicity__cls` seed 1)

_Written 2026-09-24 on the workstation `CL502-18`. Portable record: everything here can be read after a
`git pull`; the large artifacts stay on the workstation (see "GPU artifact handoff")._

Scope of this session: exactly **one** training run — `toxicity__cls` seed 1. Seeds 2–4 were **not** run,
no aggregation was run, and no DILI training was run. Later the same day the final models of all 7 completed runs were uploaded to W&B (section 7).

## 1. Session

| Item | Value |
|---|---|
| Date | 2026-09-24 (run 08:09:13 → 09:43:59 UTC) |
| Workstation | `CL502-18`, NVIDIA RTX A4000 (16376 MiB), driver 580.173.02, compute cap 8.6 |
| Branch | `milestone/m2-kermt` |
| Git SHA | `f51cb8fc71071cc39c7e741c4de3e5449cdb00a7` (`f51cb8f`) |
| Tree state | clean before launch; run recorded `git.dirty = false` |
| Launcher | `ml/runs/lab_helpers/s_run.py` (runbook copy, gitignored), `SUBGROUP=toxicity__cls SEEDS=1 WANDB=1 NOTES="Tier-0 toxicity seed 1"`, detached with `nohup` |

## 2. Run

| Item | Value |
|---|---|
| Subgroup / arm | `toxicity__cls` (hERG + AMES), model family `kermt_multitask_subgroup`, equal loss weighting |
| Seed | 1 |
| Run ID | `kermt_mtsub_toxicity__cls_seed1_20260924T080913Z` |
| W&B | entity `shashquatch`, project `mars-admet`, run id = run ID above, state `finished` |
| W&B URL | https://wandb.ai/shashquatch/mars-admet/runs/kermt_mtsub_toxicity__cls_seed1_20260924T080913Z |
| Status | `completed` (`run.json`) |
| Runtime | 5705.6 s (~95 min) |
| Train / val rows | 12,787 / 1,827 |

## 3. Provenance

| Item | Value |
|---|---|
| Prep ID | `20260918T090433Z` (workstation snapshot; 15/15 comparable datasets byte-identical to canonical `20260830T200000Z`; `dili_liver_injury__augmented` absent on the workstation and not used, `use_augmented_dili=false`) |
| Pretrained checkpoint | `NV-KERMT-70M-v2/kermt_contrastive_v2.0.pt`, sha256 `e9e6649bc96503fbdb3023e312764ecbbbafd686d9a62865a1fec9466cea6be3` (equals `ml/data/metadata/kermt_checkpoint.lock.json`) |
| KERMT source | `NVIDIA-BioNeMo/KERMT` tag `v2.0.0`, commit `e402473376ace30fa0092dad0578a88bf7f67287`, unmodified checkout |
| Docker | tag `kermt:latest`, image id `sha256:2918726c6bd041339ee00534f7b7b9c547466282dc73df71ca365887f3d5d87d` (created 2026-09-18). **The run records only the tag (`image_digest: null`); this id was read from the workstation before launch and is unchanged since seed 0.** |
| Training config | harness defaults, identical to seed 0 apart from `--seed 1`: 30 epochs, batch 32, init/max lr 1e-4, final lr 2e-5, dropout 0.0, bond_drop_rate 0.1, dist_coff 0.15, `scaffold_balanced`, ensemble 1, folds 1, FFN 700×3, per-task heads (1 layer, 64 units), metric `auc`, `holdout_calibration=True`. Command replay: `ml/runs/<run>/artifacts/kermt/run.json` → `cmd_replay` (workstation only). |

## 4. Metrics (verified values)

Validation (KERMT's shared fold; hERG is tiny — see caveats):

| Endpoint | AUROC | n | positives |
|---|---|---|---|
| hERG | 0.844 | 18 | 2 |
| AMES | 0.851 | 1810 | 958 |

Held-out test (raw AUROC = calibrated AUROC, as required of temperature scaling):

| Endpoint | n | AUROC | AUPRC | Brier raw → cal | ECE raw → cal |
|---|---|---|---|---|---|
| hERG | 2627 | 0.894 | 0.904 | 0.136 → 0.133 | 0.058 → 0.043 |
| AMES | 1453 | 0.857 | 0.895 | 0.155 → 0.151 | 0.071 → 0.048 |

Calibration (temperature scaling, fit on the held-out calibration split only):

| Endpoint | Temperature | NLL before → after | Fit size (pos / neg) | At boundary |
|---|---|---|---|---|
| hERG | 1.603 | 0.511 → 0.474 | 1050 (616 / 434) | no |
| AMES | 1.378 | 0.505 → 0.491 | 576 (392 / 184) | no |

Exact unrounded values: `kermt_tier0_results/toxicity__cls/seed1/` (`lab_summary.json`,
`*_calibration_diagnostics.json`).

For context, seed 0 (same arm, run `kermt_mtsub_toxicity__cls_seed0_20260922T062623Z`, SHA `7475342`,
recorded `git.dirty=true`, 5800 s): test AUROC hERG 0.892 / AMES 0.854; val AUROC hERG 0.912 (n=19) /
AMES 0.853. This is a single-seed comparison, not an aggregate.

## 5. Verification

`s_verify.py` → **`VERDICT: PASS`**, 0 `[WARN]` lines, every check `[PASS]`:
run completed; `model.pt` saved and non-empty; val and calibration+test record per endpoint; calibration
fitted, temperature finite and > 0, optimizer success, both classes present; raw AUROC == calibrated AUROC;
checkpoint sha and prep ID recorded correctly; **train ∩ test = 0, val ∩ test = 0, train ∩ calibration = 0,
val ∩ calibration = 0, train ∩ val = 0** (checked on the CSVs actually handed to KERMT); git commit recorded.
Full text: `kermt_tier0_results/toxicity__cls/seed1/verify.txt`.

Resources: peak VRAM **4113 MiB** (seed 0: 4237 MiB); GPU back to idle (615 MiB, 7%) afterwards; no
container left running.

## 6. Caveats

- **hERG validation fold is tiny (n=18, 2 positives)**, so its validation AUROC is noise-dominated and epoch
  selection for hERG is effectively unmeasured. Known open design item (`next_steps.md`); not changed.
- **Seed 0 and seed 1 differ in recorded Git state** (`7475342` dirty vs `f51cb8f` clean). The diff between the
  two commits adds only `ml/eval/tier0_artifacts.py`, `ml/eval/tier0_present.py`, `ml/requirements-m2.txt`; no
  training-path code changed.
- **Docker image is identified by tag only in run provenance** (runbook Appendix B trap 7); the image id above
  is the only record.
- **W&B run pages do not hold test metrics** (runbook Appendix B trap 8) — verified. Test metrics are in this
  document and in `lab_summary.json` only.
- `ml/eval/tier0_artifacts.py` / `tier0_present.py` (post-hoc plots) were **not** run for this seed.
- Unrelated to the run: the runbook's `EXPECTED_SHA` in `~/mars-work/lab_env.sh` still pins `7475342` (a file
  outside the repo, left unchanged); `lab_helpers/` on the workstation has no `s_ckpt.py`/`s_wandb.py`.
  `documentation/status/kermt_gpu_session_2026-09-22.md` **does not exist in the repo**; the 2026-09-22
  session (DILI seeds 0–4, toxicity seed 0) has no narrative note, but its per-run result records and model
  artifacts are now in `kermt_tier0_results/`.

## 7. GPU artifact handoff

**GitHub = source / config / results / provenance · W&B = trained model artifacts · `CL502-18` = current working copy.**

| Where | What is there |
|---|---|
| **GitHub (`git pull`)** | Source code, configs, runbook, AIMS/status docs; this note; `kermt_tier0_results/` (small result + provenance records for all 7 completed runs, DILI aggregate, per-run `wandb_artifact.json`, and a README with the artifact table and retrieval instructions; ~320 KB). |
| **W&B** (`shashquatch/mars-admet`) — *verified 2026-09-24* | Per run: config, `finished` state, validation + calibration summary, `n_test_labeled`. **Model artifacts (new this session): 7 × `model`-type artifacts `kermt-{dili,toxicity}-seed<N>:v0`, each `model.pt` + `metadata.json`, hash-verified by full download.** Still **not** in W&B: held-out test metrics, `last_checkpoint.pt`, KERMT data/predictions, the pretrained checkpoint, datasets, Docker image. |
| **Only on `CL502-18`** | Full run directories `ml/runs/kermt_*/` (toxicity seed 1: 898 MB incl. `last_checkpoint.pt` 496 MB), `ml/runs/lab_logs/`, pretrained checkpoint `ml/data/checkpoints/kermt/…`, processed data `ml/data/processed/20260918T090433Z/`, Docker image `kermt:latest`. All gitignored. |

Toxicity seed 1 artifact: `shashquatch/mars-admet/kermt-toxicity-seed1:v0`, model SHA-256
`4577899e8bbd5750fe2cb24e3ee0a4b5dbc80813f32bb4ed3478e659c450c8de`, 203,509,766 bytes. All seven references and
hashes: `kermt_tier0_results/README.md`.

## 8. Retrieving the seed-1 model / full output later

1. **W&B artifact download (supported and verified)** — see `kermt_tier0_results/README.md` for the exact API call
   and reference. Yields `model.pt` + `metadata.json` (~194 MB) and needs `wandb login`.
2. **Direct copy from `CL502-18`** — for the full run directory (898 MB) or `last_checkpoint.pt`. The repo defines no
   transfer script.
3. **Runbook §13 `lab_out_*.tgz`** — excludes every `*.pt`; ~35 MB for the selection measured earlier; not generated,
   no such file exists.

## 9. Project state after this session

- `dili_standalone__cls` seeds 0–4 complete (2026-09-22, ~4 min each; aggregate JSON on the workstation).
- `toxicity__cls` seed 0 complete (2026-09-22); **seed 1 complete and verified (this session)**.
- Final `model.pt` of all 7 completed runs uploaded to W&B (`kermt-*-seed<N>:v0`) and hash-verified; references in
  `kermt_tier0_results/README.md`. Git contains no model binaries.
- `toxicity__cls` seeds 2–4 **pending**; five-seed toxicity aggregation (`s_agg.py`) **pending**.
  Toxicity is not complete until seeds 0–4 are verified.
- Remaining Tier-0 arms (`absorption_distribution__cls`, `absorption_distribution__reg`, …), Tier 1/2 and the
  KERMT-vs-XGBoost comparison are unchanged.
