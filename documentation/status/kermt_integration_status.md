# KERMT integration status

_Last updated: 2026-09-18, RTX A4000 GPU workstation session. Companion to
`documentation/AIMS/decisions.md`'s 2026-09-18 entry (full rationale) and
`documentation/AIMS/next_steps.md`'s live M2 pre-flight checklist — this file
is the point-in-time status snapshot; those two are the process record._

## 1. KERMT identity

- Model: **KERMT (Kinetic GROVER Multi-Task), Contrastive v2.0**.
- Hugging Face: `nvidia/NV-KERMT-70M-v2`, repo sha `7df5eb3179235fdea1e8124db73215da33d77dce`.
- Checkpoint file: `kermt_contrastive_v2.0.pt` — the only variant hosted at that repo (no base masked-pretrain variant exists there).
- Architecture: GROVER-lineage graph-transformer, 70.6M params, hidden size 800, depth 6, 4 attention heads/layer, 1 MT block, PReLU, dropout 0.1, latent dim 512.

## 2. Official source / version

- `github.com/NVIDIA-BioNeMo/KERMT`, tag `v2.0.0`, commit `e402473376ace30fa0092dad0578a88bf7f67287`.
- Vendored **outside** the mars-admet git tree at `~/mars-work/kermt-src/` (sibling checkout — it's a third-party tool dependency, not MARS source). Referenced via `MARS_KERMT_REPO` env var.
- Includes an "agent skill suite" (`agent/skills/kermt-*`) purpose-built for LLM-agent-driven workflows (Claude Code, Codex, Nemotron) — this integration follows that suite's documented CLI contracts exactly (no invented flags).

## 3. Checkpoint identifier + hashes

Recorded in `ml/data/metadata/kermt_checkpoint.lock.json` (tracked). Binaries live at `ml/data/checkpoints/kermt/NV-KERMT-70M-v2/` (gitignored, mirrors the `ml/data/raw/` convention).

| File | Bytes | SHA256 |
|---|---:|---|
| `kermt_contrastive_v2.0.pt` | 282,379,314 | `e9e6649bc96503fbdb3023e312764ecbbbafd686d9a62865a1fec9466cea6be3` |
| `pretrain_atom_vocab.json` | 128,862 | `6482e71a0b48c0711af6ada6fe5373c67a7078bbc5130946aff3dd7a64b65b8f` |
| `pretrain_bond_vocab.json` | 599,943 | `09a6206d46e83bcff9a50ef4bfd407cd0fa23caf8ffd9c4e655712447fe4a48b` |
| `pretrain_smiles_vocab.pkl` | 4,044 | `c30db667d18aa8dbbfb1c6d843f5cb56dcf3bfd6718ae91e766192c54c6d4863` |

Downloaded via plain `curl` from the HF `resolve/main` URLs (no `huggingface_hub` dependency added). **Not yet loaded with `torch.load` inside the container** as of this writing — see §9 Smoke 2.

## 4. Dependency decisions

MARS's `ml/.venv` is **unmodified** by this integration — no `torch`, no `transformers`, no PyTorch Geometric were installed there. Rationale:

- KERMT's `environment.yml`/`Pipfile` pin `python=3.11`, `torch==2.9.1`, `rdkit==2025.9.1`, `cuik_molmaker>=0.2,<0.3`, `descriptastorus==2.7.0`, `optuna`, `scikit-learn`, `tensorboard`, `wandb`, `protobuf>=5.29.6`.
- KERMT uses **neither** `transformers` nor PyTorch Geometric anywhere (confirmed by reading `kermt/model/models.py`, `kermt/model/layers.py`) — it's a from-scratch GROVER-style message-passing + attention implementation. The `transformers>=4.40` line in `ml/requirements.txt` is a stale placeholder predating the backbone decision.
- `cuik_molmaker` is imported **unconditionally** at module load time in `kermt/data/molgraph.py`, `kermt/data/kermtdataset.py`, `kermt/util/features.py` — not gated behind `--use_cuikmolmaker_featurization` as previously assumed (that flag only gates which codepath runs once the module is already imported). It ships only as a source sdist on PyPI (no wheel), compiling CUDA extensions against a specific torch+CUDA build.

**Decision:** run KERMT inside its own official docker container (`kermt:latest`, built from the repo's own `Dockerfile`/`environment.yml` via `agent/scripts/kermt_container.sh ensure_image`) rather than hand-installing into `ml/.venv`. This is container-based isolation, not a parallel venv — chosen because it's what NVIDIA built, tested, and documents as the primary path (`agent/README.md`: "Container-first").

## 5. RDKit compatibility result

**Moot by construction, not answered by a compatibility test.** `ml/.venv` keeps `rdkit==2026.3.6` (M1/M2's own `>=2026.3.1` pin); the `kermt` conda env inside the container has its own isolated `rdkit==2025.9.1`. The two never share a Python process or site-packages, so there is no version conflict to resolve. This was a deliberate choice over "install a CPU-only torch build inside ml/.venv and see if kermt/data imports with the newer rdkit" — that path was ruled out once the unconditional `cuik_molmaker` import was found (see §4), independent of the rdkit question.

## 6. Workstation GPU specification

- GPU: NVIDIA RTX A4000, 16,376 MiB VRAM, compute capability 8.6 (Ampere).
- Driver: 580.173.02 (CUDA 13.0 runtime support). Host `nvcc`: 13.2.
- Docker: 29.1.3. `nvidia-container-toolkit`: 1.20.0. `docker run --gpus all ... nvidia-smi` verified working against the exact base image KERMT's own Dockerfile uses (`nvidia/cuda:12.6.3-base-ubuntu22.04`).
- KERMT's own hardware table (`agent/README.md`): finetune needs ≥8GB VRAM at the default batch_size 32; this GPU clears that with margin for single-task work. Pretrain/continue-pretrain want ≥16GB for batch_size 256 (falls back to 32 on 1 GPU) — this GPU is at the documented floor for that heavier workflow, not above it.

## 7. Memory strategy

Not yet exercised against a real training run (blocked on real M1 data — §11). Planned, per the blueprint's 2026-08-30 compute decision (predates this GPU workstation, written for an even-smaller 16GB free-tier card, so directly applicable here too):
- Small batch size + gradient accumulation for any run that doesn't fit at the KERMT-default `batch_size=32`.
- `--dropout`/`--bond_drop_rate` left at KERMT's own finetune defaults (0.0 / 0.1) for the first smoke run — not tuned.
- Explicit CUDA memory reporting: planned for Smoke 4 (backward pass) via `torch.cuda.memory_allocated()` / `torch.cuda.max_memory_allocated()`, run inside the container.
- KERMT's finetune CLI does not currently expose a `--gradient-checkpointing` flag in `kermt/util/parsing.py` (not found by inspection) — if VRAM pressure appears at real batch sizes, the escalation path is gradient accumulation (already CLI-native via smaller `--batch-size`) before assuming checkpointing is available.

## 8. Adapter design

See `ml/featurize/kermt_adapter.py`'s module docstring for the full writeup. Summary: KERMT's CLI has no entry point accepting a precomputed graph tensor — every workflow takes `--csv` with a `smiles` column and re-featurizes internally. The adapter is therefore a **SMILES/CSV contract**, not a `mars-graph-v1` tensor transform:
- MARS's already-standardized SMILES pass through verbatim (no re-standardization).
- Chirality preservation is a vocabulary-equivalence claim: MARS's `CHIRAL_TAGS` (`ml/featurize/graph.py`) and KERMT's `ATOM_FEATURES['chiral_tag']` (`kermt/data/molgraph.py`) one-hot the identical four `Chem.ChiralType` members in the same order — both keyed off the same RDKit enum, not independently chosen. Verified by `ml/tests/test_kermt_adapter.py::test_chiral_tag_vocab_matches_kermt` (passing).
- Missing-label convention for multi-task CSVs is an **empty cell**, verified from `kermt/data/moldataset.py`'s literal parsing code, not assumed.

13 adapter unit tests passing; 16 wrapper unit tests passing (pure-Python paths, no docker/GPU needed for either).

## 9. Smoke-test commands + results

All six run against **real** MARS data: endpoint `ames_mutagenicity`, 300 train / 80 val molecules drawn from the real scaffold-balanced fold (seed 0) of the real 5,802-compound train_val pool, held-out test set (1,453 compounds) never touched.

| # | Test | Status | Notes |
|---|---|---|---|
| 1 | Import official KERMT source | ✅ PASS | `cuda_available=True`, `device_count=1`, `torch==2.9.1`, CUDA 12.8 runtime, `kermt`/`cuik_molmaker` import clean inside `kermt:latest`. |
| 2 | Load `kermt_contrastive_v2.0.pt` | ✅ PASS | `check_checkpoint.py --mode finetune_init` → `ok:true`, `model_type=hybrid`, arch fields match the HF model card exactly. |
| 3 | Forward pass on real data | ✅ PASS | Real graph conversion + forward inside `main.py finetune`; `loss_train=1.3317` at epoch 0, no NaNs. |
| 4 | Backward pass | ✅ PASS (inferred, not an isolated hook) | KERMT's CLI has no standalone forward-only/backward-only entry point — demonstrated instead by real training dynamics: `loss_train` 1.3317→1.0341→0.8531 and `auc_val` 0.6575→0.6756→0.7244 monotonically improve over 3 epochs, proving gradients flow and the optimizer updates real weights. |
| 5 | Tiny finetune + ckpt save/reload | ✅ PASS | 3 epochs, batch_size=16, wall time 50.2s total (includes container/prepare overhead; pure train loop ≈13.5s, ~4.5s/epoch). Reload-then-repredict bit-identical (`RELOAD_PREDS_MATCH=True`). |
| 6 | MARS eval/tracking integration | ✅ PASS | `ml/eval/metrics.py::compute_metrics` → AUROC 0.7244 (matches KERMT's own `auc_val`), AUPRC 0.8457, Brier 0.1920, ECE 0.1395. `tracking.experiment.ExperimentRun` logs config/provenance/metrics cleanly. Calibration interface (`TemperatureScaler`) not exercised — needs raw logits, and `KermtModel.predict()` currently returns post-sigmoid probabilities only. |

Three real bugs were found and fixed in `ml/models/kermt_model.py` (not in KERMT itself) while getting here — see `decisions.md`'s 2026-09-18 "Smoke tests 1-6 PASSED" entry for the exact diffs: (1) JSON-stdout parsing choked on banner-prefixed pretty-printed JSON, (2) the wrapper let a regression-oriented default metric leak through for a classification run, (3) container-path strings from `run.json` were used directly as host paths. All three have regression tests now (`ml/tests/test_kermt_model.py`).

## 10. Known limitations

- **Mixed-type multi-task clusters unsupported by the stock CLI.** Still true of the *stock CLI* and always will be — but **no longer an open question for MARS as of 2026-09-20**: resolved by the three-tier ladder in `decisions.md`'s 2026-09-20 entry (stock KERMT on type-homogeneous subgroups; a MARS-owned mixed-type trainer importing KERMT as a library; ordinalized all-classification runs). Stock KERMT stays unforked and pinned. See `next_steps.md` for the live work breakdown.
- **CPU inference latency still unmeasured** (B-7/CF-8) — orthogonal to this GPU work.
- **Calibration interface (`TemperatureScaler`) not yet exercised** — `KermtModel.predict()` returns probabilities, not the raw pre-sigmoid logits `fit_temperature_scaler` expects. **Resolution chosen 2026-09-20:** `KermtModel.predict_logits()` returns `logit(p)` of the served two-view mean (clipped to ±12) — a well-defined monotone recalibration of exactly the quantity that serving emits, and precisely what `fit_temperature_scaler` needs. This unblocks temperature scaling for **every** KERMT classification run and does not depend on the mixed-type trainer. (The Tier-1 trainer additionally exposes true pre-sigmoid logits, since `KermtFinetuneTask.forward()` returns logits in training mode.)
- **No gradient-checkpointing, AMS/mixed-precision, or gradient-accumulation flag exists** in KERMT's finetune CLI — confirmed by grepping `kermt/util/parsing.py` for `fp16|bf16|amp|precision|accum|grad_checkpoint` (zero matches). The only VRAM lever is `--batch_size` itself.
- **Largest practical batch size not yet determined** — peak VRAM at batch_size=16 on this tiny run was ~1.5GB above baseline (of 16GB total), suggesting large headroom, but no larger-batch run has actually been tried yet (out of this session's scope per explicit instruction to stop after the tiny smoke fine-tune).
- **`ppb_binding` acquisition/test drift** and **DILIst augmentation needs an external, non-TDC file** — both real findings from re-acquiring M1 data this session, neither is a KERMT-integration blocker; see `decisions.md`.

## 10b. Calibration path (added 2026-09-21 — CPU-verified only)

`fit_temperature_scaler` previously had no production call site, so nothing in the KERMT
path calibrated. It is now wired: `ml/eval/cluster_calibration.py::calibrate_endpoints`,
called from `ml/train/train_kermt_cluster.py::train_one_seed`. Flow: calibration-split
logits (`KermtModel.predict_logits`) → `fit_temperature_scaler` → persist scaler +
diagnostics → untouched test logits → calibrated probabilities → raw **and** calibrated
test metrics. The test set never reaches the fitter (enforced by function signature and
mutation-tested).

| Aspect | State |
|---|---|
| Fit / isolation / persistence / diagnostics logic | ✅ 51 CPU tests pass (25 + 13 + 8 + 5) |
| Harness wiring (holdout, order of operations, artifacts) | ✅ tested with `StubKermt`, a labelled test double — **not KERMT** |
| Real-data dry run on `metabolism__cls`, `absorption_distribution__cls`, `metabolism__reg` | ✅ ran on the laptop with the stub — data flow and shapes only |
| **Real KERMT logits on the calibration and test sets** | ⬜ **never run** — GPU-gated |
| Whether a 241-molecule (CYP3A4) or 47-molecule (HIA, 1 negative) calibration set gives a usable temperature | ⬜ **not established** — depends on real logit separability |

The `predict_logits()` caveat in §10 still applies: it is `logit` of the two-view mean, not
either head's pre-sigmoid activation. `holdout_calibration=True` (default) removes the
calibration molecules from the training pool because KERMT selects epochs on the
validation fold — see `decisions.md` 2026-09-21.

## 11. Reproducing the smoke fine-tune

Real, executed command (not a template) — `prep_id=20260918T090433Z` is this session's actual processed-data snapshot:

```bash
export MARS_KERMT_REPO=~/mars-work/kermt-src
export MARS_KERMT_IMAGE=kermt:latest

cd ~/mars-work/mars-admet/ml
PYTHONPATH=. ../.venv/bin/python -c "
from pathlib import Path
import numpy as np
from data.loaders import load_endpoint
from data.split import five_seed_train_val_folds
from models.kermt_model import KermtModel, KermtConfig
from mars_contracts.endpoints import TaskType

ep = load_endpoint('data/processed/20260918T090433Z', 'ames_mutagenicity')
tv_smiles = ep.train_val['standardized_smiles'].tolist()
smiles_to_label = dict(zip(ep.train_val['standardized_smiles'], ep.train_val['label'].astype(float)))
_, train_smiles, val_smiles = five_seed_train_val_folds(tv_smiles, seeds=(0,))[0]
rng = np.random.default_rng(0)
train_sub = [train_smiles[i] for i in rng.choice(len(train_smiles), 300, replace=False)]
val_sub = [val_smiles[i] for i in rng.choice(len(val_smiles), 80, replace=False)]
y_train = np.array([smiles_to_label[s] for s in train_sub])
y_val = np.array([smiles_to_label[s] for s in val_sub])

ckpt = Path('data/checkpoints/kermt/NV-KERMT-70M-v2/kermt_contrastive_v2.0.pt')
m = KermtModel(TaskType.CLASSIFICATION, ckpt, ['ames_mutagenicity'],
               config=KermtConfig(epochs=3, batch_size=16))
m.fit(train_sub, y_train, X_val=val_sub, y_val=y_val, run_dir=Path('runs/kermt_smoke_ames'))
preds = m.predict(val_sub, run_dir=Path('runs/kermt_smoke_ames'))
"
```

Full training log: `ml/runs/kermt_smoke_ames/logs/finetune.log`. Finetuned checkpoint: `ml/runs/kermt_smoke_ames/ckpt/fold_0/model_0/model.pt` (not committed — gitignored `*.pt`).

## 12. RTX A4000 viability verdict

| Workload | Verdict | Basis |
|---|---|---|
| Inference (finetuned ckpt) | **Demonstrated** | Smoke 6: real `predict()` call on 80 real molecules, no NaNs, reload-consistent. |
| Single-task finetuning | **Demonstrated at small scale (300 mol, 3 epochs, batch 16)** | Real loss/AUC improvement across epochs; peak VRAM ~1.5GB above baseline — comfortable headroom on 16GB. **Not yet demonstrated at the endpoint's full scale** (5,802 train_val) or at larger batch sizes — no claim made either way beyond what was actually run. |
| Multi-task (same-type) finetuning | **Not yet demonstrated** | Wrapper supports it (`ffn_num_task_specific_layers`, KERMT's native `MTLLoss`), but no run attempted this session. |
| Multi-task (mixed-type, e.g. Metabolism) | **Blocked, not a VRAM question** | Stock CLI architectural limitation — see §10 / decisions.md. |

No claim of "full 14-endpoint training viable" is made — only what was actually run and measured above.
