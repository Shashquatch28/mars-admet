# lab_session_tier1.md — Tier 1 (mixed-type trainer): gates, tuning, arms

_Written 2026-10-14, revised the same day. Companion to `lab_session_tasks.md` (Tier 0), whose preflight (P-1 … P-3), per-launch
banner and verify discipline (P-5, P-7) apply unchanged. Decision: `decisions.md` 2026-10-14. **Nothing here has been run on the
workstation.** Commands were checked against the code in this repo and against KERMT's source at the pinned tag; they were not
executed against the container. Where a step depends on something not established, it says so._

> **UPDATE 2026-10-19 — first workstation execution.** G4, G1 and G2 were run on `5084d71` (2026-10-15) and **pass**; the `toxicity__cls`
> half of G3 was run (5 mixed seeds, stock values) and **fails on both endpoints**. Nothing was tuned or changed. Results, commands, the
> per-seed table and the open question: `status/kermt_tier1_gates_session_2026-10-15.md`; records: `status/kermt_tier1_gates/`.
> Corrections found by running this runbook: a mixed run's files live under `<run>/artifacts/kermt/` (not `<run>/logs/`), run directories are
> named `kermt_mx_<cluster>_seed<N>_<mode>_<UTC>`, and `git dirty` is in `provenance.json`. The single-task `ames_mutagenicity` half of G3 was not run.

**Where the code is.** Tier-0 training stays on `milestone/m2-kermt`. The Tier-1/2 code is on `milestone/m2-kermt-tier1`; the lab
session that runs Tier 1 checks out *that* branch and pins its tip as `EXPECTED_SHA`. The Tier-0 guard (P-2) still holds there:
Tier 1 adds files and edits none of the protocol-critical list.

**What nothing in this runbook does:** pick a hyperparameter. Epochs, learning rates, the stratified-batch floor, GradNorm `alpha`
and its weight learning rate, the epoch-selection rule and Tier-2 `n_bins` have **no default** in the code; every one is either the
stock value *by explicit statement* (`hyperparameter_source="parity-gate"` or `"stock-default"`) or comes from a registered tuning
trial (`"tuning:<hash prefix>:<trial>"`). See "Why nothing is pre-set" at the end.

## 0. Plain-language map

| Name | What it is | Needs GPU? | Where defined |
|---|---|---|---|
| **G4** | The Kendall loss at log σ = 0 equals equal-weight × 1 (classification) / × 0.5 (regression), plus loss-reduction checks | no (seconds) | `selfcheck.py`, `test_kermt_mixed_losses.py` |
| **G1** | Same trained model, same 64 molecules: stock KERMT vs the MARS forward pass agree to 1e-5 | inference only | `gates.g1_forward_parity` |
| **G2** | One epoch, same fold and arguments: epoch-0 training loss within 5% of stock (`fixed` mode) | ~2 short runs | `gates.g2_loss_parity` |
| **G3** | 5 seeds, classification-only: validation AUROC mean and paired per-seed parity with stock | 10+ runs | `gates.g3_auroc_parity` |
| **T2 gate** | Tier 2 only: decoded regression MAE within a tolerance of a direct-regression MAE | with Tier 2 | `train_kermt_ordinal.t2_decoded_mae_gate` |

`glossary.md` has the full definitions. **Order is G4 → G1 → G2 → G3**: each is cheaper than the next and isolates a different
thing; if an early one fails the later ones are not worth their GPU time.

## 0.5 Session variables used by the snippets below

`lab_env.sh` exports `MARS_REPO`, `PREP_ID`, `PY`, `LAB`, `LOGS`, `WANDB_ENTITY`, `WANDB_PROJECT`, `MARS_KERMT_REPO`,
`MARS_KERMT_IMAGE` and `PYTHONPATH=.` (so Python snippets run from `$MARS_REPO/ml`). It does **not** export `PREP`, `CKPT`, `W`,
`RUNS` or `MODEL_DIR`; the Python snippets assume this preamble:

```python
import os
from pathlib import Path
PREP = Path("data/processed") / os.environ["PREP_ID"]
CKPT = Path("data/checkpoints/kermt/NV-KERMT-70M-v2/kermt_contrastive_v2.0.pt")
RUNS = Path("runs")
W = RUNS / "tier1_gates"; W.mkdir(parents=True, exist_ok=True)
# Tier-0 toxicity__cls seed-0 model, as saved by KermtModel.save (model.pt + metadata.json):
_c = sorted(RUNS.glob("kermt_mtsub_toxicity__cls_seed0_*/artifacts/model/kermt"))
MODEL_DIR = _c[-1]   # if the list is empty, download kermt-toxicity-cls-seed0:v0 from W&B instead and point MODEL_DIR at it
```

