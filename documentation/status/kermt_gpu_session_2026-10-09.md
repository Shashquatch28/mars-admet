# KERMT Tier-0 Pass-2 GPU session — 2026-10-09 (`absorption_distribution__reg` seed 4; arm complete)

_Workstation `CL502-18`, RTX A4000. Result records: `kermt_tier0_results/absorption_distribution__reg/seed4/` and `aggregate_5seeds.json`.
Times are workstation local (IST). Session window 13:02–15:45 (hard). Only one run fit: `toxicity__cls` seeds are ≈ 95 min each, and seed 4 (≈ 57 min) plus one
toxicity seed (≈ 152 min of GPU time) would not finish inside the window._

## Identity and environment

| Item | Last session (2026-10-08) | This session |
|---|---|---|
| Repo SHA | `e6c3dee` | `26c63ccd27b81512387a9d7417dbd1d24b68e19c` == EXPECTED_SHA == origin/milestone/m2-kermt; no pull needed; tree clean at launch |
| `lab_env.sh` pin | `e6c3dee` | replaced (backup `lab_env.sh.bak_20261008`); `grep -c '^export EXPECTED_SHA='` = 1 |
| `kermt:latest` image id | `sha256:2918726c…d87d` | **unchanged** |
| NVIDIA driver | 595.91.07 | 595.91.07 |
| Host Python | 3.11.17 | 3.11.17 |
| GPU | RTX A4000 16376 MiB | same; 556 MiB idle, no other compute apps; container torch `2.9.1 True 1` |
| KERMT repo | `e402473…`, v2.0.0 | same, clean |
| Checkpoint sha256 | `e9e6649b…6cea6be3` | same; `s_ckpt.py` 5/5 PASS |
| W&B | shashquatch28 / shashquatch / mars-admet | same |

The maintainer accepted the pushed origin tip `26c63cc…` as `EXPECTED_SHA` (same practice as 2026-10-08). Protocol files identical to `ae5d28d`; descends from
`ad6eaf1`; `decisions.md` 2026-09-30 entry present. CPU tests: 229 passed, 3 skipped. `compare_prep`: solubility / lipophilicity / Caco-2 / PPB `A_BYTE_IDENTICAL`;
only `dili_liver_injury__augmented` is `D` (expected); `pipeline_version_mismatch` `{}`. Readiness `READY_FOR_GPU_SMOKE_TEST`, no smoke blockers. Cluster preflight output
identical to the previous file (only the output filename line differs). Disk 318 GB free.

## Run this session (banner matched P-5 exactly, `s_verify` PASS with no `[WARN]`, `s_protocol` MATCH, 0 W&B warnings, `completed`, W&B artifact verified)

| Seed | Run id | Launch | Wall (s) | Peak VRAM (MiB) | Saved epoch | Val MAE at saved epoch | KERMT logged best (epoch) |
|---:|---|---|---:|---:|---:|---|---|
| 4 | `kermt_mtsub_absorption_distribution__reg_seed4_20261009T081039Z` | 13:40:31 | 3369.0 | 3717 | 9 | 2.8808 | 2.880806 (25, D1 bug) |

Saved epoch = `N` of the last `Saving model at epoch N` line in `finetune.log` (5 such lines), not the final `best validation … on epoch` line. Peak VRAM includes about
0.5 GiB desktop baseline. No calibration (regression). `tier0_artifacts.py` not run (it refuses regression arms).

## Results (test set, MAE, raw units) — arm COMPLETE, 5 seeds

| Endpoint (n test) | seed 4 | 5-seed mean ± std (`s_agg.py`) |
|---|---:|---:|
| `solubility_logs` (1960) | 0.8219 | 0.8083 ± 0.0170 |
| `lipophilicity_logp` (840) | 0.4774 | 0.4600 ± 0.0137 |
| `caco2_permeability` (180) | 0.3515 | 0.3209 ± 0.0256 |
| `ppb_binding` (323) | 7.2450 | 7.3957 ± 0.2312 |

Aggregate written to `ml/runs/kermt_tier0_absorption_distribution__reg_aggregate.json`, copied to `kermt_tier0_results/absorption_distribution__reg/aggregate_5seeds.json`.

## W&B

`kermt-absorption-distribution-reg-seed4:v0` (type `model`, aliases `final` + `latest`, files `model.pt` + `metadata.json`, logged by resuming the training run) plus the
additive `run-record` artifact (29 files). `s_wandb_verify.py`: `VERIFY: PASS` (COMMITTED, exact file set, re-downloaded `model.pt` SHA-256 == local).
model.pt sha256 `5085e9a6eb43e07d2cae1b705734d5fdbcb4d1597b4b108a64bf0ada629ded67`.

## Not run / unchanged

`toxicity__cls` seeds 2–4 (≈ 95 min each) not started, since none could finish by 15:45. No crashed or re-run runs; nothing deleted. Git: no pull; at the maintainer's request, one local commit of these records and doc updates; nothing pushed by the session.

## For the maintainer

- Commit and push `kermt_tier0_results/absorption_distribution__reg/{seed4/,aggregate_5seeds.json}` and this note.
- **Resume at P-6 order 5: `toxicity__cls` seeds 2, 3, 4** (≈ 95 min each; one per session unless the window is ≥ 3.3 h for two).
- Tier-0 progress: **27 of 30 seeds**; five of six arms complete.
