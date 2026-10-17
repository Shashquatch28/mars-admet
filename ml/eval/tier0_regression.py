"""
Regression reporting for the Tier-0 KERMT regression arms, and the KERMT vs XGBoost MAE table.

Read-only. Everything here is read from the lightweight records already in git
(``documentation/status/kermt_tier0_results/<arm>/seed<N>/lab_summary.json``) and from the
XGBoost held-out reports (``ml/runs/test_evaluations/<endpoint>.json``). It needs no GPU, no
container, no prediction files and no model.

Why this is separate from ``tier0_artifacts.py``: that module rebuilds plots from each run's
``predict_*/out/predictions.csv`` and from a temperature scaler. A regression arm has no scaler
by design (decisions.md D2) and its prediction files are not in git, so the only per-seed result
a git checkout holds for a regression endpoint is the test MAE. This module reports exactly
that and nothing more. It does not compute R2, RMSE, residuals or intervals.

What the comparison does and does not say
-----------------------------------------
* Both sides score the same number of held-out test molecules per endpoint (checked here). That
  the molecules are the same is not verified here: the KERMT runs used a different processed
  snapshot id than the XGBoost evaluation, and split-file identity is the ``compare_prep.py``
  check, which needs both machines.
* The training pools differ: KERMT carves out a calibration split and trains on fewer
  molecules (decisions.md, 2026-09-30), and it trains multi-task for the absorption/distribution
  endpoints. The table is a difference in test MAE, not a like-for-like model comparison.
* The table reports the signed difference and both seed spreads. It does not rank, pick a
  winner, or call an endpoint better; which model serves an endpoint is a Module 11 decision.

Usage (from ``ml/``):
    PYTHONPATH=. ./.venv/Scripts/python.exe eval/tier0_regression.py --out ../documentation/status/kermt_vs_xgboost_regression.md
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS_DIR = REPO_ROOT / "documentation" / "status" / "kermt_tier0_results"
DEFAULT_XGB_DIR = REPO_ROOT / "ml" / "runs" / "test_evaluations"
DEFAULT_ARMS = ("metabolism__reg", "absorption_distribution__reg")
FIXED_SEEDS = 5


@dataclass(frozen=True)
class EndpointRuns:
    """Test MAE of one endpoint of one KERMT regression arm, one value per seed."""

    arm: str
    endpoint: str
    prep_id: str
    seeds: tuple[int, ...]
    mae: tuple[float, ...]
    n_test: int
    model_id: str

    @property
    def mae_mean(self) -> float:
        return float(np.mean(self.mae))

    @property
    def mae_std(self) -> float | None:
        # Sample std (ddof=1), None below two seeds: same convention as eval.metrics.
        return float(np.std(self.mae, ddof=1)) if len(self.mae) > 1 else None


def load_arm(results_dir: Path, arm: str, *, min_seeds: int = FIXED_SEEDS) -> list[EndpointRuns]:
    """Per-endpoint seed results of a regression arm, or raise if the records cannot support a report."""
    if not arm.endswith("__reg"):
        raise NotImplementedError(f"{arm} is not a regression arm; tier0_regression is regression-only")
    arm_dir = results_dir / arm
    summaries = sorted(arm_dir.glob("seed*/lab_summary.json"))
    if not summaries:
        raise FileNotFoundError(f"No seed*/lab_summary.json under {arm_dir}")

    seeds: list[int] = []
    prep_ids: set[str] = set()
    model_ids: set[str] = set()
    per_endpoint: dict[str, dict[int, tuple[float, int]]] = {}
    for path in summaries:
        summary = json.loads(path.read_text(encoding="utf-8"))
        seed = int(summary["seed"])
        if seed in seeds:
            raise ValueError(f"{arm}: seed {seed} appears twice")
        seeds.append(seed)
        for endpoint, record in summary["calibration"].items():
            if record.get("task_type") != "regression" or record.get("status") != "skipped_regression":
                raise ValueError(f"{arm}/{path.parent.name}/{endpoint}: not a regression record ({record.get('status')!r})")
            test = record["test_metrics_raw"]
            mae = test["mae"]
            if mae is None or not math.isfinite(mae):
                raise ValueError(f"{arm}/{path.parent.name}/{endpoint}: test MAE is {mae!r}")
            if test["n_samples"] != record["n_test_labeled"]:
                raise ValueError(f"{arm}/{path.parent.name}/{endpoint}: n_samples != n_test_labeled")
            prep_ids.add(record["prep_id"])
            model_ids.add(record["model_id"])
            per_endpoint.setdefault(endpoint, {})[seed] = (float(mae), int(test["n_samples"]))

    if len(prep_ids) != 1 or len(model_ids) != 1:
        raise ValueError(f"{arm}: seeds mix snapshots or model ids ({sorted(prep_ids)}, {sorted(model_ids)})")
    if len(seeds) < min_seeds:
        raise ValueError(
            f"{arm}: {len(seeds)} seed record(s), need {min_seeds}. A partial arm is provisional "
            "and is not reported (pass min_seeds to override and label it)."
        )

    runs = []
    for endpoint, by_seed in per_endpoint.items():
        if set(by_seed) != set(seeds):
            raise ValueError(f"{arm}/{endpoint}: missing seeds {sorted(set(seeds) - set(by_seed))}")
        ordered = sorted(by_seed)
        n_tests = {by_seed[s][1] for s in ordered}
        if len(n_tests) != 1:
            raise ValueError(f"{arm}/{endpoint}: n_test differs across seeds {sorted(n_tests)}")
        runs.append(
            EndpointRuns(
                arm=arm,
                endpoint=endpoint,
                prep_id=next(iter(prep_ids)),
                seeds=tuple(ordered),
                mae=tuple(by_seed[s][0] for s in ordered),
                n_test=n_tests.pop(),
                model_id=next(iter(model_ids)),
            )
        )
    return runs


@dataclass(frozen=True)
class ComparisonRow:
    endpoint: str
    arm: str
    n_test: int
    kermt_mae_mean: float
    kermt_mae_std: float | None
    kermt_seeds: int
    xgb_mae_mean: float
    xgb_mae_std: float | None
    xgb_seeds: int
    difference: float  # KERMT minus XGBoost, in the endpoint's own units


def compare(runs: EndpointRuns, xgb_dir: Path) -> ComparisonRow:
    """One endpoint's KERMT result beside the XGBoost held-out report, after checking they are comparable."""
    path = xgb_dir / f"{runs.endpoint}.json"
    if not path.exists():
        raise FileNotFoundError(f"No XGBoost held-out report for {runs.endpoint}: {path}")
    report = json.loads(path.read_text(encoding="utf-8"))
    if report["task_type"] != "regression" or report["split"] != "test":
        raise ValueError(f"{path.name}: expected a regression test-split report")
    if report["n_test"] != runs.n_test:
        raise ValueError(
            f"{runs.endpoint}: KERMT scored {runs.n_test} test molecules, XGBoost {report['n_test']}; "
            "the two are not on the same test set"
        )
    raw = report["aggregated_test_raw"]
    xgb_seeds = int(raw["n_valid_seeds"])
    if xgb_seeds < FIXED_SEEDS:
        raise ValueError(f"{runs.endpoint}: XGBoost report has {xgb_seeds} valid seeds, need {FIXED_SEEDS}")
    return ComparisonRow(
        endpoint=runs.endpoint,
        arm=runs.arm,
        n_test=runs.n_test,
        kermt_mae_mean=runs.mae_mean,
        kermt_mae_std=runs.mae_std,
        kermt_seeds=len(runs.seeds),
        xgb_mae_mean=float(raw["mae_mean"]),
        xgb_mae_std=raw["mae_std"],
        xgb_seeds=xgb_seeds,
        difference=runs.mae_mean - float(raw["mae_mean"]),
    )


