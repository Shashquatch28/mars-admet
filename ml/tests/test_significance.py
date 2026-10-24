"""Module 11 section 3 significance tests: ranks, direction of the metric, the Nemenyi constant."""

from __future__ import annotations

import pytest
from eval.significance import (
    analyse,
    nemenyi_critical_difference,
    primary_rows,
    rank_endpoint,
    render_markdown,
)
from eval.tier0_pool_matched import MetricRow, Side


def _row(endpoint: str, metric: str, kermt: float, matched: float, full: float, *, std: float = 0.01) -> MetricRow:
    return MetricRow(
        endpoint=endpoint,
        arm="absorption_distribution__reg",
        metric=metric,
        n_test=100,
        n_pool=300,
        kermt=Side(kermt, std),
        matched=Side(matched, std),
        full=Side(full, std),
    )


def test_nemenyi_critical_difference_matches_the_published_constant():
    # q_0.05 for k = 3 is 2.343 (Demsar 2006, table 5); CD = 2.343 * sqrt(3 * 4 / (6 * 8)).
    assert nemenyi_critical_difference(3, 8) == pytest.approx(1.17, abs=0.01)
    assert nemenyi_critical_difference(3, 16) < nemenyi_critical_difference(3, 8)


def test_a_lower_mae_gets_the_lower_rank_and_a_higher_auroc_does_too():
    mae = rank_endpoint(_row("a", "MAE", kermt=0.5, matched=0.7, full=0.6))
    assert mae.ranks == (1.0, 3.0, 2.0)
    auroc = rank_endpoint(_row("b", "AUROC", kermt=0.90, matched=0.95, full=0.92))
    assert auroc.ranks == (3.0, 1.0, 2.0)


def test_ties_share_the_average_rank():
    tied = rank_endpoint(_row("c", "MAE", kermt=0.5, matched=0.5, full=0.9))
    assert tied.ranks == (1.5, 1.5, 3.0)


def test_secondary_metrics_are_left_out_of_the_ranking():
    rows = [_row("x", "AUPRC", 0.9, 0.9, 0.9), _row("x", "AUROC", 0.9, 0.8, 0.7)]
    assert [r.metric for r in primary_rows(rows)] == ["AUROC"]


def test_a_variant_that_is_always_ahead_is_found_and_the_sign_test_counts_it():
    rows = [_row(f"e{i}", "MAE", kermt=0.1, matched=0.5, full=0.9) for i in range(8)]
    sig = analyse(rows)
    assert sig.mean_ranks == (1.0, 2.0, 3.0)
    assert sig.friedman_p < 0.001
    first = sig.pairs[0]  # KERMT against the pool-matched model
    assert (first.a_ahead, first.b_ahead, first.ties) == (8, 0, 0)
    assert first.p_sign == pytest.approx(2 / 2**8)
    # 2.0 is further from 1.0 than the critical difference of 1.17, so the claim is allowed.
    assert max(sig.mean_ranks) - min(sig.mean_ranks) > sig.critical_difference


def test_mixed_directions_give_no_significant_ordering():
    rows = [
        _row("e0", "MAE", 0.1, 0.5, 0.9),
        _row("e1", "MAE", 0.5, 0.9, 0.1),
        _row("e2", "MAE", 0.9, 0.1, 0.5),
        _row("e3", "AUROC", 0.9, 0.5, 0.1),
        _row("e4", "AUROC", 0.5, 0.1, 0.9),
        _row("e5", "AUROC", 0.1, 0.9, 0.5),
    ]
    sig = analyse(rows)
    assert sig.friedman_p == pytest.approx(1.0)
    assert max(sig.mean_ranks) - min(sig.mean_ranks) <= sig.critical_difference


def test_fewer_than_three_endpoints_is_refused():
    with pytest.raises(ValueError):
        analyse([_row("a", "MAE", 0.1, 0.2, 0.3), _row("b", "MAE", 0.1, 0.2, 0.3)])


def test_the_report_states_its_limits_and_names_no_winner():
    rows = [_row(f"e{i}", "MAE", kermt=0.1 + i / 100, matched=0.5, full=0.9) for i in range(8)]
    text = render_markdown(analyse(rows))
    assert "## Limits" in text
    assert "not a verdict" in text
    lowered = text.lower()
    for word in ("winner", "outperform", "superior", "best model"):
        assert word not in lowered
