# KERMT Tier-0 Pass-2 GPU session — 2026-10-07 (`metabolism__cls` seeds 1–4 complete)

_Workstation `CL502-18`, RTX A4000. Result records: `kermt_tier0_results/metabolism__cls/seed<N>/`. Times are workstation local (IST)._

## Identity and environment

| Item | Last session (2026-10-06) | This session |
|---|---|---|
| Repo SHA | `c1f0f04` (at session start) | `3d32817b560c4b8f77ce9a64342c75a51f872b3f` == EXPECTED_SHA == origin/milestone/m2-kermt, tree clean at every launch |
| `lab_env.sh` pin | `c1f0f04` | replaced; `grep -c '^export EXPECTED_SHA='` = 1 |
| `kermt:latest` image id | `sha256:2918726c…d87d` | **unchanged**, same id |
| NVIDIA driver | 595.91.07 | 595.91.07 (unchanged) |
| Host Python | 3.11.17 | 3.11.17 (unchanged) |
| GPU | RTX A4000 16376 MiB | same; 551 MiB idle, no other compute apps; container torch 2.9.1 sees 1 GPU |
| KERMT repo | `e402473…`, v2.0.0 | same, clean |
| Checkpoint sha256 | `e9e6649b…6cea6be3` | same; `s_ckpt.py` 5/5 PASS |
| W&B | shashquatch28 / shashquatch / mars-admet | same |

