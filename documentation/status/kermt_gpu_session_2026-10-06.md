# KERMT Tier-0 Pass-2 GPU session — 2026-10-06 (arms 1–2 complete; stopped before arm 3)

_Workstation `CL502-18`, RTX A4000. Result records: `kermt_tier0_results/<arm>/seed<N>/`._

## Identity and environment

| Item | Pass 1 | This session |
|---|---|---|
| Repo SHA | `ae5d28d` | `c1f0f0407a8849325d38aaf940193c0c7bcfa253` (== origin/milestone/m2-kermt, tree clean) |
| `kermt:latest` image id | `sha256:2918726c6bd041339ee00534f7b7b9c547466282dc73df71ca365887f3d5d87d` | **unchanged**, same id |
| NVIDIA driver | 580.173.02 | **595.91.07** (changed; newer; container reports CUDA 13.2 in nvidia-smi, torch in container 2.9.1 sees 1 GPU) |
| Host Python | 3.11.15 | **3.11.17** (changed) |
| GPU | RTX A4000 16376 MiB | same; 314 MiB idle, no other compute apps |
| KERMT repo | `e402473…`, v2.0.0 | same, clean |
| Checkpoint sha256 | `e9e6649b…6cea6be3` | same, `s_ckpt.py` 5/5 PASS |
| W&B | shashquatch28 / shashquatch / mars-admet | same (first `s_wandb.py` call timed out with "service process busy"; immediate retry OK) |

Preflight (P-1..P-4): `lab_env.sh` already pinned `c1f0f04` (Oct 1; no edit) and the repo was already at the tip (`git pull --ff-only` was a no-op).
Protocol files identical to `ae5d28d`; `metrics.py` differs only in `aggregate_seed_metrics` / `format_mean_std`. CPU tests 216 passed, 3 skipped.
`compare_prep`: all datasets used A_BYTE_IDENTICAL (only `dili_liver_injury__augmented` is D, expected). Readiness `READY_FOR_GPU_SMOKE_TEST`. Preflight counts unchanged.
Helper scripts byte-identical to runbook text (`s_agg.py` differs only by the documented defensive `.get()`).
Undated files overwritten in lab_logs during P-4 (accepted): `ws_fingerprint.json`, `prep_compare.json`, `readiness_report_ws.*`, `cluster_preflight_ws.*`.

## Runs this session (all: banner matched P-5, `s_verify` PASS, `s_protocol` MATCH, 0 W&B warnings, `completed`, W&B artifacts verified)

| Arm | Seed | Run id | Wall (s) | Peak VRAM (MiB) | Saved epoch | Val score at saved epoch |
|---|---|---|---:|---:|---:|---|
| metabolism__reg | 1 | `kermt_st_metabolism__reg_seed1_20261006T062005Z` | 422.1 | 3565 | 15 | 16.3351 |
| metabolism__reg | 2 | `kermt_st_metabolism__reg_seed2_20261006T064018Z` | 417.9 | 3577 | 19 | 16.1667 |
| metabolism__reg | 3 | `kermt_st_metabolism__reg_seed3_20261006T064839Z` | 422.0 | 3573 | 11 | 14.8459 |
| metabolism__reg | 4 | `kermt_st_metabolism__reg_seed4_20261006T065650Z` | 416.4 | 3581 | 8 | 15.4693 |
| absorption_distribution__cls | 1 | `kermt_mtsub_absorption_distribution__cls_seed1_20261006T070452Z` | 1076.6 | 3703 | 20 (KERMT final line says 29: D1 bug) | 0.9437 (logged best 0.943685) |
| absorption_distribution__cls | 2 | `kermt_mtsub_absorption_distribution__cls_seed2_20261006T075522Z` | 1077.0 | 3673 | 21 (KERMT says 29) | 0.9435 |
| absorption_distribution__cls | 3 | `kermt_mtsub_absorption_distribution__cls_seed3_20261006T081414Z` | 1094.0 | 3759 | 26 (KERMT says 26) | 0.9395 |
| absorption_distribution__cls | 4 | `kermt_mtsub_absorption_distribution__cls_seed4_20261006T083321Z` | 1081.5 | 3939 | 9 (KERMT says 25) | 0.9365 |

