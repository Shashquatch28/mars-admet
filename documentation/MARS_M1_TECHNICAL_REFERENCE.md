# MARS — Milestone 1 Technical Reference

**Data & Featurization (blueprint Modules 1 + 3)**

> **Purpose.** A single, exhaustive reference for every engineering, domain,
> dataset, and architecture decision made in Milestone 1 — written to be cited
> directly when drafting the project report or a paper. Everything here is
> traceable to code, a generated artifact, or a dated decision in
> `documentation/AIMS/decisions.md`.
>
> **Status.** M1 complete as of 2026-08-30. Delivered in four reviewed runs
> (Run 1: environment + acquisition; Run 2: standardization + EDA + dedup +
> split + calibration + augmentation; Run 3a/3b: featurization stages 2–5 +
> batch pipeline; Run 4: caching + comprehensive tests + this document).
>
> **Source of truth.** `documentation/mars-blueprint_v4.md`. Where this
> document and the blueprint disagree, the blueprint wins and the disagreement
> is a bug in this document.

---

## 1. Project overview

MARS is an AI-powered ADMET (Absorption, Distribution, Metabolism, Excretion,
Toxicity) and drug-safety screening platform. It predicts **14 endpoints**
(13 machine-learned + 1 rule-based synthetic-accessibility score) from a single
SMILES string, and is designed to support both a working product and a
publication (target venues: MLSB / AI4Science).

Reproducibility, provenance, deterministic processing, leakage prevention, and
auditable datasets are treated as first-class requirements, not add-ons. Every
dataset transformation in M1 emits a hashed, versioned, timestamped record.

### 1.1 The 14 endpoints

| # | Endpoint (contract key) | Category | Task | Metric | TDC dataset | Multi-task cluster |
|---|---|---|---|---|---|---|
| 1 | `solubility_logs` — Aqueous solubility (logS) | Absorption/Physchem | regression | MAE | `Solubility_AqSolDB` | absorption_distribution |
| 2 | `lipophilicity_logp` — Lipophilicity (logP) | Absorption/Physchem | regression | MAE | `Lipophilicity_AstraZeneca` | absorption_distribution |
| 3 | `caco2_permeability` — Caco-2 permeability | Absorption | regression | MAE | `Caco2_Wang` | absorption_distribution |
| 4 | `hia_absorption` — Human intestinal absorption | Absorption | classification | AUROC+AUPRC | `HIA_Hou` | absorption_distribution |
| 5 | `pgp_inhibition` — P-glycoprotein inhibition | Absorption | classification | AUROC+AUPRC | `Pgp_Broccatelli` | absorption_distribution |
| 6 | `bbb_permeability` — Blood-brain barrier | Distribution | classification | AUROC+AUPRC | `BBB_Martins` | absorption_distribution |
| 7 | `ppb_binding` — Plasma protein binding | Distribution | regression | MAE | `PPBR_AZ` (**human only**, Option C) | absorption_distribution |
| 8 | `cyp3a4_inhibition` — CYP3A4 inhibition | Metabolism | classification | AUROC+AUPRC | `CYP3A4_Veith` | metabolism |
| 9 | `cyp2d6_inhibition` — CYP2D6 inhibition | Metabolism | classification | AUROC+AUPRC | `CYP2D6_Veith` | metabolism |
| 10 | `cyp2c9_inhibition` — CYP2C9 inhibition | Metabolism | classification | AUROC+AUPRC | `CYP2C9_Veith` | metabolism |
| 11 | `clearance_microsomal` — Microsomal clearance | Excretion | regression | MAE | `Clearance_Microsome_AZ` | metabolism |
| 12 | `herg_cardiotoxicity` — hERG cardiotoxicity | Toxicity | classification | AUROC+AUPRC | `hERG_Karim` (**not in TDC benchmark**) | toxicity |
| 13 | `ames_mutagenicity` — AMES mutagenicity | Toxicity | classification | AUROC+AUPRC | `AMES` | toxicity |
| 14 | `dili_liver_injury` — Drug-induced liver injury | Toxicity | classification | AUROC+AUPRC | `DILI` + DILIst augmentation | dili_standalone |
| — | `synthetic_accessibility` — SA score | N/A | rule-based | — | none (Ertl & Schuffenhauer via RDKit) | — |

Endpoint keys are the locked `mars_contracts.Endpoint` enum values (M0 contract).
Cluster assignments come from `mars_contracts.ENDPOINT_METADATA` and drive
Module 4's multi-task design (out of M1 scope; recorded here for completeness).

### 1.2 Endpoints deliberately excluded

Half-life, Carcinogenicity, Skin Reaction (small/noisy — risk of unreliable
models undermining trust), VDss (specialist PK, not fast-triage), CYP *substrate*
variants (inhibition is the more decision-relevant DDI signal).

---

## 2. Environment & tooling architecture

Three isolated Python environments on the development machine (Windows 11,
PowerShell primary shell). They are kept separate on purpose — merging them
either breaks PyTDC's pins or drags a heavy stack into the API image.

| Env | Python | Purpose | Key packages |
|---|---|---|---|
| root `.venv/` | 3.11.9 | API + repo tooling. Runs the FastAPI stub, `contracts`/`api` tests, and repo-wide `ruff`. | fastapi, pydantic v2, uvicorn, httpx, ruff, pytest, `mars-contracts` (editable) |
| `ml/.venv/` | 3.11.9 | **M1 working environment.** Standardization, EDA, dedup, splitting, featurization, all ml tests. CPU-only (no torch). | numpy 2.4.6, pandas 2.3.3, scikit-learn 1.9.0, **rdkit 2026.3.5**, joblib 1.5.3, pytest 9.1.1, `mars-contracts` (editable) |
| WSL Ubuntu 24.04 `~/mars-acq-venv` | 3.12.3 | **Isolated TDC acquisition only.** Runs `ml/data/acquire.py`, nothing else. | `PyTDC==1.1.15` (installed `--no-deps`), numpy<2, pandas 2.2.3, scikit-learn 1.9.0, tqdm, fuzzywuzzy, requests, packaging, setuptools<81, huggingface_hub, openpyxl |

**Why PyTDC is isolated.** Every modern PyTDC (0.4.17–1.1.15) hard-pins
`numpy<2.0.0` and `rdkit<2024.3.1`, and declares `tiledbsoma`, which has **no
Windows wheel**. Those heavy deps (`tiledbsoma`, `cellxgene-census`, `gget`,
`biopython`, `transformers`, `accelerate`, `datasets`, `seaborn`) are only
imported by TDC's multi-omics / model-server modules — never by
`tdc.single_pred` or `tdc.benchmark_group`. Installing PyTDC `--no-deps` plus a
pinned minimal runtime gives a working ADMET-dataset loader and lets `ml/.venv`
stay on NumPy 2.x / RDKit 2026.3. `packaging`, `setuptools<81` (for
`pkg_resources`, removed in setuptools 81), and `huggingface_hub` (imported
eagerly by `tdc/__init__.py`) are additionally required.

Pinned manifests: `ml/requirements-m1.txt` (+ `ml/requirements-m1.lock.txt`),
`ml/data/requirements-acquire.lock.txt` (SHA-256 recorded in the acquisition
lockfile).

### 2.1 WSL↔Windows quoting trap

`wsl -d Ubuntu -- bash -lc '…'` mangles quoting whenever the script or a path
contains a space (the MARS repo path does). The acquisition is always driven by
piping the script to `bash -s` over stdin instead.

---

## 3. Module 1 — Data pipeline

### 3.1 Acquisition (`ml/data/acquire.py`, `ml/data/dataset_registry.py`)

All datasets are pulled through **PyTDC 1.1.15** — programmatic, versioned,
reproducible by construction (blueprint Module 1 §1). No manual downloads.

**What is acquired** (15 dataset snapshots):

