# ml/ — Person A track

Owns Modules 1, 3, 4, 5 (core), 6 (post-MVP), 11.

## Layout
- `data/` — TDC acquisition, standardization, dedup, scaffold-split scripts (Module 1)
- `featurize/` — RDKit standardization, ECFP, 2D descriptors, 3D conformers (Module 3)
- `models/` — backbone + multi-task cluster heads, XGBoost baselines (Module 4)
- `train/` — training loops, checkpoint/resume with RNG-state restoration (Module 10 constraint)
- `eval/` — metrics, CV/seed aggregation, ablation matrix (Module 11)
- `configs/` — one YAML per run (endpoint/cluster, seed, hyperparams) for W&B + reproducibility

## Day 1
1. `pip install -r requirements.txt`
2. `python data/acquire.py` — pull all 14 TDC datasets, write lockfile with dataset snapshot hashes
3. Confirm `../contracts` importable: `python -c "from mars_contracts import Endpoint; print(list(Endpoint))"`
