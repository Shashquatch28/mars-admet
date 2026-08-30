# MARS datasets — licensing record

Blueprint Module 1 §7: dataset licensing is verified against project goals
before any source is used, not assumed. This file is the in-repo record.

MARS is framed as portfolio/publication work modeled on commercial platforms,
so **NonCommercial (NC) and NoDerivatives (ND) terms are disqualifying** for
training data.

## TDC-sourced endpoint datasets (all 14 endpoints)

**All confirmed CC BY 4.0**, verified against TDC's per-dataset license pages
(blueprint Module 1 §7). Attribution-only; commercial use permitted; derivatives
permitted. Several list "Not Specified. CC BY 4.0" — the *original* source
(e.g. AstraZeneca's 2016 disclosure) did not itself declare a license, but TDC's
redistribution terms are CC BY 4.0 and govern downstream use.

| Endpoint | TDC dataset | In ADMET Benchmark Group | License |
|---|---|:--:|---|
| Aqueous solubility (logS) | `Solubility_AqSolDB` | yes | CC BY 4.0 |
| Lipophilicity (logP) | `Lipophilicity_AstraZeneca` | yes | CC BY 4.0 |
| Caco-2 permeability | `Caco2_Wang` | yes | CC BY 4.0 |
| HIA | `HIA_Hou` | yes | CC BY 4.0 |
| P-gp inhibition | `Pgp_Broccatelli` | yes | CC BY 4.0 |
| BBB permeability | `BBB_Martins` | yes | CC BY 4.0 |
| Plasma protein binding | `PPBR_AZ` | yes | CC BY 4.0 |
| CYP3A4 inhibition | `CYP3A4_Veith` | yes | CC BY 4.0 |
| CYP2D6 inhibition | `CYP2D6_Veith` | yes | CC BY 4.0 |
| CYP2C9 inhibition | `CYP2C9_Veith` | yes | CC BY 4.0 |
| Clearance (microsomal) | `Clearance_Microsome_AZ` | yes | CC BY 4.0 |
| hERG cardiotoxicity (primary) | `hERG_Karim` | **no** | CC BY 4.0 |
| hERG cardiotoxicity (benchmark alt) | `hERG` | yes | CC BY 4.0 |
| AMES mutagenicity | `AMES` | yes | CC BY 4.0 |
| DILI (liver injury) | `DILI` | yes | CC BY 4.0 |

**Attribution:** cite Huang et al., *Therapeutics Data Commons* (NeurIPS 2021
Datasets & Benchmarks) plus each dataset's primary publication (recorded per
dataset in `ml/data/metadata/datasets.lock.json` → `license_ref`).

## Augmentation sources

| Source | Endpoint | Status | License / basis |
|---|---|---|---|
| **DILIst** (FDA / National Center for Toxicological Research) | DILI | **Adopted** (Module 1 §6) — acquisition + provenance handled in Run 2 (not a TDC dataset) | US federal government work product — **public domain, 17 U.S.C. § 105**. Low risk, no action needed. |
| **PharmaBench** | BBB, Clearance | **Dropped** (Module 1 §7) | **CC BY-NC-ND 4.0** per its Nature *Scientific Data* publication. NC conflicts with MARS's commercial-platform framing; ND blocks sharing adapted material and MARS's pipeline is inherently derivative. BBB and Clearance stay TDC-only. |

## Backbone / other

| Artifact | License | Notes |
|---|---|---|
| KERMT `nvidia/NV-KERMT-70M-v2` (M2) | NVIDIA Open Model License | Commercial + derivatives OK, no attribution/NC/ND. Clears Module 1 §7. (`documentation/AIMS/decisions.md`, 2026-08-30) |

_Last verified: 2026-08-30 (M1 acquisition). Re-check on any dataset/source change._