- 11 ADME datasets via `tdc.single_pred.ADME`
- 4 Tox datasets via `tdc.single_pred.Tox` (`hERG_Karim`, `hERG`, `AMES`, `DILI`)
- For the 13 datasets in TDC's **ADMET Benchmark Group**, the official fixed
  80/20 scaffold split is additionally pulled via
  `tdc.benchmark_group.admet_group` and stored alongside the full dataset.

Two hERG datasets are acquired deliberately: `hERG_Karim` (13,445, blueprint
Module 2 primary) and `hERG` (655, the benchmark-group dataset) — see §3.6.

**Storage layout** (`ml/data/raw/` is git-ignored, ~22 MB, immutable):

```
ml/data/raw/<TDC_name>/<acq_id>/
    tdc_download/<name>.tab        the exact bytes TDC delivered (verbatim)
    <TDC_name>.full.csv            normalized copy (Drug_ID, Drug, Y)
    benchmark_split/train_val.csv  official split (benchmark-group datasets only)
    benchmark_split/test.csv
    source_meta.json              per-dataset provenance
ml/data/raw/_tdc_benchmark_cache/<acq_id>/   the admet_group archive TDC shipped
```

`acq_id` = UTC timestamp (`20260830T181633Z` for the M1 snapshot). A re-run
writes a fresh `acq_id` directory and **refuses to overwrite** an existing one;
the previous lockfile is archived to `ml/data/metadata/history/` before a new
one is written. Nothing is ever destructively modified.

**The data-versioning lockfile** (`ml/data/metadata/datasets.lock.json`,
schema v1, git-tracked) answers, per blueprint Module 1 §5:

| Question | Field |
|---|---|
| Which PyTDC version? | `acquisition.pytdc_version` = `1.1.15` (read from `importlib.metadata`, not hardcoded) |
| Which dataset identifiers? | `datasets[*].tdc_name`, `datasets[*].benchmark_group_name` (TDC's resolved lowercase name), `acquisition.tdc_benchmark_group_dataset_names` |
| When acquired? | `acquisition.acquired_at_utc` + per-dataset `acquired_at_utc` |
| What raw files? | `datasets[*].raw_files[*]` — `path`, `sha256`, `bytes`, `n_rows`, `role` |
| What hash identifies the snapshot? | `datasets[*].snapshot_sha256` (see below) |
| Plus | `acquisition.repo_git_sha`, `acquisition.acq_env_lockfile.sha256`, `acquisition.platform`, `acquisition.python_version` |

**Snapshot hashing** (`ml/data/snapshot.py`). Two kinds:

- `sha256_file` — byte hash of a stored file.
- **`canonical_csv_digest`** — an *order-independent* SHA-256 over
  canonicalized `(SMILES, label)` pairs read back from the persisted CSV.
  Scheme id: `mars-canonical-rows-v1`. PyTDC does not guarantee row ordering,
  so a raw `df.to_csv()` byte hash would be fragile; this digest canonicalizes
  each row (numeric-string coercion so `1`, `1.0`, `"1.0"` collapse identically;
  `repr` for non-integer floats; a fixed null token for missing) then sorts
  before hashing. Computed by reading the written CSV — the same code path
  verification uses — so the acquisition-time digest can never drift from the
  value recorded.

**Determinism evidence.** Independent re-acquisition of DILI + Caco2 into a
throwaway directory produced byte-identical `snapshot_sha256` values (full set
and benchmark split).

**Acquired sample counts vs. blueprint Module 2 headline N** (TDC has revised
datasets since the blueprint was written):

| Dataset | Acquired N | Blueprint N | Δ |
|---|--:|--:|---|
| Solubility_AqSolDB | 9,982 | 9,982 | exact |
| Lipophilicity_AstraZeneca | 4,200 | 4,200 | exact |
| Caco2_Wang | 910 | 906 | +4 |
| HIA_Hou | 578 | 578 | exact |
| Pgp_Broccatelli | 1,218 | 1,212 | +6 |
| BBB_Martins | 2,030 | 1,975 | +55 (+2.8%) |
| PPBR_AZ (human, `single_pred`) | 1,614 | 1,797* | −183 (see §3.7) |
| CYP3A4_Veith | 12,328 | 12,328 | exact |
| CYP2D6_Veith | 13,130 | 13,130 | exact |
| CYP2C9_Veith | 12,092 | 12,092 | exact |
| Clearance_Microsome_AZ | 1,102 | 1,102 | exact |
| hERG_Karim | 13,445 | 13,445 | exact |
| hERG (benchmark) | 655 | ~648 | +7 |
| AMES | 7,278 | 7,255 | +23 |
| DILI | 475 | 475 | exact |

\* the blueprint's 1,797 is the multi-species compound count; see §3.7.

The lockfile records exact N and a per-dataset
`n_matches_blueprint_within_5pct` flag (false only for PPBR_AZ under the human
subset).

### 3.2 Standardization (`ml/featurize/standardize.py`) — Module 3 Stage 1

A reusable **library** (not a script). Every downstream consumer — dedup,
splitting, augmentation, all featurization stages — calls into it; none
re-implements standardization. Version id: **`mars-standardizer-v1`**.

**Ordered pipeline** (`_standardize_one`), components built once per batch:

1. Reject empty / non-string input → `empty-input`
2. `Chem.MolFromSmiles(raw, sanitize=False)`; failure → `smiles-parse-failed`
3. `Chem.SanitizeMol`; failure → `sanitize-failed` (+ RDKit error text captured)
4. `AssignStereochemistry(cleanIt=True, force=True)`; record `had_defined_stereo`
5. `rdMolStandardize.Normalizer().normalize` (nitro/azide/iminium/… rules)
6. `rdMolStandardize.LargestFragmentChooser().choose` — salt/counter-ion strip;
   record `fragment_stripped`; if 0 heavy atoms remain → `no-heavy-atoms-after-fragment-strip`
7. `rdMolStandardize.Uncharger().uncharge` then `Reionizer().reionize`; record `charge_changed`
8. (optional, **off by default**) `TautomerEnumerator().Canonicalize`
9. `RemoveHs`
10. re-`AssignStereochemistry`
11. `Chem.MolToSmiles(isomericSmiles=True, canonical=True)`

**Rejection reasons** are a closed set (`REJECTION_REASONS`): `empty-input`,
`smiles-parse-failed`, `sanitize-failed`, `no-heavy-atoms-after-fragment-strip`,
`unexpected-standardizer-error`. Each rejected molecule keeps its input SMILES
and reason for audit.

**Stereochemistry** (blueprint Module 3 §Stereochemistry):
- Defined stereocenters survive — `isomericSmiles=True` canonicalization means
  L- and D-alanine produce *different* canonical SMILES (verified by test).
- Undefined stereo is **not fabricated** — the chiral tag stays unset (RDKit
  default); the canonical SMILES carries no `@`.
- Tautomer canonicalization is opt-in (`canonicalize_tautomer=True`), off by
  default: RDKit's canonical tautomer is occasionally chemically
  counter-intuitive, and the blueprint does not prescribe a specific canonical
  form. 2-hydroxypyridine ⇄ 2-pyridone stay distinct with the default.

**Config** is a frozen dataclass; `version` is part of every downstream cache key.

**Validity on the acquired data: 100% across all 15 datasets** — not one raw
SMILES was rejected. (Standardization rejections *do* occur in the DILIst
augmentation source — see §3.8.)

### 3.3 Exploratory data analysis (`ml/data/eda.py`)

Lightweight, decision-gating EDA (blueprint Module 1 §3, Module 3
§Stereochemistry). Output: `ml/data/eda/20260830T191149Z/` —
`rollup.json` + `eda_report.md` + `per_dataset/<key>.json`. Version-linked to
`mars-standardizer-v1`.

Per dataset it computes, over standardized molecules with parseable labels:
validity rate + rejection reasons; unique-molecule count; duplicate rate at
standardized identity; molecules with multiple measurements; molecules with
conflicting labels; **conflict rate over multi-measurement molecules** (the
§3 tier driver); class balance / regression target distribution (min, p25,
median, p75, max, mean, std); **stereo-defined ratio**; scaffold diversity
(unique Murcko scaffolds, scaffolds/molecule, top-scaffold share, acyclic
share).

**Full EDA findings** (`eda_id=20260830T191149Z`):

| Dataset | Task | N raw | Valid % | Uniq mol | Dup % | Multi-meas | Conflicts | Conflict %(multi) | Stereo-def % | Uniq scaffolds | Top scaffold % |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| ames_mutagenicity | clf | 7,278 | 100.0 | 7,255 | 0.3 | 23 | 0 | 0.0 | 14.0 | — | — |
| bbb_permeability | clf | 2,030 | 100.0 | 1,966 | 3.2 | 60 | 11 | 18.3 | 35.3 | — | — |
| caco2_permeability | reg | 910 | 100.0 | 904 | 0.7 | 6 | 4 | 66.7 | 54.1 | — | — |
| clearance_microsomal | reg | 1,102 | 100.0 | 1,102 | 0.0 | 0 | 0 | 0.0 | 34.2 | — | — |
| cyp2c9_inhibition | clf | 12,092 | 100.0 | 12,051 | 0.3 | — | — | 16.2 | 30.5 | — | — |
| cyp2d6_inhibition | clf | 13,130 | 100.0 | 13,090 | 0.3 | — | — | 13.5 | 29.1 | — | — |
| cyp3a4_inhibition | clf | 12,328 | 100.0 | 12,296 | 0.3 | — | — | 3.2 | 29.0 | — | — |
| dili_liver_injury | clf | 475 | 100.0 | 474 | 0.2 | 1 | 0 | 0.0 | **0.0** | — | — |
| herg_cardiotoxicity | clf | 13,445 | 100.0 | 13,152 | 2.2 | — | — | 5.6 | 41.0 | — | — |
| herg_cardiotoxicity (benchmark) | clf | 655 | 100.0 | 616 | 6.0 | — | — | 23.1 | 54.8 | — | — |
| hia_absorption | clf | 578 | 100.0 | 578 | 0.0 | 0 | 0 | 0.0 | 58.3 | — | — |
| lipophilicity_logp | reg | 4,200 | 100.0 | 4,200 | 0.0 | 0 | 0 | 0.0 | 28.2 | — | — |
| pgp_inhibition | clf | 1,218 | 100.0 | 1,212 | 0.5 | 6 | 0 | 0.0 | 54.1 | — | — |
| ppb_binding (human) | reg | 1,614 | 100.0 | 1,614 | 0.0 | 0 | 0 | 0.0 | 36.0 | — | — |
| solubility_logs | reg | 9,982 | 100.0 | 9,478 | 5.0 | — | — | **94.0** | 9.8 | — | — |

(Per-dataset scaffold-diversity numbers are in the JSON; not all reproduced
here.)

**Key EDA conclusions that drove policy:**

- **100% standardization validity** everywhere.
- **Solubility_AqSolDB has a 94% conflict rate** over its duplicate compounds —
  the strongest data-quality signal in the corpus. Regression → averaged.
- **Caco2 67%, hERG-benchmark 23%, BBB 18%, CYP2C9 16%, CYP2D6 14%** conflict
  rates → non-trivial; drive the tiered policy (§3.4).
- **CYP3A4 3.2%, hERG_Karim 5.6%** — near the 5% threshold; hERG_Karim treated
  conservatively (majority-vote).
- **Stereo-defined ratio** for the blueprint-flagged endpoints: Pgp 54%,
  Caco2 54%, BBB 35%, CYP2C9 30%, CYP2D6 29%, CYP3A4 29% — all non-trivial,
  which is why Module 3 Stage 2/3 chirality handling matters. **DILI is 0%**
  (drug-name → structure resolution did not preserve stereo) — so the
  `useChirality=True` fix has no effect on DILI specifically.

### 3.4 Deduplication & conflict resolution (`ml/data/dedup.py`) — Module 1 §3

Version id: **`mars-dedup-v1`**. **EDA-gated tiered policy**, chosen per endpoint
from the EDA rollup by `select_policy_from_eda`:

| Condition | Policy |
|---|---|
| conflict rate < 5% **and** dataset N ≥ 1500 | `drop_conflicting` — keep singletons + consensus groups; drop any group with label disagreement |
| conflict rate ≥ 5%, **or** dataset N < 1500 | regression → `average`; classification → `majority_vote` |
| majority-vote tie (even split) | drop **only that molecule** |

`LOW_CONFLICT_THRESHOLD = 0.05`; `SMALL_DATASET_N = 1500` (keeps DILI, HIA,
Caco2, Clearance, Pgp, PPB-human, hERG-benchmark in the size-protected bucket;
blueprint names DILI explicitly). Groups where **all labels agree** are
collapsed regardless of policy (`consensus_kept`) — no information is lost;
only conflicting groups exercise the policy.

**Auditable output** — `resolution_report.json` per dataset: counts of
`consensus_kept` / `dropped_conflicting` / `averaged` / `majority_voted` /
`dropped_tie` / `singletons`, plus the full list of dropped SMILES and the
rationale string.

**Per-endpoint policy + outcome** (`prep_id=20260830T200000Z`):

| Dataset | Policy | Rationale | Dedup N (valid → unique) |
|---|---|---|--:|
| ames_mutagenicity | drop_conflicting | 0.0% < 5%, N ≥ 1500 | 7,278 → 7,255 |
| cyp3a4_inhibition | drop_conflicting | 3.2% < 5%, N ≥ 1500 | 12,328 → 12,295 |
| lipophilicity_logp | drop_conflicting | 0.0%, N ≥ 1500 | 4,200 → 4,200 |
| ppb_binding (human) | drop_conflicting | 0.0%, N=1614 | 1,614 → 1,614 |
| solubility_logs | average | 94% conflict (regression) | 9,980 → 9,478 |
| caco2_permeability | average | 67% conflict (regression) | 910 → 904 |
| clearance_microsomal | average | 0% (regression, size-protected) | 1,102 → 1,102 |
| bbb_permeability | majority_vote | 18.3% conflict (classification) | 2,030 → 1,955 |
| cyp2c9_inhibition | majority_vote | 16.2% conflict | 12,092 → 12,047 |
| cyp2d6_inhibition | majority_vote | 13.5% conflict | 13,130 → 13,085 |
| herg_cardiotoxicity | majority_vote | 5.6% (borderline; conservative) | 13,445 → 13,136 |
| herg_cardiotoxicity (benchmark) | majority_vote | 23.1% conflict | 655 → 607 |
| hia_absorption | majority_vote | 0% but N < 1500 | 578 → 578 |
| pgp_inhibition | majority_vote | 0% but N < 1500 | 1,218 → 1,212 |
| dili_liver_injury | majority_vote | 0% but N < 1500 (small-dataset override) | 475 → 474 |

### 3.5 Scaffold splitting & leakage prevention (`ml/data/split.py`) — Module 1 §4

Version id: **`mars-split-v1`**. Two paths:

1. **`adopt_benchmark_split`** — for the 12 endpoints whose primary dataset is
   in TDC's ADMET Benchmark Group, TDC's official 80/20 scaffold split is
   adopted **verbatim** (leaderboard comparability). The benchmark-delivered
   rows are standardized through Module 3 Stage 1 and the compound-level
   train_val / test membership sets re-derived.

2. **`scaffold_split(smiles, test_fraction=0.20, seed)`** — a deterministic
   Murcko scaffold splitter used for the 2 endpoints without an official split
   (`herg_cardiotoxicity` via `hERG_Karim`, and `ppb_binding` human-only under
   Option C). Algorithm: group standardized SMILES by Murcko scaffold
   (`ml/featurize/scaffold.py`, `MurckoScaffold.GetScaffoldForMol`, acyclic →
   `""` sentinel); sort groups descending by size then by scaffold string;
   place whole groups into test until the target fraction, then the rest into
   train_val — a group is never split across sides. `seed` deterministically
   shuffles equal-size groups.

**Fixed test set.** Written once per `prep_id` to
`ml/data/processed/<prep_id>/<dataset>/test.csv` with its SHA-256 in
`provenance.json`. A new `prep_id` starts a fresh snapshot without overwriting.
The test set is never used for model selection, tuning, calibration, or
iterative development — enforced by the calibration carve (§3.5.1) and the
integration test `test_five_seed_folds_never_touch_the_test_set`.

**Automated leakage audit** (`leakage_audit`, `build_split_report`,
`assert_no_leakage`):
- **SMILES-level overlap between train_val and test is a hard failure for every
  split method.**
- **Scaffold-level overlap (non-empty Murcko) is a hard failure for
  self-generated splits.** `hERG_Karim` and `ppb_binding` pass with zero.
- For **adopted TDC benchmark splits**, non-empty-scaffold overlap under our
  stricter Murcko-on-standardized-molecules definition is *logged, not failed*
  — it is a property of TDC's own protocol and is retained for leaderboard
  comparability. Observed counts: BBB 2, Caco2 3, Clearance 2, CYP3A4 3,
  CYP2C9 3, CYP2D6 3, HIA 1, hERG-benchmark 3. Each is recorded in that
  dataset's `split_report.json` `notes[]`.
- **Post-standardization SMILES collision:** one BBB benchmark compound had two
  distinct raw SMILES collapse to one canonical form under Module 3 Stage 1,
  landing on both sides. Resolved automatically: kept on the (fixed) test side,
  removed from train_val, logged in
  `bbb_permeability/split_report.json → post_standardization_leaks_removed_from_train_val`.

**5-seed CV** (`five_seed_train_val_folds`, seeds `(0,1,2,3,4)`,
`val_fraction=0.125` ≈ 10% of the full set) — scaffold-aware, deterministic per
seed, computed from `train_val` only. Not persisted at prepare time; the
training layer (M2) calls it.

#### 3.5.1 Calibration split (blueprint Module 4 / Module 5)

Carved from `train_val` **before** any CV division. Size =
`max(50, round(0.10 × |train_val|))` — a 10% share with a 50-compound floor.
Scaffold-aware (`scaffold_split(seed=42)`), and asserted disjoint from the
fixed test set at prepare time (`if set(cal) & set(test): raise`). Persisted as
`calibration.csv`; SHA-256 in `provenance.json`; `calibration_report.json`
records the rule, target, and achieved N. This split is shared infrastructure —
temperature scaling (Module 4) uses it now, conformal prediction (Module 5,
Post-MVP) reuses it later.

#### 3.5.2 Final split sizes (`prep_id=20260830T200000Z`)

| Dataset | Split method | train_val | test | calibration |
|---|---|--:|--:|--:|
| solubility_logs | adopt_benchmark | 7,518 | 1,960 | 752 |
| lipophilicity_logp | adopt_benchmark | 3,360 | 840 | 336 |
| caco2_permeability | adopt_benchmark | 724 | 180 | 72 |
| hia_absorption | adopt_benchmark | 461 | 117 | 50 (floor) |
| pgp_inhibition | adopt_benchmark | 967 | 245 | 97 |
| bbb_permeability | adopt_benchmark | 1,572 | 394 | 157 |
| **ppb_binding (human)** | **scaffold (seed 0)** | **1,291** | **323** | **129** |
| cyp3a4_inhibition | adopt_benchmark | 9,833 | 2,463 | 983 |
| cyp2d6_inhibition | adopt_benchmark | 10,469 | 2,621 | 1,047 |
| cyp2c9_inhibition | adopt_benchmark | 9,640 | 2,411 | 964 |
| clearance_microsomal | adopt_benchmark | 881 | 221 | 88 |
| **herg_cardiotoxicity** | **scaffold (seed 0)** | **10,509** | **2,627** | **1,051** |
| herg_cardiotoxicity (benchmark) | adopt_benchmark | 493 | 123 | 50 (floor) |
| ames_mutagenicity | adopt_benchmark | 5,802 | 1,453 | 580 |
| dili_liver_injury | adopt_benchmark | 378 | 96 | 50 (floor) |
| **dili_liver_injury__augmented** | scaffold + DILIst merge | **1,119** | 96 (frozen) | 112 |

### 3.6 hERG exception (blueprint Module 1 §4, added 2026-08-30)

`hERG_Karim` (13,445) is **not** part of TDC's ADMET Benchmark Group — the
published TDC hERG leaderboard is computed on the 655-compound `hERG` (Wang).
Consequences:

- hERG gets a **self-generated deterministic Murcko scaffold split** replicating
  the 80/20 / no-shared-scaffold methodology (seed 0). Zero non-empty-scaffold
  overlap between train_val and test.
- hERG results are reported as **not directly leaderboard-comparable**. The
  `hERG_Karim` choice is deliberate — the large-data regime is what motivates
  the KERMT backbone and the multi-task Toxicity cluster for this endpoint.
- Both `hERG_Karim` (primary) and `hERG` (benchmark alt) are acquired and
  processed; the benchmark alt exists for a possible future comparison.
- **Future work** (`documentation/FUTURE_SCOPE.md`): a MARS-built merged
  `hERG_Karim + ChEMBL + PubChem + BindingDB` superset, mirroring 2025–2026
  frontier work (UnihERG_DB; the Zhang/Chen series; a Feb 2025 preprint). The
  field's trend is to *pool* `hERG_Karim`, not replace it — Karim remains the
  credible backbone dataset.

### 3.7 PPB Option C exception (blueprint Module 1 §4 + Module 2, locked 2026-08-30)

The raw TDC `PPBR_AZ` file pools **five species** (*Homo sapiens* 1,614,
*Rattus norvegicus* 717, *Canis lupus familiaris* 244, *Mus musculus* 162,
*Cavia porcellus* 91 — 2,828 measurements over 1,797 unique compounds). The two
loaders slice it differently:

- `tdc.single_pred.ADME('PPBR_AZ')` → **human only**, 1,614 rows / 1,614
  compounds (species column dropped).
- `tdc.benchmark_group.admet_group.get('PPBR_AZ')` → **all species pooled**,
  2,231 + 559 = 2,790 measurements over 1,797 compounds, scaffold-split at
  compound level (species column dropped; ~38% of train_val compounds carry
  >1 measurement).

PPBR_AZ is the *only* dataset where the benchmark split is not a clean partition
of the `single_pred` set. Training on the pooled target would regress a scalar
that mixes human + rodent + dog PPB values with no species covariate — a hidden
assumption for a clinically-framed endpoint.

**Decision — Option C** (maintainer):

- **Primary MARS PPB endpoint = human only** (`single_pred`, N = 1,614).
  Independent deterministic Murcko scaffold split (seed 0), same policy shape as
  hERG. Reported as **not directly leaderboard-comparable**.
- **Secondary all-species pooled dataset** = retained, provenance-tracked
  (`dataset_registry.py` declares `ppb_binding__all_species` as a
  `benchmark_alt` variant; raw files already on disk), scheduled as a
  **comparability ablation only** — not on the M2 critical path, and only run
  once M2's training architecture and compute cost are confirmed (specifically
  whether swapping the PPB target requires re-training the whole multi-task
  cluster per seed).

