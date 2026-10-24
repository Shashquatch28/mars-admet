# Held-out results (Module 11 sections 1-2)

Generated 2026-10-24 by `ml/eval/evaluation_results.py` on processed snapshot `20260830T200000Z`. Test split only: nothing here was fit, selected or tuned on it. Raw (uncalibrated) scores, as served.

## Table 1: XGBoost on all 14 endpoints

*Seeds* is mean ± sample std over the five seed models (training noise). *Ensemble* is the served score, the mean of the five seeds, with a 95 % percentile bootstrap interval over the test molecules (2000 resamples; sampling noise). Rank-based classification metrics need both classes in a resample; resamples without both are skipped and counted.

| endpoint | n_test | metric | seeds | ensemble [95 % bootstrap] | resamples used | test molecules sharing a scaffold with training | ensemble on the rest [95 % bootstrap] |
|---|---|---|---|---|---|---|---|
| solubility_logs | 1960 | MAE | 0.810 ± 0.014 | 0.802 [0.768, 0.835] | 2000 of 2000 | 408 (20.8%) | 0.830 [0.792, 0.869] |
| lipophilicity_logp | 840 | MAE | 0.544 ± 0.006 | 0.539 [0.511, 0.570] | 2000 of 2000 | 0 | - |
| caco2_permeability | 180 | MAE | 0.288 ± 0.012 | 0.284 [0.254, 0.314] | 2000 of 2000 | 0 | - |
| hia_absorption | 117 | AUROC | 0.972 ± 0.002 | 0.972 [0.928, 1.000] | 2000 of 2000 | 0 | - |
| pgp_inhibition | 245 | AUROC | 0.910 ± 0.005 | 0.912 [0.876, 0.943] | 2000 of 2000 | 0 | - |
| bbb_permeability | 394 | AUROC | 0.901 ± 0.009 | 0.907 [0.868, 0.941] | 2000 of 2000 | 2 (0.5%) | 0.907 [0.869, 0.941] |
| ppb_binding | 323 | MAE | 7.363 ± 0.122 | 7.254 [6.317, 8.248] | 2000 of 2000 | 0 | - |
| cyp3a4_inhibition | 2463 | AUROC | 0.901 ± 0.001 | 0.904 [0.892, 0.915] | 2000 of 2000 | 29 (1.2%) | 0.902 [0.890, 0.914] |
| cyp2d6_inhibition | 2621 | AUROC | 0.873 ± 0.002 | 0.876 [0.855, 0.893] | 2000 of 2000 | 569 (21.7%) | 0.882 [0.861, 0.902] |
| cyp2c9_inhibition | 2411 | AUROC | 0.897 ± 0.001 | 0.900 [0.887, 0.913] | 2000 of 2000 | 49 (2.0%) | 0.900 [0.887, 0.912] |
| clearance_microsomal | 221 | MAE | 25.956 ± 0.497 | 25.792 [22.433, 29.701] | 2000 of 2000 | 0 | - |
| herg_cardiotoxicity | 2627 | AUROC | 0.876 ± 0.005 | 0.880 [0.866, 0.892] | 2000 of 2000 | 0 | - |
| ames_mutagenicity | 1453 | AUROC | 0.858 ± 0.005 | 0.862 [0.844, 0.881] | 2000 of 2000 | 0 | - |
| dili_liver_injury | 96 | AUROC | 0.898 ± 0.022 | 0.923 [0.860, 0.972] | 2000 of 2000 | 25 (26.0%) | 0.948 [0.888, 0.991] |

The last two columns are the scaffold check of `self_audit.md` made visible. A test molecule counts as sharing when its non-acyclic Murcko scaffold also occurs among the training molecules. For the endpoints that adopt TDC's benchmark split the overlap is inherited from TDC's split (recorded by M1 in each `split_report.json`) and is small. DILI is different: the base split has none, and the DILIst-augmented training pool adds molecules that share scaffolds with a quarter of the test set (Module 1 section 6 asks for a re-check after merging; the count of 19 was recorded at augmentation time and called expected for a small chemical space, `mars-status_M1.md` H-5, and the pool was used as it stood). The served DILI model was trained on that pool, so a number measured on the molecules that share no scaffold with it is the one to read.

Classification, the other metrics (mean ± std over seeds; Brier and ECE are on raw scores, which are not validated probabilities - `xgboost_c0_raw_vs_calibrated.md`):

