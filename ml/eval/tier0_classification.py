"""
Classification reporting for the Tier-0 KERMT arms, beside the XGBoost held-out reports, with no claim.

Read-only. Reads the five-seed aggregates already in git
(``documentation/status/kermt_tier0_results/<arm>/aggregate_5seeds.json``) and the XGBoost held-out
reports (``ml/runs/test_evaluations/<endpoint>.json``). No GPU, no model, no prediction files.

Why this prints no difference and no winner
-------------------------------------------
Every classification arm is on a different training pool from its XGBoost counterpart, so a
KERMT-minus-XGBoost number would measure the pools as much as the models:

* ``absorption_distribution__cls`` is one multi-task model. It holds out a calibration split and drops
  the labels that would leak across endpoints (``cluster_split_report``), and XGBoost is one
  single-task model per endpoint on the full train_val pool.
* ``metabolism__cls`` lost 27-29 % of each CYP's labels to leakage-safe assembly (decisions.md 2026-09-30,
  Option A). The single-task CYP baselines on the full original splits are still owed (ship checklist
  B3), so a multi-task benefit cannot be told apart from the smaller pool.
* ``dili_standalone__cls`` trained on the base pool (287 molecules) and XGBoost on the DILIst-augmented
  pool (979) (decisions.md D6). The two share the same 96 test molecules and nothing else.

The ship-checklist fallback applies: make no KERMT-versus-XGBoost claim on classification until the rows
are pool-matched, and say so. ``toxicity__cls`` is left out: on this branch it has two of five seeds, which
is provisional (no mean, no ranking). Raw (uncalibrated) metrics are shown on both sides because the XGBoost
report's calibrated block applies one calibrator to every seed (its own ``notes``).

Usage (from ``ml/``; the XGBoost reports are gitignored, so point ``--xgb-dir`` at a checkout that has them):
    PYTHONPATH=. ./.venv/Scripts/python.exe eval/tier0_classification.py --out ../documentation/status/kermt_vs_xgboost_classification.md
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS_DIR = REPO_ROOT / "documentation" / "status" / "kermt_tier0_results"
DEFAULT_XGB_DIR = REPO_ROOT / "ml" / "runs" / "test_evaluations"
FIXED_SEEDS = 5

# Arm -> why its rows cannot be compared with the XGBoost rows yet. One entry per arm, quoted in the table.
ARM_NOTES = {
    "absorption_distribution__cls": (
        "Multi-task, calibration holdout and cross-endpoint leakage removal vs single-task on the full pool"
    ),
    "metabolism__cls": "Pool cut 27-29 % by leakage removal; single-task CYP baselines still owed (B3)",
    "dili_standalone__cls": "KERMT on the base pool (287), XGBoost on the augmented pool (979)",
}
DEFAULT_ARMS = tuple(ARM_NOTES)


@dataclass(frozen=True)
class ClassificationRow:
    endpoint: str
    arm: str
    n_test: int
    kermt_auroc: tuple[float, float | None]
    kermt_auprc: tuple[float, float | None]
    xgb_auroc: tuple[float, float | None]
    xgb_auprc: tuple[float, float | None]
    note: str


def _pair(block: dict, metric: str) -> tuple[float, float | None]:
    mean = block[f"{metric}_mean"]
    std = block.get(f"{metric}_std")
    if mean is None or not math.isfinite(mean):
        raise ValueError(f"{metric} mean is {mean!r}")
    return float(mean), (None if std is None or not math.isfinite(std) else float(std))


def load_arm(results_dir: Path, arm: str) -> list[tuple[str, int, dict]]:
    """(endpoint, n_test, raw aggregate block) for each endpoint of a complete five-seed classification arm."""
    if not arm.endswith("__cls"):
        raise NotImplementedError(f"{arm} is not a classification arm")
    arm_dir = results_dir / arm
    path = arm_dir / "aggregate_5seeds.json"
    if not path.exists():
        raise FileNotFoundError(f"{arm}: no aggregate_5seeds.json (a partial arm is provisional and is not reported)")
    aggregate = json.loads(path.read_text(encoding="utf-8"))
    summaries = sorted(arm_dir.glob("seed*/lab_summary.json"))
    if len(summaries) < FIXED_SEEDS:
        raise ValueError(f"{arm}: {len(summaries)} seed record(s), need {FIXED_SEEDS}")

    out = []
    for endpoint, record in aggregate["test_metrics_across_seeds"].items():
        raw = record["raw"]
        if int(raw["n_valid_seeds"]) < FIXED_SEEDS:
            raise ValueError(f"{arm}/{endpoint}: {raw['n_valid_seeds']} valid seeds, need {FIXED_SEEDS}")
        n_tests = set()
        for summary_path in summaries:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            n_tests.add(int(summary["calibration"][endpoint]["n_test_labeled"]))
        if len(n_tests) != 1:
            raise ValueError(f"{arm}/{endpoint}: n_test differs across seeds {sorted(n_tests)}")
        out.append((endpoint, n_tests.pop(), raw))
    return out


def compare(arm: str, endpoint: str, n_test: int, kermt_raw: dict, xgb_dir: Path) -> ClassificationRow:
    path = xgb_dir / f"{endpoint}.json"
    if not path.exists():
        raise FileNotFoundError(f"No XGBoost held-out report for {endpoint}: {path}")
    report = json.loads(path.read_text(encoding="utf-8"))
    if report["task_type"] != "classification" or report["split"] != "test":
        raise ValueError(f"{path.name}: expected a classification test-split report")
    if report["n_test"] != n_test:
        raise ValueError(
            f"{endpoint}: KERMT scored {n_test} test molecules, XGBoost {report['n_test']}; not the same test set"
        )
    xgb = report["aggregated_test_raw"]
    if int(xgb["n_valid_seeds"]) < FIXED_SEEDS:
        raise ValueError(f"{endpoint}: XGBoost report has {xgb['n_valid_seeds']} valid seeds, need {FIXED_SEEDS}")
    return ClassificationRow(
        endpoint=endpoint,
        arm=arm,
        n_test=n_test,
        kermt_auroc=_pair(kermt_raw, "auroc"),
        kermt_auprc=_pair(kermt_raw, "auprc"),
        xgb_auroc=_pair(xgb, "auroc"),
        xgb_auprc=_pair(xgb, "auprc"),
        note=ARM_NOTES[arm],
    )


def _fmt(pair: tuple[float, float | None]) -> str:
    mean, std = pair
    return f"{mean:.3f} ± {std:.3f}" if std is not None else f"{mean:.3f}"


def render_markdown(rows: list[ClassificationRow]) -> str:
    lines = [
        "# KERMT Tier-0 and XGBoost: classification endpoints, held-out test metrics (no comparison made)",
        "",
        "Generated by `ml/eval/tier0_classification.py` from the five-seed aggregates in git",
        "(`documentation/status/kermt_tier0_results/`) and the XGBoost held-out reports. Mean ± sample std over",
        "5 seeds, **test set, raw (uncalibrated)** on both sides.",
        "",
        "**No KERMT-versus-XGBoost claim is made on classification.** The two sides were trained on different",
        "pools (last column), so a difference would measure the pools as much as the models. The table has no",
        "difference column, no ranking and no winner on purpose. The pool-matched rows that can support a",
        "comparison are in `kermt_vs_xgboost_pool_matched.md` where that file exists.",
        "",
        "| endpoint | KERMT arm | n_test | KERMT AUROC | XGBoost AUROC | KERMT AUPRC | XGBoost AUPRC | Why not comparable |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r.endpoint} | {r.arm} | {r.n_test} | {_fmt(r.kermt_auroc)} | {_fmt(r.xgb_auroc)} "
            f"| {_fmt(r.kermt_auprc)} | {_fmt(r.xgb_auprc)} | {r.note} |"
        )
    lines += [
        "",
        "## Read this before using the table",
        "",
        "- **Same test size, not proven same molecules.** Per endpoint the n_test match, but the KERMT runs used",
        "  processed snapshot `20260918T090433Z` and the XGBoost evaluation `20260830T200000Z`. Split-file hash",
        "  equality is the `ml/data/compare_prep.py` check, which needs both machines.",
        "- **Not covered.** `toxicity__cls` has two of five seeds and is provisional (no mean, no ranking), so it",
        "  is not here. The CYP rows stay uncomparable until the single-task CYP baselines on full splits exist.",
        "- **Metrics.** AUROC and AUPRC only. Calibration (Brier, ECE) is reported per arm in each",
        "  `aggregate_5seeds.json` and is not compared here: the calibration splits differ between the models.",
        "- **Spread.** Five seeds do not support a significance claim and none is made.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR))
    p.add_argument("--xgb-dir", default=str(DEFAULT_XGB_DIR))
    p.add_argument("--arms", nargs="*", default=list(DEFAULT_ARMS))
    p.add_argument("--out", default=None, help="Write the markdown table here; print it if omitted.")
    args = p.parse_args(argv)

    rows: list[ClassificationRow] = []
    for arm in args.arms:
        if arm not in ARM_NOTES:
            raise SystemExit(f"{arm}: no pool note on record; add one to ARM_NOTES before reporting this arm")
        for endpoint, n_test, raw in load_arm(Path(args.results_dir), arm):
            rows.append(compare(arm, endpoint, n_test, raw, Path(args.xgb_dir)))
    text = render_markdown(rows)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {args.out} ({len(rows)} endpoints)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
