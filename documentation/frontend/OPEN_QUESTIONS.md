# Open questions — maintainer review required

Pass 1, 2026-09-30. **Blocking** questions gate the next design pass;
**non-blocking** ones gate implementation. Each states what the design does
today so work can continue either way.

---

## Blocking

### Q1 — Is MARS 14 endpoints or 15? — **RESOLVED 2026-10-06 (verified against code)**

**Resolution: 14 ML endpoints is the headline count; the roster renders 15
rows.** Evidence: `contracts/mars_contracts/endpoints.py` defines 15 `Endpoint`
members and `ML_ENDPOINTS` (all but `SA_SCORE`) = 14, enforced by
`contracts/tests/test_contracts.py` (`len(ML_ENDPOINTS) == 14`). The API
(`prediction_service.predict`, `stub_predictor`) defaults to `ML_ENDPOINTS`, the
sweep was 14 × 5 = 70, and the blueprint table has 14 numbered ML rows plus an
unnumbered "—" row for SA. The frontend already does this: `reconcile` counts
over ML only (`requested: 14`) and renders `ALL_ENDPOINTS` (15 rows). The only
off-by-one is prose — the blueprint heading and `AIMS/context.md` say
"13 ML + 1 rule-based"; it should read "14 ML + 1 rule-based". Not edited here
(blueprint and AIMS are maintainer-owned). Original text below for the record.

`Endpoint` has **15** members. `ML_ENDPOINTS` has 14 (all but
`synthetic_accessibility`). `AIMS/context.md` says "14 ADMET endpoints (13 ML +
1 rule-based)", and the M2 sweep was 14 endpoints × 5 seeds = 70 runs, which
matches `ML_ENDPOINTS`. So "14" in project prose means the ML set, while the
user-visible roster is 15 rows.

