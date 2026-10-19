# KERMT Tier-1 equivalence-gates session — 2026-10-15 (workstation CL502-18)

Branch `milestone/m2-kermt-tier1`, `EXPECTED_SHA` `5084d71be12256d7d504d87b57816c6873a5c280` (maintainer-supplied; `HEAD`, remote tip and
`lab_env.sh` agreed; tree clean at every launch). Runbook: `AIMS/lab_session_tier1.md` §2–§4. Records: `kermt_tier1_gates/`.
Scope: gates G4 → G1 → G2 and the `toxicity__cls` half of G3, **at stock values**. No tuning, no Tier-1 arms, no Tier 2.

## Result in one paragraph

G4, G1 and G2 **pass**. The `toxicity__cls` half of G3 **fails on both endpoints**: hERG fails both rules (0/5 seeds within 0.02; mean
difference 0.043 vs band 0.041), AMES passes the paired rule (5/5) but fails the mean rule (0.0046 vs band 0.0018). Under the project rule
("no mixed-type result is believed until G1–G4 pass") the mixed trainer is **not yet certified equivalent to stock KERMT**, so no Tier-1 arm
result should be read. Nothing was changed or tuned in response. The cause is not established (see "What the failure does and does not say").

## Environment

| Item | Value |
|---|---|
| GPU / driver / kernel | RTX A4000 16 GB / 595.91.07 / Linux 7.0.0-38-generic |
| `kermt:latest` | `sha256:2918726c…d5d87d` — **identical to the Pass-1 / Tier-0 image** |
| Checkpoint sha256 | `e9e6649bc96503fbdb3023e312764ecbbbafd686d9a62865a1fec9466cea6be3` (5/5 `s_ckpt.py` PASS) |
| KERMT | `e402473376ace30fa0092dad0578a88bf7f67287`, `v2.0.0`, clean |
| Container torch | 2.9.1, CUDA available |
| Prep | `20260918T090433Z`; both `toxicity__cls` endpoints `A_BYTE_IDENTICAL` (overall `D` only because `dili_liver_injury__augmented` is absent: known, irrelevant) |
| Protocol guard (P-2) | `HEAD == EXPECTED_SHA`; descends from `ad6eaf1`; the 11 protocol files byte-identical to `ae5d28d` |
| Host tests | `58 passed, 4 skipped` (all four skips: no `torch` on the host Python, as expected) |

`ml/eval/metrics.py` (deliberately outside the guard) differs from `ae5d28d` only by the single-seed-std fix in `aggregate_seed_metrics` and a new
`format_mean_std`; `compute_metrics`, ECE and Brier are untouched (read by hand).

## Gates G4, G1, G2 — pass

| Gate | Result | Margin | Record |
|---|---|---|---|
| **G4** Kendall math | `"ok": true`, six checks true (`python -m kermt_mixed.selfcheck` in the container, trainer staged to `/tmp/mars_stage`) | — | `kermt_tier1_gates/g4_selfcheck.json` |
| **G1** forward parity | `passed=True`, max \|stock − mixed\| = **0** over 64 test molecules (both columns exactly 0.0) | tolerance 1e-5 | `g1_result.txt`, `scripts/g1_gate.py` |
| **G2** one-epoch loss | `passed=True`, stock 1.181015 vs mixed 1.176209, **0.41 %** | tolerance 5 % | `g2_result.txt`, `scripts/g2_gate.py` |

The G2 fold was `n_train=12787`, `n_val=1827`, equal to the Tier-0 records. This was the first execution of the Tier-1 trainer against the real
KERMT; none of the eight anticipated first-contact failure points fired.

## G3, `toxicity__cls` half — five mixed seeds at stock values

Mixed trainer: `loss_mode="fixed"`, `min_per_task=0`, `hyperparameter_source="parity-gate"`, `KermtConfig()`. Stock side: Tier-0
`toxicity__cls` seeds 0–4 (seed 4 = the completed `…101513Z`; the crashed `…094244Z` has no `metrics.jsonl` and is excluded).

