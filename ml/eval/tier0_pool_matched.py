"""
The pool-matched KERMT vs XGBoost table (ship checklist B4).

Read-only. Combines three things already on disk:

* the KERMT five-seed results in git (``documentation/status/kermt_tier0_results/``);
* XGBoost retrained on exactly KERMT's training pool, by ``train/run_pool_matched_xgboost.py``
  (``--pool-matched``: its JSON output, committed beside the table);
* the production XGBoost held-out reports (full train_val), shown as context.

A row appears only if every check passes: the three sides score the same number of test molecules,
each has five valid seeds, and the retrained pool is the pool KERMT recorded. The signed difference is
KERMT minus the pool-matched XGBoost, in the metric's own unit. There is no ranking and no winner;
a difference smaller than either side's seed std is marked "within spread".

Usage (from ``ml/``; the production reports are gitignored, so point ``--xgb-dir`` at a checkout that has them):
    PYTHONPATH=. python eval/tier0_pool_matched.py --pool-matched ../documentation/status/kermt_pool_matched_xgboost.json \\
        --xgb-dir <.../ml/runs/test_evaluations> --out ../documentation/status/kermt_vs_xgboost_pool_matched.md
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

from train.run_pool_matched_xgboost import expected_pool_sizes

from eval import tier0_classification, tier0_regression

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS_DIR = REPO_ROOT / "documentation" / "status" / "kermt_tier0_results"
DEFAULT_XGB_DIR = REPO_ROOT / "ml" / "runs" / "test_evaluations"
FIXED_SEEDS = 5

# (arm, task) pairs that can be pool-matched. CYP and DILI arms are deliberately absent:
# metabolism__cls needs the single-task CYP baselines (B3) and DILI trained on a different pool by design.
MATCHED_ARMS = ("absorption_distribution__reg", "absorption_distribution__cls", "metabolism__reg")


@dataclass(frozen=True)
class Side:
    mean: float
    std: float | None


@dataclass(frozen=True)
class MetricRow:
    endpoint: str
    arm: str
    metric: str  # "MAE", "AUROC" or "AUPRC"
    n_test: int
    n_pool: int
    kermt: Side
    matched: Side
    full: Side

    @property
    def difference(self) -> float:
        return self.kermt.mean - self.matched.mean

    @property
    def within_spread(self) -> bool:
        spreads = [s for s in (self.kermt.std, self.matched.std) if s is not None]
        return bool(spreads) and abs(self.difference) < max(spreads)


def _side(block: dict, metric: str) -> Side:
    mean = block[f"{metric}_mean"]
    std = block.get(f"{metric}_std")
    if mean is None or not math.isfinite(mean):
        raise ValueError(f"{metric} mean is {mean!r}")
    return Side(float(mean), None if std is None or not math.isfinite(std) else float(std))


def _production(xgb_dir: Path, endpoint: str, task: str, n_test: int) -> dict:
    report = json.loads((xgb_dir / f"{endpoint}.json").read_text(encoding="utf-8"))
    if report["task_type"] != task or report["split"] != "test":
        raise ValueError(f"{endpoint}: production report is not a {task} test-split report")
    if report["n_test"] != n_test:
        raise ValueError(f"{endpoint}: production n_test {report['n_test']} != {n_test}")
    raw = report["aggregated_test_raw"]
    if int(raw["n_valid_seeds"]) < FIXED_SEEDS:
        raise ValueError(f"{endpoint}: production report has {raw['n_valid_seeds']} valid seeds")
    return raw


def build_rows(pool_matched: dict, results_dir: Path, xgb_dir: Path) -> list[MetricRow]:
    if pool_matched.get("control"):
        raise ValueError("this file is a control run (full train_val), not a pool-matched run")
    rows: list[MetricRow] = []
    kermt_reg = {r.endpoint: r for arm in MATCHED_ARMS if arm.endswith("__reg") for r in tier0_regression.load_arm(results_dir, arm)}
    kermt_cls = {
        endpoint: (n_test, raw)
        for arm in MATCHED_ARMS
        if arm.endswith("__cls")
        for endpoint, n_test, raw in tier0_classification.load_arm(results_dir, arm)
    }
    expected = {arm: expected_pool_sizes(results_dir, arm) for arm in MATCHED_ARMS}

    for rec in pool_matched["records"]:
        endpoint, arm = rec["endpoint"], rec["arm"]
        if arm not in MATCHED_ARMS:
            raise ValueError(f"{endpoint}: arm {arm} is not one that can be pool-matched")
        if rec["n_pool_labels"] != expected[arm][endpoint]:
            raise ValueError(
                f"{endpoint}: retrained on {rec['n_pool_labels']} labels, KERMT trained on {expected[arm][endpoint]}"
            )
        agg = rec["aggregated_test_raw"]
        if int(agg["n_valid_seeds"]) < FIXED_SEEDS or len(rec["per_seed"]) < FIXED_SEEDS:
            raise ValueError(f"{endpoint}: pool-matched run has fewer than {FIXED_SEEDS} seeds")
        if endpoint in kermt_reg:
            runs = kermt_reg[endpoint]
            if rec["n_test"] != runs.n_test:
                raise ValueError(f"{endpoint}: n_test differs between KERMT and the pool-matched run")
            prod = _production(xgb_dir, endpoint, "regression", runs.n_test)
            rows.append(
                MetricRow(endpoint, arm, "MAE", runs.n_test, rec["n_pool_labels"],
                          Side(runs.mae_mean, runs.mae_std), _side(agg, "mae"), _side(prod, "mae"))
            )
        else:
            n_test, kraw = kermt_cls[endpoint]
            if rec["n_test"] != n_test:
                raise ValueError(f"{endpoint}: n_test differs between KERMT and the pool-matched run")
            prod = _production(xgb_dir, endpoint, "classification", n_test)
            for metric in ("auroc", "auprc"):
                rows.append(
                    MetricRow(endpoint, arm, metric.upper(), n_test, rec["n_pool_labels"],
                              _side(kraw, metric), _side(agg, metric), _side(prod, metric))
                )
    return rows


def _fmt(side: Side) -> str:
    def num(v: float) -> str:
        return f"{v:.3f}" if abs(v) < 10 else f"{v:.2f}"

    return f"{num(side.mean)} ± {num(side.std)}" if side.std is not None else num(side.mean)


def render_markdown(rows: list[MetricRow]) -> str:
    lines = [
        "# KERMT Tier-0 vs XGBoost trained on the same pool: held-out test metrics",
        "",
        "Generated by `ml/eval/tier0_pool_matched.py`. Mean ± sample std over 5 seeds, test set, raw",
        "(uncalibrated). \"XGBoost, KERMT's pool\" is XGBoost retrained on exactly the molecules KERMT",
        "trained on (`ml/train/run_pool_matched_xgboost.py`); \"XGBoost, full pool\" is the production model,",
        "shown for context. The difference is KERMT minus the pool-matched XGBoost in the metric's own unit.",
        "It is **not a ranking**: no winner is named, and a lower MAE or a higher AUROC is not called better",
        "here. \"within spread\" means the difference is smaller than the larger seed std of the two sides.",
        "",
        "| endpoint | metric | n_test | pool labels | KERMT | XGBoost, KERMT's pool | XGBoost, full pool | KERMT minus XGBoost (pool-matched) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        note = " (within spread)" if r.within_spread else ""
        lines.append(
            f"| {r.endpoint} | {r.metric} | {r.n_test} | {r.n_pool} | {_fmt(r.kermt)} | {_fmt(r.matched)} "
            f"| {_fmt(r.full)} | {r.difference:+.3f}{note} |"
        )
    lines += [
        "",
        "## What \"pool-matched\" means, and what it does not",
        "",
        "- **Same labelled molecules for training.** Each XGBoost model was trained on the endpoint's labels",
        "  inside KERMT's pool: the cluster's test molecules removed everywhere, and every molecule in any",
        "  member's calibration split held out. The retrained pool size equals KERMT's recorded pool size for",
        "  every endpoint (a hard check: the run stops otherwise).",
        "- **Not the same folds.** KERMT and XGBoost each draw their own train/validation fold per seed (0-4).",
        "- **Still different models.** XGBoost is single-task. KERMT is multi-task on the absorption/distribution",
        "  endpoints, so those rows differ in the model *and* in what the model saw during training (the other",
        "  endpoints' labels). That is part of what is being compared, not something this table removes.",
        "- **Same test molecules.** Every endpoint's test set comes from the same loader the production report",
        "  uses, and the n_test of all three sides are checked equal. KERMT ran on processed snapshot",
        "  `20260918T090433Z`, XGBoost on `20260830T200000Z`; the rebuilt pool sizes matching exactly is evidence",
        "  the snapshots agree, and `ml/data/compare_prep.py` hash equality remains the proof (needs both machines).",
        "- **The retraining code path reproduces production.** The same script on the full train_val gave the",
        "  production held-out numbers to six decimals for `hia_absorption` seeds 0 and 1 (control run).",
        "- **Spread.** Five seeds do not support a significance claim and none is made.",
        "",
        "## Not in this table",
        "",
        "- **`metabolism__cls` (CYP3A4, CYP2D6, CYP2C9).** A cut of 27-29 % of each CYP's labels comes from the",
        "  leakage-safe assembly. Whether a KERMT result is due to multi-task learning or to that smaller pool",
        "  needs the single-task CYP baselines on full splits (checklist B3), which need the GPU workstation.",
        "- **`dili_standalone__cls`.** KERMT trained on the base pool (287) and XGBoost on the augmented pool",
        "  (979). A pool-matched DILI row needs XGBoost on the base pool, or KERMT on the augmented one (decisions.md D6).",
        "- **`toxicity__cls`.** Two of five seeds are in git; provisional, no mean or ranking.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pool-matched", required=True, dest="pool_matched")
    p.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR))
    p.add_argument("--xgb-dir", default=str(DEFAULT_XGB_DIR))
    p.add_argument("--out", default=None)
    args = p.parse_args(argv)

    data = json.loads(Path(args.pool_matched).read_text(encoding="utf-8"))
    rows = build_rows(data, Path(args.results_dir), Path(args.xgb_dir))
    text = render_markdown(rows)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {args.out} ({len(rows)} rows)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
