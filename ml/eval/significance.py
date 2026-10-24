"""
Module 11 section 3: significance testing for the model variants MARS can compare on identical test sets.

What can honestly be compared
-----------------------------
Three variants score the same test molecules on eight endpoints (the pool-matched table,
``tier0_pool_matched.py``): KERMT Tier-0, XGBoost retrained on KERMT's pool, and the production
XGBoost on the full pool. Each endpoint has one primary metric (MAE for regression, AUROC for
classification). This module ranks the three variants per endpoint, then reports:

* the Friedman test over the eight endpoints and the Nemenyi critical difference (the test the
  blueprint names);
* for each pair, an exact two-sided sign test on the direction of the difference across endpoints
  (unit-free, so MAE and AUROC rows can be pooled);
* per endpoint, a Welch test of KERMT against the pool-matched XGBoost from the five seed means and
  standard deviations.

What the numbers mean, and do not
---------------------------------
* A rank is a position on the metric (rank 1 = lowest MAE or highest AUROC). It is not a verdict on
  the model; the table it feeds says the same.
* Eight endpoints is a small sample and the endpoints are not independent draws of anything. The
  smallest two-sided sign-test p-value attainable with eight endpoints is 2 / 2^8 = 0.0078.
* The per-endpoint Welch test sees only training-seed variation on one fixed test set. It does not
  see test-set sampling noise, which dominates on the small sets (HIA 117, P-gp 245, BBB 394).
* KERMT is multi-task on the absorption and distribution endpoints and XGBoost is single-task, so a
  difference there mixes the model and what the model saw in training.
* The CYPs, DILI and toxicity are not in the comparison (``kermt_vs_xgboost_pool_matched.md``).

Usage (from ``ml/``; the production reports are gitignored, so point ``--xgb-dir`` at a checkout that has them):
    PYTHONPATH=. python eval/significance.py --pool-matched ../documentation/status/kermt_pool_matched_xgboost.json \\
        --out ../documentation/status/significance.md
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import stats

from eval.tier0_pool_matched import DEFAULT_RESULTS_DIR, DEFAULT_XGB_DIR, MetricRow, build_rows

VARIANTS = ("KERMT Tier-0", "XGBoost, KERMT's pool", "XGBoost, full pool")
PRIMARY = {"MAE": False, "AUROC": True}  # metric -> higher is the top rank
ALPHA = 0.05
SEEDS = 5


@dataclass(frozen=True)
class EndpointRanks:
    endpoint: str
    metric: str
    values: tuple[float, float, float]
    ranks: tuple[float, float, float]


@dataclass(frozen=True)
class PairTest:
    a: str
    b: str
    a_ahead: int  # endpoints where a sits at the better rank position
    b_ahead: int
    ties: int
    p_sign: float


@dataclass(frozen=True)
class WelchRow:
    endpoint: str
    metric: str
    difference: float
    p: float


@dataclass(frozen=True)
class Significance:
    ranks: list[EndpointRanks]
    mean_ranks: tuple[float, float, float]
    friedman_chi2: float
    friedman_p: float
    critical_difference: float
    pairs: list[PairTest]
    welch: list[WelchRow]


def nemenyi_critical_difference(k: int, n: int, alpha: float = ALPHA) -> float:
    """CD = q_alpha * sqrt(k (k + 1) / (6 n)), q_alpha from the studentized range over sqrt(2)."""
    q = stats.studentized_range.ppf(1 - alpha, k, np.inf) / math.sqrt(2)
    return float(q * math.sqrt(k * (k + 1) / (6 * n)))


def primary_rows(rows: list[MetricRow]) -> list[MetricRow]:
    return [r for r in rows if r.metric in PRIMARY]


def rank_endpoint(row: MetricRow) -> EndpointRanks:
    values = (row.kermt.mean, row.matched.mean, row.full.mean)
    keyed = [-v for v in values] if PRIMARY[row.metric] else list(values)
    ranks = stats.rankdata(keyed, method="average")
    return EndpointRanks(row.endpoint, row.metric, values, tuple(float(r) for r in ranks))


def analyse(rows: list[MetricRow]) -> Significance:
    prim = primary_rows(rows)
    if len(prim) < 3:
        raise ValueError("need at least three endpoints for a Friedman test")
    ranks = [rank_endpoint(r) for r in prim]
    matrix = np.array([e.ranks for e in ranks])
    chi2, p = stats.friedmanchisquare(*[matrix[:, j] for j in range(3)])
    pairs: list[PairTest] = []
    for i, j in itertools.combinations(range(3), 2):
        a_ahead = int(np.sum(matrix[:, i] < matrix[:, j]))
        b_ahead = int(np.sum(matrix[:, j] < matrix[:, i]))
        ties = len(ranks) - a_ahead - b_ahead
        decided = a_ahead + b_ahead
        p_sign = 1.0 if decided == 0 else float(stats.binomtest(a_ahead, decided, 0.5).pvalue)
        pairs.append(PairTest(VARIANTS[i], VARIANTS[j], a_ahead, b_ahead, ties, p_sign))
    welch = []
    for r in prim:
        if r.kermt.std is None or r.matched.std is None:
            continue
        res = stats.ttest_ind_from_stats(
            r.kermt.mean, r.kermt.std, SEEDS, r.matched.mean, r.matched.std, SEEDS, equal_var=False
        )
        welch.append(WelchRow(r.endpoint, r.metric, r.difference, float(res.pvalue)))
    return Significance(
        ranks=ranks,
        mean_ranks=tuple(float(x) for x in matrix.mean(axis=0)),
        friedman_chi2=float(chi2),
        friedman_p=float(p),
        critical_difference=nemenyi_critical_difference(3, len(ranks)),
        pairs=pairs,
        welch=welch,
    )


def _p(p: float) -> str:
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def render_markdown(sig: Significance) -> str:
    n = len(sig.ranks)
    lines = [
        "# Significance of the differences between model variants (Module 11 section 3)",
        "",
        "Generated by `ml/eval/significance.py` from the pool-matched table inputs "
        "(`kermt_vs_xgboost_pool_matched.md`). Read the limits at the end before quoting any p-value.",
        "",
        f"## Friedman test and Nemenyi critical difference ({n} endpoints, 3 variants)",
        "",
        "Rank 1 is the lowest MAE or the highest AUROC on that endpoint. A rank is a position on a metric, "
        "not a verdict.",
        "",
        "| endpoint | metric | " + " | ".join(VARIANTS) + " |",
        "|---|---|---|---|---|",
    ]
    for e in sig.ranks:
        cells = " | ".join(f"{v:.3f} (rank {r:g})" for v, r in zip(e.values, e.ranks, strict=True))
        lines.append(f"| {e.endpoint} | {e.metric} | {cells} |")
    lines += [
        "| **mean rank** | | " + " | ".join(f"**{m:.2f}**" for m in sig.mean_ranks) + " |",
        "",
        f"Friedman chi-square = {sig.friedman_chi2:.2f}, p = {_p(sig.friedman_p)}. "
        f"Nemenyi critical difference at alpha = {ALPHA}: {sig.critical_difference:.2f} rank units; two "
        "variants differ significantly only if their mean ranks are further apart than that. "
        + (
            "No pair of mean ranks is."
            if max(sig.mean_ranks) - min(sig.mean_ranks) <= sig.critical_difference
            else "At least one pair of mean ranks is."
        ),
        "",
        "## Pairwise sign test across endpoints",
        "",
        "How many endpoints put the first variant at the better rank position than the second. Exact "
        f"two-sided p; the smallest attainable with {n} endpoints is {2 / 2 ** n:.4f}.",
        "",
        "| first variant | second variant | first ahead | second ahead | ties | p |",
        "|---|---|---|---|---|---|",
    ]
    for t in sig.pairs:
        lines.append(f"| {t.a} | {t.b} | {t.a_ahead} | {t.b_ahead} | {t.ties} | {_p(t.p_sign)} |")
    lines += [
        "",
        "## Per endpoint: KERMT against the pool-matched XGBoost (Welch, from 5 seed means and stds)",
        "",
        "| endpoint | metric | KERMT minus XGBoost (pool-matched) | p |",
        "|---|---|---|---|",
    ]
    for w in sig.welch:
        lines.append(f"| {w.endpoint} | {w.metric} | {w.difference:+.4f} | {_p(w.p)} |")
    lines += [
        "",
        "## Limits",
        "",
        f"- {n} endpoints is a small sample, and the endpoints are not independent draws. Treat the "
        "Friedman and sign-test p-values as a description of how consistent the ordering is, not as "
        "evidence about a population of endpoints.",
        "- The Welch column sees only training-seed variation on one fixed test set. It does not see "
        "test-set sampling noise, which is large on the small sets (HIA 117 molecules, P-gp 245, BBB 394). "
        "With five seeds a tiny seed std makes almost any difference look significant; read the "
        "bootstrap intervals in `evaluation_results.md` beside it.",
        "- Eight p-values are shown without a multiple-comparison correction; at alpha = 0.05 about one "
        "in twenty would pass by chance alone.",
        "- On the absorption and distribution endpoints KERMT is multi-task and XGBoost is single-task, so "
        "a difference mixes the model with what the model saw in training.",
        "- Not covered: the CYPs (the single-task KERMT baselines are not run), DILI (KERMT trained on the "
        "base pool, XGBoost on the augmented one) and toxicity.",
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
    text = render_markdown(analyse(rows))
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