def _fmt(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}" if abs(value) < 10 else f"{value:.2f}"


def render_markdown(rows: list[ComparisonRow], *, prep_ids: dict[str, str]) -> str:
    lines = [
        "# KERMT Tier-0 vs XGBoost: regression endpoints, held-out test MAE",
        "",
        "Generated by `ml/eval/tier0_regression.py` from the records in git",
        "(`documentation/status/kermt_tier0_results/`) and the XGBoost held-out reports. Mean and sample std",
        "(ddof=1) over 5 seeds, test set only. MAE is in each endpoint's own unit, so rows are not comparable",
        "with each other. This is a difference in test MAE, **not a ranking**: no winner is named.",
        "",
        "| endpoint | KERMT arm | n_test | KERMT MAE | XGBoost MAE | KERMT minus XGBoost |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r.endpoint} | {r.arm} | {r.n_test} | {_fmt(r.kermt_mae_mean)} ± {_fmt(r.kermt_mae_std)} "
            f"| {_fmt(r.xgb_mae_mean)} ± {_fmt(r.xgb_mae_std)} | {r.difference:+.3f} |"
        )
    lines += [
        "",
        "## Read this before using the table",
        "",
        "- **Same test size, not proven same molecules.** Per endpoint the KERMT and XGBoost n_test are equal, but",
        "  the KERMT runs used processed snapshot "
        + ", ".join(f"`{p}`" for p in sorted(set(prep_ids.values())))
        + " and the XGBoost evaluation used `20260830T200000Z`. Hash equality of the split files is the",
        "  `ml/data/compare_prep.py` check, which needs both machines.",
        "- **Different training pools.** KERMT holds out a calibration split and trains on fewer molecules",
        "  (decisions.md 2026-09-30); the four absorption/distribution endpoints are one multi-task model. XGBoost",
        "  is one single-task model per endpoint on the full train_val pool.",
        "- **MAE only.** The git records hold test MAE per seed and nothing else for regression arms. R2, RMSE and",
        "  residual plots need the per-seed `predictions.csv` files, which live on the workstation and in the",
        "  seed-0 run-record artifacts in W&B, not in git.",
        "- **Spread.** Several differences are within one seed std of either side. Five seeds do not support a",
        "  significance claim and none is made.",
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

    rows: list[ComparisonRow] = []
    prep_ids: dict[str, str] = {}
    for arm in args.arms:
        for runs in load_arm(Path(args.results_dir), arm):
            rows.append(compare(runs, Path(args.xgb_dir)))
            prep_ids[runs.endpoint] = runs.prep_id
    text = render_markdown(rows, prep_ids=prep_ids)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {args.out} ({len(rows)} endpoints)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