| Seed | Run id (`kermt_mx_toxicity__cls_…_fixed_…`) | Launched (IST) | Wall | Peak VRAM | Best epoch (mixed) | Stock saved epoch | W&B model artifact |
|---:|---|---|---:|---:|---:|---:|---|
| 0 | `seed0_…20261015T070652Z` | 12:36 | 101.4 min | 3,842 MiB | 6 | 13 | `kermt-mixed-toxicity-seed0-parity-gate:v0` |
| 1 | `seed1_…20261015T084925Z` | 14:19 | 101.5 min | 3,818 MiB | 3 | 21 | `…seed1-parity-gate:v0` |
| 2 | `seed2_…20261015T103115Z` | 16:01 | 101.5 min | 3,950 MiB | 5 | 20 | `…seed2-parity-gate:v0` |
| 3 | `seed3_…20261015T121306Z` | 17:43 | 101.7 min | 3,796 MiB | 2 | 21 | `…seed3-parity-gate:v0` |
| 4 | `seed4_…20261015T135516Z` | 19:25 | 101.7 min | 3,786 MiB | 2 | 7 | `…seed4-parity-gate:v0` |

Wall = `run.json` `started_at` → `finished_at`. Per-run checks, all five: `run.json` `completed`; last `mixed_epochs.jsonl` line is the
`summary` event; all 11 `trainer_provenance.json` hashes equal the files; config `kermt_mixed` / `fixed` / 0 / `parity-gate` / prep
`20260918T090433Z` / `holdout_calibration` true / right seed / `git dirty` false; zero `FloatingPointError`; zero `UserWarning: W&B`.

Validation AUROC (host-side, from `metrics.jsonl`), mixed vs stock:

| Seed | hERG mixed | hERG stock | Δ | AMES mixed | AMES stock | Δ |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 0.9706 | 0.9118 | +0.059 | 0.8489 | 0.8532 | −0.004 |
| 1 | 0.7500 | 0.8438 | −0.094 | 0.8543 | 0.8509 | +0.003 |
| 2 | 0.9062 | 0.8750 | +0.031 | 0.8518 | 0.8576 | −0.006 |
| 3 | 0.8125 | 0.8750 | −0.063 | 0.8441 | 0.8580 | −0.014 |
| 4 | 0.7870 | 0.9352 | −0.148 | 0.8526 | 0.8547 | −0.002 |

`gates.g3_auroc_parity(stock, mixed)` per endpoint, verbatim (`kermt_tier1_gates/g3/g3_verdicts.json`):

```
herg_cardiotoxicity: GateResult(gate='G3', passed=False, summary='|mean diff| 0.0429 vs band 0.0406 (FAIL); paired |dAUROC| <= 0.02 on 0/5 seeds (FAIL)')
ames_mutagenicity:   GateResult(gate='G3', passed=False, summary='|mean diff| 0.0046 vs band 0.0018 (FAIL); paired |dAUROC| <= 0.02 on 5/5 seeds (ok)')
```

Both must pass; **G3 (`toxicity__cls` half) = FAIL.** The single-task `ames_mutagenicity` half was not run (no single-task stock harness exists in the repo).

### What the failure does and does not say

- **AMES is close, not matched, by the frozen rule.** All five paired differences are ≤ 0.014 and the mean differs by 0.0046 (mixed lower), but both
  paths are so tight (std 0.003–0.004) that the rule's band `0.5·max(std)` = 0.0018 is smaller than that difference. An earlier remark in this session that
  AMES looked on track was optimistic: it only held for the paired rule.