| endpoint | AUPRC | Brier | ECE |
|---|---|---|---|
| hia_absorption | 0.990 ± 0.001 | 0.041 ± 0.001 | 0.049 ± 0.004 |
| pgp_inhibition | 0.916 ± 0.003 | 0.132 ± 0.003 | 0.085 ± 0.017 |
| bbb_permeability | 0.972 ± 0.003 | 0.104 ± 0.006 | 0.120 ± 0.006 |
| cyp3a4_inhibition | 0.880 ± 0.001 | 0.127 ± 0.001 | 0.020 ± 0.004 |
| cyp2d6_inhibition | 0.676 ± 0.006 | 0.086 ± 0.001 | 0.017 ± 0.003 |
| cyp2c9_inhibition | 0.790 ± 0.003 | 0.117 ± 0.000 | 0.018 ± 0.003 |
| herg_cardiotoxicity | 0.888 ± 0.005 | 0.147 ± 0.004 | 0.057 ± 0.011 |
| ames_mutagenicity | 0.896 ± 0.004 | 0.149 ± 0.003 | 0.031 ± 0.004 |
| dili_liver_injury | 0.889 ± 0.025 | 0.212 ± 0.013 | 0.239 ± 0.025 |

## Table 2: what is served

The routing table (`ml/serve/routing.json`) picks KERMT or XGBoost per endpoint. For an endpoint routed to KERMT the number is the KERMT Tier-0 five-seed mean ± std from the records in git. No interval is given for KERMT: per-molecule KERMT test predictions are not stored, so a bootstrap needs the KERMT service run over the test set.

| endpoint | served by | metric | served model: seeds | XGBoost ensemble [95 % bootstrap] |
|---|---|---|---|---|
| solubility_logs | xgboost | MAE | 0.810 ± 0.014 (XGBoost, as Table 1) | 0.802 [0.768, 0.835] |
| lipophilicity_logp | kermt | MAE | 0.460 ± 0.014 | 0.539 [0.511, 0.570] |
| caco2_permeability | xgboost | MAE | 0.288 ± 0.012 (XGBoost, as Table 1) | 0.284 [0.254, 0.314] |
| hia_absorption | xgboost | AUROC | 0.972 ± 0.002 (XGBoost, as Table 1) | 0.972 [0.928, 1.000] |
| pgp_inhibition | kermt | AUROC | 0.932 ± 0.004 | 0.912 [0.876, 0.943] |
| bbb_permeability | kermt | AUROC | 0.941 ± 0.003 | 0.907 [0.868, 0.941] |
| ppb_binding | xgboost | MAE | 7.363 ± 0.122 (XGBoost, as Table 1) | 7.254 [6.317, 8.248] |
| cyp3a4_inhibition | xgboost | AUROC | 0.901 ± 0.001 (XGBoost, as Table 1) | 0.904 [0.892, 0.915] |
| cyp2d6_inhibition | kermt | AUROC | 0.879 ± 0.003 | 0.876 [0.855, 0.893] |
| cyp2c9_inhibition | xgboost | AUROC | 0.897 ± 0.001 (XGBoost, as Table 1) | 0.900 [0.887, 0.913] |
| clearance_microsomal | kermt | MAE | 24.510 ± 0.650 | 25.792 [22.433, 29.701] |
| herg_cardiotoxicity | kermt | AUROC | 0.892 ± 0.004 | 0.880 [0.866, 0.892] |
| ames_mutagenicity | xgboost | AUROC | 0.858 ± 0.005 (XGBoost, as Table 1) | 0.862 [0.844, 0.881] |
| dili_liver_injury | xgboost | AUROC | 0.898 ± 0.022 (XGBoost, as Table 1) | 0.923 [0.860, 0.972] |

## How to read this, and what it does not show

- The routing rule chose KERMT where it beat XGBoost on these same test records (`kermt_routing_evidence.md`), so the six KERMT numbers carry a selection effect and are likely optimistic relative to a fresh split. The XGBoost column is not selected on the test set.
- The KERMT and XGBoost pools differ; see `kermt_vs_xgboost_pool_matched.md` for the like-for-like rows and `significance.md` for how little those rows can support.
- The test split is scaffold-based. Performance on molecules unlike the training set is lower; that is what the applicability-domain flag is for. Module 11 section 5.5 (Lo-Hi, DataSAIL) is not run.
- Small test sets give wide intervals (DILI 96 molecules, HIA 117, P-gp 245). A point estimate on those is not a precise number.
- These are intervals for the number on this test set. They say nothing about drift, new chemistry or assay differences.
