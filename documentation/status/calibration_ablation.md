# Calibration method on the XGBoost classifiers (Module 11 section 6)

Generated 2026-10-25 by `ml/eval/calibration_ablation.py` on snapshot `20260830T200000Z`. Each calibrator is fitted on a seed model's predictions for the calibration split and scored on the untouched test split; mean ± sample std over the five seeds. Lower Brier and lower ECE are the metrics' own convention. **This is a table of numbers on one test set, not a ranking of methods**, and no method turns a score into a validated probability.

## Brier score, per-seed models

| endpoint | calibration n (positives) | raw | Platt | temperature | isotonic |
|---|---|---|---|---|---|
| ames_mutagenicity | 580 (392) | 0.149 ± 0.003 | 0.157 ± 0.005 | 0.150 ± 0.003 | 0.159 ± 0.005 |
| bbb_permeability | 157 (120) | 0.104 ± 0.006 | 0.136 ± 0.006 | 0.105 ± 0.006 | 0.104 ± 0.004 |
| cyp2c9_inhibition | 964 (138) | 0.117 ± 0.000 | 0.122 ± 0.001 | 0.118 ± 0.001 | 0.122 ± 0.002 |
| cyp2d6_inhibition | 1047 (152) | 0.086 ± 0.001 | 0.089 ± 0.001 | 0.087 ± 0.001 | 0.089 ± 0.002 |
| cyp3a4_inhibition | 983 (111) | 0.127 ± 0.001 | 0.129 ± 0.001 | 0.127 ± 0.001 | 0.132 ± 0.003 |
| dili_liver_injury | 112 (61) | 0.212 ± 0.013 | 0.231 ± 0.007 | 0.215 ± 0.010 | 0.158 ± 0.005 |
| herg_cardiotoxicity | 1051 (617) | 0.147 ± 0.004 | 0.150 ± 0.003 | 0.149 ± 0.004 | 0.149 ± 0.003 |
| hia_absorption | 50 (49) | 0.041 ± 0.001 | 0.219 ± 0.001 | 0.041 ± 0.002 | 0.040 ± 0.003 |
| pgp_inhibition | 97 (36) | 0.132 ± 0.003 | 0.136 ± 0.002 | 0.133 ± 0.003 | 0.181 ± 0.014 |

## ECE (10 equal-width bins), per-seed models

| endpoint | calibration n (positives) | raw | Platt | temperature | isotonic |
|---|---|---|---|---|---|
| ames_mutagenicity | 580 (392) | 0.031 ± 0.004 | 0.079 ± 0.012 | 0.033 ± 0.002 | 0.059 ± 0.013 |
| bbb_permeability | 157 (120) | 0.120 ± 0.006 | 0.158 ± 0.009 | 0.121 ± 0.008 | 0.083 ± 0.009 |
| cyp2c9_inhibition | 964 (138) | 0.018 ± 0.003 | 0.039 ± 0.003 | 0.029 ± 0.002 | 0.050 ± 0.007 |
| cyp2d6_inhibition | 1047 (152) | 0.017 ± 0.003 | 0.025 ± 0.001 | 0.020 ± 0.002 | 0.034 ± 0.010 |
| cyp3a4_inhibition | 983 (111) | 0.020 ± 0.004 | 0.048 ± 0.003 | 0.028 ± 0.003 | 0.041 ± 0.006 |
| dili_liver_injury | 112 (61) | 0.239 ± 0.025 | 0.061 ± 0.047 | 0.246 ± 0.011 | 0.157 ± 0.076 |
| herg_cardiotoxicity | 1051 (617) | 0.057 ± 0.011 | 0.072 ± 0.007 | 0.080 ± 0.005 | 0.067 ± 0.007 |
| hia_absorption | 50 (49) | 0.049 ± 0.004 | 0.209 ± 0.000 | 0.046 ± 0.005 | 0.046 ± 0.009 |
| pgp_inhibition | 97 (36) | 0.085 ± 0.017 | 0.107 ± 0.016 | 0.079 ± 0.009 | 0.166 ± 0.015 |

## AUROC, per-seed models