- **hERG is dominated by a tiny validation set** (18–24 labels per seed): with 6 positives and 18 negatives there are only 108 positive–negative pairs, so each re-ordered pair moves AUROC by 0.0093 (seed 4's 0.148 gap is exactly 16 pairs). The deltas change sign across seeds, so there is no consistent offset. The gate cannot tell "different trainer"
  from "hERG validation is too small to measure". This is the limitation recorded for Tier 0 and in the runbook arm table.
- **G1 and G2 rule out gross implementation errors** (identical forward pass; epoch-0 loss within 0.41 %). What G3 adds is the whole training trajectory.
- **A difference by design that G3 does not control: epoch selection.** Stock saves the epoch with the best validation AUROC; the mixed trainer saves
  the epoch with the lowest summed per-task validation loss on scaled targets (`decisions.md` 2026-10-14). The mixed runs selected epochs 2–6; stock saved
  epochs 7–21. This was tested post hoc, with no GPU, on 2026-10-19 (next section).

## Post-hoc diagnostic (2026-10-19, no GPU, validation fold only) — does not replace the official verdict

`scripts/g3_posthoc_rescore.py`: for each mixed run, re-pick the epoch from the saved per-epoch validation views by **stock's rule** (maximum over epochs of
the mean-over-tasks validation AUROC; ties → first epoch, as KERMT's strict `>`), then call `gates.g3_auroc_parity` again. Sanity check: at each run's own
epoch the script reproduces the run's recorded validation AUROC with **zero error on all 5 seeds × 2 endpoints**, so fold alignment and metric are right.

| Seed | Own epoch → stock-rule epoch | hERG own → stock-rule | AMES own → stock-rule |
|---:|---|---:|---:|
| 0 | 6 → 3 | 0.9706 → 1.0000 | 0.8489 → 0.8455 |
| 1 | 3 → 14 | 0.7500 → 0.8125 | 0.8543 → 0.8587 |
| 2 | 5 → 24 | 0.9062 → 0.9375 | 0.8518 → 0.8624 |
| 3 | 2 → 18 | 0.8125 → 0.9375 | 0.8441 → 0.8592 |
| 4 | 2 → 11 | 0.7870 → 0.9167 | 0.8526 → 0.8544 |

```
herg_cardiotoxicity: |mean diff| 0.0327 vs band 0.0305 (FAIL); paired |dAUROC| <= 0.02 on 1/5 seeds (FAIL)   passed=False
ames_mutagenicity:   |mean diff| 0.0012 vs band 0.0029 (ok);   paired |dAUROC| <= 0.02 on 5/5 seeds (ok)     passed=True
```

- **AMES: the whole gap was the selection rule.** Under stock's rule AMES passes both parts of G3 (mean difference 0.0012, 5/5 paired).
- **hERG: not explained by selection alone.** It improves (mean difference 0.043 → 0.033, paired 0/5 → 1/5) but still fails narrowly on the mean rule and clearly on the paired rule.
  Under stock's rule the mixed hERG AUROC now *exceeds* stock's in four of five seeds (mixed mean 0.921 vs stock 0.888), and one seed reaches 1.0 on 24 molecules.
  With 108 positive–negative pairs per fold and 30 candidate epochs to choose from, both paths are selecting the maximum of noisy validation scores, so
  agreement to 0.02 on hERG is not a realistic bar for this fold. Whether the remaining hERG difference is trainer behaviour or noise is **not established**.
- **Caveats.** (1) Diagnostic only: the official G3 result above stands, and the stock-rule epoch's model weights were not saved (only the mixed trainer's own best epoch was), so
  this says what the validation AUROC would have been, not that a usable model exists. (2) Selection and scoring both use the validation fold, as stock's own numbers do. (3) The test set was not read.
  (4) Re-picking among saved epochs is not the same as training with a different epoch count (KERMT's learning-rate schedule depends on the total epochs).

## Deviations, incidents and corrections (all reported, none hidden)

1. **False STOP after seed 0 (my driver bug).** The overnight driver looked for `mixed_epochs.jsonl` / `trainer_provenance.json` under `logs/` and the run
   root; they are under `artifacts/kermt/`. The run itself was healthy. I re-ran every per-run check by hand against the real paths (all passed), fixed the two paths in
   my gitignored script, set the STOP file aside (`g3/g3_STOP_seed0_driverpathbug_20261015.txt`, not deleted) and resumed. The runbook's "kill the job and
   STOP" rule is for a *run* failing a check; I judged a tooling path error not to be that, and said so at the time. Seed 0's wall time is therefore from `run.json`, not the driver.
2. **First driver also never matched run directories** (it filtered on `mixed`; they are `kermt_mx_…`). Caught at minute four; fixed; seed 0 training was not interrupted
   (the fixed driver adopted the running process).
3. **Seed-4 process lingered ~3.6 days after finishing.** Training ended 2026-10-15 21:06 IST (`run.json` `completed`, result printed, 30 epochs, all checks pass), but the
   Python process did not exit until 2026-10-19 11:19 IST, so the driver logged `wall_s: 316445.9` and "DONE" only then. The log has no error. **The
   `wall_s` in `g3/g3_state.json` for seed 4 is wrong; use the 101.7 min above.** Cause not established. Seeds 0–3 exited normally.
4. **Uploader written against the runbook's "do not write one".** Maintainer instruction in-session overrode it. `scripts/g3_upload.py` follows the Tier-0 convention
   (type `model`, `model.pt` + `metadata.json`, aliases `final`/`latest`, logged by resuming the training run) plus a `run-record` artifact, under the
   names `kermt-mixed-toxicity-seed<N>-parity-gate` so nothing collides with Tier-0 `kermt-toxicity-seed<N>`. All five verified from W&B (`COMMITTED`, exact files, aliases, full-download SHA
   equals local). It is **not** a verified Tier-1 helper in the sense the runbook means; treat it as session tooling.
5. **Per-seed driver instead of `train_mixed_all_seeds`**, per the task document ("one seed per launch"); `scripts/g3_seed.py` is the document's script verbatim.
6. `~/mars-work/lab_env.sh` `EXPECTED_SHA` replaced (one occurrence); backup `lab_env.sh.bak_20261014`.
7. Git: the only repository mutation during the sweep was the authorised fetch and branch switch. The Tier-0 records were committed separately, in a worktree on
   `milestone/m2-kermt`, so this checkout's `HEAD` never moved during the sweep. This note and `kermt_tier1_gates/` were committed after the sweep ended.

## Not done

- `ames_mutagenicity` single-task G3 half; tuning; the 30 Tier-1 arm runs; Tier 2. No hyperparameter was chosen by this session.
- No Tier-1 result should be reported until the maintainer decides what the G3 outcome means.

## Questions for the maintainer

1. Should G3 hold epoch selection fixed? The post-hoc result above says that alone brings AMES inside the frozen rule. If yes, which rule, and does the mixed trainer's selection
   (or the saved-views mechanism) change so that G3 compares like with like?
2. hERG validation has 18–24 labels. Should G3's hERG verdict use a pooled or test-based comparison instead, or is hERG excluded from the rule? (Changing the rule needs a `decisions.md` entry first.)
3. Should the AMES band be reconsidered? With std ≈ 0.003 the frozen `0.5·max(std)` band is tighter than the paired tolerance by an order of magnitude.

## Artefacts

`kermt_tier1_gates/`: `g4_selfcheck.json`, `g1_result.txt`, `g2_result.txt`, `g3/g3_verdicts.json`, `g3/g3_state.json`, `g3/seed{0..4}/` (`config.json`, `run.json`, `provenance.json`,
`metrics.jsonl`, `trainer_provenance.json`, `mixed_epochs.jsonl`, `model_metadata.json`, `wandb_artifact.json`), `scripts/`. Model weights are in W&B, not git.

## Fold audit, selection-free parity and selection diagnostics (2026-10-19, CPU + inference only)

Scope: no gate re-run, `gates.py` and the frozen G3 rule untouched, nothing trained, test set and `test_result.csv` not read.
Scripts `ml/eval/{fold_audit,selection_free_parity,selection_diagnostics}.py`; results under
`documentation/status/kermt_tier1_gates/diagnostics/`. A replacement-rule **draft** (not adopted) is the top entry of
`documentation/AIMS/decisions.md`.

### Result: scoring the deployed checkpoints on the calibration holdouts

Paired ΔAUROC (mixed − stock), molecule-level paired bootstrap, 90 % interval, 4,000 resamples, fixed RNG, five seeds, margin ±0.02.

| endpoint (n; pos/neg) | stock | mixed | pooled Δ | 90 % interval | inside ±0.02 |
|---|---|---|---|---|---|
| AMES (576; 392/184) | 0.8218 | 0.8228 | +0.0010 | [−0.0076, +0.0100] | yes |
| hERG (1,050; 616/434) | 0.8565 | 0.8371 | −0.0194 | [−0.0292, −0.0098] | **no** |

Per seed Δ (interval): AMES −0.013, +0.010, +0.017, +0.026, −0.034 (none of the five intervals is inside ±0.02; signs are mixed, so
this is seed noise, not a shift). hERG −0.007, −0.011, −0.006, −0.044, −0.030 (seeds 3 and 4 are outside; every seed is negative).

- **AMES: equivalent within ±0.02 pooled (verified).** Per-seed it cannot be shown: 576 molecules give per-seed intervals about ±0.012 wide.
- **hERG: a real gap of about −0.02 on the deployed checkpoints (verified); its cause is not established.** The gap is concentrated in
  seeds 3 and 4, whose mixed checkpoints are the epoch-2 ones (stock saved epochs 21 and 7). Ordered by the mixed epoch (2, 2, 3, 5, 6) the
  hERG deltas are −0.044, −0.030, −0.011, −0.006, −0.007: nearly monotone, which points at early-epoch selection (inferred; n = 5, no
  weights at other epochs were saved, so it cannot be tested without training). Mixed hERG seed SD on the holdout is 0.0148 vs 0.0027 for stock.
- Not a finding about the four components. The interval conditions on these 10 trained models and excludes training-seed variance.
- Provenance verified: `holdout_calibration=True` in all 10 configs; 0 of the 1,626 calibration molecules in any of the 20 `train.csv`/`val.csv`
  files; train/val equal the recomputed `five_seed_train_val_folds` folds in both arms. The mixed trainer's `test_placeholder.csv` is a copy of `val.csv`.
- Host-side AUROC equals a rank-based reimplementation to 1e-9. The mixed checkpoints were scored by the mixed code path, stock by the
  stock path (G1 showed the two paths agree to 1e-5 on 64 molecules).
- Single-task AMES half of G3: **not run**; no 5-seed stock single-task AMES and no mixed single-task AMES run exist (only a stock smoke run).

### Step 0: facts re-checked on the runs' prep `20260918T090433Z` (all reproduce)

Pool 14,614; validation 1,827 for every seed; hERG validation (molecules/positives/pairs) 19/2/34, 18/2/32, 18/2/32, 18/2/32, 24/6/108;
AMES 1809/953, 1810/958, 1810/960, 1810/956, 1804/953; Jaccard 0.973-0.990; 1,802 molecules in all five folds; hERG labelled in pool 9,437 (19 in
validation, 0.2 %), AMES 5,212 (1,809, 34.7 %); smallest AUROC step 1/34 or 1/32 on seeds 0-3. Stock selection (verified in `task/train.py`
at e402473): keeps the epoch with the highest `np.nanmean` of per-task validation AUROC unless `select_by_loss`; the Tier-0 args show
`select_by_loss=False`; the saved epoch equals the first argmax of the logged mean AUROC on all five seeds. The mixed trainer selects on the summed per-task validation loss.

### Step 1: fold audit, all four multitask subgroups (`fold_audit.json`)

Flagged (a classification task with < 70 positives or < 70 negatives in the validation fold, every seed):
`toxicity__cls` hERG (2-6 positives); `absorption_distribution__cls` HIA (41 pos / 5 neg), P-gp (67 / 26-27), BBB (147 / 26-27).
`metabolism__cls` (CYP3A4/2D6/2C9, ≥ 176 positives and ≥ 400 negatives) and AMES are not flagged. Regression validation n: 125-761
(solubility), 433-451 (lipophilicity), 125-138 (Caco-2), 42-50 (PPB). Cross-seed Jaccard: toxicity 0.973-0.990, absorption cls 0.994,
absorption reg 0.915-0.955, metabolism 0.899-0.939. The same fold design therefore also governs the Tier-0 absorption results; a
caveat on any validation-selected number for those tasks (not re-analysed here).

### Step 3: selection diagnostics (`selection_diagnostics.json`)

- Picks (epochs, seeds 0-4): stock rule on stock runs 13, 21, 20, 21, 7 (range 7-21, SD 5.6); mixed own rule 6, 3, 5, 2, 2 (range 2-6); stock rule applied to
  the mixed trajectories 3, 14, 24, 18, 11 (range 3-24); AMES-only argmax on the mixed trajectories 20, 24, 24, 11, 4.
- hERG carries 97-100 % of the epoch-to-epoch variance of the task-mean AUROC (covariance share, epochs ≥ 5: 0.995, 0.979, 0.995, 1.004, 0.970; first
  differences 0.97-1.01). Measured on the mixed trajectories. The stock log has only the task-mean AUROC (`show_individual_scores=False`), so for stock
  this is inferred: its task-mean SD over epochs ≥ 5 (0.029-0.045) is as large as the mixed one (0.022-0.038), where hERG's SD is 0.04-0.08 against 0.002-0.004 for AMES.
- Mean AUROC range over the 30 epochs is 0.69-0.90 for stock; AMES alone moves 0.83-0.865. Mixed AMES at its own epoch is 0.844-0.854, at epoch 29 0.855-0.862.
- Stock's `loss_val` (0.36-0.37 at epoch 0) and the mixed `val_selection_loss` (1.92 at epoch 0) are different quantities (training-mode two-view sum vs mean of
  per-task fused loss, inferred from the values); the two loss curves are not comparable as they stand. Stock's validation loss is lowest at epochs 27, 26, 28, 22, 26,
  the mixed one at 6, 3, 5, 2, 2: the rules disagree because the mixed validation loss bottoms out early (inferred: AMES AUROC is still rising at epoch 29).