## 1. Preconditions — do not start before all hold

1. **Tier 0 is complete** (30 of 30 seeds; `toxicity__cls` 5/5 with its aggregate), records committed.
2. A fresh `EXPECTED_SHA` for the tip of `milestone/m2-kermt-tier1`; `kermt:latest` image id and checkpoint sha256 unchanged. A changed
   image invalidates comparability with every Tier-0 number, which is the point of G3.
3. The host-Python test suite passes there (the torch tests *skip*: no torch on the host; expected).
4. For §5 onward: **the maintainer has answered the open items in `decisions.md` 2026-10-14** (trials, seeds, axes, objective,
   threshold, whether Tier 0 is tuned) and the protocols are registered. §2–§4 (the parity gates) do not need that: they run at stock
   values by design.

## 2. Gate G4 — in the container, about a minute, no GPU

```bash
cd "$MARS_REPO/ml" && PYTHONPATH=. $PY - <<'PY'
from pathlib import Path
from models.kermt_mixed_model import stage_trainer
stage_trainer(Path("/tmp/mars_stage"))
PY
"$MARS_KERMT_REPO/agent/scripts/kermt_container.sh" run --data /tmp/mars_stage -- \
  "PYTHONPATH=/data python -m kermt_mixed.selfcheck"
```

Expect `"ok": true` and six checks true, including `G4_kendall_at_zero_is_1_per_cls_and_half_per_reg`. **STOP** otherwise.
The full suite (`pytest ml/tests/test_kermt_mixed_*.py`) is the authority and needs torch.

## 3. Gate G1 — forward / inference parity (about 2 minutes)

Uses the Tier-0 `toxicity__cls` seed-0 model (W&B `kermt-toxicity-cls-seed0:v0`; download `model.pt` and `metadata.json` into
`$MODEL_DIR`). A stock classification checkpoint carries no data scaler; the mixed predict path accepts that for an
all-classification spec.

```python
# from $MARS_REPO/ml with PYTHONPATH=. ; PREP, CKPT, W, MODEL_DIR from §0.5
from configs.clusters import type_homogeneous_subgroups
from data.cluster_loaders import load_cluster
from mars_contracts.endpoints import TaskType
from models.kermt_model import KermtModel
from models.kermt_mixed_model import KermtMixedModel
from train.kermt_mixed import gates
from train.kermt_mixed.train_mixed import write_predictions_csv

keys = list(type_homogeneous_subgroups("toxicity")["toxicity__cls"].endpoints)
cd = load_cluster(PREP, keys, cluster_key="toxicity__cls")
smi = cd.smiles("test")[:64]                       # fixed: first 64 test molecules

stock = KermtModel.load(MODEL_DIR)
p_stock = stock.predict(smi, run_dir=W / "g1_stock")

mixed = KermtMixedModel.from_finetuned(            # inference only: no training settings involved
    MODEL_DIR / "model.pt", {k: TaskType.CLASSIFICATION for k in keys}, CKPT, work_dir=W / "g1_mixed")
p_mixed = mixed.predict(smi)

write_predictions_csv(W / "g1_stock.csv", smi, keys, p_stock)
write_predictions_csv(W / "g1_mixed.csv", smi, keys, p_mixed)
print(gates.g1_forward_parity(W / "g1_stock.csv", W / "g1_mixed.csv"))   # tolerance 1e-5
```

**Pass:** `passed=True`, max |Δ| ≤ 1e-5 over 64 molecules. **If it fails,** the usual suspects in order: feature handling (the
checkpoint was trained with `--features_path` / feature scaling); `check_checkpoint.py --mode inference` rejecting the path;
per-column sigmoid placement in `forward.combine_views`. Do not proceed to G2.

## 4. Gates G2 and G3 — stock values, parity only

Both are run at stock values; `hyperparameter_source="parity-gate"` says so in the record. Neither result is a Tier-1 finding.

### G2 — one-epoch loss parity (two short runs)

