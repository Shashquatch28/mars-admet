# Seed-spread evidence, 2026-10-08

Raw scripts and outputs behind the 2026-10-08 AIMS entry "Seed spread is not an uncertainty interval" (frontend ADR-024).

- `q4_eval.py`: loads each endpoint's promoted seeds and its held-out test split, and computes the coverage of the served
  `mean +/- k*std` spread plus rank correlation between spread and absolute error. Writes `results/per_endpoint_*.json`.
- `q4_conformal.py`: builds the pooled out-of-fold absolute-residual band (80% and 90%) for one endpoint at a time. Writes `results/out2_*.json`.
  Only four result files were saved (caco2 and solubility regression; ames and dili classification). The band figures in the AIMS entry for the other
  regression endpoints have no saved JSON here; re-run the script to regenerate them.

**Not turnkey.** Both scripts were run from a scratch directory outside the repo and hard-code `~/scratch` for the feature
cache and output paths, and `~/mnt/mars-admet` for the repo root. Edit those three constants before re-running. They
need the promoted artifacts in `ml/artifacts/` (git-ignored) and the processed data in `ml/data/processed/`. They ran under
Python 3.10 with import shims (the repo targets 3.11) and xgboost 3.2.0, not the pinned environment. Before relying on the
numbers the same pipeline reproduced the recorded test metrics exactly (HIA AUROC 0.9721, solubility MAE 0.8098).

`ml/` is not touched; these scripts live under `documentation/` on purpose.