### Side finding: CLI `--dist_coff`, `--dropout`, `--bond_drop_rate` do not reach the loss

`load_checkpoint(..., current_args=args)` overwrites `args` with the pretrain checkpoint's values for every name in `get_model_args()`, which includes
`dist_coff`, `dropout`, `bond_drop_rate`, `weight_decay`, `select_by_loss` (`kermt/util/utils.py`). The stock log prints `dist_coff=0.15` (the CLI value, before
the overwrite) while the mixed trainer's own log records `dist_coff = 0.1` (after it). Both arms load the checkpoint before building the loss, so both use the same
effective value; this is **not** a parity difference (stock side inferred from the source, mixed side measured). It does matter for tuning: a Tier-1 sweep over any
of those flags would silently change nothing unless the overwrite is accounted for. I did not open the checkpoint to read its saved values (no torch on the host).

### What failed to reproduce / what is missing

- Failed to reproduce: nothing in Step 0.
- Missing: the single-task AMES half of G3 (both arms); per-task per-epoch AUROC of stock runs; weights at any epoch other than each arm's saved one; a same-seed
  stock-vs-stock replicate (so δ could not be derived from replicate spread); the second, crashed stock seed-4 directory is excluded, as before.

### Proposal for approval (not done): extend G2 beyond epoch 0 if the hERG gap is to be attributed