```python
from data.cluster_loaders import SMILES_COL
from data.split import five_seed_train_val_folds
from models.kermt_model import KermtConfig
from train.kermt_mixed.metrics_hooks import read_jsonl
from train.train_kermt_cluster import _label_lookup, _stack

pool, _ = cd.train_pool(holdout_calibration=True)
_, tr, va = five_seed_train_val_folds(pool[SMILES_COL].tolist(), seeds=(0,))[0]
lk = _label_lookup(pool)
ytr, yva = _stack(tr, lk), _stack(va, lk)
cfg = KermtConfig(epochs=1)

KermtModel(TaskType.CLASSIFICATION, CKPT, keys, seed=0, config=cfg).fit(
    tr, ytr, X_val=va, y_val=yva, run_dir=W / "g2_stock")
KermtMixedModel({k: TaskType.CLASSIFICATION for k in keys}, CKPT, seed=0, config=cfg,
                loss_mode="fixed", min_per_task=0, hyperparameter_source="parity-gate").fit(
    tr, ytr, X_val=va, y_val=yva, run_dir=W / "g2_mixed")

stock_log = (W / "g2_stock" / "logs" / "finetune.log").read_text()
mixed_ep0 = next(r for r in read_jsonl(W / "g2_mixed" / "logs" / "mixed_epochs.jsonl")
                 if r.get("event") == "epoch" and r["epoch"] == 0)["train_loss"]
print(gates.g2_loss_parity(stock_log, mixed_ep0))   # within 5%
```

