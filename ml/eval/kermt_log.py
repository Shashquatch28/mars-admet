"""Parsing of KERMT's ``finetune.log`` and identification of the epoch whose checkpoint was saved.

Why this exists (``documentation/AIMS/decisions.md`` 2026-09-30, D1). KERMT's final line
``best validation auc = X on epoch N`` was reported (workstation, three runs, per the 2026-09-30
session note — *not* independently verified on the laptop) to name an epoch **other than** the one
whose checkpoint was saved as ``model.pt``, while its score ``X`` equals the saved epoch's
``auc_val``. MARS always evaluates the saved ``model.pt`` (``KermtModel.fit``), so results are
unaffected; only post-hoc reporting that read that line's epoch number was.

What this module does about it:

* the **saved epoch** is taken from the per-epoch ``auc_val`` rows — the epoch with the best
  validation score (first occurrence on ties, i.e. a strict-improvement rule). These rows share
  their epoch numbering with the plots, so a marker placed at this epoch is placed on the right
  point. **Assumption, stated rather than hidden:** KERMT's checkpoint rule saves the best-``auc_val``
  epoch; this has not been confirmed against KERMT's source on the laptop;
* two independent cross-checks are recorded, never silently resolved: a ``Saving model at epoch N``
  line (its wording comes only from the session note) and the logged best *score*;
* KERMT's logged best *epoch* is kept for audit only and is never used as the saved epoch.

Pure standard library, so it is importable (and testable) without matplotlib or the KERMT container.
Classification logs only: the epoch-line pattern requires ``auc_val``; a regression log yields no rows
and therefore ``source == "unavailable"`` rather than a guess.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

EPOCH_LINE = re.compile(
    r"Epoch:\s*(\d+)\s+loss_train:\s*([\d.eE+-]+)\s+loss_val:\s*([\d.eE+-]+)\s+"
    r"auc_val:\s*([\d.eE+-]+)\s+cur_lr:\s*([\d.eE+-]+)\s+t_time:\s*([\d.eE+-]+)s\s+v_time:\s*([\d.eE+-]+)s"
)
BEST_EPOCH_LINE = re.compile(r"best validation auc\s*=\s*([\d.eE+-]+)\s+on epoch\s+(\d+)", re.IGNORECASE)
# Wording taken from the 2026-09-30 session note only; never seen in a log on the laptop.
SAVING_LINE = re.compile(r"Saving model at epoch\s+(\d+)", re.IGNORECASE)

# Same tolerance as the runbook's "saved epoch's val score equals the logged best score" check (D1).
SCORE_TOLERANCE = 1e-3

SOURCE_DERIVED = "derived_from_auc_val"
SOURCE_SAVING_LINE = "saving_line"
SOURCE_UNAVAILABLE = "unavailable"


def parse_epoch_rows(text: str) -> list[dict[str, float | int]]:
    """Per-epoch rows (``epoch, loss_train, loss_val, auc_val, lr, t_time, v_time``) in log order."""
    rows: list[dict[str, float | int]] = []
    for line in text.splitlines():
        m = EPOCH_LINE.search(line)
        if m:
            rows.append(
                {
                    "epoch": int(m.group(1)),
                    "loss_train": float(m.group(2)),
                    "loss_val": float(m.group(3)),
                    "auc_val": float(m.group(4)),
                    "lr": float(m.group(5)),
                    "t_time": float(m.group(6)),
                    "v_time": float(m.group(7)),
                }
            )
    return rows


def parse_logged_best(text: str) -> tuple[int | None, float | None]:
    """``(epoch, score)`` exactly as KERMT's final ``best validation`` line states them.

    The epoch is **not** reliable as the saved epoch (see the module docstring).
    """
    bm = BEST_EPOCH_LINE.search(text)
    if not bm:
        return None, None
    return int(bm.group(2)), float(bm.group(1))


def parse_saving_epochs(text: str) -> list[int]:
    """Every ``Saving model at epoch N`` epoch in log order (empty if the wording never appears)."""
    return [int(m.group(1)) for m in SAVING_LINE.finditer(text)]


@dataclass(frozen=True)
class SavedEpoch:
    epoch: int | None
    source: str
    logged_best_epoch: int | None
    logged_best_auc: float | None
    saving_line_epoch: int | None
    consistent_with_logged_best_score: bool | None
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["notes"] = list(self.notes)
        return d


def resolve_saved_epoch(text: str, *, tolerance: float = SCORE_TOLERANCE) -> SavedEpoch:
    """Identify the saved epoch from a ``finetune.log`` text (see the module docstring)."""
    rows = parse_epoch_rows(text)
    logged_epoch, logged_auc = parse_logged_best(text)
    saving = parse_saving_epochs(text)
    saving_epoch = saving[-1] if saving else None
    notes: list[str] = []

    derived: int | None = None
    auc_at: dict[int, float] = {}
    if rows:
        auc_at = {int(r["epoch"]): float(r["auc_val"]) for r in rows}
        best_score = max(float(r["auc_val"]) for r in rows)
        derived = next(int(r["epoch"]) for r in rows if float(r["auc_val"]) == best_score)

    if derived is not None:
        epoch, source = derived, SOURCE_DERIVED
        if saving_epoch is not None and saving_epoch != derived:
            notes.append(
                f"the last 'Saving model at epoch' line says {saving_epoch} but the best per-epoch auc_val is at "
                f"epoch {derived}; the derived epoch is used because it shares the per-epoch rows' numbering — "
                "check the log"
            )
    elif saving_epoch is not None:
        epoch, source = saving_epoch, SOURCE_SAVING_LINE
        notes.append("no per-epoch auc_val rows were parsed; epoch taken from the 'Saving model at epoch' line only")
    else:
        epoch, source = None, SOURCE_UNAVAILABLE
        notes.append("no per-epoch auc_val rows and no 'Saving model at epoch' line were found in the log")

    consistent: bool | None = None
    if epoch is not None and logged_auc is not None and epoch in auc_at:
        consistent = abs(auc_at[epoch] - logged_auc) <= tolerance
        if not consistent:
            notes.append(
                f"the saved epoch's auc_val ({auc_at[epoch]:.4f}) differs from KERMT's logged best score "
                f"({logged_auc:.4f}) by more than {tolerance:g} — STOP and report (runbook §12)"
            )
    if logged_epoch is not None and epoch is not None and logged_epoch != epoch:
        notes.append(
            f"KERMT's logged best epoch ({logged_epoch}) differs from the saved epoch ({epoch}): known KERMT "
            "logging behaviour (decisions.md 2026-09-30 D1); the logged epoch is kept for audit only"
        )

    return SavedEpoch(
        epoch=epoch,
        source=source,
        logged_best_epoch=logged_epoch,
        logged_best_auc=logged_auc,
        saving_line_epoch=saving_epoch,
        consistent_with_logged_best_score=consistent,
        notes=tuple(notes),
    )


def resolve_saved_epoch_from_file(path: Path, *, tolerance: float = SCORE_TOLERANCE) -> SavedEpoch:
    return resolve_saved_epoch(Path(path).read_text(encoding="utf-8", errors="replace"), tolerance=tolerance)
