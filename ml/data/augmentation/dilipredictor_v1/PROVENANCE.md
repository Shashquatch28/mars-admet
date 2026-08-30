# DILIPredictor DILI gold standard (v1) — augmentation source provenance

**Purpose.** Structures + labels used to augment the TDC DILI training pool per
blueprint Module 1 §6 ("Currently applied: DILI augmented with DILIst …").

**File.** `DILI_Goldstandard_1111.csv`
- Downloaded 2026-08-30 from `github.com/srijitseal/DILI`, path `data/DILI_Goldstandard_1111.csv`, branch `main`.
- URL: `https://raw.githubusercontent.com/srijitseal/DILI/main/data/DILI_Goldstandard_1111.csv`
- SHA-256: `a86fd3a71c6832aac5e89bcdc35bdd27c000d6449260e4467a92982ae8e89be6`
- Size: 195,950 bytes; 1,111 rows.

**Columns.** `smiles_r, TOXICITY, Source_rank, Source, Data, InChIKey, InChIKey14, protonated_smiles_r`.
Class balance: 716 positive / 395 negative.

**Source of truth for the labels.** FDA / NCTR *DILIst* release
(Thakkar et al., 2020; hosted at the FDA Liver Toxicity Knowledge Base, LTKB) —
a public-domain US federal government work product (17 U.S.C. § 105). LTKB is
the cited authoritative source for the label methodology; the DILIPredictor
distribution provides an already SMILES-resolved+standardized version so we do
not have to rebuild a name→structure resolution step.

**Source of the structures.** DILIPredictor (Seal, Williams, Hosseini-Gerami,
Mahale, Carpenter, Spjuth, Bender — Cambridge / Broad / Uppsala) —
[github.com/srijitseal/DILI](https://github.com/srijitseal/DILI), MIT license
(SPDX: MIT). Curated from DILIst + DILIrank with SMILES resolved and
standardized. Post-resolution attrition (~1,303 → 1,111, ≈13 %) is expected and
consistent with independent replications.

**Licensing (Module 1 §7).**
- Labels: US federal government work product, public domain (17 U.S.C. § 105).
- Distribution used: MIT (no NC/ND conflict; consistent with the disqualifying
  criteria that dropped PharmaBench).

**Downstream handling.** Standardized through the same Module 3 Stage 1
pipeline as every TDC dataset. Deduplicated against the TDC DILI **held-out
test set** (non-negotiable, blueprint Module 1 §6 leakage rule). Merged only
into the DILI train/val pool. Scaffold-overlap re-check is re-run
post-augmentation and the split is only accepted if it passes.
