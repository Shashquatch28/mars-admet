# KERMT Tier-0 lightweight result records

Storage roles: **GitHub = source / config / results / provenance** · **W&B = trained model artifacts** ·
**`CL502-18` = current working copy** (full run directories under `ml/runs/`, gitignored). Git contains no
model binaries.

Layout: `<arm>/seed<N>/` holds the small files copied from `ml/runs/<run_id>/` (`lab_summary.json`, `config.json`,
`run.json`, `provenance.json`, `<endpoint>__calibration_diagnostics.json`, `<endpoint>__temperature_scaler.json`,
`verify.txt` = `s_verify.py` output), plus `artifact_metadata.json` (the exact `metadata.json` stored inside the W&B
artifact) and `wandb_artifact.json` (artifact reference, digest, hashes). `dili_standalone__cls/aggregate_5seeds.json`
is the DILI five-seed aggregate produced on 2026-09-22. No `toxicity__cls` aggregate exists yet (seeds 2–4 not run).
Since 2026-09-30 the four breadth-first Pass-1 arms (`metabolism__reg`, `absorption_distribution__cls`,
`absorption_distribution__reg`, `metabolism__cls`) have `seed0/` records in the same layout (regression arms have no
`temperature_scaler.json`: none is produced). Session record: `../kermt_gpu_session_2026-09-30.md`.

## Model artifacts (uploaded and verified 2026-09-24; Pass-1 seed-0 rows added 2026-09-30)

Every artifact (type `model`, version `v0`, aliases `latest`, `final`) contains `model.pt` (the final trained model =
best-validation KERMT checkpoint, byte-identical to `ckpt/fold_0/model_0/model.pt`; `last_checkpoint.pt` was
deliberately NOT uploaded) and `metadata.json`. Verification per artifact: queried through `wandb.Api`, state
`COMMITTED`, both files present, produced by the run in the table, metadata hash equals the local hash, and a full
download to a temporary directory on `CL502-18` had SHA-256 equal to the local `model.pt` (temporary copies deleted).

| Endpoint | Seed | Run ID | Git SHA (dirty) | model.pt bytes | model.pt SHA-256 | W&B artifact (version) |
|---|---:|---|---|---:|---|---|
| dili_standalone__cls | 0 | `kermt_st_dili_standalone__cls_seed0_20260922T052900Z` | `7475342` (False) | 203,151,758 | `6c31aa2106e92698f60ee8c2d769dd736024d294d171434c67bc0cd2a7fab523` | `shashquatch/mars-admet/kermt-dili-seed0:v0` |
| dili_standalone__cls | 1 | `kermt_st_dili_standalone__cls_seed1_20260922T054638Z` | `7475342` (True) | 203,151,758 | `ecf83d0bf17e1dd64888d29ab7d60a9cd8a177cce1f843b4bc1be53c342f8c4d` | `shashquatch/mars-admet/kermt-dili-seed1:v0` |
| dili_standalone__cls | 2 | `kermt_st_dili_standalone__cls_seed2_20260922T055135Z` | `7475342` (True) | 203,151,758 | `236769daacaaf491bf0dd6226046f2d5ef4fcc54c79ff0906a928f97418bad13` | `shashquatch/mars-admet/kermt-dili-seed2:v0` |
| dili_standalone__cls | 3 | `kermt_st_dili_standalone__cls_seed3_20260922T055629Z` | `7475342` (True) | 203,151,758 | `a91d7555d31d66d7f4b97975821240a8b80323d1623167c966be1a6a51574194` | `shashquatch/mars-admet/kermt-dili-seed3:v0` |
| dili_standalone__cls | 4 | `kermt_st_dili_standalone__cls_seed4_20260922T060122Z` | `7475342` (True) | 203,151,758 | `e72c62379b6414ab9c796e6e49c338e4d035ce3d7f7ea1b3e75f38cae57c982d` | `shashquatch/mars-admet/kermt-dili-seed4:v0` |
| toxicity__cls | 0 | `kermt_mtsub_toxicity__cls_seed0_20260922T062623Z` | `7475342` (True) | 203,509,766 | `ebf4e283079db3d69d3e99feec7c2a8e94f1a81f6aa53da8342176e65d6972ce` | `shashquatch/mars-admet/kermt-toxicity-seed0:v0` |
| toxicity__cls | 1 | `kermt_mtsub_toxicity__cls_seed1_20260924T080913Z` | `f51cb8f` (False) | 203,509,766 | `4577899e8bbd5750fe2cb24e3ee0a4b5dbc80813f32bb4ed3478e659c450c8de` | `shashquatch/mars-admet/kermt-toxicity-seed1:v0` |
| metabolism__reg | 0 | `kermt_st_metabolism__reg_seed0_20260930T062626Z` | `ae5d28d` (False) | 203,152,142 | `8ca10190c44f550c3690f9e6f281a43b22583774d6e23b0307bb436c5781dc2a` | `shashquatch/mars-admet/kermt-metabolism-reg-seed0:v0` |
| absorption_distribution__cls | 0 | `kermt_mtsub_absorption_distribution__cls_seed0_20260930T063831Z` | `ae5d28d` (False) | 203,512,002 | `3b7d2be6f1e8fdd7e82a6c9f6f4c7d81024d7b2663a2f45e887517f8f007abc6` | `shashquatch/mars-admet/kermt-absorption-distribution-cls-seed0:v0` |
| absorption_distribution__reg | 0 | `kermt_mtsub_absorption_distribution__reg_seed0_20260930T065737Z` | `ae5d28d` (False) | 203,514,686 | `10e3553eede7bd187e1bb9c3d258b39d9ec3a62868663a3c10250862cda1c04a` | `shashquatch/mars-admet/kermt-absorption-distribution-reg-seed0:v0` |
| metabolism__cls | 0 | `kermt_mtsub_metabolism__cls_seed0_20260930T080420Z` | `ae5d28d` (False) | 203,512,002 | `35ce5318e51fddce72c3061ba6f4b7a9cbc0e2a9e1fa6652203c8b9833caca00` | `shashquatch/mars-admet/kermt-metabolism-cls-seed0:v0` |

