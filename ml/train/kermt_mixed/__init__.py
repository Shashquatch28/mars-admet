"""
Tier 1 (path b) — MARS-owned mixed-type KERMT trainer.

This package is **staged verbatim into the KERMT container** (``/data/_mars_trainer``)
and run with ``python -m kermt_mixed.train_mixed``. Two consequences:

* Every intra-package import is relative, so the same code imports as
  ``train.kermt_mixed`` on the host and as ``kermt_mixed`` in the container.
* Importing the package must stay cheap. Nothing here imports ``torch`` or
  ``kermt`` at package level; the torch-only modules (``losses``, ``gradnorm``,
  ``forward``, ``trainer``) are imported explicitly by the code that needs them,
  and ``train_mixed`` imports KERMT lazily inside ``main()``.

KERMT itself is never modified: it is imported as a library at the pinned commit
(``e402473``), exactly as ``documentation/AIMS/decisions.md`` (2026-09-20,
finding 3) specifies. See ``documentation/AIMS/decisions.md`` (2026-10-14) for
the decision to build this and ``documentation/AIMS/lab_session_tier1.md`` for how
it is validated (gates G1-G4).
"""

from __future__ import annotations

TRAINER_VERSION = "mars-kermt-mixed-trainer-v1"
