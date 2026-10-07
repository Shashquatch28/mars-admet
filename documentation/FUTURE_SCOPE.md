# MARS — Future Scope

Deliberately deferred work: things that are legitimate, citable improvements but
are **not** required for the current milestone plan (M1–M5, blueprint Module 14). Items here may still change the
blueprint when the cut is made — the 2026-10-07 entry did.
Nothing here blocks the MVP or the publication baseline. Each item records the
finding that motivates it so a future decision has the context it needs.

Newest first. Absolute dates only.

---

## 2026-10-07 — Tier 1 (mixed-type trainer), Tier 2 (ordinal homogenization), Kendall / GradNorm loss weighting

**Status:** deferred by maintainer decision 2026-10-07. **Does change the blueprint** (Module 4 clusters and loss
balancing, Module 11 §6 ablation axis, the compute budget) — recorded in `documentation/AIMS/decisions.md` 2026-10-07 and
applied to `documentation/mars-blueprint_v4.md` the same day. The MARS product ships on **Tier 0**: stock KERMT, one task
type per subgroup, equal weighting.

**What is deferred.**

- **Tier 1 (path b)** — a MARS-owned trainer that imports KERMT as a library and can train mixed classification/regression
  clusters with type-correct losses and selectable weighting (`fixed` / `kendall` / `gradnorm`). Planned layout:
  `ml/train/kermt_mixed/` (`train_mixed.py`, `losses.py`, `sampler.py`, `scaling.py`, `gradnorm.py`, `metrics_hooks.py`) and
  `ml/models/kermt_mixed_model.py`. **None of it was written.** It would restore the original Metabolism and Absorption &
  Distribution mixed-type clusters. Four equivalence gates (G1 forward/inference parity, G2 one-epoch loss parity, G3
  multi-seed AUROC parity against stock KERMT on `ames_mutagenicity` and `toxicity__cls`, G4 Kendall-loss unit test) must pass
  before any mixed run is believed; their definitions are in `documentation/AIMS/next_steps.md` (Tier 1 section).
- **Tier 2 (path c)** — regression endpoints re-encoded as ordinal-CDF binary columns so a mixed cluster runs through the
  unmodified stock CLI. The codec (`ml/featurize/ordinal.py`) and the zero-GPU discretization-ceiling test exist
  (`n_bins = 16` clears the gate for all five regression endpoints; solubility is tightest at 23.3% of baseline MAE). The GPU
  gate (decoded MAE within 15% of direct regression) was **not run**. Investigate only after Tier 1.
- **Loss-weighting ablation** — Module 11 §6's fixed vs. Kendall vs. GradNorm axis, plus stratified batches, per-task
  log σₜ monitoring and the fixed-weight fallback. All of it needs Tier 1: the stock `run_finetune_local.py` never forwards
  `--use_mtl_loss`, so stock KERMT can only produce the equal-weighting arm.

**Cost estimate if revived (rough, 2026-10-07; none of it measured).** About 45–50 GPU-hours: G3 parity 10 runs (about
10 h), then fixed / Kendall / GradNorm × 5 seeds on each of the two mixed clusters (30 runs, about 37 h), assuming a mixed
cluster costs the sum of its pure parts (about 1 h Metabolism, about 1.2 h A&D) and GradNorm about 1.4× for its extra backward
pass. At about 4 usable hours per workstation session that is 11–13 sessions. Writing and debugging the trainer is on top of
that and has no estimate. Tier 2's GPU work is on top again.

**What was given up.** (1) Cross-type transfer inside a cluster — Clearance no longer trains with the CYP endpoints. (2) Any
Kendall / GradNorm result; uncertainty weighting was **never tested**, so this is a scope cut, not evidence against it. (3) The
"one forward pass per cluster" property for Metabolism and Absorption & Distribution — each now needs two forward passes.

**If/when tackled:** read `documentation/AIMS/decisions.md` 2026-09-20 (three-tier ladder, the cross-endpoint split-leakage
finding, the Kendall reparameterization note) and 2026-10-07 first. The original blueprint text, preserved verbatim below,
is the design to start from; the Module 4 cluster table of the earlier blueprint (Metabolism: CYP3A4, CYP2D6, CYP2C9,
Clearance; Absorption & Distribution: logS, logP, Caco-2, HIA, P-gp, BBB, PPB) is what Tier 1 would restore. Report any
Tier-1 result beside the Tier-0 numbers, never as a silent replacement.

### Preserved original text — blueprint v4, Module 4 "Multi-task loss balancing" (verbatim as of 2026-10-06)

### Multi-task loss balancing
`LAUNCH SCOPE: MVP`

**Which clusters actually need this:** two of the three clusters mix task types — Metabolism (3 classification: CYP3A4/2D6/2C9 + 1 regression: Clearance) and Absorption & Distribution (4 regression: logS/logP/Caco-2/PPB + 3 classification: HIA/P-gp/BBB). Toxicity (hERG, AMES) is classification-only. This matters because it changes which method is actually well-matched to the problem — see below.