**Run-record artifacts (2026-09-30 runs only).** Each Pass-1 seed-0 run also has a type-`run-record` artifact
`kermt-<arm>-seed0-record:v0` with configs, `metrics.jsonl`, `finetune.log` (per-epoch history), KERMT `run.json`
(`cmd_replay`), the exact train/val CSVs handed to KERMT, val/calibration/test `predictions.csv`, calibration JSONs,
`verify.txt`, launch log and VRAM trace. The file list for each is in its `wandb_artifact.json`. Earlier runs have no record artifact.

`metadata.json` is a superset of the loader metadata written by `KermtModel.save()` (`model_id`,
`pretrained_checkpoint`, `seed`, `target_names`, `task_type`) plus provenance (run id, git SHA/dirty, prep id,
checkpoint sha256, KERMT commit, Docker tag + image id, model sha256/size, training config, runtime, verification).
Note: the pretrained checkpoint path stored there is relative to `ml/`; the pretrained checkpoint itself is not in W&B.

## Retrieval on another machine

Verified in this session: the Python API (used for the verification downloads):

```python
import wandb
art = wandb.Api().artifact("shashquatch/mars-admet/kermt-toxicity-seed1:v0", type="model")
path = art.download(root="kermt-toxicity-seed1")   # -> model.pt + metadata.json (~194 MB)
```

The CLI form is documented by `wandb artifact get --help` in the repo venv (`entity/project/name:version`), but it
was not run to completion here: `wandb artifact get shashquatch/mars-admet/kermt-toxicity-seed1:v0`.
Requires `wandb login` for the `shashquatch` account. After download compare `sha256sum model.pt` with the table.

## Caveats

- Recorded Git state differs between runs: `7475342` for all DILI and toxicity seed-0 runs (DILI seed 0 recorded clean;
  DILI seeds 1–4 and toxicity seed 0 recorded `git.dirty=true`), `f51cb8f` clean for toxicity seed 1. Whether the
  dirty flag reflected code changes or only untracked files during those sessions was not established; the two
  commits differ only by `ml/eval/tier0_*.py` and `ml/requirements-m2.txt`.
- The Docker image is recorded by tag in run provenance; the image id in `artifact_metadata.json` was read from the
  workstation (`sha256:2918726c…d87d`, created 2026-09-18, before every run).
- W&B run pages do not carry held-out test metrics; those are in each `lab_summary.json` here.
- Uploading attached each artifact to its original W&B run (resume) and set that run's `job_type` to `model-upload`;
  run config, summary and state were unchanged (checked on toxicity seed 1).

## Reading rules (added 2026-09-30; authoritative text: `../../AIMS/decisions.md` 2026-09-30)

No record in this folder was changed by these rules; they say how to read them.

- **Provisional until 5 seeds.** An arm with fewer than five seeds has provisional single-seed numbers — no "± std", no ranking.
- **Epoch.** Where an epoch is quoted, it is the **saved** epoch (last `Saving model at epoch N` line of `finetune.log`, i.e. the epoch
  of `model.pt`). KERMT's final `best validation … on epoch N` line was wrong on all three runs checked (per the 2026-09-30 session note) and must not be used. `model.pt` (SHA-256 in the table
  above) — not any epoch number — identifies the model.
- **HIA calibration.** `absorption_distribution__cls`: HIA's calibration set is N=47 (46 positive / 1 negative), below the blueprint
  floor of 50. The run is valid; HIA AUROC/AUPRC and raw Brier/ECE stand. HIA **calibrated** metrics and the HIA temperature are
  recorded but **not reportable**. Calibrated metrics count as results only where `n_fit_samples ≥ 50` and both classes are present.
- **Calibration in general.** One fixed calibration split per endpoint (same for every seed, withheld from training in every arm,
  regression included; regression calibration is unused). Always read raw and calibrated columns together — calibration worsened test ECE for
  Pgp, BBB and HIA, and improved it for CYP3A4 and CYP2C9; the session note attributes this to the calibration split's class prior differing from the test set's.
- **DILI.** `dili_standalone__cls` is the **base-pool, non-augmented** variant (`use_augmented_dili=false`, 287 training molecules at
  seed 0). XGBoost's DILI used the augmented pool (979). Do not compare the two directly; pool-match first.
- **`metabolism__cls`** follows Option A (strict cluster-level leakage removal: 27–29 % of each CYP's labels lost). It is a
  multi-task arm on a reduced pool; the single-task CYP baselines on full splits are still owed, so multi-task benefit cannot yet be
  separated from the pool reduction.
- **`absorption_distribution__reg`** selects its epoch by the unweighted mean of per-task raw-unit MAE, which PPB (MAE ≈ 10 on a % scale, 42 val molecules)
  dominates. Treat the solubility/logP/Caco-2 rows as evaluated at a PPB-chosen epoch.
- **Hyperparameters.** `config.json` `hyperparams` are all `null` by design (KERMT defaults); the applied values are in
  `artifact_metadata.json` → `training_config` (`args_applied`, `cmd_replay`).
