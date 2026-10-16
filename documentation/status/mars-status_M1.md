# MARS — M1 Implementation Status & Verification Matrix

**Source of truth:** `mars-blueprint_v4.md` (Modules 1, 3; Module 11 §5/§6; Module 14)
**Milestone:** M1 — Data & Featurization — **COMPLETE 2026-08-30**. Next milestone: M2 (Modeling).
**Comprehensive reference:** `documentation/MARS_M1_TECHNICAL_REFERENCE.md`
**Repo SHA at this update:** M0 `daddcf7` · M1 Run 1 `ec9c604` · Run 2 `c86a956` · Run 3 `77aab38` (+ `b072865` CI fix) · **Run 4 uncommitted** (feature cache, integration tests, Cloud Run edit, `.gitignore` cache rule, this doc + `MARS_M1_TECHNICAL_REFERENCE.md`). Branch `milestone/m1-data-featurization`.
**Last updated:** 2026-08-30 — **M1 COMPLETE. Run 4: feature/conformer cache + comprehensive tests + Cloud Run serving edit + `documentation/MARS_M1_TECHNICAL_REFERENCE.md`**

Status legend: **COMPLETE** = implemented + verified with evidence · **PARTIAL** ·
**MISSING** · **CONFLICTING** (implementation would violate the blueprint; needs a decision).

Run plan (agreed 2026-08-30):
- **Run 1** — env/dependency audit, storage & provenance architecture, TDC acquisition + lockfile ✅ complete
- **Run 2** — standardization, EDA, dedup, split, calibration, DILIst augmentation ✅ complete
- **Run 3a** — molecular graph representation + Morgan/ECFP fingerprints + un-defer PPB per Option C ✅ complete
- **Run 3b** — RDKit 2D descriptors + batch-pipeline façade + ETKDG+MMFF94 3D conformers ✅ complete
- **Run 4 (this update)** — on-disk feature/conformer cache + comprehensive deterministic + integration tests + Cloud Run serving blueprint edit + full `MARS_M1_TECHNICAL_REFERENCE.md` ✅ complete. **M1 DONE.**

---

## 1. Repository state (M1-relevant)

| Area | State after Run 1 |
|---|---|
| **Acquisition env** | Isolated WSL Ubuntu 24.04 venv, `PyTDC==1.1.15` (`--no-deps` + pinned minimal runtime). Frozen: `ml/data/requirements-acquire.lock.txt`. Reproduce: `ml/data/acquisition/README.md`. |
| **M1 working env** | Dedicated `ml/.venv` (Python 3.11.9): numpy 2.4.6, pandas 2.3.3, scikit-learn 1.9.0, rdkit 2026.03.5, joblib 1.5.3, pytest 9.1.1, `-e ../contracts`. Pins: `ml/requirements-m1.txt` + `ml/requirements-m1.lock.txt`. No torch (M1 is CPU-only). |
| **`ml/data/` code** | `dataset_registry.py` (15 dataset specs, dep-free), `snapshot.py` (deterministic hashing), `acquire.py` (real acquisition pipeline — replaces the stub), `__init__.py`. |
| **Raw data** | `ml/data/raw/<TDC_name>/<acq_id>/` — 15 datasets, ~22 MB, git-ignored, immutable. Each dir: `tdc_download/<name>.tab` (TDC-delivered bytes), `<name>.full.csv` (normalized), `benchmark_split/{train_val,test}.csv` where applicable, `source_meta.json`. |
| **Lockfile** | `ml/data/metadata/datasets.lock.json` (schema v1, git-tracked) + `acquisition_report.md`. |
| **Provenance modules** | `ml/tracking/provenance.py` + `ml/utils/seed.py` — torch imports made lazy (CF-5 resolved). |
| **Docs** | `ml/data/LICENSES.md` (Module 1 §7 record), `documentation/FUTURE_SCOPE.md` (hERG merged-superset item). |
| **Tests** | `ml/tests/` — 28 tests, all passing in `ml/.venv`. M0 suite (contracts+api, 12) unaffected. |
| Standardization / EDA / dedup / split / augmentation / featurization | **not started** — Runs 2–3. |

---

## 2. M1 verification matrix

### M1-A — Environment & dependencies

| # | Task (blueprint / task spec) | Status | Evidence / remaining |
|---|---|---|---|
| A-1 | ML virtualenv with the M1 stack | **COMPLETE** | `ml/.venv` created; `import numpy,pandas,sklearn,rdkit,joblib` + an RDKit canonicalization smoke all pass. |
| A-2 | Minimal, explicit, pinned dependencies (no blind large stacks) | **COMPLETE** | `ml/requirements-m1.txt` (human) + `…-m1.lock.txt` (frozen). No torch/transformers/xgboost/mmpdb in the M1 env. `ml/requirements.txt` restructured into milestone sections with a pointer to the pinned files. |
| A-3 | Reproducible acquisition environment, exact PyTDC pinned | **COMPLETE** | Isolated WSL venv; `PyTDC==1.1.15`; `ml/data/requirements-acquire.lock.txt` (sha256 recorded in the lockfile). Rationale + reproduce steps in `ml/data/acquisition/README.md`. |
| A-4 | `provenance.py` / `seed.py` usable without torch (CF-5) | **COMPLETE** | Lazy/guarded torch import; `set_global_seed` now returns a record and seeds py+numpy always, torch if present. Guard test `ml/tests/test_provenance_cpu_only.py` (5 tests) green in a torch-free env. |
| A-5 | Env-structure decision recorded | **COMPLETE** | `documentation/AIMS/decisions.md` 2026-08-30 (dedicated `ml/.venv`, numpy 2.x + rdkit 2026.3; PyTDC isolated). |

### M1-B — Data acquisition & lockfile (Module 1 §1, §5)

