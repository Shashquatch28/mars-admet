# PPBR_AZ single_pred vs benchmark size mismatch — Run 2 investigation

**Motivating gap (CF-M1-2, `mars-status_M1.md` §3).**
Acquisition recorded PPBR_AZ `single_pred` at **1,614 rows** (below the blueprint's headline 1,797) while the TDC ADMET Benchmark Group split totalled **2,790 rows** (2,231 train_val + 559 test). Every other benchmark-group dataset is a clean partition of its `single_pred` full set — PPBR_AZ is the only exception.

## Finding

The PPBR_AZ dataset TDC redistributes is a **multi-species** collection. The raw `ppbr_az.tab` file TDC delivered contains **2,828 rows over 1,797 unique compounds** with an extra `Species` column:

| Species | rows | unique compounds |
|---|---:|---:|
| *Homo sapiens* | 1,614 | 1,614 |
| *Rattus norvegicus* | 717 | 717 |
| *Canis lupus familiaris* | 244 | 244 |
| *Mus musculus* | 162 | 162 |
| *Cavia porcellus* | 91 | 91 |
| **union** | **2,828** | **1,797** |

The two loaders slice this differently:

- **`tdc.single_pred.ADME(name='PPBR_AZ')`** filters to **human only** → 1,614 rows / 1,614 unique compounds. Same number as *Homo sapiens*, and single_pred ⊆ *Homo sapiens* exactly. The species column is dropped in the returned frame.
- **`tdc.benchmark_group.admet_group.get('PPBR_AZ')`** pools **all species** (also dropping the species column). The scaffold split partitions the **1,797 unique compounds** (1,454 in train_val, 343 in test; no compound appears in both sides) but each compound can carry 1–5 measurements. `train_val` = 2,231 measurements over 1,454 compounds; `test` = 559 measurements over 343 compounds. Distribution: max = 5 measurements/compound, ~551/1,454 (~38%) of train_val compounds have >1 measurement.
- The 2,828 → 2,790 gap (38 rows) is TDC's own de-duplication inside the benchmark archive.

Sample of a training-set compound (`CHEMBL493677`, 3 rows in train_val):
`Y = 95.53, 91.64, 88.11` — the model sees three copies of the same SMILES with slightly different labels but **no species column**.

## Why this matters

Choosing between the two forms is a scientific decision, not a bookkeeping one:

**Option A — `benchmark_group` (all species pooled, leaderboard-comparable).**
- Reproduces TDC's ADMET Benchmark Group protocol verbatim, so PPB numbers can be reported next to leaderboard entries directly (Module 11 §4 discipline).
- Model input is `(SMILES) → Y`, but Y is an unlabelled mixture of species — the same molecule can have `Y=95` from a human assay and `Y=88` from a rat assay in the training pool. The learned target is a distributional average across whatever species the compound was measured in, not "human plasma protein binding fraction." For a *clinical* decision aid this is a real hidden assumption.
- Compound-level scaffold split is clean (no train↔test compound overlap). But the standardization + dedup pipeline in Run 2 must be told **not** to average the multi-measurement compounds silently, or that mixture-of-species meaning gets erased.

**Option B — `single_pred` (human only, ~1,614).**
- Clean scientific target: human PPB. Matches how the blueprint describes the endpoint ("Plasma protein binding").
- Loses direct leaderboard comparability for PPB — the same trade-off already accepted for hERG (see the Module 1 §4 hERG-exception paragraph added 2026-08-30). Would need the same "not directly comparable" caveat in Module 11's PPB row.
- ~10% below the blueprint's stated N (1,614 vs 1,797) because the blueprint's headline number is the multi-species compound count.

**Option C — human-first hybrid.**
Train and evaluate the primary reported model on the human subset (Option B's scientific target); *optionally* report a second, leaderboard-comparable model trained on the benchmark split as an ablation. Adds one training run per seed to the compute budget but keeps both the science and the leaderboard row honest.

## What Run 2 does now (pending the choice)

- Standardization + EDA are run over **both** representations (both `PPBR_AZ.full.csv` and the benchmark `train_val`+`test`). Numbers land in the same EDA report so the choice can be made against real data, not intuition.
- Splitting for PPB is **deferred** until the choice is made. All other 13 endpoints proceed.
- Dedup/conflict-resolution logic will treat any repeated `(standardized SMILES, Y)` triple as a duplicate; a repeated SMILES with *different* Y values is a conflict — this is where PPBR_AZ's multi-species measurements will surface as elevated conflict rate in EDA, giving an evidence-based signal for the choice.
- Nothing else in Run 2 depends on the outcome.

## Not decided (needs maintainer input)

Which of A / B / C to use for PPB in MARS. The recommendation is **Option C** (human primary, all-species ablation) — matches the honesty already established for hERG, and the compute cost is small compared to Module 11's ablation matrix — but this is the maintainer's call, not the pipeline's.