The UI must print a number in several places ("All 15 endpoints", "15 requested
· 14 returned"). **Currently the design says 15**, counting the rule-based SA
score as a visible endpoint. Confirm, and note that the AIMS phrasing
"13 ML + 1 rule-based" appears to be off by one against the enum.

### Q2 — `synthetic_accessibility` is filed under `ABSORPTION` — **RESOLVED 2026-10-06 (UI side; live-mode gap closed, ADR-019)**

**Resolution:** the UI keeps SA in its own trailing `RULE-BASED` group and
excludes it from every count (`AGENTS.md`; `reconcile.test.ts`). The contract's
`category: ABSORPTION` is left as is — it is unread by the grouping logic.

**Gap found 2026-10-06 — CLOSED by option (a), ADR-019:** the API never returns an SA
value on any path. `stub_predictor` skips `RULE_BASED` with `continue`, and
`prediction_service` filters it out before real inference; the stub's comment
says "served by rdkit rule" but no such code exists. Against the live API the SA
row will therefore render **NOT RETURNED** — a claim that the service failed to
return something it was never going to compute. Options: (a) the API computes
the Ertl–Schuffenhauer score with RDKit and returns it (matches the blueprint,
Module 12 "SA score"); (b) the UI renders a rule-based row with no prediction as
a distinct "not computed" state instead of NOT RETURNED. Note `deriveRowState`
checks `!prediction` before `rule_based`, so (b) is a small change there.
Recommend (a).
**Done:** option (a) implemented — `ml/serve/rule_based.py`, `prediction_service`, verified in the Docker image.

`ENDPOINT_METADATA` gives it `category: ABSORPTION`, `cluster: None`,
`task_type: RULE_BASED`. Grouping a rule-based synthesis score under absorption
is chemically odd and visually confusing next to logS and Caco-2.

**Currently the design puts it in its own `RULE-BASED` group** at the end of
the list, which contradicts the contract. Either the contract's category should
change, or the UI should follow the contract and accept the oddity. This needs
your call, not mine.

### Q3 — Per-endpoint display domain for regression intervals

ADR-005: regression intervals are printed, not drawn, because no validated
display range exists for logS, logP, Caco-2, PPB or clearance. This makes
regression rows less scannable than classification rows.

Options: (a) accept the asymmetry, which is the current design; (b) add a
frontend-owned per-endpoint display-domain table, derived from training-set
percentiles and clearly labelled as a *display* range with no interpretive
meaning; (c) add the range to the API response as real metadata.

(b) is the cheapest and the most dangerous — a display range is read as a
reference range whether or not it is labelled as one.

### Q4 — Interval labelling and the narrow-CI case

You named "unusually narrow confidence intervals" as a constraint the UI should
surface. There is currently no validated per-endpoint reference distribution of
interval widths, so **the design does not flag narrow intervals at all** — it
prints the width in the inspector and leaves the judgement to the reader.

Flagging would need a per-endpoint reference width distribution. Do you want
one computed from the existing 5-seed evaluations, or should this stay
unflagged until conformal prediction lands?

Related and already actioned: the interval is labelled `ENSEMBLE INTERVAL`, not
"95% CI", since `confidence_low/high` is ensemble spread across 5 seeds. Please
confirm that wording is the one you want users to see.

---

## Non-blocking

### Q5 — Should `per_endpoint_winner` be removed from the contract?

ADR-007 means the field is permanently unread by the UI. A nullable field no
client consumes is a standing invitation for a future client to consume it.
Recommend deprecating it in `mars_contracts/api.py` until direction-of-good is
validated. Contract change, so it is your call and out of scope here.

### Q6 — Model-generation selector behaviour

The top bar carries a permanent serving-generation readout
(`mars-routing@v0.3.1`) drawn as a picker. Unspecified: does switching
generations re-run the prediction, filter saved history, or both? This matters
for the "multiple model generations" goal and shapes whether the control
belongs in the shell or in the workspace.

### Q7 — Auth boundary in the shell

`/predict` and `/compare` are anonymous; `/batch/*`, `/molecules`, `/reports`
require a session. So two of the four rail destinations are gated. Currently
the rail shows all four with no gating affordance. Should locked workspaces be
marked in the rail, or should sign-in be prompted on entry?

### Q8 — Default density

Compact (30px) or comfortable (36px) as the shipped default? Compact fits all
15 endpoints at 1440×900 without scrolling, which is the argument for it.

### Q9 — Structure sketcher

`PredictEmpty` offers "Draw a structure" as an entry point, but no sketcher is
vendored — `package.json` has only `3dmol`. Is a sketcher (Ketcher, JSME) in
MVP scope, or should that affordance be removed from the design until it is?

### Q10 — Contract drift fix and CI check

`frontend/src/types/contracts.ts` is missing `EndpointPrediction.model_id`,
which ADR-008's stub detection depends on. Not fixed here, because this pass
was scoped to design only and the file is frontend source. Want it fixed as a
standalone change, with the CI check from ADR-009?

### Q11 — Reserved space for explainability

`/molecule/{id}/explain` is M4/Post-MVP (integrated gradients, fragment-level
attributions). The inspector has no attribution section. Reserve a slot in the
inspector's information architecture now, or add it when Module 6 lands?

### Q12 — Accent colour

The accent is an instrument cyan (`#49AEC4`), chosen to sit away from the
generic indigo/violet, to be distinguishable from amber by lightness as well as
hue, and to clear 7:1 on every surface. It is the one purely aesthetic decision
in the palette. Confirm or redirect.

---

# Pass 2 — 2026-10-01

### Q13 — `CRAFT_AND_INTERACTION.md` did not exist (resolved, confirm)

The pass-2 brief named this file as the source everything in it was drawn from.
It was not in the repository — pass 1 never created it. The brief was fully
self-contained, so nothing was blocked, and the file now exists as pass 2's
written record. Confirm that is what you wanted it to be, rather than a
document you were holding elsewhere.

### Q14 — 9px floor contradicts the brief's own "8.5px tags" — **RESOLVED 2026-10-01**

**Resolution: the 9px floor is locked.** Confirmed in pass 2.1. All micro-type
sits at 9px or above, condensed caps track at `0.09em`, and this is now a
standing constraint in `DESIGN_SYSTEM.md` and `ACCESSIBILITY.md` rather than an
open question. Original text below for the record.

**Blocking-ish.** The brief's hard constraints say *"No text below 9px"*, and
its typography section says *"verify condensed-caps optical tracking holds at
8.5px on the tags"*. Those cannot both hold.

Hard constraints were stated to outrank everything else, so **the 9px floor was
applied**: 8px nav labels and 8.5px tags and column heads all moved to 9px,
with tracking loosened `0.08em → 0.09em`. Density is essentially unchanged —
the Predict list still fits all 15 endpoints without scrolling.

If you actually wanted 8.5px tags kept, say so and I will revert the tags only;
the nav labels should stay at 9px regardless.

### Q15 — The endpoint name at rest — **RESOLVED 2026-10-01, reverted**

**Resolution: the name stays at `--text-primary` in every state.** The pass-2
demotion is reverted; ADR-014 is rewritten as a reversal.

The reasoning that settled it: the endpoint name is the **row identifier**, not
a field label. Table practice keeps the identifier prominent and demotes only
field labels and column heads — which in MARS means units, the `REG`/`CLS`
glyph, column heads and the source readout, all already at tertiary. Dimming
the identifier taxes the densest, most frequent scanning task in the product to
pay for a hover effect.

Hover now lifts the **surface** (`#0B0D0E` → `#101315`) alongside the row-rule
brighten. This yields a stronger rule than the one it replaces: *no interaction
state changes the contrast of any text*, which now holds absolutely.

### Q16 — The ⌘K palette is on the Interaction artboard, not over Predict

The brief asked for the palette rendered on the Predict result artboard.
Overlaying it there would cover the endpoint table — the exact grammar that
artboard exists to demonstrate — so the palette is drawn at full fidelity on
the new **Interaction & motion** artboard instead.

If you want it in situ over a dimmed workspace as well, that is a separate
artboard and I can add it.

### Q17 — Which cache state the reference artboard shows — **RESOLVED 2026-10-01**

**Resolution: the Predict result artboard shows a cache MISS** (`412 ms`,
`computed now · cached for 48 h`), so first-run latency and the skeleton
behaviour are visible on the canonical board. The inspector's provenance block
matches.

The **cache HIT** state is kept as a clearly labelled variant on the
Interaction & motion artboard, paired with the MISS chip under *Status bar —
cache states*, where the zero-skeleton rule that goes with it is also
specified. The two are distinguished by a filled versus hollow marker rather
than by colour, so the distinction survives greyscale.

### Q18 — The spring on the AD-gauge marker

ADR-013 records this as the one sanctioned exception to "nothing draws itself",
bounded hard: track and threshold drawn instantly, one marker settling, once,
placed instead of animated under reduced motion.

Flagging it explicitly rather than burying it, because it is the only place in
pass 2 where a brief instruction and a standing principle genuinely met. If you
would rather the gauge be fully static, the reduced-motion path is already the
design and costs nothing to make universal.

---

# Pass 2.1 — 2026-10-01

Corrections only. No new open questions were created.

**Resolved above:** Q14 (9px floor locked), Q15 (name reverted to primary),
Q17 (reference artboard shows a cache MISS).

**Also fixed, no decision needed:**

- **Canvas contradiction (ADR-015).** Pass 2 left the interaction taxonomy on
  two artboards. The States board now owns the six data/contract states only;
  the Interaction board owns default/hover/focus/active/primary/disabled. The
  States board carries a pointer so a reader expecting it there is redirected.
- **AD-gauge threshold tick.** Moved from `--text-quiet` to `--text-tertiary`.
  A sole-carrier graphical reference line needs 3:1 against everything it
  crosses; `--text-quiet` does not clear it. Now 5.4:1 against the track.
- **Covered-zone contrast** raised `#2A3336` → `#4A5558` (1.45:1 → 2.32:1
  against the track). Bounded from above by the marks it carries — see below.
- **Label collision rule** added: when the threshold and marker labels would
  overlap, the threshold label drops below the track. Both cases drawn.
- **States artboard row grammar** brought up to date: machined highlight on the
  selected row, 9px tags.

**One judgement call worth your eye.** The covered zone was *not* raised all
the way to 3:1 against the track, which would need roughly `#5C6A6E`. At that
lightness an in-domain (neutral) marker drops to ~2.6:1 against the zone it
sits on — the fill would clear the bar by pushing a mark below it. `#4A5558`
keeps every marker legible (amber 3.1:1, neutral 3.6:1) and the zone is a
reinforcing fill rather than a sole carrier: the tick, the labels, the legend
and the caption all state the same boundary. If you would rather have the
stronger zone and give the in-domain marker an outline to compensate, say so —
that is the other coherent way to resolve it.

---

# M4 scaffold — 2026-10-01

### Q19 — The AD-gauge threshold is not in the prediction response — **RESOLVED 2026-10-06 (ADR-020)**

**RESOLVED 2026-10-06 (ADR-020): option (a), `ad_threshold` is now in `EndpointPrediction`. The text below is the original question.**

**Blocking for a *live* gauge, not for the scaffold.** `EndpointPrediction`
carries `in_domain` and `knn_distance`, but **not** the per-endpoint threshold
the gauge draws its tick at. That threshold is the 90th-percentile of the
training set's own internal 5-NN distances (blueprint Module 5) — real, validated,
per-endpoint metadata that currently lives only in the ML artifacts.

The frontend holds a placeholder `AD_THRESHOLD` table in `domain/endpoints.ts`
(all 0.58) so the gauge renders in the prototype. Before the gauge is shown on
real predictions it must use real thresholds. Options: (a) add `threshold` (or
`domain_threshold`) to `EndpointPrediction` in the contract — cleanest, travels
with the value it describes; (b) expose a `/metadata` endpoint the client reads
once; (c) ship a versioned threshold table generated from the Module 5
evaluation, pinned to `model_version`. Recommend (a).

Until then, `in_domain` alone is honest (it is a real boolean from the model);
the *tick position* is the only part that needs the real number.

### Q20 — Styling approach (ADR-016), confirm

The scaffold uses CSS Modules over the token layer, not Tailwind v4 utilities —
see ADR-016 for the reasoning. This narrows the Tailwind half of ADR-001. Confirm
you are happy with that, or say the word and the token layer can be re-expressed
as a Tailwind `@theme` with utilities on the layout surfaces.
