"""
Module 11 — TDC leaderboard comparison scaffolding.

Structured storage for comparing MARS's own 5-seed aggregated results
against the TDC ADMET Benchmark Group leaderboard, with an explicit
comparability flag derived from each dataset's own M1 provenance
(`split_method`, written at prepare-time by `data/split.py`): only the 12
endpoints that adopted TDC's official benchmark split verbatim
(`split_method == "adopt_benchmark"`) are apples-to-apples comparable.
hERG_Karim and PPB (human-only, Option C) self-generate a deterministic
Murcko split because no official TDC benchmark split exists for them — their
results are still reported, but flagged non-comparable, never silently
plotted next to leaderboard numbers.

This module does NOT hardcode or fetch live TDC leaderboard numbers — the
leaderboard is a live, externally-hosted resource that changes over time.
What it owns is the comparability logic (fully data-driven, no hardcoded
endpoint names) and a durable record tying one MARS EvaluationReport to one
manually-looked-up TDC reference value at a point in time.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from data.loaders import EndpointData

from eval.evaluate import EvaluationReport

TDC_COMPARISON_VERSION = "mars-tdc-comparison-v1"

_COMPARABLE_NOTE = "Uses TDC's official benchmark split verbatim — directly leaderboard-comparable."
_NON_COMPARABLE_NOTE = (
    "Self-generated deterministic Murcko split (no official TDC benchmark split exists "
    "for this dataset) — NOT directly comparable to the TDC leaderboard."
)


@dataclass(frozen=True)
class TDCBenchmarkEntry:
    """One TDC leaderboard reference value, recorded manually at lookup time
    (the leaderboard itself is not fetched or hardcoded by this module)."""

    tdc_dataset_name: str
    metric_name: str
    leaderboard_best: float
    leaderboard_best_method: str
    looked_up_at_utc: str


@dataclass
class TDCComparisonResult:
    endpoint_key: str
    mars_metric_name: str
    mars_metric_mean: float
    mars_metric_std: float
    split_method: str
    comparable: bool
    comparability_note: str
    tdc_reference: TDCBenchmarkEntry | None = None
    version: str = TDC_COMPARISON_VERSION

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> TDCComparisonResult:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        ref_data = data.pop("tdc_reference", None)
        ref = TDCBenchmarkEntry(**ref_data) if ref_data is not None else None
        return cls(tdc_reference=ref, **data)


def determine_comparability(split_method: str) -> tuple[bool, str]:
    """Comparability is fully determined by the M1 split method — no
    per-endpoint hardcoding. See data/split.py's SplitReport.method."""
    if split_method == "adopt_benchmark":
        return True, _COMPARABLE_NOTE
    if split_method == "scaffold":
        return False, _NON_COMPARABLE_NOTE
    raise ValueError(f"Unknown split_method: {split_method!r}")


def build_tdc_comparison(
    evaluation_report: EvaluationReport,
    endpoint_data: EndpointData,
    *,
    mars_metric_name: str,
    tdc_reference: TDCBenchmarkEntry | None = None,
) -> TDCComparisonResult:
    """Build a comparison record for one metric of one EvaluationReport.

    Parameters
    ----------
    evaluation_report:
        Aggregated 5-seed result from eval.evaluate.build_evaluation_report.
    endpoint_data:
        The same endpoint's loaded M1 splits — provides `provenance["split_method"]`.
    mars_metric_name:
        Base metric name as it appears in `evaluation_report.aggregated`
        without the `_mean`/`_std` suffix, e.g. "auroc" or "mae".
    tdc_reference:
        Optional manually-looked-up TDC leaderboard value; omit if not yet
        looked up (the comparability flag is independent of whether a
        reference value has been recorded).
    """
    if endpoint_data.endpoint_key != evaluation_report.endpoint_key:
        raise ValueError(
            f"endpoint mismatch: evaluation_report is for {evaluation_report.endpoint_key!r}, "
            f"endpoint_data is for {endpoint_data.endpoint_key!r}"
        )

    split_method = endpoint_data.provenance.get("split_method")
    if not split_method:
        raise ValueError(
            f"{endpoint_data.endpoint_key}: provenance.json is missing 'split_method' — "
            "cannot determine TDC comparability"
        )
    comparable, note = determine_comparability(split_method)

    mean_key = f"{mars_metric_name}_mean"
    std_key = f"{mars_metric_name}_std"
    if mean_key not in evaluation_report.aggregated:
        raise ValueError(
            f"{mars_metric_name!r} not found in evaluation_report.aggregated "
            f"(available: {sorted(k for k in evaluation_report.aggregated if k.endswith('_mean'))})"
        )

    return TDCComparisonResult(
        endpoint_key=endpoint_data.endpoint_key,
        mars_metric_name=mars_metric_name,
        mars_metric_mean=evaluation_report.aggregated[mean_key],
        mars_metric_std=evaluation_report.aggregated[std_key],
        split_method=split_method,
        comparable=comparable,
        comparability_note=note,
        tdc_reference=tdc_reference,
    )