G2 compares only the epoch-0 mean training loss (0.41 % apart), which cannot see per-task weighting, per-view behaviour or batch composition. If you want the
hERG gap traced to the trainer, check the four re-implemented components in this order, cheapest first, each on one fixed batch before any run:

1. **Loss** (`train/kermt_mixed/losses.py` vs `KermtFinetuneTask.get_loss_func`): feed identical logits/targets/masks (including partially masked rows) to both and compare
   per-element and reduced values; tolerance 1e-6. Includes the `dist_coff` term at the effective 0.1.
2. **Two-view forward**: same weights, same batch, training mode with identical RNG for dropout and bond-drop; compare atom/bond logits (G1 covers eval mode only).
3. **Per-column target scaling**: for classification columns the scaler must be the identity (logged means 0, std 1); compare with KERMT's scaler on a regression cluster, where it matters.
4. **Batch composition**: compare the sampler's batches with stock's (order, size, labels per task per batch, epoch seed) over a full epoch; the mixed epoch-0 log shows labels per batch of 16-… for hERG (mean 23.5) and 2-… for AMES (mean 8.5) out of 32, no batch with zero labels.
Then, if 1-4 agree, a G2b trajectory check (option 5 in the draft): per-epoch train loss and AMES validation AUROC for stock and mixed against a stock replicate. Steps 1-4 need
no training; G2b needs GPU time and your approval.

