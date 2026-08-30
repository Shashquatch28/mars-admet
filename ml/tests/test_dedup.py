"""Tests for the tiered dedup / conflict resolution (Module 1 §3)."""

from __future__ import annotations

from data.dedup import DedupOptions, dedup, select_policy


def _dedup(pairs, task, policy):
    return dedup(
        dataset_key="test",
        endpoint_key="test",
        pairs=pairs,
        options=DedupOptions(policy=policy, task=task, rationale="test"),
    )


# --- policy selection -----------------------------------------------------


def test_low_conflict_large_dataset_drops_conflicting():
    p = select_policy(task="classification", conflict_rate_over_multi=0.03, dataset_n=10_000)
    assert p.policy == "drop_conflicting"


def test_moderate_conflict_regression_averages():
    p = select_policy(task="regression", conflict_rate_over_multi=0.5, dataset_n=10_000)
    assert p.policy == "average"


def test_moderate_conflict_classification_majority_votes():
    p = select_policy(task="classification", conflict_rate_over_multi=0.2, dataset_n=10_000)
    assert p.policy == "majority_vote"


def test_small_dataset_overrides_low_conflict_to_preserving_policy():
    p = select_policy(task="classification", conflict_rate_over_multi=0.0, dataset_n=475)  # DILI
    assert p.policy == "majority_vote"


# --- classification core --------------------------------------------------


def test_consensus_classification_is_kept():
    pairs = [("A", 1), ("A", 1)]
    out, r = _dedup(pairs, "classification", "drop_conflicting")
    assert len(out) == 1
    assert out[0].label == 1
    assert out[0].action == "consensus_kept"
    assert r.n_dropped_conflicting == 0


def test_conflicting_classification_dropped_under_drop_policy():
    pairs = [("A", 0), ("A", 1)]
    out, r = _dedup(pairs, "classification", "drop_conflicting")
    assert out == []
    assert r.n_dropped_conflicting == 1
    assert r.dropped_smiles == ["A"]


def test_conflicting_classification_majority_voted():
    pairs = [("A", 1), ("A", 1), ("A", 0)]
    out, r = _dedup(pairs, "classification", "majority_vote")
    assert len(out) == 1
    assert out[0].label == 1
    assert out[0].action == "majority_vote"
    assert r.n_majority_voted == 1


def test_tie_in_majority_vote_drops_that_molecule_only():
    pairs = [("A", 1), ("A", 0), ("B", 1)]
    out, r = _dedup(pairs, "classification", "majority_vote")
    smis = [o.standardized_smiles for o in out]
    assert "B" in smis
    assert "A" not in smis
    assert r.n_dropped_tie == 1


# --- regression core ------------------------------------------------------


def test_consensus_regression_is_kept():
    pairs = [("A", 1.234), ("A", 1.234)]
    out, r = _dedup(pairs, "regression", "average")
    assert len(out) == 1
    assert out[0].label == 1.234


def test_conflicting_regression_averaged():
    pairs = [("A", 1.0), ("A", 3.0)]
    out, r = _dedup(pairs, "regression", "average")
    assert len(out) == 1
    assert out[0].label == 2.0
    assert out[0].action == "averaged"
    assert r.n_averaged == 1


def test_conflicting_regression_dropped_under_drop_policy():
    pairs = [("A", 1.0), ("A", 3.0)]
    out, r = _dedup(pairs, "regression", "drop_conflicting")
    assert out == []
    assert r.n_dropped_conflicting == 1


# --- singleton handling ---------------------------------------------------


def test_singletons_pass_through():
    pairs = [("A", 1), ("B", 0), ("C", 1)]
    out, r = _dedup(pairs, "classification", "drop_conflicting")
    assert {o.standardized_smiles for o in out} == {"A", "B", "C"}
    assert r.n_singletons == 3
