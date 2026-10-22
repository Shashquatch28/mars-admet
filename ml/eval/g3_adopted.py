"""Adopted G3 rule (decisions.md 2026-10-22): equivalence interval on the selection-free calibration holdouts.

Options 3 + 4 of the 2026-10-19 draft. The frozen validation-fold rule in ``train/kermt_mixed/gates.py`` is not
edited or re-run; this module re-scores the cached holdout evidence in ``selection_free_parity.json``.

* Estimand: deployed checkpoints (stock's saved epoch vs the mixed trainer's own epoch), scored on the per-endpoint
  calibration holdout, which is in no train or validation set of either arm.
* Gate: AMES only. Pass iff the 90 % paired-bootstrap interval of the pooled (5-seed mean) delta AUROC
  (mixed - stock) lies inside [-margin, +margin].
* hERG is reported with its interval and does not gate. It raises ``watch`` when its interval is not inside the
  margin, so a regression cannot go unnoticed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

MARGIN = 0.02
GATING = ("ames_mutagenicity",)
PARITY_JSON = Path(__file__).resolve().parents[2] / "documentation/status/kermt_tier1_gates/diagnostics/selection_free_parity.json"


def inside(ci: list[float], margin: float) -> bool:
    return ci[0] >= -margin and ci[1] <= margin


def g3_adopted(parity: dict, margin: float = MARGIN, gating: tuple[str, ...] = GATING) -> dict:
    eps = parity["endpoints"]
    missing = [g for g in gating if g not in eps]
    if missing:
        raise ValueError(f"gating endpoint(s) missing from the evidence: {missing}")
    out: dict = {"margin": margin, "gating": list(gating), "endpoints": {}}
    for name, e in eps.items():
        p = e["pooled"]
        ok = inside(p["ci90"], margin)
        out["endpoints"][name] = {
            "n_scored": e["n_scored"], "delta": p["delta"], "ci90": p["ci90"],
            "inside_margin": ok, "gating": name in gating,
            "status": ("PASS" if ok else "FAIL") if name in gating else ("reported" if ok else "WATCH"),
        }
    out["passed"] = all(out["endpoints"][g]["inside_margin"] for g in gating)
    out["verdict"] = "PASS" if out["passed"] else "FAIL"
    return out


def main() -> None:
    parity = json.loads(PARITY_JSON.read_text())
    res = g3_adopted(parity)
    dst = PARITY_JSON.with_name("g3_adopted_verdict.json")
    dst.write_text(json.dumps(res, indent=2) + "\n")
    for n, e in res["endpoints"].items():
        print(f"{n}: delta {e['delta']:+.4f} CI90 [{e['ci90'][0]:+.4f}, {e['ci90'][1]:+.4f}] {e['status']}")
    print("G3 (adopted rule):", res["verdict"])
    sys.exit(0 if res["passed"] else 1)


if __name__ == "__main__":
    main()
