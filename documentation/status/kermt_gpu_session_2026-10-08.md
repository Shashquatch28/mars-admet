# KERMT Tier-0 Pass-2 GPU session — 2026-10-08 (`absorption_distribution__reg` seeds 1–3)

_Workstation `CL502-18`, RTX A4000. Result records: `kermt_tier0_results/absorption_distribution__reg/seed<N>/`. Times are workstation local (IST).
Session window 11:55–15:30; seed 4 was not started because it could not finish inside the window (P-6: no run that cannot finish)._

## Identity and environment

| Item | Last session (2026-10-07) | This session |
|---|---|---|
| Repo SHA | `3d32817` | `e6c3dee92c899db7101a5f1e28b482093dcfe64b` == EXPECTED_SHA == origin/milestone/m2-kermt, tree clean at every launch |
| `lab_env.sh` pin | `3d32817` | replaced; `grep -c '^export EXPECTED_SHA='` = 1 |
| `kermt:latest` image id | `sha256:2918726c…d87d` | **unchanged**, same id |
| NVIDIA driver | 595.91.07 | 595.91.07 (unchanged) |
| Host Python | 3.11.17 | 3.11.17 (unchanged) |
| GPU | RTX A4000 16376 MiB | same; 546 MiB idle, no other compute apps; container torch 2.9.1 sees 1 GPU (`2.9.1 True 1`) |
| KERMT repo | `e402473…`, v2.0.0 | same, clean |
| Checkpoint sha256 | `e9e6649b…6cea6be3` | same; `s_ckpt.py` 5/5 PASS |
| W&B | shashquatch28 / shashquatch / mars-admet | same |

Preflight (11:53–11:57): HEAD was `28c7602`, 2 commits behind origin (`5da3091`, `e6c3dee`, both documentation only; the only `ml/` file touched since `3d32817` is `ml/README.md`).
One `git pull --ff-only` was run. The maintainer did not have the tip SHA at hand and accepted `e6c3dee…` (the pushed origin tip) as `EXPECTED_SHA`.
Protocol files identical to `ae5d28d`; descends from `ad6eaf1`; `decisions.md` 2026-09-30 entry present.
CPU tests: 221 passed, 3 skipped (13 test files). `compare_prep`: solubility / lipophilicity / Caco-2 / PPB datasets `A_BYTE_IDENTICAL`; only
`dili_liver_injury__augmented` is `D` (expected, irrelevant); `pipeline_version_mismatch` `{}`. Readiness `READY_FOR_GPU_SMOKE_TEST`, no smoke blockers.
Preflight counts identical to the 2026-10-01 file (`absorption_distribution__reg`: 11,570 rows, 446 dropped, worst sacrifice 14.6%). Disk 320 GB free.

Launches were chained by a session script: each seed was checked (P-7) before the next launch, the next launch's banner was checked against P-5 (kill on mismatch),
and the finished seed was uploaded and W&B-verified (P-9) while the next one trained. The seed-1 VRAM sampler started 42 s after launch (before the GPU was in use).

## Runs this session (every launch: banner matched P-5 exactly, `s_verify` PASS with no `[WARN]`, `s_protocol` MATCH, 0 W&B warnings, `completed`, W&B artifacts verified)

| Seed | Run id | Launch | Wall (s) | Peak VRAM (MiB) | Saved epoch | Val MAE at saved epoch | KERMT logged best (epoch) |
|---:|---|---|---:|---:|---:|---|---|
| 0 (Pass 1) | `kermt_mtsub_absorption_distribution__reg_seed0_20260930T065737Z` | — | 3400.1 | 4053 | — | — | — |
| 1 | `kermt_mtsub_absorption_distribution__reg_seed1_20261008T062711Z` | 11:57:02 | 3346.7 | 3752 | 16 | 3.2127 | 3.212684 (16) |
| 2 | `kermt_mtsub_absorption_distribution__reg_seed2_20261008T072316Z` | 12:53:08 | 3358.1 | 3704 | 18 | 2.6649 | 2.664902 (18) |
| 3 | `kermt_mtsub_absorption_distribution__reg_seed3_20261008T081927Z` | 13:49:19 | 3363.2 | 3632 | 13 | 3.1151 | 3.115119 (28, D1 bug) |

