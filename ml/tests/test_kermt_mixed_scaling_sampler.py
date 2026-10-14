"""CPU tests for the Tier-1 trainer's numpy-only pieces: scaling and batch sampling."""

from __future__ import annotations

import numpy as np
import pytest
from train.kermt_mixed.sampler import batch_stats, stratified_batches
from train.kermt_mixed.scaling import (
    ColumnScaler,
    from_kermt_targets,
    to_kermt_targets,
)

NAN = np.nan


def _stock_scaler(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Verbatim numerics of kermt.data.scaler.StandardScaler.fit (pinned v2.0.0)."""
    x = np.array(x).astype(float)
    means = np.nanmean(x, axis=0)
    stds = np.nanstd(x, axis=0)
    means = np.where(np.isnan(means), np.zeros(means.shape), means)
    stds = np.where(np.isnan(stds), np.ones(stds.shape), stds)
    stds = np.where(stds == 0, np.ones(stds.shape), stds)
    return means, stds


# ---- scaling ---------------------------------------------------------------


def test_regression_columns_match_stock_standard_scaler():
    rng = np.random.default_rng(0)
    y = rng.normal(5.0, 3.0, size=(200, 3))
    y[::7, 1] = NAN
    sc = ColumnScaler.fit(y, ["a", "b", "c"], [True, True, True])
    means, stds = _stock_scaler(y)
    np.testing.assert_allclose(sc.means, means)
    np.testing.assert_allclose(sc.stds, stds)


def test_classification_columns_are_untouched_and_only_regression_is_scaled():
    y = np.array([[1.0, 10.0], [0.0, 20.0], [NAN, 30.0], [1.0, NAN]])
    sc = ColumnScaler.fit(y, ["cls", "reg"], [False, True])
    assert sc.means[0] == 0.0 and sc.stds[0] == 1.0
    out = sc.transform(y)
    np.testing.assert_array_equal(out[:, 0], y[:, 0])  # labels preserved, NaN included
    assert np.nanmean(out[:, 1]) == pytest.approx(0.0, abs=1e-12)


def test_transform_roundtrips_and_keeps_nan_missing():
    rng = np.random.default_rng(1)
    y = rng.normal(size=(50, 2))
    y[3, 0] = NAN
    sc = ColumnScaler.fit(y, ["a", "b"], [True, False])
    back = sc.inverse_transform(sc.transform(y))
    np.testing.assert_allclose(back, y, equal_nan=True)


def test_degenerate_columns_follow_kermt_conventions():
    y = np.array([[5.0, NAN], [5.0, NAN], [5.0, NAN]])  # constant, all-NaN
    sc = ColumnScaler.fit(y, ["const", "empty"], [True, True])
    assert sc.stds == (1.0, 1.0)
    assert sc.means == (5.0, 0.0)


def test_fit_uses_only_what_it_is_given():
    train = np.array([[0.0], [2.0]])
    other = np.array([[1000.0]])
    sc = ColumnScaler.fit(train, ["r"], [True])
    assert sc.means == (1.0,)
    assert sc.transform(other)[0, 0] > 100  # the scaler never saw it


def test_classification_column_with_nontrivial_scale_is_rejected():
    with pytest.raises(ValueError, match="mean=0, std=1"):
        ColumnScaler(names=("c",), is_regression=(False,), means=(0.5,), stds=(1.0,))


def test_dict_roundtrip():
    sc = ColumnScaler.fit(np.array([[1.0, 0.0], [3.0, 1.0]]), ["r", "c"], [True, False])
    assert ColumnScaler.from_dict(sc.to_dict()) == sc


def test_to_kermt_targets_uses_none_for_missing_never_nan():
    out = to_kermt_targets(np.array([[1.0, NAN], [NAN, 0.0]]))
    assert out == [[1.0, None], [None, 0.0]]
    assert all(v is None or not np.isnan(v) for row in out for v in row)
    np.testing.assert_array_equal(
        from_kermt_targets(out), np.array([[1.0, NAN], [NAN, 0.0]])
    )


# ---- sampler ---------------------------------------------------------------


def _mask(n=2000, seed=0):
    rng = np.random.default_rng(seed)
    dense = rng.random(n) < 0.95  # task 0: dense
    sparse = rng.random(n) < 0.04  # task 1: sparse (~80 rows)
    return np.stack([dense, sparse], axis=1)


def test_no_stratification_is_exactly_shuffle_then_chunk():
    m = _mask(100)
    b = stratified_batches(m, 32, min_per_task=0, seed=3, epoch=0)
    flat = np.concatenate(b)
    assert sorted(flat.tolist()) == list(range(100))  # every row exactly once
    assert [len(x) for x in b] == [32, 32, 32, 4]  # ceil(n / bs) batches, stock-style


def test_deterministic_per_seed_and_epoch_but_varies_across_epochs():
    m = _mask()
    a = stratified_batches(m, 32, min_per_task=2, seed=1, epoch=0)
    b = stratified_batches(m, 32, min_per_task=2, seed=1, epoch=0)
    c = stratified_batches(m, 32, min_per_task=2, seed=1, epoch=1)
    assert all(np.array_equal(x, y) for x, y in zip(a, b, strict=True))
    assert not all(np.array_equal(x, y) for x, y in zip(a, c, strict=True))


def test_every_batch_meets_the_per_task_minimum_when_labels_exist():
    m = _mask()
    plain = stratified_batches(m, 32, min_per_task=0, seed=0, epoch=0)
    strat = stratified_batches(m, 32, min_per_task=2, seed=0, epoch=0)
    assert batch_stats(plain, m)["batches_with_zero_labels_per_task"][1] > 0  # the problem is real
    s = batch_stats(strat, m)
    assert min(s["per_task_min"]) >= 2
    assert s["n_batches"] == len(plain)


def test_stratification_never_drops_base_rows_and_never_repeats_within_a_batch():
    m = _mask(500)
    base = stratified_batches(m, 32, min_per_task=0, seed=5, epoch=2)
    strat = stratified_batches(m, 32, min_per_task=3, seed=5, epoch=2)
    for b0, b1 in zip(base, strat, strict=True):
        assert set(b0.tolist()) <= set(b1.tolist())
        assert len(set(b1.tolist())) == len(b1)


def test_task_with_too_few_labels_is_topped_up_not_an_error():
    m = np.zeros((100, 2), dtype=bool)
    m[:, 0] = True
    m[:2, 1] = True  # only two labels exist for task 1
    out = stratified_batches(m, 10, min_per_task=5, seed=0, epoch=0)
    assert len(out) == 10  # no exception
