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