| endpoint | calibration n (positives) | raw | Platt | temperature | isotonic |
|---|---|---|---|---|---|
| ames_mutagenicity | 580 (392) | 0.858 ± 0.005 | 0.858 ± 0.005 | 0.858 ± 0.005 | 0.851 ± 0.007 |
| bbb_permeability | 157 (120) | 0.901 ± 0.009 | 0.901 ± 0.009 | 0.901 ± 0.009 | 0.896 ± 0.007 |
| cyp2c9_inhibition | 964 (138) | 0.897 ± 0.001 | 0.897 ± 0.001 | 0.897 ± 0.001 | 0.895 ± 0.001 |
| cyp2d6_inhibition | 1047 (152) | 0.873 ± 0.002 | 0.873 ± 0.002 | 0.873 ± 0.002 | 0.868 ± 0.003 |
| cyp3a4_inhibition | 983 (111) | 0.901 ± 0.001 | 0.901 ± 0.001 | 0.901 ± 0.001 | 0.895 ± 0.003 |
| dili_liver_injury | 112 (61) | 0.898 ± 0.022 | 0.898 ± 0.022 | 0.898 ± 0.022 | 0.884 ± 0.028 |
| herg_cardiotoxicity | 1051 (617) | 0.876 ± 0.005 | 0.876 ± 0.005 | 0.876 ± 0.005 | 0.871 ± 0.005 |
| hia_absorption | 50 (49) | 0.972 ± 0.002 | 0.972 ± 0.002 | 0.972 ± 0.002 | 0.955 ± 0.009 |
| pgp_inhibition | 97 (36) | 0.910 ± 0.005 | 0.910 ± 0.005 | 0.910 ± 0.005 | 0.832 ± 0.020 |

## The served score: five-seed mean, calibrator fitted on the mean

| endpoint | Brier raw | Platt | temperature | isotonic | ECE raw | Platt | temperature | isotonic |
|---|---|---|---|---|---|---|---|---|
| ames_mutagenicity | 0.147 | 0.155 | 0.147 | 0.159 | 0.024 | 0.075 | 0.032 | 0.062 |
| bbb_permeability | 0.103 | 0.135 | 0.103 | 0.099 | 0.122 | 0.158 | 0.122 | 0.081 |
| cyp2c9_inhibition | 0.116 | 0.120 | 0.117 | 0.120 | 0.018 | 0.037 | 0.030 | 0.042 |
| cyp2d6_inhibition | 0.086 | 0.088 | 0.086 | 0.088 | 0.016 | 0.026 | 0.021 | 0.035 |
| cyp3a4_inhibition | 0.125 | 0.128 | 0.126 | 0.132 | 0.016 | 0.043 | 0.034 | 0.041 |
| dili_liver_injury | 0.210 | 0.231 | 0.214 | 0.149 | 0.289 | 0.042 | 0.222 | 0.188 |
| herg_cardiotoxicity | 0.145 | 0.148 | 0.147 | 0.146 | 0.061 | 0.073 | 0.085 | 0.065 |
| hia_absorption | 0.041 | 0.219 | 0.041 | 0.038 | 0.048 | 0.209 | 0.042 | 0.046 |
| pgp_inhibition | 0.131 | 0.135 | 0.132 | 0.172 | 0.077 | 0.110 | 0.086 | 0.156 |

Counts on the served-score table (how many of the 9 endpoints show a value lower than raw):

- Brier: Platt 0, temperature 1, isotonic 3.
- ECE: Platt 1, temperature 2, isotonic 3.

## Reading it, and what it does not show

- **Calibration sets are small.** The counts in the first column are the whole calibration split. Isotonic regression on a few dozen molecules is a step function that follows them, so a low calibration-split error there says nothing about the test split. Where a calibration split has very few molecules of one class (HIA's has a single negative), every method is fitted on almost no information about that class.
- **Platt here is a fit on the probability, not the logit.** That is the MARS definition (`eval/calibration.py`); the usual textbook form is a fit on the score before the sigmoid. Temperature scaling is the logit form.
- **The calibration split is not label-representative** (the C1 caveat in `SHIP_CHECKLIST.md` D2 and `xgboost_c0_raw_vs_calibrated.md`): its positive rate can differ from the test set's, and any monotone map learned there inherits that shift.
- **One test set.** Differences of a few thousandths are inside the noise of 96 to 2,600 test molecules; see the bootstrap intervals in `evaluation_results.md` for how wide that is.
- **Not covered:** KERMT (it has its own temperature scalers, `kermt_tier0_results`, and no per-molecule test predictions in git), and regression endpoints (nothing to calibrate).