The species-filter recipe (source, loader, inclusion/exclusion, dropped-row
count = 1,214, dedup policy, hash provenance) is documented in
`dataset_registry.py` above the primary spec. Full investigation:
`documentation/status/ppbr_az_investigation.md`.

`ml/data/prepare.py` sources the split method from the **registry**, not the
Run-1 lockfile (which still records PPB's benchmark_split from acquisition
time), and records both `registry_says_adopt_benchmark` and
`lockfile_had_benchmark_split` in provenance so the deliberate divergence is
auditable.

### 3.8 DILIst augmentation (`ml/data/dilist_augment.py`) — Module 1 §6

Version id: **`mars-augmentation-v1`**.

**Source of truth for labels:** the FDA / NCTR **DILIst** release (Thakkar et
al., 2020), hosted at the FDA Liver Toxicity Knowledge Base — a US federal
government work product, **public domain (17 U.S.C. § 105)**. DILIst is FDA's
own successor to DILIrank, built specifically to remove DILIrank's unusable
"Ambiguous-DILI-Concern" category for binary classification (1,303 drugs;
789 positive / 514 negative).

**Source of structures:** the DILIst release ships drug *names*, not SMILES.
Rather than rebuild a name→structure resolution step, structures come from the
**DILIPredictor** project's `DILI_Goldstandard_1111.csv` (Seal, Williams,
Hosseini-Gerami, Mahale, Carpenter, Spjuth, Bender — Cambridge / Broad /
Uppsala, bioRxiv 2024) — 1,111 SMILES-resolved, standardized drugs curated
directly from DILIst + DILIrank, **MIT-licensed** (no NC/ND conflict; consistent
with the criteria that dropped PharmaBench). Downloaded 2026-08-30 from
`github.com/srijitseal/DILI`, `data/DILI_Goldstandard_1111.csv`,
SHA-256 `a86fd3a71c6832aac5e89bcdc35bdd27c000d6449260e4467a92982ae8e89be6`,
1,111 rows (716 positive / 395 negative). Post-resolution attrition
(1,303 → 1,111, ≈13%) is consistent with independent replications.
Provenance record: `ml/data/augmentation/dilipredictor_v1/PROVENANCE.md`.