| # | Requirement | Status | Evidence / remaining |
|---|---|---|---|
| B-1 | All blueprint datasets pulled via PyTDC | **COMPLETE** | 14 primary (11 ADME + 3 Tox) + `hERG` benchmark alt = 15 datasets acquired via `tdc.single_pred` + `tdc.benchmark_group`. Console + `acquisition_report.md`. |
| B-2 | Raw data preserved non-destructively | **COMPLETE** | `raw/<name>/<acq_id>/` immutable; the TDC-delivered `.tab` is kept verbatim alongside a normalized `.full.csv`. `acquire.py` refuses to overwrite an existing `<acq_id>` dir; a prior lockfile is archived to `metadata/history/`. Verified by re-run (kept both `acq_id`s until a deliberate clean). |
| B-3 | Dataset metadata stored | **COMPLETE** | Per-dataset `source_meta.json` + a `datasets` block in the lockfile: tdc_name, loader, task, license + ref, benchmark-group flag + resolved name, N, columns, id/smiles/label column names, blueprint-N deviation flag. |
| B-4 | Exact PyTDC version recorded | **COMPLETE** | `acquisition.pytdc_version = "1.1.15"` (from `importlib.metadata`, not hardcoded). |
| B-5 | Dataset identifiers recorded | **COMPLETE** | `datasets[*].tdc_name` + `benchmark_group_name` (TDC's resolved lowercase name, e.g. `ppbr_az`) + `acquisition.tdc_benchmark_group_dataset_names` (full list TDC exposed). |
| B-6 | Deterministic snapshot hashes | **COMPLETE** | `snapshot_sha256` per dataset = order-independent SHA-256 over canonicalized `(Drug, Y)` rows read back from the persisted CSV (scheme `mars-canonical-rows-v1`). Cross-run determinism proven: independent re-acquisition of DILI + Caco2 → byte-identical digests (full + benchmark split). Benchmark train_val/test each carry their own digest. |
| B-7 | Data-versioning lockfile | **COMPLETE** | `ml/data/metadata/datasets.lock.json` answers all six required questions (PyTDC version, dataset ids, acquisition time, raw files, snapshot hash, + git SHA, acq-env lockfile hash, platform). Git-tracked. |
| B-8 | No silent overwrite of prior snapshots | **COMPLETE** | `FileExistsError` on a non-empty existing `<acq_id>` dir unless `--force`; previous lockfile archived under `metadata/history/` before rewrite. |
| B-9 | Storage separation (raw / processed / metadata / cache) | **PARTIAL** | `raw/` and `metadata/` in use and separated; `processed/` exists (empty, Run 2); `interim/` and `cache/` layout is specified in this doc + `acquire.py` docstring but not yet created (Runs 2–4 own them). |
| B-10 | Licensing record in-repo (Module 1 §7) | **COMPLETE** | `ml/data/LICENSES.md` — all 14 CC BY 4.0 (per-dataset `license_ref` in the lockfile), DILIst public-domain, PharmaBench dropped. |

### M1-C — Standardization (Module 3 Stage 1)

| # | Task | Status | Evidence |
|---|---|---|---|
| C-1 | Reusable library (not a script); batched API; deterministic | **COMPLETE** | [ml/featurize/standardize.py](ml/featurize/standardize.py) — `standardize` / `standardize_batch`, `STANDARDIZER_VERSION = "mars-standardizer-v1"`, `StandardizerConfig` |
| C-2 | Ordered pipeline: parse → sanitize → normalize → largest-fragment → uncharge/reionize → canonicalize | **COMPLETE** | `_standardize_one`; components built once per batch |
| C-3 | Reject invalid with named enum reason (deterministic) | **COMPLETE** | `REJECTION_REASONS` = {empty-input, smiles-parse-failed, sanitize-failed, no-heavy-atoms-after-fragment-strip, unexpected-standardizer-error} |
| C-4 | Preserve defined stereo; do NOT fabricate undefined | **COMPLETE** | `isomericSmiles=True` canonicalization; test guarantees enantiomers produce distinct output; `had_defined_stereo` flag per row |
| C-5 | Tautomer normalization — off by default; opt-in | **COMPLETE** | `canonicalize_tautomer=False` default; 2-hydroxypyridine ⇄ 2-pyridone test confirms both cases |
| C-6 | Unit tests | **COMPLETE** | [ml/tests/test_standardize.py](ml/tests/test_standardize.py) — 18 tests: salts, invalid, empty, tautomer on/off, batch=singleton, enantiomers stay distinct, determinism |

### M1-D — EDA + PPBR investigation

| # | Task | Status | Evidence |
|---|---|---|---|
| D-1 | Per-endpoint EDA over ALL 15 datasets (validity, dup rate, conflict rate, stereo-defined ratio, class balance / target dist, scaffold diversity) | **COMPLETE** | [ml/data/eda.py](ml/data/eda.py); output at `ml/data/eda/20260830T191149Z/` — rollup.json + eda_report.md + per_dataset/*.json |
| D-2 | PPBR_AZ size-mismatch root cause | **COMPLETE** | See [documentation/status/ppbr_az_investigation.md](documentation/status/ppbr_az_investigation.md). PPBR_AZ is multi-species (5); `single_pred` returns human only (1,614), `benchmark_group` pools all species (2,790 measurements / 1,797 compounds; species column dropped). **PPBR_AZ split deferred pending your decision (Options A / B / C in the investigation note).** |

**Key EDA findings that drove policy** (from `eda/20260830T191149Z/eda_report.md`):
- **100% standardization validity** across all 15 datasets — no molecules were rejected.
- **Duplicate rate at standardized identity:** solubility 5.0% (highest), hERG-bench 6.0%, BBB 3.2%, hERG_Karim 2.2%; the rest <1%.
- **Conflict rate over multi-measurement molecules** (§3 tier driver): solubility 94% (reg → average), Caco2 67% (reg → average), hERG-bench 23% (clf), BBB 18%, CYP2C9 16%, CYP2D6 14%, hERG_Karim 5.6% (borderline; conservative majority-vote), CYP3A4 3.2% (low → drop). Everything else 0%.
- **Stereo-defined ratio:** HIA 58%, Pgp 54%, Caco2 54%, hERG_Karim 41%, PPB 36%, BBB 35%, Clearance 34%, CYP2C9 30%, CYP2D6/3A4 29%, Lipophilicity 28%, AMES 14%, Solubility 10%, **DILI 0%** (all names→structures, no stereo). The blueprint's "flagged" endpoints (CYP2C9/3A4/2D6, Caco2, Pgp, BBB) are all in the 29–54% range — nontrivial, worth Module 3's `useChirality=True` fix in Run 3.

### M1-E — Dedup / conflict resolution (Module 1 §3)

| # | Task | Status | Evidence |
|---|---|---|---|
| E-1 | Tiered policy selector: low-conflict → drop; moderate/high or small → avg/majority-vote; ties → drop | **COMPLETE** | [ml/data/dedup.py](ml/data/dedup.py) — `select_policy`, `dedup`; `LOW_CONFLICT_THRESHOLD=0.05`, `SMALL_DATASET_N=1500` (DILI-safe) |
| E-2 | Policy chosen from EDA per endpoint, recorded in provenance | **COMPLETE** | `select_policy_from_eda`; `prepare_report.md` shows per-dataset policy + rationale |
| E-3 | Auditable resolution report per endpoint | **COMPLETE** | `resolution_report.json` per dataset: counts of consensus_kept / dropped_conflicting / averaged / majority_voted / dropped_tie + list of dropped SMILES |
| E-4 | Unit tests | **COMPLETE** | [ml/tests/test_dedup.py](ml/tests/test_dedup.py) — 12 tests covering all policies, ties, consensus, singletons, and policy selection |

**Dedup outcome per endpoint (see `prepare_report.md`):**
- `drop_conflicting`: ames (7278→7255), CYP3A4 (12328→12295), lipophilicity (4200→4200)
- `average` (regression): solubility (9982→9478), Caco2 (910→904), clearance (1102→1102)
- `majority_vote` (clf): BBB (2030→1955), CYP2C9 (12092→12047), CYP2D6 (13130→13085), hERG_Karim (13445→13136), hERG-bench (655→607), HIA (578→578), Pgp (1218→1212), DILI (475→474 — small override)

### M1-F — Fixed scaffold split + leakage prevention (Module 1 §4)

| # | Task | Status | Evidence |
|---|---|---|---|
| F-1 | Adopt TDC official 80/20 benchmark split for the 13 in-group endpoints | **COMPLETE** | [ml/data/split.py](ml/data/split.py) `adopt_benchmark_split`; used by [prepare.py](ml/data/prepare.py) |
| F-2 | Deterministic Murcko scaffold split for hERG_Karim (not in benchmark group) | **COMPLETE** | `scaffold_split(seed=0)` — largest-group-first placement; verified: 0 SMILES overlap, 0 non-empty-scaffold overlap between hERG_Karim train_val and test |
| F-3 | Fixed test set (persisted, versioned; not touched by CV or calibration) | **COMPLETE** | Written once per `prep_id` under `ml/data/processed/<prep_id>/<dataset>/test.csv` + sha256 in `provenance.json`; a fresh prep_id starts a new snapshot without overwriting |
| F-4 | Automated leakage checks: SMILES overlap, scaffold overlap, deterministic reproducibility | **COMPLETE** | `leakage_audit` + `build_split_report` + `assert_no_leakage`; SMILES-level overlap is a hard failure for all methods; scaffold overlap is a hard failure for self-generated splits (hERG_Karim); adopted benchmark splits log-and-carry any scaffold overlap the TDC protocol produces under our stricter Murcko-post-standardization definition (BBB has 2, CYP2C9 has 3, CYP2D6 has 3, etc.). See §Findings. |
| F-5 | 5-seed train/valid CV within train_val | **COMPLETE** (utility) | `five_seed_train_val_folds` — scaffold-aware, deterministic per seed. Called from training (Run 3+), not persisted at prepare-time. |
| F-6 | Split unit tests | **COMPLETE** | [ml/tests/test_split.py](ml/tests/test_split.py) — 8 tests including scaffold-only-overlap, injected-leak detection, deterministic reproducibility, 5-seed disjointness |
| F-7 | Split integration tests over persisted outputs | **COMPLETE** | [ml/tests/test_prepare_outputs.py](ml/tests/test_prepare_outputs.py) — asserts on every dataset directory that train ∩ test = ∅, cal ∩ test = ∅, cal ⊂ train_val, provenance versions + sha256 present. Parametrized across all datasets; PPB skips cleanly. |

**Two post-standardization findings surfaced by the audit (Module 11 self-audit discipline):**
1. **1 SMILES collapse in BBB.** Two originally-distinct raw SMILES in the BBB benchmark file collapse to one canonical form under Module 3 Stage 1. Both landed on different sides. Resolved by dropping the compound from train_val (test is fixed); the removal is logged in `bbb_permeability/split_report.json` → `post_standardization_leaks_removed_from_train_val`.
2. **Non-empty Murcko-scaffold overlap in adopted TDC splits under our stricter standardization:** BBB 2, Caco2 3, Clearance 2, CYP3A4 3, CYP2C9 3, CYP2D6 3, HIA 1, hERG-bench 3. Retained for leaderboard comparability, but surfaced honestly in each `split_report.json` `notes[]`. `assert_no_leakage` only fires on this for splits **we** generate (hERG_Karim passes).

### M1-G — Calibration split (Module 4)

| # | Task | Status | Evidence |
|---|---|---|---|
| G-1 | Scaffold-aware, deterministic, ≥10% of train_val or 50-compound floor | **COMPLETE** | `_calibration_size` in prepare.py; seed=42 fixed; sizes actualized: HIA 50 (floor), DILI 50 (floor), Caco2 72, Pgp 97, hERG-bench 50, Clearance 88, BBB 157, PPB deferred, Lipophilicity 336, AMES 580, Solubility 752, CYP3A4 983, CYP2C9 964, CYP2D6 1047, hERG_Karim 1051 |
| G-2 | Isolated from the fixed test set | **COMPLETE** | Hard assertion in prepare.py: `if set(cal_smis) & set(te_pair_labels): raise AssertionError("calibration ∩ test != ∅")`; re-checked in integration tests |
| G-3 | Persisted as `calibration.csv` alongside train_val + test | **COMPLETE** | Written per dataset dir; sha256 in `provenance.json` |
| G-4 | Deferred behavior documented | **COMPLETE** | Blueprint Module 4 & Module 5's conformal-prediction reuse of the same split is documented in the module; nothing else deferred at prepare time |

### M1-H — DILIst augmentation (Module 1 §6)

| # | Task | Status | Evidence |
|---|---|---|---|
| H-1 | Acquire DILIst-based augmentation source with provenance record | **COMPLETE** | `DILI_Goldstandard_1111.csv` (1,111 rows, MIT license), sha256 `a86fd3a71c…`. See [ml/data/augmentation/dilipredictor_v1/PROVENANCE.md](ml/data/augmentation/dilipredictor_v1/PROVENANCE.md) — FDA LTKB DILIst = label source of truth (public domain 17 U.S.C. § 105); DILIPredictor = SMILES-resolved, MIT-licensed distribution. |
| H-2 | Standardize augmentation source through the *identical* Module 3 Stage 1 pipeline | **COMPLETE** | Same `standardize_batch` call in [dilist_augment.py](ml/data/dilist_augment.py). 1,096 valid of 1,111 raw (15 rejected via `sanitize-failed` — invalid phosphate SMILES; kept the raw rows in the report `rejection_samples`). |
| H-3 | Dedup against the fixed TDC DILI **test set** (non-negotiable) | **COMPLETE** | **57 compounds** dropped for being in the TDC DILI test set. `augmentation_report.json` → `steps.dropped_because_in_test_set = 57`. |
| H-4 | Only train/val pool augmented; test set unchanged | **COMPLETE** | Test set copied byte-identical from the base DILI processed output; asserted by `test_augmented_test_matches_baseline_test`. |
| H-5 | Post-merge scaffold-overlap re-check | **COMPLETE** | `augmentation_report.json` → `leakage_audit`: **SMILES overlap = 0** (hard requirement met), Murcko-scaffold overlap = 19 (expected for a small chemical space; surfaced honestly). |
| H-6 | Auditable augmentation report | **COMPLETE** | `augmentation_report.json` contains every step count, source-tag distribution, the sha256 of the source file, the resolution report, and the leakage audit. |
| H-7 | Integration tests | **COMPLETE** | [ml/tests/test_dilist_augmentation.py](ml/tests/test_dilist_augmentation.py) — 6 tests covering all non-negotiables. |

**Augmentation outcome for DILI:**
- Base (TDC DILI): train_val 378, test 96, cal 50, total unique compounds = 474
- After DILIst augmentation: train_val **1,119**, test 96 (frozen), cal 112, total unique = 1,215 — well above the pre-augmentation ~475 baseline, matching the blueprint's Module 4 note ("cross into range where joint training with Toxicity cluster may be worth testing").

### M1-I — Molecular graph representation (Module 3 Stage 2)

| # | Task | Status | Evidence |
|---|---|---|---|
| I-1 | Atom + bond feature extraction with chirality tags EXPLICIT (Module 3 §Stereochemistry non-negotiable) | **COMPLETE** | [ml/featurize/graph.py](ml/featurize/graph.py); `ATOM_FEATURE_DIM=42`, `BOND_FEATURE_DIM=10`; version `mars-graph-v1`; chirality is a 4-bin one-hot (`CHIRAL_TAGS` — `CHI_UNSPECIFIED` is its own bin so undefined stereo is explicit, never fabricated). |
| I-2 | Undefined stereo not fabricated | **COMPLETE** | `test_undefined_stereo_is_not_fabricated` — racemic center encodes as `CHI_UNSPECIFIED`, not a guessed R/S. |
| I-3 | Enantiomers produce different graph features | **COMPLETE** | `test_enantiomers_produce_different_atom_features_with_chirality_on` + `test_chirality_bins_are_the_only_difference_between_enantiomers` — L- and D-alanine's atom features differ ONLY in the chirality bins. Disabling chirality collapses them (`test_disabling_chirality_collapses_enantiomers_in_atom_features`). |
| I-4 | Bond stereo (E/Z) captured | **COMPLETE** | `test_bond_stereo_survives_into_edge_features` — (E)- vs (Z)-2-butene produce different edge features. |
| I-5 | Batched API; deterministic | **COMPLETE** | `molecule_graphs_batch` returns `(graphs, dropped_indices)` matching Morgan's convention; `test_batch_matches_singleton_and_drops_invalid_indices` + `test_deterministic`. |
| I-6 | Config version part of any cache key | **COMPLETE** | `GraphFeaturizerConfig.cache_key()` encodes version + dims + `include_chirality`. `test_cache_key_encodes_chirality_choice`. |
| I-7 | KERMT-native featurizer schema locked | **DEFERRED (M2 pre-flight)** | Per `AIMS/decisions.md` 2026-08-30 (KERMT decision item #4); a thin adapter can map from `mars-graph-v1` to KERMT's schema without redoing the atom-walk. Chirality inclusion is the blueprint constraint that must survive that adapter. |

### M1-J — Morgan/ECFP fingerprints (Module 3 Stage 3)

| # | Task | Status | Evidence |
|---|---|---|---|
| J-1 | radius=2, 2048-bit, `useChirality=True` — the blueprint's CYP2C9 fix | **COMPLETE** | [ml/featurize/fingerprints.py](ml/featurize/fingerprints.py); `MORGAN_FP_VERSION = "mars-morgan-r2-2048-chirality-v1"`. `test_default_config_matches_blueprint` locks the defaults. |
| J-2 | Enantiomers produce different fingerprints | **COMPLETE** | `test_enantiomers_produce_different_fingerprints_with_chirality_on` — L- and D-alanine ECFPs differ; `test_disabling_chirality_collapses_enantiomers` proves the opposite direction; `test_undefined_stereo_still_hashes_stably_with_chirality_on` shows chirality flag has no effect for undefined-stereo molecules. |
| J-3 | Deterministic, batched, invalid-safe | **COMPLETE** | `test_output_is_deterministic`, `test_batch_matches_singleton`, `test_batch_drops_invalid_indices_and_keeps_matrix_dense`, `test_empty_batch_returns_zero_row_matrix_not_error`. |
| J-4 | Tanimoto helper (for k-NN AD in Module 5) | **COMPLETE** | `tanimoto_similarity`; 4 targeted tests covering self=1, disjoint=0, shape-mismatch raise, and enantiomer sanity (0 < T < 1). |
| J-5 | Config version becomes part of any cache key | **COMPLETE** | `MorganConfig.cache_key()` encodes all four variables; `test_cache_key_encodes_all_variables` confirms four distinct configs produce four distinct keys. |

### M1-K — PPB Option C (locked 2026-08-30 per maintainer)

| # | Item | Status |
|---|---|---|
| K-1 | Blueprint Module 1 §4 + Module 2 record Option C (primary human, all-species pooled = secondary ablation) | **COMPLETE** — see the "PPB exception" paragraph added to Module 1 §4 (parallel to hERG) and the revised Module 2 row (`1,614 (human) / 1,797 compounds pooled`). |
| K-2 | Registry declares both variants with explicit species-filter provenance | **COMPLETE** — [ml/data/dataset_registry.py](ml/data/dataset_registry.py) `ppb_binding` (primary, `in_admet_benchmark_group=False`, N≈1614) + `ppb_binding__all_species` (`variant="benchmark_alt"`). Species-filter recipe documented in the docstring above the primary spec (source dataset, loader, inclusion/exclusion, dropped-row count, dedup/conflict policy, hash provenance). |
| K-3 | Prepare uses the REGISTRY (not the stale lockfile) for split method | **COMPLETE** — [ml/data/prepare.py](ml/data/prepare.py) now looks up `spec.in_admet_benchmark_group` and skips the lockfile's attached benchmark_split for PPB. Provenance records both `registry_says_adopt_benchmark` and `lockfile_had_benchmark_split` so the divergence is auditable. |
| K-4 | Human-only PPB processed end-to-end | **COMPLETE** — `prep_id=20260830T200000Z`: N_raw=1614 → dedup 0% conflict → 1614 → scaffold split train_val 1291 / test 323 / calibration 129. Test set is fixed. Method: `scaffold` (self-generated Murcko, seed=0), same policy shape as hERG_Karim. |
| K-5 | All-species pooled dataset provenance-tracked for the later ablation | **PARTIAL** — registry declares `ppb_binding__all_species`; raw all-species files are already on disk from the Run-1 acquisition (`ml/data/raw/PPBR_AZ/<acq_id>/benchmark_split/`). Actual processing waits until the ablation is scheduled per Option C §3. |
| K-6 | Ablation scheduling constraints recorded | **COMPLETE** — spec.notes on `ppb_binding__all_species`: "NOT on the M2 critical path... only executed if compute cost is acceptable (specifically: whether swapping the PPB target requires re-training the multi-task cluster for each seed vs only PPB-specific runs)." |

### M1-L — RDKit 2D descriptors (Module 3 Stage 4)

| # | Task | Status | Evidence |
|---|---|---|---|
| L-1 | ~200 RDKit 2D descriptors | **COMPLETE** | [ml/featurize/descriptors.py](ml/featurize/descriptors.py) — the full `Descriptors._descList` frozen at import (217 in RDKit 2026.3.5, matches blueprint "~200"). `test_the_blueprint_named_descriptors_are_present` locks MolWt/TPSA/MolLogP/NumHDonors/NumHAcceptors/NumRotatableBonds. |
| L-2 | Deterministic ordering, stable feature names | **COMPLETE** | `DESCRIPTOR_NAMES` is sorted + frozen; `test_names_are_sorted_and_unique`, `test_column_order_is_positional_and_stable` (column j ⇔ `DESCRIPTOR_NAMES[j]` always). |
| L-3 | No silent feature-column drift | **COMPLETE** | `DESCRIPTOR_SET_SHA` = SHA-256 of the newline-joined name list; `assert_descriptor_set_matches(config)` raises `RuntimeError` if the running RDKit's descriptor set differs from what a cache/lockfile was built against. `descriptor_matrix` calls it. |
| L-4 | Invalid / undefined values handled explicitly | **COMPLETE** | Raw matrix keeps inf/NaN (imputation is a Module 4 modelling call, not featurization); `descriptor_matrix` also returns a `finite_mask` + per-row `non_finite` dict naming exactly which descriptors overflowed. `test_non_finite_values_are_recorded_not_silently_passed` cross-checks mask vs dict. |
| L-5 | Versionable configuration | **COMPLETE** | `DescriptorConfig.cache_key()` = `mars-rdkit2d-v1\|n=217\|set=<sha16>`. |
| L-6 | Unit tests | **COMPLETE** | [ml/tests/test_descriptors.py](ml/tests/test_descriptors.py) — 15 tests (count, ordering, aspirin MolWt = 180.16, determinism, positional stability, non-finite handling, drift guard, empty batch). |

### M1-M — Batched featurization pipeline façade (Module 3 non-negotiable)

| # | Task | Status | Evidence |
|---|---|---|---|
| M-1 | Single batch entry point over Stages 1-5 | **COMPLETE** | [ml/featurize/pipeline.py](ml/featurize/pipeline.py) — `featurize_batch(raw_smiles, PipelineConfig)`. Standardizes **once** for the whole batch; each downstream stage's own batch function is called once (no hidden per-molecule loop at a higher layer). |
| M-2 | Aligned outputs; caller can re-align labels | **COMPLETE** | `FeaturizedBatch.kept_input_indices` + `standardized_smiles`; graph list / morgan matrix / descriptor matrix all aligned to `standardized_smiles`. `test_every_requested_stage_output_aligns_to_standardized_smiles`. |
| M-3 | Pipeline == calling each stage directly | **COMPLETE** | `test_pipeline_matches_calling_each_stage_directly` — per-molecule equality of morgan + graph features vs the standalone stage calls. |
| M-4 | 3D conformers off by default (blueprint: lazy) | **COMPLETE** | `want_conformers=False` default; `test_conformers_are_off_by_default_and_opt_in`. |
| M-5 | One provenance/version bundle per call (cache-keyable) | **COMPLETE** | `PipelineConfig.provenance()` → `pipeline_version` + every active stage's version + `*_cache_key`. `test_provenance_bundle_names_every_active_stage_version`. This is exactly what Run 4's feature cache will key on. |
| M-6 | Deterministic; all-invalid batch safe | **COMPLETE** | `test_batch_is_deterministic`, `test_all_invalid_batch_returns_empty_but_valid_structure`. |
| M-7 | Tests | **COMPLETE** | [ml/tests/test_pipeline.py](ml/tests/test_pipeline.py) — 9 tests. |

### M1-N — 3D conformer generation (Module 3 Stage 5)

| # | Task | Status | Evidence |
|---|---|---|---|
| N-1 | ETKDGv3 embed + MMFF94 optimize | **COMPLETE** | [ml/featurize/conformers.py](ml/featurize/conformers.py) — `generate_conformer`; `ETKDGv3` params, `MMFFOptimizeMoleculeConfs`. |
| N-2 | Deterministic seed handling | **COMPLETE** | `ConformerConfig.random_seed` (default `0xC0FFEE`) → `params.randomSeed`. `test_same_seed_gives_identical_geometry_and_energy` — byte-identical SDF under a fixed seed. |
| N-3 | Single lowest-energy conformer from an ensemble | **COMPLETE** | `n_conformers=10` embedded, MMFF energies computed for all, `min` selected. `n_conformers_tried` recorded. |
| N-4 | MMFF94 energy recorded | **COMPLETE** | `energy_kcal_mol` on the result; `test_energy_is_recorded_and_finite`. |
| N-5 | Graceful MMFF-failure handling | **COMPLETE** | `_optimise` tries MMFF94 (guarded by `MMFFHasAllMoleculeParams`), falls back to **UFF**; `force_field` field records which was used; `rejection_summary` counts MMFF94 vs UFF. If both fail → `reason="optimization-failed"`. |
| N-6 | No fabricated conformer on failure | **COMPLETE** | Failure → typed `ConformerResult(ok=False, reason=…)` with empty atoms/bonds and `sdf_block=None`; `to_contract_dict` raises rather than emit a fake payload. `test_invalid_smiles_is_a_named_failure_not_a_fake_conformer`. Reasons drawn from a closed `REJECTION_REASONS` enum. |
| N-7 | Output maps to `contracts.conformer.ConformerResponse` | **COMPLETE** | `ConformerResult.to_contract_dict(molecule_id)` → atoms (element/xyz/Gasteiger `partial_charge`), bonds (order incl. 1.5 aromatic), `energy_kcal_mol`, full `sdf_block`. `test_maps_onto_the_conformer_response_contract` constructs a real `ConformerResponse` from it. |
| N-8 | Expensive → cache-ready | **PARTIAL** | Result object is serialisable and `ConformerConfig.cache_key()` exists; the actual on-disk cache lands in Run 4. |
| N-9 | Tests | **COMPLETE** | [ml/tests/test_conformers.py](ml/tests/test_conformers.py) — 14 tests. |

### M1-O — Feature + conformer cache (Module 3 §caching, Module 12)

| # | Task | Status | Evidence |
|---|---|---|---|
| O-1 | On-disk cache for Morgan / descriptors / graph / conformers | **COMPLETE** | [ml/featurize/cache.py](ml/featurize/cache.py) — `FeatureCache(root)`; per-stage `<stage>_cached(smiles_list, config)` helpers; content-addressed sharded store under `ml/data/cache/`. |
| O-2 | Cache key = stable molecular identity + featurization config/version | **COMPLETE** | key = `sha256(stage ␟ stage.cache_key() ␟ standardized_smiles)`. Deterministic (`test_entry_key_is_deterministic_and_config_sensitive`). |
| O-3 | Incompatible config must NOT silently be reused | **COMPLETE** | different `cache_key()` → different key files → full recompute; `test_incompatible_config_is_not_silently_reused`. `<stage>/_config.json` records **every** cache_key ever written, first-seen time, entry count, and `numpy`/`rdkit`/all-5-stage-version strings. |
| O-4 | Round-trip identity | **COMPLETE** | Morgan/descriptor/graph values byte-match direct computation; conformer SDF byte-identical; enantiomer graph features + conformer failures survive the round-trip. |
| O-5 | Batched (one compute call per stage for the misses) | **COMPLETE** | each `<stage>_cached` collects misses and calls the stage's batch fn once; returns `CacheStats(hits, misses, computed, invalid)`. |
| O-6 | Cache-build driver + real-data smoke | **COMPLETE** | [ml/featurize/build_cache.py](ml/featurize/build_cache.py); Run 4 warmed Morgan+descriptors+graph for 3,572 unique molecules across {DILI, DILI-augmented, HIA, Caco2, Pgp} + a 150-molecule conformer sample → `ml/data/cache/build_report.json`. |
| O-7 | Tests | **COMPLETE** | [ml/tests/test_cache.py](ml/tests/test_cache.py) (~18) + [ml/tests/test_m1_integration.py](ml/tests/test_m1_integration.py) (~6, incl. "5-seed folds never touch the test set" and "processed SMILES are standardization fixed-points"). |

### M1-P — Comprehensive test suite + documentation

| # | Task | Status | Evidence |
|---|---|---|---|
| P-1 | Deterministic test suite across every M1 layer | **COMPLETE** | **219 ml tests passed, 14 skipped** (`ml/.venv`); 12 M0 tests passed (root `.venv`); `ruff` clean. Inventory in `MARS_M1_TECHNICAL_REFERENCE.md §8`. |
| P-2 | End-to-end integration on real processed data | **COMPLETE** | `test_m1_integration.py` — real DILI/HIA slices through pipeline + cache; asserts round-trip identity, standardization idempotence, test-set isolation of 5-seed CV. |
| P-3 | Full technical reference document | **COMPLETE** | [documentation/MARS_M1_TECHNICAL_REFERENCE.md](documentation/MARS_M1_TECHNICAL_REFERENCE.md) — every dataset/engineering/architecture/spec detail with the real numbers, for report/paper drafting. |

---

## Run 4 findings (new)

**F-Run4-1 — feature cache is inspectable and config-safe.** `<stage>/_config.json` records every `cache_key()` the cache has ever been written under (with library versions + entry counts), so a config change is *visible*, and the key includes the `cache_key()` so an incompatible config can never resolve to a stale entry. Verified by `test_incompatible_config_is_not_silently_reused` (two Morgan configs → both recorded, neither shadows the other).

**F-Run4-2 — processed SMILES are standardization fixed-points.** Re-standardizing the `standardized_smiles` column that `prepare.py` wrote is a no-op (`featurize_batch` keeps every row and maps each to itself). Confirms the canonical form is idempotent and the featurization layer can trust processed data without re-standardizing.

**F-Run4-3 — 5-seed CV provably never touches the fixed test set.** `test_five_seed_folds_never_touch_the_test_set` runs the real HIA processed split: all 5 seeds' train and valid sets are disjoint from `test.csv`, and the 5 partitions differ from each other.

**F-Run4-4 — cache build at real scale is fast.** Morgan + descriptors + graph over 3,572 unique standardized molecules (5 datasets) — see `ml/data/cache/build_report.json` for per-stage timing. Descriptors dominate; Morgan + graph are sub-second-per-thousand. Conformers (150-molecule sample) confirm the MMFF94 path; UFF fallback + failure counts recorded.

**F-Run4-5 — serving moved to Google Cloud Run** (maintainer decision): backend + async worker only; Cloud Tasks → Cloud Run worker for async batch; Neon/Upstash/Vercel/R2/Resend stay on free tiers. $0 at demo scale. Blueprint Modules 8, 10, 12, 13, 14 + `.env.example` updated.

## Run 3b findings (new)

**F-Run3b-1 — RDKit 2026.3.5 ships 217 2D descriptors, not "~200".** Taken as the whole set rather than a hand-picked subset (no subjective selection to justify; matches every RDKit-based ADMET baseline). The exact list is frozen + SHA-hashed at import; a future RDKit that adds/removes a descriptor fails `assert_descriptor_set_matches` rather than silently reshaping the feature matrix.

**F-Run3b-2 — descriptor non-finite values are surfaced, not imputed.** A few descriptors (`Ipc` etc.) can overflow to `inf` on large fused-ring systems. The featurization layer returns the raw matrix + a `finite_mask` + a per-row `{descriptor: value}` dict; imputation strategy is deferred to Module 4 (a modelling decision). None of the acquired M1 datasets have been run through descriptors at scale yet — that pairs with Run 4's cache build.

**F-Run3b-3 — conformer generation is fully deterministic under a fixed seed.** Same SMILES + same `ConformerConfig` → byte-identical SDF block and identical MMFF94 energy across runs. Aspirin: MMFF94, E ≈ 18.91 kcal/mol, 10 conformers tried, lowest selected. UFF fallback path is wired and counted but not yet exercised on real data.

**F-Run3b-4 — the batch façade standardizes once.** `featurize_batch` runs Module 3 Stage 1 a single time for the whole batch, then calls each stage's own batch function once. Provenance bundle carries every active stage's version + `cache_key()` — this is the exact object Run 4's feature cache keys on.

**F-Run3b-5 — no-paid-compute blueprint edit applied.** Per the 2026-08-30 maintainer directive: Module 10 training-compute row, a new "no-paid-compute constraint" box, the GPU-strategy section, all three cost-ceiling lines (now "$0"), the Module 11 compute-budget line, and the Module 14 M2 note. Fallback for lab-A100 unavailability is now free-tier cloud notebooks (Kaggle 30 GPU-hr/wk / Colab free), never a paid card. **Residual paid items NOT changed** (M3 scope, flagged below): the serving hosting stack still names Render Starter (~$7/mo) + "~$15-20/mo" for the always-on demo.

## Run 3a findings (new)

**F-Run3-1 — PPB primary Option C landed cleanly.** Human-only PPB (N=1,614) has 0% duplicate-conflict rate; dedup policy is `drop_conflicting` (no-op); self-generated Murcko scaffold split matches the hERG_Karim policy. `ppb_binding/split_report.json` records `method=scaffold`, `seed=0`, non-empty scaffold overlap between train_val and test = 0. Test set is FIXED from now on; per Run-4 discipline nothing may re-generate it.

**F-Run3-2 — Registry–vs–lockfile divergence handled without re-acquisition.** The Run-1 lockfile has PPB's `in_admet_benchmark_group=True` and an attached (all-species) benchmark_split. The Run-3 registry says False. Prepare.py now consults the registry, so Option C flows without a re-download; provenance records both values so a future auditor can see that the divergence was intentional and version-controlled. If the ablation is scheduled, a fresh acquisition of just `PPBR_AZ` under `--only ppb_binding__all_species` will populate the second variant.

**F-Run3-3 — Enantiomer distinguishability actually verified in both featurizers.** The blueprint's CYP2C9 concern is now proven directly against both featurizers on the same input: L- and D-alanine's Morgan fingerprints differ (Tanimoto 0.71, not 1.0), and their graph atom features differ ONLY in the 4-bin chirality slice. Undefined-stereo molecules encode as `CHI_UNSPECIFIED`, never fabricated. This closes a class of silent-default bug the blueprint explicitly warned about.

**F-Run3-4 — Graph schema is portable, not KERMT-locked.** Per the KERMT decision (`decisions.md` 2026-08-30), the KERMT featurizer schema is pinned at M2 pre-flight — until then, the graph module produces a portable atom/bond feature representation that is a superset of typical GNN needs and can be mapped into KERMT's schema with a thin adapter. Chirality inclusion at the atom level is the invariant that must survive that adapter.

## Run 2 findings (new)

**F-Run2-1 — Post-standardization SMILES collision in BBB benchmark.** One raw SMILES pair in the BBB benchmark split collapses to the same canonical form under Module 3 Stage 1 and appears in both `train_val` and `test`. Resolved automatically: kept on test side, removed from train_val. Logged in `bbb_permeability/split_report.json`.

**F-Run2-2 — Non-empty Murcko scaffolds shared across adopted TDC benchmark splits.** After Module 3 Stage 1 standardization, several TDC benchmark splits show low-count shared scaffolds (BBB 2, Caco2 3, Clearance 2, CYP3A4 3, CYP2C9 3, CYP2D6 3, HIA 1, hERG-bench 3) between train_val and test. This is a property of TDC's own split under our stricter Murcko-on-standardized-molecules definition; retained for leaderboard comparability, surfaced honestly in each split report. `assert_no_leakage` only enforces zero non-empty-scaffold overlap on splits **we** generate — hERG_Karim (our only self-generated split) passes.

**F-Run2-3 — DILI has 0% stereo-defined ratio.** All DILI compounds carry no stereo annotations (drug names→structures were resolved without preserving/asserting stereo). Consistent with the blueprint's "do not fabricate undefined stereo" rule. Practical consequence: Module 3 Stage 3's `useChirality=True` will not help DILI specifically — noted for Run 3.

**F-Run2-4 — DILIst augmentation removed 57 compounds** that appear in TDC's DILI held-out test set — this is the exact non-negotiable rule Module 1 §6 protects against, and it triggered on the real data. Additional 15 rows were rejected during standardization (invalid phosphate SMILES in the DILIPredictor distribution — kept as `rejection_samples` in the augmentation report for auditability).

**F-Run2-5 — DILI conflict rate 0% between DILIst and TDC DILI**, so the augmentation contributes cleanly. Small-dataset override still runs majority-vote to be safe; 41 augmentation-vs-base ties were dropped (blueprint policy: drop only the tied molecule).

**F-Run2-6 — Solubility_AqSolDB has a 94% conflict rate.** This is the strongest data-quality signal in the entire acquisition. Regression → averaged per blueprint policy (9,982 raw → 9,478 unique compounds after averaging). Worth explicit acknowledgement when reporting solubility numbers.

## 3. Critical findings (Run 1)

**CF-M1-1 — `hERG_Karim` is not in the TDC ADMET Benchmark Group.** Confirmed
against TDC `metadata.py` and by acquisition (`hERG_Karim` has no benchmark
split; the benchmark `hERG` is a separate 655-compound dataset). Consequences:
(a) 13/14 endpoints get an official fixed 80/20 scaffold split adopted verbatim;
hERG needs a self-generated deterministic Murcko split in Run 2. (b) Blueprint
Module 1 §4's "the specific split required to make our results directly
comparable to published TDC leaderboard numbers" over-claims for hERG.
**Decision (2026-08-30):** acquire both `hERG_Karim` (primary) and `hERG`
(benchmark alt); choose per-endpoint in Run 2 after EDA. Merged multi-source
hERG superset logged as future work (`documentation/FUTURE_SCOPE.md`).
**Blueprint wording fix proposed below — not applied.**

**CF-M1-2 — PPBR_AZ: `single_pred` N (1,614) ≠ benchmark-group N (2,231 + 559 =
2,790).** PPB is the *only* dataset where the benchmark split is not a partition
of the `single_pred` full set — for the other 13, `train_val + test == full N`
exactly. The benchmark version has ~1.7× more compounds. Root cause not yet
established (dedup by the `single_pred` loader vs. a different revision in the
benchmark archive). Also PPB's `single_pred` N is ~10% below the blueprint's
1,797. **Must be resolved in Run 2 before PPB is used** — pinned by
`test_benchmark_split_partitions_the_full_set_except_ppbr` so a silent change is
caught. Recorded in the lockfile (`n_matches_blueprint_within_5pct = false`).

**CF-M1-3 — minor sample-count drift from blueprint Module 2 headline N**
(TDC has revised datasets since the blueprint was written): BBB 2,030 vs 1,975
(+2.8%); AMES 7,278 vs 7,255; Pgp 1,218 vs 1,212; Caco2 910 vs 906; hERG(bench)
655 vs ~648. Solubility, Lipophilicity, HIA, CYP3A4/2D6/2C9, Clearance, DILI
match exactly. Not blocking; the lockfile records exact N and the deviation flag.
The blueprint's N column could carry an "as of TDC 2026-08 / PyTDC 1.1.15" note.

**CF-M1-4 (resolved) — CF-5.** `provenance.py` / `seed.py` hard-imported torch,
blocking CPU-only M1 provenance. Fixed: lazy imports, guard test added.

**CF-M1-5 — status-doc path.** Task spec references
`documentation/MARS_IMPLEMENTATION_STATUS.md`; repo convention is
`documentation/status/mars-status_M<n>.md`. This file follows the convention.
Flag if you want the exact path instead.

**No data-leakage findings** — splitting/augmentation code does not exist yet.
The leakage rules become live in Run 2 and will be built into the split code from
its first commit (self-audit hook: assert zero scaffold overlap train↔test, esp.
post-augmentation).

---

## 4. Proposed blueprint change — NOT APPLIED (awaiting maintainer decision)

**Module 1 §4, current wording:**
> "...with **5-seed cross-validation on the train/valid division within
> train_val** — this is TDC's own ADMET Benchmark Group protocol, not an
> arbitrary choice, and is the specific split required to make our results
> directly comparable to published TDC leaderboard numbers..."

**Observed problem.** True for 13/14 endpoints. `hERG_Karim` (Module 2's chosen
hERG dataset, N≈13,445) is **not** in the ADMET Benchmark Group; the TDC hERG
leaderboard is on the 655-compound `hERG`. So for hERG there is no official split
to adopt and no leaderboard number to be "directly comparable" to.

**Proposed wording (add after the sentence above):**
> "Exception: `hERG_Karim` (Module 2) is not part of the ADMET Benchmark Group.
> For hERG we generate a deterministic Murcko scaffold split replicating the same
> 80/20 methodology, and report it as *not* directly leaderboard-comparable —
> the published TDC hERG leaderboard uses the smaller `hERG` (Wang) dataset. The
> `hERG_Karim` choice is deliberate (large-data regime for the KERMT backbone and
> the multi-task Toxicity cluster); the comparability trade-off is accepted and
> stated, not hidden."

**Impact if accepted:** documentation only; matches what Run 2 will implement.
**Prefer fixing the spec text over weakening the implementation** — the
implementation already does the right, honest thing.

---

## 5. Verification performed (Run 1)

| Item | How verified | Result |
|---|---|---|
| Acquisition env | `import tdc`, `from tdc.single_pred import ADME, Tox`, `from tdc.benchmark_group import admet_group` | OK (PyTDC 1.1.15) |
| M1 working env | import all + RDKit `MolToSmiles(MolFromSmiles('c1ccccc1O'))` → `Oc1ccccc1` | OK |
| Full acquisition | ran `acquire.py` end-to-end in WSL | 15 datasets, 13 benchmark splits + hERG-bench split, ~22 MB, lockfile + report written |
| Lockfile ↔ disk integrity | `pytest ml/tests/test_acquisition_lockfile.py` — re-hash every raw file, recompute every snapshot digest from the persisted CSV | 8/8 pass |
| Cross-run determinism | independent re-acquisition of DILI + Caco2 into a throwaway root; compare digests | full + benchmark digests byte-identical |
| Registry ↔ contracts drift | `pytest ml/tests/test_dataset_registry.py` (imports `mars_contracts.Endpoint`) | 9/9 pass — 14 primary datasets == 14 ML endpoint keys; task types match `ENDPOINT_METADATA` |
| Snapshot hashing unit | `pytest ml/tests/test_snapshot.py` — order-independence, int/float-string equivalence, content sensitivity, file hash vs hashlib | 8/8 pass |
| CF-5 fix | `pytest ml/tests/test_provenance_cpu_only.py` in torch-free `ml/.venv` | 5/5 pass |
| Lint | `ruff check ml api contracts` (repo config) | clean |
| M0 regression | `pytest contracts/tests api/tests` in root `.venv` | 12/12 pass |

**Not verified this run (correctly out of Run 1 scope):** anything requiring
standardization, splitting, featurization, or model code. No GPU use. DILIst not
yet acquired.

---

## 6. Remaining M1 work

**None. M1 is complete.** Deferred items below are *by design* and do not block
M1 sign-off or M2 start:
- **PPB Option C all-species ablation processing** (K-5) — runs when the ablation is scheduled per Option C §3 (after M2 architecture + compute cost are known). Raw files on disk; no new download.
- **KERMT graph-featurizer schema adapter** — pinned at M2 pre-flight; the `mars-graph-v1` schema is a portable superset until then.
- **3D conformers at full dataset scale** — lazy/expensive per the blueprint; Run 4 warmed a representative subset + a 150-molecule sample. Full population is on-demand (Module 8) or an explicit `build_cache.py` run.

---

## 7. Risks / blockers requiring maintainer input

| ID | Item | Needs |
|---|---|---|
| CF-M1-1 | Blueprint Module 1 §4 wording vs. `hERG_Karim` | ✅ RESOLVED 2026-08-30 — §4 wording fix applied; §6 DILIst note refreshed; Module 2 DILI N updated to 1,111. |
| CF-M1-2 | PPBR_AZ `single_pred` vs benchmark-group size mismatch | ✅ RESOLVED 2026-08-30 — Option C locked. Primary human PPB processed (K-1..K-4, K-6); all-species pooled retained provenance-tracked for a later scheduled ablation (K-5). |
| CF-M1-5 | Status-doc path convention | ✅ RESOLVED 2026-08-30 — repo convention `documentation/status/mars-status_M<n>.md` accepted. |
| DILIst source | ✅ RESOLVED 2026-08-30 — DILIPredictor gold standard (MIT), 1,111 SMILES-resolved compounds. Provenance recorded. |
| hERG endpoint→dataset | ✅ RESOLVED 2026-08-30 — keep `hERG_Karim` (large-data KERMT rationale). |
| No-paid-compute (GPU) | ✅ RESOLVED 2026-08-30 — blueprint edited; RunPod paid fallback removed, free-tier cloud notebooks are the fallback. Whole training + ablation budget now stated as $0. |
| No-paid-infra (serving) | ✅ RESOLVED 2026-08-30 — maintainer chose **Google Cloud Run** (backend + async worker; Cloud Tasks queue; Neon/Upstash/Vercel/R2/Resend stay free-tier). $0 at demo scale. Blueprint Modules 8/10/12/13/14 + `.env.example` updated. |

**No open blockers for M2.** M2 pre-flight items (KERMT checkpoint identity,
CPU-inference feasibility for the Cloud Run serving assumption, free-tier
smoke-finetune, KERMT featurizer package + Stage-2 schema pin) are tracked in
`AIMS/next_steps.md` and belong to M2, not M1.