## Phase A (2026-10-19): G2 extension on one fixed batch, and the checkpoint-args overwrite (no training)

Scripts `ml/eval/g2_extension{,_host,_a2_all}.py` (run inside the KERMT container on the RTX A4000; stock and mixed paths on mixed-run seed 3's staged inputs;
that run's `clean_test.csv` was verified byte-identical to `clean_val.csv`, so no test data was used). Results `diagnostics/g2_extension.json`,
`a2_all_model_args.json`, `lr_trace_first3_epochs.npy`. Gates, `gates.py`, the trainer and all existing runs untouched.

| # | Check | Tolerance | Max abs / rel difference | Result |
|---|---|---|---|---|
| 1 | Loss, mode `fixed`, effective `dist_coff` 0.1: totals, per-element values and gradients w.r.t. both views' logits; 4 cases (random mask, dense mask, one task empty, real train-mode batch) | 1e-6 | 0.0 / 0.0 in all four | match |
| 1b | Mask conventions: collator-style (0-filled targets + mask) and NaN-filled targets with the same mask | 1e-6 | 0.0 / 0.0 both | match |
| 1c | Data layer: collator mask vs label matrix over the whole train (12,787) and val (1,827) folds; NaN floats among KERMT targets | exact | 0 mismatches; no NaN floats | match |
| 2 | Two-view forward in TRAINING mode, identical RNG (dropout p = 0.1 active, `model.training` True) | 1e-5 | atom 0.0, bond 0.0; control (other seed) differs by 1.23 | match |
| 3 | Scaling: fitted means 0,0 / stds 1,1; transform is the identity on train and val labels; inverse identity on probabilities; saved checkpoint `data_scaler` = (0,0)/(1,1) | exact | identity | match |
| 4 | Batches, 5 epochs, seed 0: coverage, sizes, last batch | exact | each row exactly once; 400 batches; 399 × 32 + 19 in both; labels/batch mean 23.55 (hERG) and 8.51 (AMES) in both; no batch without labels | match |
| 4b | Molecule order | — | **not identical** (0 % of positions equal in epoch 0) | differs, by construction |
| 5 | LR per step, first 3 epochs (1,200 steps), both stepping rules built from the same args | exact | 0.0; and the stock-printed `cur_lr` equals the mixed `lr` to 5 decimals on all 30 epochs × 5 seeds | match |

- **Check 4b is the only difference, and it is a different RNG, not a different design.** Stock draws the permutation from the global torch RNG (one stream across
  epochs, continuing from model initialisation); the mixed trainer uses `default_rng([seed, epoch])`. The sampler docstring's claim "exactly what `DataLoader(shuffle=True)`
  does" is true in distribution, not bitwise. Coverage, sizes, last-batch handling and per-batch label counts match; I treated this as not a divergence (it is the case your
  instruction anticipated) and report it so you can overrule that.