**Non-negotiable pipeline** (blueprint Module 1 §6, all enforced in code):

1. DILIst structures standardized through the **identical** Module 3 Stage 1
   pipeline (`standardize_batch`, same call). **15 of 1,111 rejected** —
   invalid phosphate SMILES (`[P](=O)(=O)O`, valence 6) in the DILIPredictor
   distribution; the raw rows are kept in `augmentation_report.json →
   rejection_samples[]`. 1,096 valid.
2. **Deduplicated against the fixed TDC DILI test set first.** **57 compounds
   dropped** for appearing in the held-out test set. This is the exact leakage
   the blueprint's §6 rule prevents, and it fired on real data.
3. Merged only into the DILI **train/val** pool (1,096 − 57 = 1,039 surviving,
   + base train_val 378 = 1,417 before dedup).
4. Re-run tiered dedup on the merged pool (classification, N < 1500 →
   `majority_vote`): 1,417 → 1,119 (216 consensus_kept, 903 singletons,
   **41 majority-vote ties dropped**, 0 conflicts).
5. Fresh scaffold-aware calibration carve (112) from the merged train_val.
6. **Post-merge leakage re-check.** `augmentation_report.json → leakage_audit`:
   **SMILES overlap between augmented train_val and test = 0** (hard requirement
   met); Murcko-scaffold overlap = 19 (expected for a small chemical space;
   surfaced honestly, not failed); calibration ∩ test = 0.

**Test-set identity:** the augmented dataset's `test.csv` is copied
byte-identical from the base DILI processed output — asserted by
`test_augmented_test_matches_baseline_test`.

**Result:** DILI training pool grows from ~475 unique compounds to **1,215**
(train_val 1,119 + test 96), matching the blueprint's Module 4 note that
augmentation crosses DILI into a range where joint training with the Toxicity
cluster becomes worth testing.

---

## 4. Module 3 — Featurization pipeline

All stages: deterministic, batched (per the blueprint's "critical
non-negotiable requirement"), and each exposes a `cache_key()` string folding in
every knob + a version tag.

### 4.1 Stage 1 — Standardization

See §3.2. Version `mars-standardizer-v1`.

### 4.2 Stage 2 — Molecular graph representation (`ml/featurize/graph.py`)

Version **`mars-graph-v1`**. Portable, backbone-agnostic; a thin adapter maps it
to KERMT's featurizer schema at M2 pre-flight (the KERMT-native schema pin is
deferred per the KERMT decision).

Output `MoleculeGraph`: `atom_features (n_atoms, 42) float32`,
`edge_index (2, 2·n_bonds) int64` (PyG-style directed; each undirected bond →
two directed edges with matching features), `edge_features (2·n_bonds, 10)
float32`.

**Atom feature vector — 42 dims, fixed order:**

| Block | Vocabulary | Dims |
|---|---|--:|
| atomic number | {B, C, N, O, F, P, S, Cl, Br, I} + other | 11 |
| degree | {0,1,2,3,4,5} + other | 7 |
| formal charge | {−2,−1,0,+1,+2} + other | 6 |
| **chirality tag** | {`CHI_UNSPECIFIED`, `CHI_TETRAHEDRAL_CW`, `CHI_TETRAHEDRAL_CCW`, `CHI_OTHER`} | **4** |
| hybridization | {SP, SP2, SP3, SP3D, SP3D2} + other | 6 |
| total H count | {0,1,2,3,4} + other | 6 |
| is aromatic, is in ring | binary flags | 2 |

`CHI_UNSPECIFIED` is bin 0 of the chirality block — an **explicit category**, so
undefined stereo is represented, never guessed (blueprint non-negotiable).
`chirality_bit_slice()` returns `(24, 28)` for tests.

**Bond feature vector — 10 dims, fixed order:** bond type
{SINGLE, DOUBLE, TRIPLE, AROMATIC} (4) + is-conjugated, is-in-ring (2) + bond
stereo {STEREONONE, STEREOZ, STEREOE, STEREOANY} (4).

**Verified:** L- and D-alanine atom features differ **only** in the chirality
block (checked by masking); disabling chirality collapses them; (E)- and
(Z)-2-butene produce different edge features; deterministic;
batch == singleton.

### 4.3 Stage 3 — Morgan / ECFP fingerprints (`ml/featurize/fingerprints.py`)

Version **`mars-morgan-r2-2048-chirality-v1`**. Blueprint spec, locked in
`MorganConfig` defaults and by `test_default_config_matches_blueprint`:

- `radius = 2`
- `n_bits = 2048`
- **`useChirality = True`** (RDKit default is `False`)
- standard ECFP (`useFeatures = False`)
- generated via `rdFingerprintGenerator.GetMorganGenerator(...).GetFingerprintAsNumPy` → `(2048,) uint8`

**Why `useChirality=True` matters** (blueprint Module 3 §Stereochemistry):
CYP2C9 — a MARS endpoint — shows systematic stereoselective metabolism (median
Vmax/CLint enantiomer ratios 0.43 / 0.60; warfarin is the textbook case). With
the RDKit default, two enantiomers produce identical ECFP4. **Verified:**
L- and D-alanine fingerprints differ (Tanimoto 0.71, not 1.0); disabling
chirality collapses them; an undefined-stereo molecule's fingerprint is
unchanged by the flag.

`tanimoto_similarity(a, b)` helper is included for Module 5's k-NN
applicability-domain distance (ECFP4 space) when that lands.

### 4.4 Stage 4 — RDKit 2D descriptors (`ml/featurize/descriptors.py`)

Version **`mars-rdkit2d-v1`**. The full `rdkit.Chem.Descriptors._descList`,
**217 descriptors** in RDKit 2026.3.5 (blueprint says "~200"; the whole set is
taken rather than a curated subset — a subset needs its own justification and
drifts silently).

- `DESCRIPTOR_NAMES` — the list **sorted and frozen at import**.
- **`DESCRIPTOR_SET_SHA`** = SHA-256 of the newline-joined name list
  (`84cea0bf91c3c74a…`). `assert_descriptor_set_matches(config)` raises
  `RuntimeError` if the running RDKit's descriptor set ever differs from what a
  cache/lockfile was built against — no silent feature-column drift.
- **Column j always corresponds to `DESCRIPTOR_NAMES[j]`** — a training pipeline
  can rely on position.
- Blueprint-named descriptors present: MolWt, TPSA, MolLogP, NumHDonors,
  NumHAcceptors, NumRotatableBonds (+ 211 more). Aspirin MolWt = 180.16.
- **Non-finite handling:** a few descriptors (notably `Ipc`) can overflow to
  `inf` on large fused-ring systems. The raw matrix keeps inf/NaN (imputation
  is a Module 4 modelling decision, not a featurization one);
  `descriptor_matrix` additionally returns a boolean `finite_mask` and a per-row
  `{descriptor: value}` dict of the offending values. Nothing is silently
  imputed or dropped.
