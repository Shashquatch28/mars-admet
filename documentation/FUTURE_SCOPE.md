# MARS — Future Scope

Deliberately deferred work: things that are legitimate, citable improvements but
are **not** required for the current milestone plan (M1–M5, blueprint Module 14).
Nothing here blocks the MVP or the publication baseline. Each item records the
finding that motivates it so a future decision has the context it needs.

Newest first. Absolute dates only.

---

## 2026-08-30 — hERG: a merged multi-source superset as a citable upgrade

**Status:** future work. Does **not** change M1. M1 acquires `hERG_Karim`
(13,445 cmpds, blueprint Module 2 primary) *and* the 655-compound benchmark
`hERG`; the endpoint→dataset choice is settled in Run 2 after EDA
(`documentation/AIMS/decisions.md`, 2026-08-30).

**Finding.** `hERG_Karim` is absent from TDC's ADMET Benchmark Group — the
published TDC hERG leaderboard is computed on the 655-compound `hERG` (Wang et
al.). So results on `hERG_Karim` are not directly leaderboard-comparable, and
blueprint Module 1 §4's "the specific split required to make our results
directly comparable to published TDC leaderboard numbers" over-claims for this
one endpoint (flagged to the maintainer; wording fix proposed, not applied).

**Why this is not a reason to route around `hERG_Karim`.** The field's genuine
frontier work in 2025–2026 (UnihERG_DB; the Zhang/Chen series) is trending
toward **pooling `hERG_Karim` with ChEMBL / PubChem / BindingDB rather than
replacing it** — which is itself a signal that Karim remains the credible
backbone dataset, not something to treat as a liability. Switching to the small
benchmark `hERG` to buy leaderboard comparability would trade away the large-data
regime that motivates the KERMT backbone for this endpoint
(`documentation/AIMS/decisions.md`, 2026-08-30 KERMT entry) and would weaken the
multi-task Toxicity cluster.

**The deferred improvement.** Build MARS's own merged
`ChEMBL + PubChem + hERG_Karim` hERG superset, the way the February 2025 preprint
did — a legitimate, citable methodological contribution (larger, more chemically
diverse training pool; explicit provenance and de-duplication across sources;
leakage-checked against whichever test set MARS fixes). Carries its own
licensing review (ChEMBL approved-compound filter is open; PubChem BioAssay is
public domain; BindingDB is CC BY 4.0 — verify at build time) and its own
standardization + conflict-resolution pass through the Module 3 / Module 1 §3
pipeline before any merge.

**If/when tackled:** slot beside the Module 11 §5.5 robustness work (Post-MVP-
parallel). Report merged-superset hERG numbers *beside* the `hERG_Karim`-only
numbers, never as a silent replacement.