**Evidence base:** The most directly domain-matched paper found (QW-MTL, Zhang et al. 2025 — the first systematic multi-task study across all 13 TDC ADMET classification tasks, built on Chemprop-RDKit) uses a learnable, data-scale-aware exponential weighting scheme and outperforms single-task baselines on 12/13 tasks, with the largest gains (≈7%) on the smallest datasets (DILI, CYP2C9/2D6 Substrate). **However, it explicitly excludes regression tasks from its scope** ("tasks related to excretion... are primarily regression tasks, and thus are excluded from the scope of this study") — meaning the one paper that matches our domain doesn't actually solve our specific problem, since two of our three clusters mix MAE and BCE losses. This is a real gap in the literature, not just in our own doc, and worth being explicit about rather than citing QW-MTL as if it settles the question.

For the actual mixed regression/classification case, the standard reference is **Kendall, Gal & Cipolla 2018** (homoscedastic uncertainty weighting) — notably, this method was originally developed and validated on exactly this kind of mix (depth regression + semantic segmentation classification, jointly), not adapted to it after the fact. Each task gets a learnable log-variance parameter σₜ; regression losses are weighted by 1/(2σₜ²), classification losses by 1/σₜ², with a log σₜ regularization term that prevents the trivial solution of driving all weights to zero. Simple to implement (a handful of extra learnable scalars, no architecture change), well-established (1,000+ citations, used across vision/robotics/molecular domains per the broader search), and directly applicable to Metabolism and A&D as specified without modification.

**Alternative — GradNorm** (Chen et al. 2018): dynamically reweights by equalizing gradient magnitudes/training rates across tasks rather than assuming a likelihood form. More robust to tasks with pathologically different loss scales, but requires an extra backward pass through a shared layer per step and more tuning (an asymmetry hyperparameter α). Worth keeping as the empirical alternative given Module 4's existing "empirical winner selection" philosophy, but not the default.

**Decision:**
- **Metabolism, Absorption & Distribution (mixed-type clusters):** Kendall uncertainty weighting as the default method — directly matches the problem shape, low implementation cost, strong precedent.
- **Toxicity (hERG, AMES — classification-only):** either uncertainty weighting (consistent with the other two clusters) or QW-MTL's simpler data-scale exponential weighting (directly domain-validated for pure-classification ADMET) are both reasonable; since Toxicity is only two tasks, the choice matters less than for the 4-7 task clusters.
- **Fixed/equal weighting** stays in as the mandatory baseline comparison, not the shipped method — Module 11 already treats "multi-task cluster vs. single-task" as an ablation axis; loss-balancing method (fixed vs. uncertainty-weighted vs. GradNorm) should be added as an additional ablation axis given how much this choice can affect results, rather than picked once and left untested.

**Kendall weighting under masked/sparse labels.** MARS's clusters use masked loss for missing labels (a compound isn't necessarily labeled for every endpoint in its cluster), and the interaction between that masking and Kendall's learned per-task $\log\sigma_t$ hadn't been worked through. The combination itself isn't novel risk — recent multi-task work (a 2026 wireless-channel-modeling paper) uses exactly this pattern, computing a presence-masked per-task loss (only labeled entries contribute) and then applying Kendall weighting on top of the resulting per-task scalars. The actual risk sits one level down: **batch-level label sparsity**, not the masking mechanism itself. If a given training batch happens to contain few or no labeled examples for a sparse task (e.g. Clearance inside the Metabolism cluster, given its 1,102-compound size against CYP3A4/CYP2D6/CYP2C9's 12,000+), that task's masked loss estimate for the batch is noisy — and since $\log\sigma_t$ is updated from these noisy per-batch values, its learned uncertainty can drift or become unstable for the sparsest task in a cluster, independent of whether the overall method is theoretically sound.

**Decision — layered mitigation, not a single fix:**
1. **Monitor by default (mandatory, cheap):** log each task's $\log\sigma_t$ trajectory during training as a standard diagnostic, not just a debugging afterthought — visible instability (oscillation, divergence) on a sparse endpoint is the concrete signal that the risk described above is actually occurring, rather than staying a theoretical concern.
2. **Stratified batch composition (primary preventive fix):** construct training batches to guarantee a minimum number of labeled examples per task within a cluster (oversampling compounds carrying the sparser labels) — this addresses the mechanism directly, rather than only detecting it after the fact.
3. **Fallback — fixed weight for a persistently unstable task:** if monitoring under #1 shows a specific task's $\log\sigma_t$ isn't stabilizing even with #2 in place, that task drops to a fixed (non-learned) weight within its cluster rather than forcing uncertainty weighting to work where the data doesn't support it — a targeted exception, not an abandonment of Kendall weighting for the cluster as a whole.

This is written in as a layered decision (do #1 always, apply #2 as the default engineering practice, reserve #3 as an evidence-gated escape hatch) rather than picking one option in isolation, since #1 costs nothing and #3 is only meaningful once #1 has actually surfaced a problem.

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