- **Check 5:** the schedule has no warmup in effect: `init_lr = max_lr = 1e-4`, so the rate is flat through epoch 0 and then decays (1.0e-4 → 9.996e-5 at epoch 1,
  9.436e-5 at epoch 2, 2e-5 at epoch 29). `NoamLR` counts `train_data_size // batch_size` = 399 steps per epoch against 400 real batches, identically in both arms. The
  saved mixed epochs 2-6 are therefore not "near the end of a warmup"; that hypothesis is excluded.
- **What these checks do not cover:** the effect of the different data order on training, the fit loop's accumulation of state across steps (optimizer state, scheduler stepping
  inside real training), and the validation-selection rule. They show the four re-implemented components are the same computation on a fixed batch, not that a full run is equivalent.

### A2: the checkpoint-args overwrite (verified, inside the container)

`NV-KERMT-70M-v2` saves `dist_coff` 0.1, `dropout` 0.1, `bond_drop_rate` 0, `weight_decay` 1e-7. The dry-run argv has 0.15, 0.0, 0.1, 0.0. After `load_checkpoint(..., current_args=args)`
the values in force are the checkpoint's: `dist_coff` 0.1, `dropout` 0.1 (the built model's `nn.Dropout` modules have p = 0.1), `bond_drop_rate` 0, `weight_decay` 1e-7 (both optimizer
groups). Of the 30 names in `get_model_args()`, six change: those four plus `backbone` and `num_tasks` (not hyperparameters). `ffn_hidden_size`, `ffn_num_layers`, `hidden_size`, `depth`
are not saved in the checkpoint and are **not** overwritten.