Preflight (10:42–10:45): workstation HEAD was `21a1c0e` (the maintainer's own commit of the 2026-10-06 records, already in origin), 1 commit behind origin. Fetch showed no workstation-only commits, HEAD an ancestor of the tip, collision scan clean, tree clean, so one `git pull --ff-only` was run (`21a1c0e` → `3d32817`; changed only `decisions.md`, `next_steps.md`, `ml/eval/tier0_artifacts.py`, new `ml/tests/test_tier0_artifacts.py`).
Protocol files identical to `ae5d28d`; `metrics.py` differs from `ae5d28d` only as it did last session (not touched by `3d32817`).
CPU tests: 221 passed, 3 skipped (13 test files incl. the new `test_tier0_artifacts.py`).
`compare_prep`: CYP3A4 / CYP2D6 / CYP2C9 datasets `A_BYTE_IDENTICAL`; only `dili_liver_injury__augmented` is `D` (expected, irrelevant); `pipeline_version_mismatch` `{}`. Readiness `READY_FOR_GPU_SMOKE_TEST`, no blockers. Preflight counts unchanged (`metabolism__cls`: 5,625 rows dropped, 29.2%).
Undated files overwritten in `lab_logs` during preflight (accepted, as last session): `ws_fingerprint.json`, `prep_compare.json`, `readiness_report_ws.*`, `cluster_preflight_ws.*`.
Disk 324 GB free at start (about 1 GB per run); VRAM idle.

Seed 1 launched 10:45:35 (preflight finished 10:45). The 10:30 plan target was missed only because the session started at 10:42.

## Runs this session (every launch: banner matched P-5 exactly, `s_verify` PASS with no `[WARN]`, `s_protocol` MATCH, 0 W&B warnings, `completed`, W&B artifacts verified)

| Seed | Run id | Launch | Wall (s) | Peak VRAM (MiB) | Saved epoch | Val score at saved epoch | KERMT logged best (epoch) |
|---:|---|---|---:|---:|---:|---|---|
| 0 (Pass 1) | `kermt_mtsub_metabolism__cls_seed0_20260930T080420Z` | — | 3437.9 | — | 19 | — | 0.921773 (28) |
| 1 | `kermt_mtsub_metabolism__cls_seed1_20261007T051545Z` | 10:45:35 | 3390.0 | 3783 | 28 | 0.9167 | 0.916701 (28) |
| 2 | `kermt_mtsub_metabolism__cls_seed2_20261007T061315Z` | 11:43:04 | 3407.7 | 3933 | 25 | 0.9196 | 0.919641 (28, D1 bug) |
| 3 | `kermt_mtsub_metabolism__cls_seed3_20261007T071052Z` | 12:40:42 | 3388.9 | 3841 | 29 | 0.9197 | 0.919712 (29) |
| 4 | `kermt_mtsub_metabolism__cls_seed4_20261007T080821Z` | 13:38:10 | 3414.4 | 3951 | 23 | 0.9189 | 0.918871 (27, D1 bug) |

Saved epoch = `N` of the last `Saving model at epoch N` line in `finetune.log`; never the final `best validation … on epoch` line. Peak VRAM includes about 0.5 GiB desktop baseline. Seed 0's saved epoch is derived read-only from its Pass-1 `finetune.log` with `ml/eval/kermt_log.py`.
`saved_epoch_resolution.consistent_with_logged_best_score` (computed with `resolve_saved_epoch_from_file`, the `tier0_artifacts.py` packaging step was not run): **true for seeds 1–4** (and 0); the D1 note fired for seeds 2 and 4 (and 0).
Calibration: all 15 fits `fitted`, `optimizer_success` true, `at_boundary` false, T in 1.17–1.50, calibration N = 241 / 833 / 439 (CYP3A4 / CYP2D6 / CYP2C9) in every seed. No calibration WARN in any run.

## Results (test set) — arm COMPLETE, 5 seeds (0–4)

Mean ± std over 5 seeds (`aggregate_5seeds.json`, `agg_metabolism__cls_20261007.txt`, `runs/kermt_tier0_metabolism__cls_aggregate.json`), raw | calibrated:

| Endpoint | AUROC | AUPRC | Brier | ECE |
|---|---|---|---|---|
| CYP3A4 | 0.895 ± 0.001 \| 0.895 ± 0.001 | 0.873 ± 0.003 \| 0.873 ± 0.003 | 0.134 ± 0.002 \| 0.130 ± 0.001 | 0.053 ± 0.008 \| 0.023 ± 0.004 |
| CYP2D6 | 0.879 ± 0.003 \| 0.879 ± 0.003 | 0.688 ± 0.005 \| 0.688 ± 0.005 | 0.087 ± 0.001 \| 0.087 ± 0.001 | 0.036 ± 0.004 \| 0.034 ± 0.008 |
| CYP2C9 | 0.893 ± 0.001 \| 0.893 ± 0.001 | 0.785 ± 0.003 \| 0.785 ± 0.003 | 0.122 ± 0.001 \| 0.120 ± 0.001 | 0.042 ± 0.004 \| 0.032 ± 0.004 |

(std from `aggregate_seed_metrics`, n = 5; seed 0 is a Pass-1 run on `ae5d28d`, seeds 1–4 on `3d32817` with identical protocol files and `PROTOCOL: MATCH`.) Caveat that applies to every number: Option A pool (about 29% of each CYP's training labels removed by strict leakage prevention, D5); the single-task CYP baselines on full splits are still owed, so this is not a KERMT-vs-XGBoost comparison.

## W&B

23 `model` artifacts now exist in `shashquatch/mars-admet` (listed via the API at session end): 19 before + `kermt-metabolism-cls-seed1..4` (each type `model`, one version `v0`, aliases `final` + `latest`, state `COMMITTED`, files `model.pt` + `metadata.json`, logged by the original training run; each with an additive `-record` artifact of type `run-record`, 35 files). Per-run `s_wandb_verify.py`: full-download SHA-256 == local `model.pt`.

| Artifact | model.pt sha256 |
|---|---|
| `kermt-metabolism-cls-seed1:v0` | `02072d30bcdf3a41134cfe6fd8d63acdbfa77af0f1c9ee86e4430ae5a12052b6` |
| `kermt-metabolism-cls-seed2:v0` | `1639ecc60d593b4e072f040d814eda021ee7c03f3df521188f482f5faf1fcb63` |
| `kermt-metabolism-cls-seed3:v0` | `63391251a7545aaf26e9722259cdcd6ba039f41944bdefac4dd98dc100b3310d` |
| `kermt-metabolism-cls-seed4:v0` | `dbd4b20b098356e454d64b96f67c625f8689badf53d40634ad58931e14b4ac80` |

Full list of the 23 collections: `kermt-absorption-distribution-cls-seed0..4`, `kermt-absorption-distribution-reg-seed0`, `kermt-dili-seed0..4`, `kermt-metabolism-cls-seed0..4`, `kermt-metabolism-reg-seed0..4`, `kermt-toxicity-seed0..1`.

## Not run / unchanged

`absorption_distribution__reg` 1–4 and `toxicity__cls` 2–4 were not started (not in today's scope). `ml/eval/tier0_artifacts.py` was not run for `metabolism__cls` (optional, off the critical path); no artifact package was generated. No crashed or re-run runs; nothing deleted. No git write other than the one sanctioned `git pull --ff-only`.

## State

Records moved into `kermt_tier0_results/metabolism__cls/seed<N>/` (seeds 1–4, 14 files each, same set as last session) plus `aggregate_5seeds.json`; they are untracked for the maintainer to commit. Launch logs, VRAM traces (`runs/lab_logs/records/metabolism__cls/seed<N>/`, `runs/lab_logs/`), full run directories and the `agg_*`/`verify_*`/`protocol_*` files stay under gitignored `ml/runs/` on `CL502-18` (26 GB `runs/`, 320 GB free).

## For the maintainer

- Commit and push the new `kermt_tier0_results/metabolism__cls/` records and this note. Remaining Pass-2 work: `absorption_distribution__reg` 1–4 (≈ 3.8 h, regression, no calibration; `3d32817` makes `tier0_artifacts.py` refuse regression arms by design, which I did not exercise today) and `toxicity__cls` 2–4 (≈ 4.75 h). `lab_env.sh` now pins `3d32817`.
- Per-seed cost was stable at 56.5–56.9 min (seed 0: 57.3 min). A full 4-seed arm plus verification fits in about 4.0 h of workstation time when launches are chained back to back.
