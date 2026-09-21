# documentation/

**Git-tracked since `1c252ac` (2026-09-18).** This directory was previously
untracked by deliberate choice; that is no longer the case, so AIMS files are
part of review and should be updated in the same session as the work they
describe. `AIMS/decisions.md` still carries the provenance note explaining why
early decision history predates git.

```
mars-blueprint_v4.md      SOURCE OF TRUTH. Attach this into every working chat.
MARS_M1_TECHNICAL_REFERENCE.md   Full M1 reference — every dataset/engineering/
                          architecture/spec detail with real numbers. For the
                          project report / paper. Cite, don't re-derive.
FUTURE_SCOPE.md           Deliberately deferred, citable-but-not-required work.
archive/                  Superseded blueprint drafts v1 / v1.2 / v2 / v3.
status/
  mars-status_M0.md       M0 verification matrix + critical findings (audit doc).
  mars-status_M1.md       M1 verification matrix + Run-by-run status + findings.
  ppbr_az_investigation.md  PPBR_AZ multi-species root cause + Option C.
  kermt_integration_status.md  KERMT identity, checkpoint hashes, container
                          isolation rationale, smoke-test results, A4000 verdict.
AIMS/                     AI Memory System — paste-in context for a fresh chat.
  README.md               How to use AIMS.
  context.md              Project snapshot: stack, environment, where we are.
  decisions.md            Decision log (newest first).
  next_steps.md           What to do next — the live work breakdown.
  mistakes.md             Gotchas hit + traps to avoid.
  glossary.md             Endpoints / clusters / milestones / acronyms.
  module_milestone_map.md Authoritative Module ↔ Milestone matrix + known
                          blueprint inconsistencies.
```

For "where does the project actually stand right now", read
`AIMS/next_steps.md` first, then `AIMS/module_milestone_map.md`.
