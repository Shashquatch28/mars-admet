"""
Dependency-free self-check, runnable inside the KERMT container (torch only, no
pytest, no KERMT import).

    PYTHONPATH=/data/_mars_trainer python -m kermt_mixed.selfcheck

Covers gate **G4** and the loss-reduction properties the parity gates depend on, so
the workstation can confirm the staged trainer computes what the CPU tests say it
does — on the container's own torch build. Prints one JSON document; exit status 0
iff every check passes. The full test-suite (``ml/tests/test_kermt_mixed_*.py``)
remains the authority; this is the in-container smoke version.
"""

from __future__ import annotations

import json
import math
import sys

import torch
from torch import nn

from .losses import MixedLoss, MixedLossConfig

DIST = 0.1


def _batch(is_cls: list[bool], b: int = 64, seed: int = 0, rate: float = 0.8):
    g = torch.Generator().manual_seed(seed)
    t = len(is_cls)
    atom = torch.randn(b, t, generator=g) * 2
    bond = atom + 0.3 * torch.randn(b, t, generator=g)
    mask = (torch.rand(b, t, generator=g) < rate).float()
    y = torch.randn(b, t, generator=g)
    y = torch.where(torch.tensor(is_cls), (y > 0).float(), y)
    return atom, bond, y, mask


def _stock_fixed(atom, bond, y, mask, classification: bool) -> float:
    """``task/train.py`` reduction, written independently of ``losses.py``."""
    pl = nn.BCEWithLogitsLoss(reduction="none") if classification else nn.MSELoss(reduction="none")
    el = (pl(atom, y) + pl(bond, y) + DIST * nn.MSELoss(reduction="none")(atom, bond)) * mask
    return float(el.sum() / mask.sum())


def run() -> dict[str, object]:
    checks: dict[str, bool] = {}

    for cls, tag in ((True, "classification"), (False, "regression")):
        flags = [cls, cls, cls]
        a, b, y, m = _batch(flags, seed=1)
        ours = MixedLoss(flags, MixedLossConfig(mode="fixed", dist_coff=DIST))(a, b, y, m).total
        checks[f"fixed_matches_stock_{tag}"] = math.isclose(
            float(ours.detach()), _stock_fixed(a, b, y, m, cls), rel_tol=1e-5
        )

    flags = [True, True, False, False]
    a, b, y, m = _batch(flags, seed=2, rate=0.9)
    fixed_task = MixedLoss(flags, MixedLossConfig(mode="fixed_task", dist_coff=DIST))(a, b, y, m)
    kendall = MixedLoss(flags, MixedLossConfig(mode="kendall", dist_coff=DIST))(a, b, y, m)
    want = sum((1.0 if flags[t] else 0.5) * float(fixed_task.task_means[t].detach()) for t in range(4))
    checks["G4_kendall_at_zero_is_1_per_cls_and_half_per_reg"] = math.isclose(
        float(kendall.total.detach()), want, rel_tol=1e-5, abs_tol=1e-8
    )

    # An empty task contributes nothing and cannot move log sigma.
    mask = m.clone()
    mask[:, 3] = 0.0
    k = MixedLoss(flags, MixedLossConfig(mode="kendall", dist_coff=DIST))
    out = k(a, b, y, mask)
    out.total.backward()
    checks["empty_task_has_no_logsigma_gradient"] = (
        float(k.log_sigma.grad[3]) == 0.0 and float(k.log_sigma.grad[0]) != 0.0
    )

    # Fully-masked batch is 0, not NaN.
    z = MixedLoss(flags, MixedLossConfig(mode="kendall", dist_coff=DIST))(a, b, y, torch.zeros_like(m))
    checks["all_empty_batch_is_zero"] = bool(torch.isfinite(z.total)) and float(z.total.detach()) == 0.0

    # NaN in an unlabeled slot cannot poison the loss.
    y_nan = torch.where(m.bool(), y, torch.tensor(float("nan")))
    n = MixedLoss(flags, MixedLossConfig(mode="fixed_task", dist_coff=DIST))(a, b, y_nan, m)
    checks["nan_in_unlabeled_slot_is_ignored"] = bool(torch.isfinite(n.total))

    return {
        "ok": all(checks.values()),
        "torch": torch.__version__,
        "cuda_available": torch.cuda.is_available(),
        "checks": checks,
    }


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)
