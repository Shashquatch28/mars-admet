# KERMT GPU session — 2026-10-14 (Pass 2, session 5: `toxicity__cls` seeds 2–4)

Workstation `CL502-18` (RTX A4000, driver 595.91.07, kernel 7.0.0-38-generic), branch `milestone/m2-kermt`, `EXPECTED_SHA`
`735ef89ea88a7be909924643a69325d8a1d05a68` (maintainer-supplied; HEAD, remote tip and `lab_env.sh` agreed; tree clean).
Image `kermt:latest` `sha256:2918726c6bd041339ee00534f7b7b9c547466282dc73df71ca365887f3d5d87d` (unchanged since Pass 1),
checkpoint sha256 `e9e6649bc96503fbdb3023e312764ecbbbafd686d9a62865a1fec9466cea6be3`, KERMT `e402473` / `v2.0.0`, prep
`20260918T090433Z`. No code, data, config or hyperparameter change; no git write during any launch.

## What ran

| Seed | Run id | Launched (IST) | Wall | Peak VRAM | Saved epoch (val AUROC) | `s_verify` / `s_protocol` | W&B artifact |
|---:|---|---|---:|---:|---|---|---|
| 2 | `kermt_mtsub_toxicity__cls_seed2_20261014T062957Z` | 12:00 | 95.1 min | 4,006 MiB | 20 (0.8663) | PASS / MATCH | `kermt-toxicity-seed2:v0` |
| 3 | `kermt_mtsub_toxicity__cls_seed3_20261014T080552Z` | 13:35 | 95.9 min | 4,118 MiB | 21 (0.8665) | PASS / MATCH | `kermt-toxicity-seed3:v0` |
| 4 | `kermt_mtsub_toxicity__cls_seed4_20261014T101513Z` | 15:45 | 94.7 min | 3,880 MiB | 7 (0.8950) | PASS / MATCH | `kermt-toxicity-seed4:v0` |

Peak VRAM is the maximum of each run's 5 s `nvidia-smi` trace (includes ≈ 0.3 GB desktop).
Model SHA-256 and sizes are in `kermt_tier0_results/README.md`; every `model.pt` is byte-identical to KERMT's `ckpt/fold_0/model_0/model.pt`.
Each upload passed `s_upload.py` (all `[PASS]`) and `s_wandb_verify.py` (`VERIFY: PASS`; model and run-record artifacts COMMITTED,
files `model.pt` + `metadata.json`, aliases `final` + `latest`, one version `v0`). Zero `UserWarning: W&B` lines in each launch log.

**D1 (saved epoch).** For seed 4 `eval.kermt_log` returned `consistent_with_logged_best_score=True` (saving-line epoch 7, KERMT's logged
best epoch 26 — the known logging bug, D1; the logged epoch is audit-only).

## Crashed run (reported, not fixed)

The first seed-4 launch, `kermt_mtsub_toxicity__cls_seed4_20261014T094244Z` (15:12 IST), stopped logging at 15:32:50 IST. The
workstation came back up at 15:42 IST. The previous boot's journal ends at 15:12:08 IST — before the run's last VRAM sample — and
contains no shutdown record and no kernel OOM, Xid, NVRM or panic line; the journal evidently did not flush before the machine
stopped, so it says nothing about the final ≈ 30 minutes. The cause is **not established**. The run directory is left in place with `run.json` `status: running` and no
`metrics.jsonl`; its W&B run is stuck `running`. `s_agg.py` skips it (`SKIP (not completed)`). Seed 4 was re-launched once (new
timestamp; same code, config and fold) on the maintainer's instruction. This is a re-launch after a hardware-level interruption,
not a protocol change; all five seeds share one protocol.

## Aggregate

`status/kermt_tier0_results/toxicity__cls/aggregate_5seeds.json` (`s_agg.py` output, mean ± std over **test** metrics, 5 seeds):

| Endpoint | AUROC | AUPRC | Brier raw → cal. | ECE raw → cal. |
|---|---|---|---|---|
| `herg_cardiotoxicity` | 0.8921 ± 0.0037 | 0.9055 ± 0.0035 | 0.1354 → 0.1334 | 0.043 → 0.031 |
| `ames_mutagenicity` | 0.8549 ± 0.0046 | 0.8924 ± 0.0037 | 0.1548 → 0.1519 | 0.060 → 0.037 |

hERG validation holds only 18–24 labels per seed (vs ≈ 1,810 AMES), so hERG epoch selection is barely measured — recorded, not
fixed (runbook arm table). Seed 4's hERG validation AUROC (0.935 on 24 molecules, 6 positive) shows how little that fold constrains.

## Status

30 of 30 Tier-0 seeds trained and recorded; 30 KERMT models in W&B; six arms with five-seed aggregates. Nothing remains in P-6.
Tier-1/2 work is on `milestone/m2-kermt-tier1`.
