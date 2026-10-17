# XGBoost served scores: raw vs Platt-calibrated, held-out test set (C0)

Date: 2026-10-17. Decision: `documentation/AIMS/decisions.md` 2026-10-08.

**What changed.** `ml/serve/predictor.py` serves the raw 5-seed ensemble mean for the
nine classification endpoints. The fitted Platt calibrators are applied only when the
environment variable `MARS_APPLY_PLATT` is `1`/`true`/`yes`/`on`. Regression endpoints
were never calibrated.

**How the numbers were produced.** `ml/train/evaluate_xgboost_test.py` against the
promoted artifacts in `ml/artifacts/` (prep `20260830T200000Z`), written to a scratch
directory. All 14 regenerated reports are byte-for-byte identical in their aggregated
raw and calibrated metrics to the 2026-09-21 reports in `ml/runs/test_evaluations/`
(gitignored), so the C0 decision's evidence reproduces.

Mean over 5 seeds, held-out test set. `cal` = the single served calibrator (fit on seed 4
only) applied to every seed. Lower is better for Brier and ECE.

| endpoint | n_test | AUROC raw | Brier raw | Brier cal | ECE raw | ECE cal |
|---|---|---|---|---|---|---|
| ames_mutagenicity | 1453 | 0.858 | 0.149 | 0.159 | 0.031 | 0.084 |
| bbb_permeability | 394 | 0.901 | 0.104 | 0.130 | 0.120 | 0.163 |
| cyp2c9_inhibition | 2411 | 0.897 | 0.117 | 0.121 | 0.018 | 0.035 |
| cyp2d6_inhibition | 2621 | 0.873 | 0.086 | 0.089 | 0.017 | 0.024 |
| cyp3a4_inhibition | 2463 | 0.901 | 0.127 | 0.129 | 0.020 | 0.045 |
| dili_liver_injury | 96 | 0.898 | 0.212 | 0.230 | 0.239 | 0.071 |
| herg_cardiotoxicity | 2627 | 0.876 | 0.147 | 0.149 | 0.057 | 0.071 |
| hia_absorption | 117 | 0.972 | 0.041 | 0.220 | 0.049 | 0.209 |
| pgp_inhibition | 245 | 0.910 | 0.132 | 0.135 | 0.085 | 0.095 |

Raw is better on Brier for 9 of 9 and on ECE for 8 of 9 (DILI is the exception: 0.239 raw
vs 0.071 calibrated, n_test = 96). The 2026-10-08 decision quoted 7 of 9 for ECE; that
figure was the like-for-like comparison on the calibrator's own seed 4, this table is the
5-seed aggregate with one calibrator applied to all seeds, so the counts differ by basis.

**Not claimed.** Raw scores are not validated probabilities either (ECE up to 0.24, DILI
and BBB worst). The UI keeps the label `score` (ADR-023); C1 is what could return an
endpoint to `probability`.

**Deploy note.** The API caches predictions for 48 h keyed on SMILES, endpoint set and
`MODEL_VERSION`. A running API keeps serving cached calibrated values until the cache
expires or Redis is flushed; `MODEL_VERSION` was not bumped.