Saved epoch = `N` of the last `Saving model at epoch N` line in `finetune.log`; never the final `best validation … on epoch` line. The val score is KERMT's
stock raw-unit mean MAE over the four endpoints (PPB-dominated, D1). Peak VRAM includes about 0.5 GiB desktop baseline. No calibration (regression; every endpoint `skipped_regression`).
`tier0_artifacts.py` was not run (it refuses regression arms by design).

## Results (test set, MAE, raw units) — arm PARTIAL, 4 of 5 seeds: provisional single-seed numbers, no aggregate

| Endpoint (n test) | seed 0 | seed 1 | seed 2 | seed 3 |
|---|---:|---:|---:|---:|
| `solubility_logs` (1960) | 0.7950 | 0.7866 | 0.8119 | 0.8261 |
| `lipophilicity_logp` (840) | 0.4563 | 0.4623 | 0.4397 | 0.4643 |
| `caco2_permeability` (180) | 0.3146 | 0.3058 | 0.3424 | 0.2900 |
| `ppb_binding` (323) | 7.7641 | 7.4390 | 7.1665 | 7.3640 |

`s_agg.py` was not run (it refuses < 5 seeds). No "± std" is reported until seed 4 exists.

## W&B

26 `model` collections now exist in `shashquatch/mars-admet` (23 before + `kermt-absorption-distribution-reg-seed1..3`). Each new one: type `model`, one version `v0`,
aliases `final` + `latest`, state `COMMITTED`, files `model.pt` + `metadata.json`, logged by the original training run; each with an additive `-record` artifact of type
`run-record` (29 files). Verified twice: per-run `s_wandb_verify.py`, then an independent API pass at session end that re-listed the collections and re-downloaded each
`model.pt` (SHA-256 == local).

| Artifact | model.pt sha256 |
|---|---|
| `kermt-absorption-distribution-reg-seed1:v0` | `fbb883e4c3fb9b9403820323a7dee39db4992faa47a2c1843651dc0ee3b2e60f` |
| `kermt-absorption-distribution-reg-seed2:v0` | `40cbb429e5a11b0284aae42835d10a6ebc60ef09c00143ec0895fc23ecf1aa53` |
| `kermt-absorption-distribution-reg-seed3:v0` | `9a48f5b578a4fd6e1d8ff4dabfaeb04013a747c42b80fd5cc9cf4ebfc76d565f` |

## Not run / unchanged

`absorption_distribution__reg` seed 4 (≈ 57 min; would have ended about 15:48, after the 15:30 window) and `toxicity__cls` 2–4 were not started. No crashed or re-run runs;
nothing deleted. Git: the one `git pull --ff-only`, then (at the maintainer's request) a local commit of these records; nothing pushed by the session.

## State

Records in `kermt_tier0_results/absorption_distribution__reg/seed{1,2,3}/` (12 files each: the seed-0 set plus `protocol.txt`). Launch logs, VRAM traces
(`runs/lab_logs/records/absorption_distribution__reg/seed<N>/`), the chain log `runs/lab_logs/chain_adreg_20261008.log`, full run directories and the
`verify_*`/`protocol_*`/`upload_*`/`wandb_verify_*` files stay under gitignored `ml/runs/` on `CL502-18`. `lab_env.sh` now pins `e6c3dee`.

## For the maintainer

- Push the commit. **Resume at P-6 order 4, `absorption_distribution__reg` seed 4** (≈ 57 min), then aggregate the arm (`s_agg.py`), then `toxicity__cls` 2–4 (≈ 4.75 h).
- Tier-0 progress: **26 of 30 seeds**. Per-seed cost was stable at 55.8–56.1 min.