Peak VRAM includes ~0.3-0.4 GiB desktop baseline. Only expected WARN: HIA calibration N=47 (arm 2).

## Findings

0. `consistent_with_logged_best_score` was `true` for all four classification runs (seeds 1-4); seed 4 saved epoch 9 vs KERMT-logged best epoch 25 (D1 bug), consistent.
1. **§5 confirmation.** `Saving model at epoch N` wording exists in `finetune.log` (verified on every run).
   `tier0_artifacts.py` **cannot run on regression arms**: `tier0_artifacts.py:197` unconditionally loads `calibration/<endpoint>/temperature_scaler.json`
   → `FileNotFoundError` for `metabolism__reg` (no calibration). Needs a maintainer decision/code fix before arm 4 (`absorption_distribution__reg`) packages can be generated.
   On the first classification run (`absorption_distribution__cls` seed 1): `saved_epoch_resolution.consistent_with_logged_best_score` = **true**, `epoch` 20, `source` `derived_from_auc_val`, `logged_best_epoch` 29.
2. For regression arms `resolve_saved_epoch` falls back to the saving line only (no `auc_val` rows; `consistent_with_logged_best_score` null). I read the saved epoch from the last `Saving model` line and checked the score against KERMT's logged best (equal to <1e-3 in all four runs).

## Results (test set; provisional unless 5 seeds)

- `metabolism__reg` — **5 seeds complete**: clearance_microsomal raw test MAE mean 24.510 ± 0.650 (n=5; `agg_metabolism__reg_20261006.txt`, `runs/kermt_tier0_metabolism__reg_aggregate.json`). Seeds 1–4: 24.683, 23.552, 24.175, 25.056.
- `absorption_distribution__cls` — **5 seeds complete** (`agg_absorption_distribution__cls_20261006.txt`, `runs/kermt_tier0_absorption_distribution__cls_aggregate.json`), test, mean ± std, raw | calibrated:
  - BBB: AUROC 0.941±0.003 | 0.941±0.003; Brier 0.082±0.003 | 0.079±0.002; ECE 0.055±0.005 | 0.061±0.003
  - P-gp: AUROC 0.932±0.004 | 0.932±0.004; Brier 0.103±0.004 | 0.110±0.004; ECE 0.062±0.014 | 0.098±0.009
  - HIA (raw only; calibrated omitted per D4, N=47): AUROC 0.926±0.017; AUPRC 0.974±0.008; Brier 0.075±0.003; ECE 0.067±0.003

## Not yet run

`metabolism__cls` 1–4; `absorption_distribution__reg` 1–4; `toxicity__cls` 2–4.

## State

Records moved into `documentation/status/kermt_tier0_results/<arm>/seed<N>/` at the end of the session (plus `aggregate_5seeds.json` for both arms). Full run directories, launch logs, VRAM traces and the per-session `agg_*`/`verify_*`/`protocol_*` files stay under gitignored `ml/runs/` on `CL502-18`.

## W&B

19 Tier-0 model artifacts exist in `shashquatch/mars-admet` (11 from Pass 1 + 8 this session: `kermt-metabolism-reg-seed1..4`, `kermt-absorption-distribution-cls-seed1..4`),
each type `model`, one version `v0`, aliases `final` + `latest`, state `COMMITTED`, files `model.pt` + `metadata.json`; each new one has an additive `-record` artifact (`run-record`).
Per-run verification: full-download SHA-256 == local `model.pt`. Checked again at session end by listing all `model` collections.

## For the maintainer

- `tier0_artifacts.py` fails on regression arms (see Findings 1); decide before `absorption_distribution__reg` seeds are packaged.
- The session time budget was never specified, so arm 3 (`metabolism__cls`, ≈ 3.8 h) was not started.
- Next session resumes at `metabolism__cls` seeds 1–4, then `absorption_distribution__reg` 1–4, then `toxicity__cls` 2–4 (≈ 12.5 h total). `lab_env.sh` already pins `c1f0f04`.
