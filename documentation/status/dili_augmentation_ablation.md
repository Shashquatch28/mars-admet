# DILI: augmented pool against TDC-only (Module 11 section 6)

Generated 2026-10-25 by `ml/eval/dili_augmentation_ablation.py` on snapshot `20260830T200000Z`. Same 96 test molecules for both models, raw scores, five seeds each. The TDC-only models were retrained for this comparison with the unchanged protocol (scratch directories; nothing promoted or overwritten); the augmented models are the promoted production ones. **This is a comparison of numbers, not a ranking.**

| metric (test, mean ± std over 5 seeds) | TDC-only (378 molecules) | augmented (1119 molecules) | augmented minus TDC-only |
|---|---|---|---|
| AUROC | 0.909 ± 0.009 | 0.898 ± 0.022 | -0.010 |
| AUPRC | 0.899 ± 0.008 | 0.889 ± 0.025 | -0.010 |
| Brier | 0.124 ± 0.006 | 0.212 ± 0.013 | +0.088 |
| ECE | 0.106 ± 0.013 | 0.239 ± 0.025 | +0.133 |

## Paired bootstrap of the AUROC difference (five-seed mean score of each model)

Augmented minus TDC-only on the same molecules; 95 % percentile interval over resampled test molecules (4000 resamples, those with a single class skipped).

| test molecules | n | TDC-only AUROC | augmented AUROC | difference [95 % interval] |
|---|---|---|---|---|
| all | 96 | 0.912 | 0.923 | +0.011 [-0.059, +0.082] (4000 resamples) |
| share no scaffold with the augmented pool | 71 | 0.919 | 0.948 | +0.029 [-0.045, +0.105] (4000 resamples) |
| share a scaffold with the augmented pool | 25 | 0.883 | 0.890 | +0.006 [-0.167, +0.180] (4000 resamples) |

## Reading it

- On all test molecules the paired interval contains zero: these 96 molecules cannot separate the two pools.
- The per-seed means and the five-seed ensemble differ by 0.022 in the AUROC difference and can even differ in sign. Both are inside the noise of 96 molecules; the paired interval is the figure to read.
- **Calibration quality moves much more than ranking.** Positive rate: TDC-only pool 0.49, augmented pool 0.63, test set 0.52. Brier and ECE are computed on raw scores, so a model whose training pool has a different positive rate from the test set can report scores shifted by that difference even when it ranks molecules equally well. A gap in Brier and ECE with no gap in AUROC is consistent with that; this comparison does not isolate it (the pools also differ in label source and size), so it is a reading, not a finding.
- The augmented pool shares 19 scaffolds with the test set (`self_audit.md`). The two subset rows are a leakage diagnostic: a gap that appears only on the molecules sharing a scaffold would point at the overlap. With 71 and 25 molecules each interval is wide.
- The pools differ in size and in the molecules the early-stopping folds see, so the difference is the augmentation plus those side effects. DILI labels from DILIst and from the TDC set are curated differently; the augmented labels were merged by majority vote (`augmentation_report.json`).
- No hyperparameter was tuned for either model.