- 2D descriptors are stereo-insensitive by construction — no chirality handling
  (expected, not an omission).

### 4.5 Stage 5 — 3D conformer generation (`ml/featurize/conformers.py`)

Version **`mars-etkdgv3-mmff94-lowest-of-n-v1`**.

- **ETKDGv3** embedding, `n_conformers = 10`, `randomSeed = 0xC0FFEE` (fixed →
  deterministic). One retry with `useRandomCoords=True` (still seeded) if the
  first embed produces nothing; total failure → `embedding-failed`.
- **MMFF94** optimization of the whole ensemble
  (`MMFFOptimizeMoleculeConfs`, `maxIters=2000`), guarded by
  `MMFFHasAllMoleculeParams`. **UFF fallback** when MMFF params are unavailable;
  the result records which force field was used. Both failing →
  `optimization-failed`.
- **Lowest-energy conformer** selected by MMFF/UFF energy; `energy_kcal_mol`
  and `n_conformers_tried` recorded.
- **Gasteiger partial charges** computed and attached per atom (NaN → `None`).
- Output → `contracts.conformer.ConformerResponse` via
  `ConformerResult.to_contract_dict(molecule_id)`: atoms
  (element, x, y, z, `partial_charge`), bonds (`order` incl. 1.5 aromatic),
  `energy_kcal_mol`, full `sdf_block` (`Chem.MolToMolBlock`).
- **No fabrication on failure** — a failed molecule returns
  `ConformerResult(ok=False, reason=…)` with empty atoms/bonds and
  `sdf_block=None`; `to_contract_dict` raises rather than emit a fake payload.
  Reasons: closed set `{smiles-parse-failed, embedding-failed,
  optimization-failed, unexpected-error}`.
- **Verified:** same SMILES + config → **byte-identical SDF** and identical
  energy across runs; aspirin → MMFF94, E ≈ 18.91 kcal/mol, 10 tried;
  contract round-trips; failure path produces no geometry.

### 4.6 Batch pipeline façade (`ml/featurize/pipeline.py`)

Version **`mars-featurize-pipeline-v1`**. `featurize_batch(raw_smiles,
PipelineConfig)` is the single batch entry point every caller uses (training
feature-matrix build, k-NN AD index, batch prediction).

- **Standardizes once** for the whole batch, then calls each requested stage's
  own batch function once — no hidden per-molecule loop at a higher layer.
- Returns `FeaturizedBatch`: `standardized_smiles`, `kept_input_indices`
  (callers re-align labels/metadata through this), and per requested stage an
  output aligned to `standardized_smiles`.
- 3D conformers are **off by default** (`want_conformers=False`) — expensive and
  lazy per the blueprint.
- `PipelineConfig.provenance()` → one bundle: `pipeline_version` + every active
  stage's version + `cache_key()`. This is exactly what the feature cache keys
  on and what an M2 training run records.

### 4.7 Feature + conformer cache (`ml/featurize/cache.py`)

Schema version 1. `FeatureCache(root)` — an inspectable, content-addressed,
on-disk store under `ml/data/cache/` (git-ignored).

- **Cache key** = `sha256(stage ␟ stage_cache_key ␟ standardized_smiles)`.
  Deterministic; identity is the standardized SMILES; the stage's `cache_key()`
  (which folds in every config knob + version) is *in the key*.
- **An incompatible config is never silently reused** — a changed radius / bit
  count / descriptor set / graph schema / conformer seed produces different key
  files. `<stage>/_config.json` records **every** `cache_key()` the cache has
  been written under, with first-seen time, entry count, and the library
  versions (`numpy`, `rdkit`, all five stage version strings) — the divergence
  is visible, not hidden.
- Layout: `<root>/<stage>/_config.json` + `<keyhash[:2]>/<keyhash>.{npy|npz|json}`.
  Morgan → `.npy` (uint8). Descriptors → `.npz` (`values` + `non_finite` JSON).
  Graph → `.npz` (`atom_features`, `edge_index`, `edge_features`, counts).
  Conformer → `.json` (full `ConformerResult`, including failures).
- Each `<stage>_cached(smiles_list, config)` helper: look up every input,
  compute the misses in **one** batched call, persist, return aligned to the
  input list (same drop-invalid-and-report convention as the non-cached batch
  APIs). Returns a `CacheStats(stage, hits, misses, computed, invalid)`.
- **Verified:** first pass computes, second pass is 100% hits, values
  byte-match direct computation; a changed config forces full recompute and
  both configs appear in `_config.json`; enantiomer graph features and
  conformer SDFs survive the round-trip identically; a conformer *failure* is
  stored and served from cache, not recomputed.

**Cache-build driver** (`ml/featurize/build_cache.py`) warms Morgan +
descriptors + graph over the union of unique standardized SMILES in a
`processed/<prep_id>/` snapshot, with an optional deterministic conformer
sample. Output: `ml/data/cache/build_report.json` (per-stage hit/miss/compute
counts + wall-clock). Run 4 populated the cache for
`{dili_liver_injury, dili_liver_injury__augmented, hia_absorption,
caco2_permeability, pgp_inhibition}` + a 150-molecule conformer sample:

| Stage | Molecules | Computed | Invalid | Wall-clock | Rate |
|---|--:|--:|--:|--:|--:|
| Morgan | 3,572 unique | 3,572 | 0 | 9.2 s | ~388/s |
| Graph | 3,572 unique | 3,572 | 0 | 10.6 s | ~337/s |
| RDKit 2D descriptors | 3,572 unique | 3,572 | 0 | 104.3 s | ~34/s |
| 3D conformers (deterministic sample) | 150 | 150 | **1 failed** | 534.6 s | ~3.6 s/mol |

Conformer sample: **149 MMFF94, 0 UFF, 1 failed** (embedding/optimization did not
converge for one molecule — stored as `ConformerResult(ok=False)`, not
fabricated; the UFF-fallback path is wired and counted but was not needed on
this sample). A second run of the same driver is 100% cache hits (0 s of
compute). These numbers confirm: RDKit fingerprints/graphs are fast enough to
featurize the whole ~120k-molecule corpus in minutes; descriptors are the
bottleneck at ~34/s (~1 hour for the full corpus, cached once); 3D conformers
are genuinely expensive (~3.6 s each) and correctly kept lazy.

---

## 5. Reproducibility & provenance

Every M1 artifact-producing step emits a hashed, versioned, timestamped record.

### 5.1 Version identifiers (all part of downstream cache keys / provenance)

| Component | Version id |
|---|---|
| Acquisition lockfile schema | `1` |
| Snapshot digest scheme | `mars-canonical-rows-v1` |
| Standardizer | `mars-standardizer-v1` |
| Dedup | `mars-dedup-v1` |
| Split | `mars-split-v1` |
| DILIst augmentation | `mars-augmentation-v1` |
| Prepare schema | `1` |
| Graph featurizer | `mars-graph-v1` |
| Morgan fingerprints | `mars-morgan-r2-2048-chirality-v1` |
| RDKit 2D descriptors | `mars-rdkit2d-v1` (+ `DESCRIPTOR_SET_SHA`) |
| 3D conformers | `mars-etkdgv3-mmff94-lowest-of-n-v1` |
| Pipeline façade | `mars-featurize-pipeline-v1` |
| Feature cache schema | `1` |

### 5.2 Key hashes (M1 snapshot)

| Artifact | Value |
|---|---|
| Acquisition `acq_id` | `20260830T181633Z` |
| PyTDC version | `1.1.15` |
| Acquisition env lockfile SHA-256 | `418ffe5afb0e2540…` |
| EDA `eda_id` | `20260830T191149Z` |
| Prepare `prep_id` (current) | `20260830T200000Z` |
| DILIPredictor source SHA-256 | `a86fd3a71c6832aac5e89bcdc35bdd27c000d6449260e4467a92982ae8e89be6` |
| RDKit descriptor-set SHA-256 (prefix) | `84cea0bf91c3c74a…` |
| Repo git SHA at acquisition | `daddcf7cddff04d9c19d949b7a3dfec9b39fec9e` |

