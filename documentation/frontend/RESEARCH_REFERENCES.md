# Research references

External sources consulted during the pass-1 design phase (2026-09-30), and
what each one actually changed in MARS. Sources that only confirmed existing
intent are marked as such — the point of this file is traceability, not
citation count.

## Component architecture and source ownership

- [shadcn/ui design guide, 2026 edition](https://tomodahinata.com/en/blog/shadcn-ui-design-system-architecture-production-guide) — variant design with `cva`, the role of `cn()`, `asChild`/Slot polymorphism, CSS-variable themes, extension via composition.
- [shadcn/ui vs Base UI vs Radix, 2026](https://www.pkgpulse.com/guides/shadcn-ui-vs-base-ui-vs-radix-components-2026) — the 2026 state: Tailwind v4 and React 19 support, `data-slot` attributes on primitives, Base UI selectable alongside Radix.
- [shadcn/ui vs Radix UI (Vercel)](https://vercel.com/i/shadcn-vs-radix) — the boundary between unstyled primitive and owned component.

**Effect on MARS.** Directly shaped ADR-002. The ownership argument is what
makes it possible to enforce scientific honesty in a component's *type* rather
than in review: a `ReliabilityTag` whose variant union has no "good"/"safe"
member cannot be misused. The `data-slot` convention is adopted for styling
hooks so component internals stay addressable without prop explosion.

## Data density and technical interfaces

- [Designing for data density](https://paulwallas.medium.com/designing-for-data-density-what-most-ui-tutorials-wont-teach-you-091b3e9b51f4) — density as a shipped feature with real compact/comfortable options, not a default.
- [Data table UI reference, 2026](https://www.setproduct.com/blog/data-table-ui-design) — condensed / regular / relaxed row-height tiers.
- [Fonts for dense dashboards](https://fontalternatives.com/blog/best-fonts-dense-dashboards/) — tabular numerals as a hard requirement when numbers sit in columns.
- [Using Material Density on the Web](https://medium.com/google-design/using-material-density-on-the-web-59d85f1918f0) — density as a systematic axis rather than per-screen tuning.

**Effect on MARS.** The compact (30px) / comfortable (36px) toggle is a direct
consequence, as is the absolute mono-plus-`tabular-nums` rule for every
numeric cell. The "calm despite density" framing is the standard the Predict
results column is judged against — fifteen endpoints in one view without
chrome per row.

## Uncertainty communication

- [Wilke, *Fundamentals of Data Visualization* — visualizing uncertainty](https://clauswilke.com/dataviz/visualizing-uncertainty.html) — error-bar forms, and how easily they are misread.
- [Visualizing uncertainty to promote clinicians' understanding of measurement error (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC10623599/) — familiar CI formats still produce misconceptions in expert audiences; quantile dot plots measurably improved accuracy.
- [Uncertainty as a form of transparency (arXiv 2011.07586)](https://arxiv.org/pdf/2011.07586) — communicating model uncertainty as a transparency mechanism.

**Effect on MARS.** The strongest influence in this pass. Two concrete
outcomes. First, never state an interval's coverage without having it: the
column is labelled `ENSEMBLE INTERVAL`, because `confidence_low/high` is
ensemble spread across 5 CV seeds, not a 95% interval — an early draft of this
design mislabelled it and was corrected. Second, the "never assume the audience
knows what the bars mean" guidance is why the inspector states the interval's
derivation in words rather than relying on the mark alone. The clinician study
also argued against leaning on an unfamiliar mark for the primary read, which
supports keeping the point value in plain mono text as the headline.

## Applicability domain in ADMET tools

- [ADMETlab 2.0 (Nucleic Acids Research)](https://academic.oup.com/nar/article/49/W1/W5/6249611) — includes an explicit "Application Domain" feature alongside predictions.
- [ADMETlab (J. Cheminformatics)](https://jcheminf.biomedcentral.com/articles/10.1186/s13321-018-0283-x) — module structure of a systematic ADMET evaluation platform.
- [SwissADME (Scientific Reports)](https://www.nature.com/articles/srep42717.pdf) — login-free multi-molecule input and per-molecule result display.

**Effect on MARS.** Confirms that surfacing applicability domain per endpoint
is established practice in this domain rather than an invention, which
supports giving it a permanent column rather than a detail-panel field. MARS
deliberately goes further than these tools in two places: per-endpoint (not
per-molecule) domain flags, following the blueprint's Module 5 decision, and
refusing the composite drug-likeness style summary these platforms offer,
because MARS has no validated weighting across endpoints.

## Accessibility for data-heavy interfaces

- [Accessible data grid guide: `role="grid"`, 2-D keyboard navigation](https://accessibility.build/guides/accessible-data-grid) — roving tabindex, navigation vs actionable modes, Escape semantics.
- [Keyboard navigation patterns for complex widgets, 2026](https://www.uxpin.com/studio/blog/keyboard-navigation-patterns-complex-widgets/) — Tab between widgets, arrows within.
- [MUI X Data Grid accessibility](https://mui.com/x/react-data-grid/accessibility/) — `aria-rowcount` / `aria-rowindex` for virtualized grids.

**Effect on MARS.** The whole keyboard model in `INTERACTIONS.md`, and the
requirement that a virtualized batch grid report true row indices rather than
window positions. Also the rule that the focus indicator must be visually
distinct from the selection indicator — which happens to reinforce ADR-006's
channel separation for an unrelated reason.

## Keeping AI-assisted output from converging on the generic

- [The anti-slop framework for AI frontend craftsmanship](https://moelkholy1995.medium.com/beyond-make-it-beautiful-the-anti-slop-framework-for-ai-frontend-craftsmanship-c99bbee6c994) — why unconstrained generation converges on the statistical average dashboard.
- [Can AI follow design tokens?](https://uxmagic.ai/blog/ai-follow-design-tokens-honest-answer) — three-tier token architecture: raw scale, semantic alias, component-scoped.
- [Stop AI from ignoring your design tokens (DTCG + AGENTS.md)](https://atomize.tools/blog/figma-design-tokens-vibe-coding/) — machine-readable tokens plus an agent-facing instruction file.
- [The AI design stack: a workflow that stops the slop](https://dev.to/stevengonsalvez/the-ai-design-stack-three-skills-and-a-workflow-that-stops-the-slop-5a07) — decide creative direction in text before generating.

**Effect on MARS.** The reason this documentation directory exists at all, and
the reason `DESIGN_SYSTEM.md` is written as a token table an implementation can
emit verbatim rather than as prose. The specific failure these sources describe
— rounded cards, Inter, blue-violet gradients, one card per section — became
the explicit prohibition list in `UX_PRINCIPLES.md` and the "what this UI must
never do" panel on the States artboard. The "direction in text first" practice
is the sequence this phase actually followed: repository review, then contract
review, then principles, then tokens, then artboards.

## Not adopted

- **Quantile dot plots** for intervals, despite the accuracy evidence. They
  need more vertical space than a 30px row and are most valuable for a single
  focal estimate. Reconsider for the inspector's single-endpoint view, where
  the space exists — noted as a candidate rather than a decision.
- **Animated hypothetical outcome plots (HOPs)**, which the same literature
  supports for lay audiences. They violate the motion rules, and the audience
  here is expert.
- **A charting library.** The four data-viz primitives are twenty lines of
  markup each; importing a library would invite chart types the data does not
  support.