Both paths end with those values: the stock path (`task/train.py`) and the mixed path (`train_mixed.py`) each call `load_checkpoint(path, current_args=args)` before building the
loss, optimizer and collator; the mixed log records `dist_coff` 0.1; the stock log prints the pre-overwrite argv values (`dist_coff=0.15, dropout=0.0, bond_drop_rate=0.1`). So every
Tier-0 and G3 run trained with dropout 0.1, bond-drop 0, weight decay 1e-7, `dist_coff` 0.1 whatever the records say. Consequences: (1) the Tier-0 records and session notes that list
dropout 0.0 / bond-drop 0.1 / dist-coff 0.15 as "applied" are wrong about the effective values; (2) `decisions.md` 2026-10-14 says the earlier `dist_coff = 0.1` default "was also wrong
against KERMT's 0.15", but 0.1 is the value actually in force; (3) a tuning trial that sets any of the four changes nothing.

Places that treat the four as tunable or as 0.0/0.1/0.15 facts (none edited; proposed edits below):

| Place | What it says | Proposed edit |
|---|---|---|
| `ml/train/kermt_mixed/tuning.py:66-69` `KERMT_CONFIG_PARAMS` | allows `dropout`, `bond_drop_rate`, `dist_coff` as trial parameters (`weight_decay` is not listed) | remove those three, or make `Protocol` raise a `ProtocolError` naming the overwrite; add a test. (Alternatively implement a post-`load_checkpoint` override, a design choice for you.) |
| `documentation/AIMS/decisions.md:131-132` settings table | `dropout`, `bond_drop_rate` "protocol axes"; `dist_coff` "from the stock argv (KERMT default 0.15) … optional axis" | state the effective values (0.1 / 0.1 / 0 / 1e-7), that the CLI flags are inert, and that these four are not axes unless an override is built |
| `decisions.md:179` | "`dist_coff = 0.1` … was also wrong against KERMT's 0.15" | correct: 0.1 is the effective value |
| `decisions.md:204` | stock zeroes `bond_drop_rate` after the first validation pass | add: it is already 0 from `load_checkpoint`, so the zeroing is a no-op |
| `documentation/AIMS/lab_session_tier1.md:146` | "check `dist_coff` (… KERMT's default is 0.15)" | 0.1 effective; and §5 (axes) a one-line warning |
| `documentation/AIMS/lab_session_tasks.md:163` | "dropout 0.0, bond-drop 0.1, dist-coff 0.15" listed as KERMT defaults | add "CLI defaults; overwritten by the checkpoint's 0.1 / 0 / 0.1 at load" |
| `documentation/status/kermt_integration_status.md:63`, `kermt_gpu_session_2026-09-22/24/30.md`, Tier-0 `artifact_metadata.json` (`cmd_replay` values) | record the CLI values as applied | add a dated correction note (do not rewrite the records) |
| `ml/models/kermt_model.py:200-202`, `kermt_mixed_model.py:262-264` | `KermtConfig.dropout/bond_drop_rate/dist_coff` become CLI flags | docstring: inert at present |
| `train_mixed.py` start event | logs `dist_coff` only | also log the effective `dropout`, `bond_drop_rate`, `weight_decay` |