Per-dataset `snapshot_sha256`, raw-file SHA-256s, and processed-file SHA-256s
are in `ml/data/metadata/datasets.lock.json` and each
`ml/data/processed/<prep_id>/<dataset>/provenance.json`.

### 5.3 Determinism guarantees (all test-enforced)

- Re-acquisition → identical snapshot digests.
- Re-running `prepare.py` with a fixed `prep_id` → identical processed CSVs.
- `standardize`, `molecule_graph`, `morgan_fingerprint`, `descriptor_row`,
  `generate_conformer` — identical output for identical input (byte-identical
  SDF for conformers under a fixed seed).
- `scaffold_split(seed)` and `five_seed_train_val_folds` — reproducible per seed.
- Cache round-trip — byte-identical to direct computation.

### 5.4 CF-5 fix (CPU-only provenance)

`ml/tracking/provenance.py` and `ml/utils/seed.py` had hard `import torch` at
module top, which broke provenance capture in the torch-free M1 environment.
Fixed: torch imports are lazy/guarded. `collect_environment()` reports
`torch_installed: False` cleanly; `set_global_seed(seed)` seeds Python + NumPy
always, torch only if present, and returns a small record for logging.

---

## 6. Data storage layout

```
ml/data/
  raw/                     git-ignored, immutable, ~22 MB
    <TDC_name>/<acq_id>/    tdc_download/*.tab, *.full.csv, benchmark_split/, source_meta.json
    _tdc_benchmark_cache/<acq_id>/
  metadata/                git-TRACKED
    datasets.lock.json     the data-versioning lockfile
    acquisition_report.md  human-readable acquisition summary
    history/               archived prior lockfiles
  eda/<eda_id>/            git-ignored — rollup.json, eda_report.md, per_dataset/*.json
  processed/<prep_id>/     git-ignored
    <dataset>/             train_val.csv, test.csv, calibration.csv, assignments.csv,
                           resolution_report.json, split_report.json,
                           calibration_report.json, provenance.json
    <dataset>__augmented/  + augmentation_report.json
    manifest.json, prepare_report.md
  cache/                   git-ignored — <stage>/_config.json + sharded entries, build_report.json
  augmentation/
    dilipredictor_v1/      DILI_Goldstandard_1111.csv (git-TRACKED), PROVENANCE.md
  LICENSES.md              git-TRACKED
```

Processed CSVs carry two columns: `standardized_smiles`, `label`.
`assignments.csv` carries one row per unique standardized SMILES:
`standardized_smiles`, `murcko_scaffold`, `fold ∈ {train_val, calibration, test}`.

---

## 7. Licensing (`ml/data/LICENSES.md`)

