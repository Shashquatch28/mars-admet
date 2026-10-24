# Self-audit of the served XGBoost models (Module 11 section 5)

Generated 2026-10-24 by `ml/eval/self_audit.py`. Nothing in this file is typed by hand: the checks run against the processed snapshot and promoted artifacts named below.

**Result: 14 endpoints, 135 checks, 6 failed.**

## (a) Leakage

Each check is a small pure function in `ml/eval/leakage_audit.py`. A cell is the number of checks that passed over the number that ran for that endpoint (the AD-index and calibrator checks run only when that artifact exists, so regression endpoints run fewer).

| endpoint | checks passed | detail of any failure |
|---|---|---|
| solubility_logs | 8 / 9 | test_disjoint_from_train_val_scaffolds: 14 overlapping non-acyclic scaffolds |
| lipophilicity_logp | 9 / 9 | none |
| caco2_permeability | 9 / 9 | none |
| hia_absorption | 10 / 10 | none |
| pgp_inhibition | 10 / 10 | none |
| bbb_permeability | 9 / 10 | test_disjoint_from_train_val_scaffolds: 2 overlapping non-acyclic scaffolds |
| ppb_binding | 9 / 9 | none |
| cyp3a4_inhibition | 9 / 10 | test_disjoint_from_train_val_scaffolds: 12 overlapping non-acyclic scaffolds |
| cyp2d6_inhibition | 9 / 10 | test_disjoint_from_train_val_scaffolds: 10 overlapping non-acyclic scaffolds |
| cyp2c9_inhibition | 9 / 10 | test_disjoint_from_train_val_scaffolds: 15 overlapping non-acyclic scaffolds |
| clearance_microsomal | 9 / 9 | none |
| herg_cardiotoxicity | 10 / 10 | none |
| ames_mutagenicity | 10 / 10 | none |
| dili_liver_injury | 9 / 10 | test_disjoint_from_train_val_scaffolds: 19 overlapping non-acyclic scaffolds |

Checks that ran: `ad_index_disjoint_from_test`, `calibration_disjoint_from_test`, `calibration_subset_of_train_val`, `calibrator_fit_sample_count_within_calibration_split`, `no_duplicate_smiles_within_test`, `no_duplicate_smiles_within_train_val`, `seed_fold_scaffold_isolation`, `seed_folds_cover_train_val`, `test_disjoint_from_train_val_scaffolds`, `test_disjoint_from_train_val_smiles`.

**Reading the scaffold check.** `test_disjoint_from_train_val_scaffolds` fails where a non-acyclic Murcko scaffold occurs on both sides (6 endpoints failed a check on this run: `solubility_logs`, `bbb_permeability`, `cyp3a4_inhibition`, `cyp2d6_inhibition`, `cyp2c9_inhibition`, `dili_liver_injury`). The explanation below was written for the 2026-10-24 snapshot; re-read it if that list changes. Two different causes sat behind the failures:

- *Solubility, BBB, CYP3A4, CYP2D6, CYP2C9:* these adopt TDC's benchmark split verbatim for leaderboard comparability, and MARS's stricter standardization turns a few TDC scaffold groups into overlaps. M1 recorded each in its `split_report.json` `notes[]` (`mars-status_M1.md` F-Run2-2). Small: 2 to 15 scaffolds. `evaluation_results.md` counts the test molecules involved.
- *DILI:* the base split has no overlap. The DILIst-augmented training pool, which is what the served model learned from, shares 19 scaffolds with the test set. M1 recorded the count (`mars-status_M1.md` H-5, "expected for a small chemical space") and used the pool as it stood. Module 11 section 5(a) asks for no overlap especially after augmentation, so this audit **does not meet that rule for DILI**. `evaluation_results.md` reports the DILI score on the test molecules that share no scaffold with the pool.

DILI is audited as the DILIst-augmented pool the model was trained on. Its test set is bit-identical to the base set (verified by `ml/tests`).

## (b) Hyperparameter tuning: extent and what data it touched

- The XGBoost "sweep" is 70 training runs (14 endpoints x 5 seeds); 70 completed, 0 failed. It is a seed sweep, not a hyperparameter search: `run_production_sweep.py` passes no hyperparameters.
- Every endpoint therefore uses the same fixed defaults from `ml/models/xgboost_model.py` (n_estimators 500, max_depth 6, learning_rate 0.05, subsample 0.8, colsample_bytree 0.8) with early stopping (50 rounds) on each seed's own validation fold. The only thing fitted to validation data is the stopping round. No hyperparameter was chosen by looking at the test split.
- The held-out test split is read only by `ml/train/evaluate_xgboost_test.py` and by this audit's leakage checks; nothing is fit, selected or tuned on it (`ml/eval/heldout_evaluation.py` states the same). Not tuning is a limitation as well as a safeguard: no claim is made that these defaults are the best XGBoost can do on any endpoint.
- The Platt calibrators were fit on the calibration split and are not applied to served scores (C0, `xgboost_c0_raw_vs_calibrated.md`).
- KERMT used stock hyperparameters (Tier 0): nothing was tuned. The routing rule that picks KERMT or XGBoost per endpoint was applied to test records, so the routed choice for those 14 endpoints is itself selected on test data. The per-endpoint numbers it selects between are reported as they are; a fresh split would be needed to estimate the routed system without that selection effect.

## (c) Reproducibility

- Processed snapshot: `20260830T200000Z`; manifest sha256 `14fcd199caedf486cea64bfcd80bb23820fdd7bf658d2277a2ce5c29678ea636`.
- Code commit: `cc1aa484ca5e2f65c133377f0f42d49445d4d6bf`.
- Python 3.11.9 on Windows; numpy 2.4.6, pandas 2.3.3, scikit-learn 1.9.0, scipy 1.17.1, xgboost 3.2.0, rdkit 2026.3.5, joblib 1.5.3.
- Seeds are fixed (`FIXED_SEEDS` in `ml/configs/experiment_config.py`); the promoted artifacts are the five per-seed models in `ml/artifacts/<endpoint>/seed_<n>/`, which are gitignored. A deployed service fetches them as a verified release (`ml/serve/artifact_store.py`).
- The package versions above are those of the machine that ran this audit, not necessarily those that trained the models. The deploy image resolves rdkit 2026.9.1 while the models trained on 2026.3.5; the 217 descriptors matched to 6e-14 on 31 molecules (deploy notes), not pinned.
