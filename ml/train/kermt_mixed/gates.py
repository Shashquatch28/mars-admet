"""
Pass/fail evaluators for the Tier-1 equivalence gates G1-G4.

The gates exist because the trainer is a re-implementation of part of KERMT's
fine-tune loop, so "it runs" says nothing about whether it trains the same model.
Each gate isolates one thing; the definitions are those frozen in
``documentation/AIMS/decisions.md`` (2026-09-20) and ``next_steps.md``. This module
only *decides* — it reads files and numbers the lab produced and returns a verdict
with the evidence, so the decision is reproducible and not a judgement in a notebook.

G1  forward / inference parity   — stock ``predictions.csv`` vs mixed, 64 molecules, 1e-5
G2  one-epoch loss parity        — epoch-0 ``loss_train``, stock log vs mixed, within 5%
G3  multi-seed AUROC parity      — classification-only, paired, validation fold, 5 seeds
G4  Kendall math at log sigma 0  — CPU unit test (``test_kermt_mixed_losses.py``)

Numpy/stdlib only.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class GateResult:
    gate: str
    passed: bool
    summary: str
    evidence: dict[str, Any] = field(default_factory=dict)


# ---- G1 ----------------------------------------------------------------------


def _read_pred_csv(path: Path | str) -> tuple[list[str], list[str], np.ndarray]:
    with Path(path).open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    header, body = rows[0], rows[1:]
    smiles = [r[0] for r in body]
    cols = header[1:]
    vals = np.array([[float(x) if x != "" else np.nan for x in r[1:]] for r in body], dtype=float)
    return smiles, cols, vals


def g1_forward_parity(
    stock_csv: Path | str,
    mixed_csv: Path | str,
    *,
    columns: list[str] | None = None,
    atol: float = 1e-5,
    min_rows: int = 64,
) -> GateResult:
    """Mixed ``predictions.csv`` must reproduce stock's on the same molecules.

    ``columns`` restricts the comparison (classification columns of a checkpoint
    that stock KERMT can serve; the stock path cannot produce a mixed model's
    regression columns in raw units because it never scaled them the same way).
    """
    s_smi, s_cols, s_val = _read_pred_csv(stock_csv)
    m_smi, m_cols, m_val = _read_pred_csv(mixed_csv)
    if s_smi != m_smi:
        return GateResult("G1", False, "molecule order/identity differs between the two files")
    cols = columns or [c for c in s_cols if c in m_cols]
    if not cols:
        return GateResult("G1", False, "no common columns to compare")
    if len(s_smi) < min_rows:
        return GateResult("G1", False, f"only {len(s_smi)} rows; the gate is defined on >= {min_rows}")
    diffs = {}
    for c in cols:
        a = s_val[:, s_cols.index(c)]
        b = m_val[:, m_cols.index(c)]
        diffs[c] = float(np.nanmax(np.abs(a - b))) if np.isfinite(a).any() else float("nan")
    worst = max(diffs.values())
    ok = bool(np.isfinite(worst) and worst <= atol)
    return GateResult(
        "G1",
        ok,
        f"max |stock - mixed| = {worst:.3g} over {len(s_smi)} molecules (tolerance {atol:g})",
        {"per_column_max_abs_diff": diffs, "n": len(s_smi), "atol": atol},
    )


# ---- G2 ----------------------------------------------------------------------

_EPOCH_RE = re.compile(r"Epoch:\s*(\d+)\s+loss_train:\s*([0-9.eE+-]+)")


def parse_stock_epoch_losses(log_text: str) -> dict[int, float]:
    """``{epoch: loss_train}`` from KERMT's ``finetune.log`` (``task/train.py`` print)."""
    return {int(e): float(v) for e, v in _EPOCH_RE.findall(log_text)}


def g2_loss_parity(
    stock_log_text: str,
    mixed_epoch0_train_loss: float,
    *,
    rel_tol: float = 0.05,
    epoch: int = 0,
) -> GateResult:
    """Epoch-``epoch`` train loss under ``mode="fixed"`` vs stock, within ``rel_tol``.

    Batch composition differs by construction (different shuffle RNG), so this is a
    5% band, not equality: it catches a wrong loss (a missing view, a dropped
    ``dist_coff`` term, an unmasked NaN, a wrong reduction), not sampling noise.
    """
    losses = parse_stock_epoch_losses(stock_log_text)
    if epoch not in losses:
        return GateResult("G2", False, f"no 'Epoch: {epoch:04d} loss_train' line in the stock log")
    ref = losses[epoch]
    if ref == 0:
        return GateResult("G2", False, "stock loss is exactly 0; gate undefined")
    rel = abs(mixed_epoch0_train_loss - ref) / abs(ref)
    return GateResult(
        "G2",
        bool(rel <= rel_tol),
        f"stock {ref:.6f} vs mixed {mixed_epoch0_train_loss:.6f}: relative difference {rel:.2%} "
        f"(tolerance {rel_tol:.0%})",
        {"stock": ref, "mixed": mixed_epoch0_train_loss, "relative_difference": rel},
    )


# ---- G3 ----------------------------------------------------------------------


def g3_auroc_parity(
    stock_auroc: list[float],
    mixed_auroc: list[float],
    *,
    paired_tol: float = 0.02,
    min_paired_pass: int = 4,
    std_factor: float = 0.5,
) -> GateResult:
    """Frozen G3 rule (``decisions.md`` 2026-09-20, "G3 defined precisely").

    Pass iff ``|mean_A - mean_B| <= 0.5 * max(std_A, std_B)`` **and** the paired
    per-seed ``|delta AUROC| <= 0.02`` on at least 4 of the 5 seeds. ``A`` is stock
    (path a), ``B`` the mixed trainer in ``mode="fixed"``. Inputs are validation-fold
    AUROC computed host-side by MARS for both paths, ordered by seed.

    With 5 seeds ``std`` is the population ``ddof=0`` value used everywhere else in
    MARS' aggregates (``aggregate_seed_metrics``).
    """
    a = np.asarray(stock_auroc, dtype=float)
    b = np.asarray(mixed_auroc, dtype=float)
    if a.shape != b.shape or a.size < 2:
        return GateResult("G3", False, "need paired per-seed values, >= 2 seeds, equal length")
    if np.isnan(a).any() or np.isnan(b).any():
        return GateResult("G3", False, "NaN AUROC present; a run is invalid")
    mean_diff = abs(float(a.mean() - b.mean()))
    band = std_factor * max(float(a.std()), float(b.std()))
    paired = np.abs(a - b)
    n_ok = int((paired <= paired_tol).sum())
    # A degenerate zero-variance pair would make the band 0; require equality then.
    mean_ok = mean_diff <= band + 1e-12
    paired_ok = n_ok >= min(min_paired_pass, a.size)
    return GateResult(
        "G3",
        bool(mean_ok and paired_ok),
        f"|mean diff| {mean_diff:.4f} vs band {band:.4f} ({'ok' if mean_ok else 'FAIL'}); "
        f"paired |dAUROC| <= {paired_tol} on {n_ok}/{a.size} seeds ({'ok' if paired_ok else 'FAIL'})",
        {
            "mean_stock": float(a.mean()),
            "mean_mixed": float(b.mean()),
            "std_stock": float(a.std()),
            "std_mixed": float(b.std()),
            "paired_abs_diff": paired.tolist(),
            "band": band,
        },
    )
