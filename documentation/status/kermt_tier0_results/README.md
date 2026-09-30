# KERMT Tier-0 lightweight result records

Storage roles: **GitHub = source / config / results / provenance** · **W&B = trained model artifacts** ·
**`CL502-18` = current working copy** (full run directories under `ml/runs/`, gitignored). Git contains no
model binaries.

Layout: `<arm>/seed<N>/` holds the small files copied from `ml/runs/<run_id>/` (`lab_summary.json`, `config.json`,
`run.json`, `provenance.json`, `<endpoint>__calibration_diagnostics.json`, `<endpoint>__temperature_scaler.json`,
`verify.txt` = `s_verify.py` output), plus `artifact_metadata.json` (the exact `metadata.json` stored inside the W&B
artifact) and `wandb_artifact.json` (artifact reference, digest, hashes). `dili_standalone__cls/aggregate_5seeds.json`
is the DILI five-seed aggregate produced on 2026-09-22. No `toxicity__cls` aggregate exists yet (seeds 2–4 not run).

## Model artifacts (all uploaded and verified 2026-09-24)

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