A miss means a different *loss*, not noise: check `dist_coff` (both come from the same argv; KERMT's default is 0.15), the mask
(`None` vs NaN — `scaling.to_kermt_targets`) and the reduction.

### G3 — multi-seed AUROC parity (the expensive one)

Rule, frozen 2026-09-20: `|mean_A − mean_B| ≤ 0.5·max(std_A, std_B)` **and** paired per-seed `|ΔAUROC| ≤ 0.02` on ≥ 4 of 5 seeds;
validation-fold AUROC computed host-side for both paths. A = stock, B = mixed with `fixed`.

| Half | Stock side | Mixed side | Cost |
|---|---|---|---|
| `toxicity__cls` (hERG + AMES) | **already exists** — Tier-0 seeds 0–4 | 5 runs, `loss_mode="fixed"`, `min_per_task=0` | 5 × ≈ 95 min ≈ 8 h |
| `ames_mutagenicity` (single task) | 5 stock single-task runs — **not yet run** | 5 single-target mixed runs (no per-task heads, as stock) | 10 runs, not estimated |

```python
from configs.experiment_config import ExperimentConfig
from train.train_kermt_mixed import train_mixed_all_seeds

cd = load_cluster(PREP, keys, cluster_key="toxicity__cls")
cfg = ExperimentConfig("toxicity__cls", "kermt_mixed", 0, cd.prep_id, notes="G3 parity")
res = train_mixed_all_seeds(cd, cfg, checkpoint=CKPT, loss_mode="fixed", min_per_task=0,
                            hyperparameter_source="parity-gate", runs_dir=RUNS, use_wandb=True)
mixed_auc = {k: [r.per_endpoint_metrics[k].auroc for r in res] for k in keys}
```

The stock side is in each Tier-0 run's `metrics.jsonl` (`ml/runs/kermt_mtsub_toxicity__cls_seed<k>_*/`): lines with `"split": "val"`,
field `auroc`, one per endpoint. Apply `gates.g3_auroc_parity(stock_k, mixed_k)` **per endpoint**; both must pass. Run all five seeds
or none: one seed says nothing about G3.

## 5. Tuning — only after G1–G4 pass, and only under a registered protocol

Not a recommendation of values: a procedure. Everything numeric below is the maintainer's to set.

```python
from train.kermt_mixed.tuning import (Axis, Protocol, preregister, enumerate_trials, source_tag,
                                      split_trial_params, select, assert_equal_budget)

proto = Protocol(
    name=..., cluster="metabolism", arm="kendall",
    space=(Axis("epochs", "choice", values=(...)), Axis("max_lr", "loguniform", low=..., high=...), ...),
    reference={...},            # trial 0: the stock/neutral values; always run; reported beside the tuned result
    n_trials=..., sampling_seed=..., tuning_seeds=(..., ...),       # >= 2 seeds
    objective="val_selection_loss", lower_is_better=True,
    min_improvement_in_stds=..., notes=...,
)
digest = preregister(proto, "documentation/AIMS/tuning/<name>.json")   # sha256-locked; cannot be edited later
```

1. **One protocol per arm and cluster, equal budget** — `assert_equal_budget([...])` before any run. GradNorm has more parameters; it
   does not get more trials.
2. For each trial and tuning seed: `train_one_seed_mixed(..., calibrate=False, hyperparameter_source=source_tag(proto, trial_id),
   **mixed_kwargs, kermt_config=KermtConfig(**cfg_kwargs))` where `cfg_kwargs, mixed_kwargs = split_trial_params(trial.params)`.
   `calibrate=False` means the test split is never read.
3. `select(proto, {trial_id: [objective per tuning seed]})`. It refuses partial results and moves off the reference only when the gain
   exceeds the registered multiple of seed noise.
4. **Re-score without retraining.** Each run saved every epoch's validation views (`logs/val_views.npz`);
   `posthoc.epoch_predictions` + `per_epoch_task_scores` + `best_epoch` give the epoch any other rule would have chosen.
5. Cost: `n_trials × tuning seeds × 3 arms × 2 clusters` runs at about 1.1 GPU-h. **Compute this before registering**; at 6 × 2 it is
   about 79 GPU-h, more than the arms themselves.

## 6. The arms (after §5)

2 clusters × `fixed_task` / `kendall` / `gradnorm` × 5 seeds = 30 runs at the selected configuration, **and** the same at the reference
configuration (the like-for-like comparison with untuned Tier 0). `calibrate=True` here. Re-run `train/preflight_clusters.py` first:
the whole-cluster leakage fix is what costs labels (Metabolism 29.2%, A&D 16.1% as measured 2026-09-20).

```python
from configs.clusters import cluster_members
keys = cluster_members("metabolism")
cd = load_cluster(PREP, keys, cluster_key="metabolism")
cfg = ExperimentConfig("metabolism", "kermt_mixed", 0, cd.prep_id)
# cfg_kwargs / mixed_kwargs come from the selected trial of the registered protocol (or the reference)
train_one_seed_mixed(cd, cfg, 0, checkpoint=CKPT, loss_mode="kendall", min_per_task=mixed_kwargs["min_per_task"],
                     hyperparameter_source=source_tag(proto, chosen_trial), kermt_config=KermtConfig(**cfg_kwargs),
                     runs_dir=RUNS, use_wandb=True)
```

Order: one arm, one seed, verify, next (Tier-0 P-7 discipline); `metabolism` before `absorption_distribution`.

### Per-run checks (read `<run>/artifacts/kermt/logs/mixed_epochs.jsonl`; `trainer_provenance.json` is beside it in `<run>/artifacts/kermt/`)

| Check | Look for | If wrong |
|---|---|---|
| Stratification worked | `summary.batch_stats_epoch0.batches_with_zero_labels_per_task` all 0 when the floor > 0 | do not trust the run |
| No NaN | run completed (`FloatingPointError` would abort) | read the epoch and batch in the message |
| Kendall stability | `log_sigma` per epoch: no oscillation or divergence, especially Clearance and PPB | layered mitigation #3 is the next step — **a decision, not a flag** |
| Selection not at a boundary | `best_epoch` neither 0 nor the last | record either way; consider the epochs axis |
| GradNorm weights | positive, sum = T, not pinned at the 1e-4 floor | report |
| Identity | `trainer_provenance.json` sha256s equal the committed files; `hyperparameter_source` present | a mismatch is a different trainer |

## 7. Tier 2 — only if the budget remains

Decision rule (maintainer, 2026-10-14): **trained only if GPU time remains after Tier 1.** Compute the hours left first; Tier 2 is
`n_trials`-style cost again if tuned. If go: `train/preflight_clusters.py` already measured the discretization ceilings;
`train/train_kermt_ordinal.py::train_one_seed_ordinal(..., n_bins=<registered>, strategy=<registered>,
hyperparameter_source=...)`; then `t2_decoded_mae_gate(decoded, direct, rel_tol=..., aggregation=...)`. The comparator for "direct" and
the aggregation rule are open items in the decisions entry.

## 8. What is not built, and stop conditions

- **No Tier-1 W&B model/record uploader.** The Tier-0 helpers (`s_wandb_*.py`, P-9) are workstation scripts for the stock layout.
- **No regression reporting** beyond per-endpoint MAE (the Tier-0 open P1). **No automatic GPU/driver provenance** — record it in
  the session note.
- **GradNorm on the real network is untested**; its only test is a toy.
- **Stop:** any gate fails; a run needs a code change mid-sweep (record a decision first — same rule as Tier 0); the image or checkpoint
  hash changes; a protocol-critical file differs from `ae5d28d`; a protocol is edited after registration; a mixed result is about to
  be described without its arm and `hyperparameter_source`; **any** statement that a Tier-0 result was uncertainty-weighted.

## 9. Why nothing is pre-set

Every value an earlier draft of this plan "defaulted" came from somewhere other than MARS data: KERMT's stock `epochs = 30` is called
"a faster default" by its own config; GradNorm's published optimum is `alpha ≈ 1.5` on NYUv2 but `0.12` on its synthetic regression
task; the batch floor had no source at all. Epochs also lengthen KERMT's Noam learning-rate schedule, so "would 7 epochs do better?"
is a different training run, not an earlier stop — which is why it is a protocol axis and why the saved validation views, which
*can* answer the selection half of that question for free, are not a substitute for it. The tuning seeds are among the five reporting
seeds; that is acceptable because selection never reads the test split, but their validation numbers are optimistic and are not
reported as results.