| Source | Datasets | License / basis | Status |
|---|---|---|---|
| TDC redistribution | all 14 endpoint datasets + `hERG` benchmark | **CC BY 4.0** (verified per-dataset against TDC's license pages; per-dataset `license_ref` in the lockfile) | Used |
| FDA / NCTR DILIst | DILI augmentation labels | **Public domain, 17 U.S.C. § 105** (US federal work product) | Used |
| DILIPredictor (`github.com/srijitseal/DILI`) | DILI augmentation structures | **MIT** | Used |
| PharmaBench | (BBB, Clearance candidate augmentation) | **CC BY-NC-ND 4.0** — NC conflicts with the commercial-platform framing; ND blocks derivative pipelines | **Dropped** (blueprint Module 1 §7); BBB + Clearance stay TDC-only |
| KERMT `nvidia/NV-KERMT-70M-v2` | M2 backbone | NVIDIA Open Model License (commercial + derivatives OK, no NC/ND) | M2 |

Attribution: cite Huang et al., *Therapeutics Data Commons* (NeurIPS 2021
D&B) + each dataset's primary publication + the DILIPredictor bioRxiv preprint +
the FDA LTKB DILIst release.

---

## 8. Test inventory

All ml tests run in `ml/.venv` from `ml/` (`../ml/.venv/Scripts/python.exe -m
pytest -q`). API/contracts tests run in the root `.venv`.

| Test file | Count | Covers |
|---|--:|---|
| `ml/tests/test_snapshot.py` | 8 | canonical digest: order-independence, int/float-string equivalence, content sensitivity, file hash |
| `ml/tests/test_dataset_registry.py` | 12 | registry ↔ `mars_contracts.Endpoint` drift guard; both hERG variants; both PPB variants; CC BY 4.0; 12 benchmark + 2 self-generated primaries |
| `ml/tests/test_acquisition_lockfile.py` | 8 | re-hash every raw file + snapshot digest from disk; PPBR partition anomaly pinned; blueprint-N flags |
| `ml/tests/test_provenance_cpu_only.py` | 5 | CF-5 — provenance + seeding without torch |
| `ml/tests/test_standardize.py` | 18 | salts, invalid, empty, stereo preservation, enantiomer distinctness, tautomer on/off, batch=singleton, determinism |
| `ml/tests/test_scaffold.py` | 5 | Murcko scaffold: aspirin→benzene, acyclic sentinel, batch=singleton |
| `ml/tests/test_dedup.py` | 12 | tiered policy selection; drop/average/majority-vote; ties; consensus; singletons |
| `ml/tests/test_split.py` | 8 | deterministic scaffold split; injected-leak detection; 5-seed disjointness; acyclic-bucket allowance |
| `ml/tests/test_prepare_outputs.py` | parametrized × 15 datasets | train∩test=∅, cal∩test=∅, cal⊂train_val, provenance versions + SHA-256 present, no scaffold overlap for self-generated splits |
| `ml/tests/test_dilist_augmentation.py` | 6 | 0 test-set overlap; test set frozen + byte-identical to baseline; calibration∩test=∅; train_val grew |
| `ml/tests/test_graph.py` | 15 | 42-D/10-D shapes; enantiomer distinctness confined to chirality bins; undefined stereo not fabricated; bond stereo; batch=singleton; determinism |
| `ml/tests/test_fingerprints.py` | 18 | r2/2048/`useChirality=True` defaults; enantiomer distinctness + its dual; Tanimoto; batch; determinism; cache-key sensitivity |
| `ml/tests/test_descriptors.py` | 16 | 217 count; sorted+frozen; aspirin MolWt; positional stability; non-finite via mask+dict; drift guard raises |
| `ml/tests/test_conformers.py` | 14 | MMFF94/UFF; energy recorded; aromatic 1.5 bonds; Gasteiger charges; contract round-trip; deterministic SDF; typed failure (no fabrication) |
| `ml/tests/test_pipeline.py` | 9 | standardize-once; stage alignment; pipeline==direct; conformers off by default; provenance bundle; determinism |
| `ml/tests/test_cache.py` | 13 | deterministic keys; hit/miss; incompatible-config recompute; provenance `_config.json`; per-stage round-trip identity; conformer failure cached |
| `ml/tests/test_m1_integration.py` | 5 | real processed slice through pipeline + cache; processed SMILES are standardization fixed-points; 5-seed folds never touch the test set; real conformer energies finite |
| **ml total** | **219 passed, 14 skipped** | (skips = paths that need an acquisition/prepare that isn't present, and the historic self-generated-scaffold check that only applies to hERG/PPB) |
| `contracts/tests`, `api/tests` | 12 | M0 contract + FastAPI stub — no regression |

---

## 9. Infrastructure decisions

### 9.1 Compute — nothing paid, anywhere (2026-08-30 maintainer directive)

- **Featurization + XGBoost baselines: local, CPU, free** (`ml/.venv`).
- **GNN training (M2): lab A100s (free), primary.** Access is
  walk-up/interactive; sessions end when the lab is needed for a class →
  checkpointing (model + optimizer + LR scheduler + **Python/NumPy/PyTorch RNG
  state**) synced to Cloudflare R2 is mandatory.
- **Fallback: free-tier cloud notebooks** — Kaggle Notebooks (P100 16 GB or
  2×T4, 30 GPU-hr/week quota) or Colab free (T4-class). **No paid GPU rental
  anywhere**, even as a fallback. The prior RunPod RTX 4090 paid fallback was
  removed from the blueprint.
- 16 GB free-tier VRAM < KERMT's recommended 32 GB → gradient checkpointing +
  small batch + gradient accumulation on the free tier; multi-task cluster runs
  that still OOM wait for a lab A100 session, not a paid card. This is the
  residual M2 schedule risk.
- Whole training + full-ablation compute budget: **~185 GPU-hours, $0.**

### 9.2 Serving — Google Cloud Run (2026-08-30 maintainer decision)

- **Backend (FastAPI) + async batch worker → Google Cloud Run** services,
  `min-instances=0`, scale-to-zero. ~1–3 s cold start accepted (vs Render
  free's 30–50 s, which is why Render free was originally rejected).
- **Async batch = Google Cloud Tasks → a dedicated Cloud Run worker endpoint**
  (retry/backoff by Cloud Tasks; no Celery broker, no always-on worker). SSE
  progress served from the backend reading job state in Redis.
- Everything else stays on its current free tier: Neon/Supabase (Postgres),
  Upstash (Redis), Vercel (frontend), Cloudflare R2 (object storage, kept over
  GCS for zero egress fees), Resend (email).
- **$0 at demo scale** (Cloud Run + Cloud Tasks always-free tiers); pay-per-use
  only under sustained real traffic, no always-on instance charge.
- CI/CD: GitHub Actions builds the container, pushes to Artifact Registry, and
  `gcloud run deploy`s backend + worker on merge to `main`.

---

## 10. Decision log (M1-relevant, dated)

Full text in `documentation/AIMS/decisions.md`. Newest first.

| Date | Decision |
|---|---|
| 2026-08-30 | **Serving → Google Cloud Run** (backend + worker only; Cloud Tasks queue; rest stays free-tier). |
| 2026-08-30 | **No paid compute anywhere** — RunPod paid fallback removed; free-tier notebooks are the fallback; budget stated as $0. |
| 2026-08-30 | **PPB Option C** — human-only primary (self-generated scaffold split, not leaderboard-comparable); all-species pooled = provenance-tracked ablation, off the M2 critical path. |
| 2026-08-30 | **hERG stays `hERG_Karim`** — not in the TDC benchmark group; self-generated Murcko split; not leaderboard-comparable; merged-superset logged as future work. |
| 2026-08-30 | **DILIst source = DILIPredictor gold standard** (MIT, 1,111 SMILES-resolved); FDA LTKB DILIst = label source of truth; Module 2 DILI N → 1,111. |
| 2026-08-30 | **Blueprint Module 1 §4** — added the hERG + PPB leaderboard-comparability exceptions. |
| 2026-08-30 | **M1 environment** — dedicated `ml/.venv` (NumPy 2.x / RDKit 2026.3); PyTDC isolated in a WSL venv, `--no-deps`. |
| 2026-08-30 | **M1 delivered in 4 runs** (env+acquisition / standardization+EDA+dedup+split+calibration+augmentation / featurization / caching+tests+docs). |
| 2026-08-30 | **GNN backbone = KERMT `nvidia/NV-KERMT-70M-v2`** (NVIDIA Open Model License; GROVER MIT is the fallback). — M2 scope. |
| 2026-08-30 | **Auth = server-side Redis sessions, not JWT.** — M3 scope. |

---

## 11. Known limitations & deferred items

**Deferred within M1 (not blockers):**

- **PPB Option C all-species ablation** — dataset variant declared and raw files
  on disk; processing runs only when the ablation is scheduled (Option C §3,
  after M2 architecture + compute cost are known).
- **KERMT graph-featurizer schema adapter** — the `mars-graph-v1` schema is a
  portable superset; the KERMT-native mapping is pinned at M2 pre-flight.
- **3D conformers at full dataset scale** — expensive and lazy per the
  blueprint; Run 4 warmed a representative subset + a conformer sample only.
  Full population happens on demand (Module 8 lazy computation) or as an
  explicit cache-build.

**Documented limitations carried into M2 reporting:**

- **hERG and PPB (human) results are not directly TDC-leaderboard-comparable**
  (§3.6, §3.7).
- **Adopted TDC benchmark splits contain low-count non-empty Murcko-scaffold
  overlap** under our stricter standardization (§3.5) — retained for
  comparability, surfaced per-dataset.
- **Solubility_AqSolDB has a 94% conflict rate** — its labels are averaged;
  worth an explicit caveat when reporting solubility numbers.
- **DILI has 0% defined stereochemistry** — `useChirality=True` has no effect
  on DILI specifically (structures came from name resolution).
- **Scaffold-split results generally overestimate prospective performance**
  (blueprint Module 4 caveat; a structural-frontier robustness check —
  Lo-Hi / DataSAIL, BBB priority — is Module 11 §5.5, Post-MVP-parallel).

**M2 pre-flight items (out of M1 scope, tracked in `AIMS/next_steps.md`):**
confirm the exact `NV-KERMT-70M-v2` checkpoint identity; verify KERMT CPU
inference latency for the Cloud Run serving assumption; smoke-finetune KERMT on
a 16 GB free-tier card with memory optimisation; add the KERMT featurizer
package to `ml/requirements.txt` and pin the Stage 2 graph schema to it.

---

## 12. File & module index

**Data pipeline** (`ml/data/`):

| File | Role |
|---|---|
| `dataset_registry.py` | dependency-free registry of the 15 dataset specs (TDC name, loader, task, license, benchmark-group status, PPB species-filter recipe) |
| `snapshot.py` | deterministic hashing (`sha256_file`, `canonical_csv_digest`, scheme `mars-canonical-rows-v1`) |
| `acquire.py` | TDC acquisition → raw snapshots + `datasets.lock.json` + `acquisition_report.md` (runs in the WSL acquisition env) |
| `eda.py` | per-dataset EDA → `eda/<eda_id>/` |
| `dedup.py` | tiered dedup / conflict resolution (`mars-dedup-v1`) |
| `split.py` | scaffold splitting, leakage audit, 5-seed CV (`mars-split-v1`) |
| `prepare.py` | driver: standardize → dedup → split → calibration → per-dataset provenance → `processed/<prep_id>/` |
| `dilist_augment.py` | DILIst augmentation (`mars-augmentation-v1`) |

**Featurization** (`ml/featurize/`):

| File | Role |
|---|---|
| `standardize.py` | Module 3 Stage 1 (`mars-standardizer-v1`) |
| `scaffold.py` | Murcko scaffold utility (single code path for split + leakage + EDA) |
| `graph.py` | Stage 2 molecular graph (`mars-graph-v1`) |
| `fingerprints.py` | Stage 3 Morgan/ECFP (`mars-morgan-r2-2048-chirality-v1`) + Tanimoto |
| `descriptors.py` | Stage 4 RDKit 2D descriptors (`mars-rdkit2d-v1` + set SHA) |
| `conformers.py` | Stage 5 ETKDGv3 + MMFF94/UFF conformers (`mars-etkdgv3-mmff94-lowest-of-n-v1`) |
| `pipeline.py` | batched façade `featurize_batch` (`mars-featurize-pipeline-v1`) |
| `cache.py` | on-disk feature/conformer cache (schema 1) |
| `build_cache.py` | cache-build driver over a `processed/<prep_id>/` snapshot |

**Supporting**: `ml/tracking/` (`ExperimentRun`, `collect_provenance` — torch
lazy), `ml/utils/seed.py` (`set_global_seed` — torch lazy).

**Documentation**: `documentation/mars-blueprint_v4.md` (source of truth),
`documentation/status/mars-status_M1.md` (verification matrix + findings),
`documentation/status/ppbr_az_investigation.md`,
`documentation/FUTURE_SCOPE.md`, `documentation/AIMS/*` (decisions, context,
next steps, mistakes, glossary), this file.
