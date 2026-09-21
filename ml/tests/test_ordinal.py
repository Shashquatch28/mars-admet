"""Tests for the Tier-2 ordinal/CDF codec."""

from __future__ import annotations

import numpy as np
import pytest
from featurize.ordinal import (
    ORDINAL_VERSION,
    OrdinalCdfCodec,
    decode,
    discretization_ceiling_mae,
    encode,
    fit_ordinal_codec,
    ordinal_column_names,
)


@pytest.fixture
def y_linear() -> np.ndarray:
    return np.linspace(-5.0, 5.0, 200)


def test_column_names_are_adapter_safe():
    """Names must survive write_finetune_csv/read_predictions_csv unchanged."""
    assert ordinal_column_names("solubility_logs", 3) == [
        "solubility_logs__gt0",
        "solubility_logs__gt1",
        "solubility_logs__gt2",
    ]


def test_fit_produces_n_bins_minus_one_thresholds(y_linear):
    codec = fit_ordinal_codec(y_linear, n_bins=8)
    assert codec.n_thresholds == 7
    assert codec.n_bins == 8
    assert codec.version == ORDINAL_VERSION


def test_thresholds_are_strictly_increasing(y_linear):
    codec = fit_ordinal_codec(y_linear, n_bins=10)
    assert np.all(np.diff(np.asarray(codec.thresholds)) > 0)


def test_quantile_strategy_balances_bin_occupancy():
    """Skewed targets (logS, Caco-2) are why quantile is the default."""
    rng = np.random.default_rng(0)
    y = np.concatenate([rng.normal(0, 1, 900), rng.normal(20, 1, 100)])
    codec = fit_ordinal_codec(y, n_bins=5, strategy="quantile")
    counts = encode(codec, y)[:, 0]  # P(y > t_0) indicator
    # ~80% of mass should sit above the first quintile cut, not ~10%
    assert 0.7 < counts.mean() < 0.9


def test_uniform_strategy_differs_from_quantile_on_skewed_data():
    rng = np.random.default_rng(0)
    y = np.concatenate([rng.normal(0, 1, 900), rng.normal(20, 1, 100)])
    q = fit_ordinal_codec(y, n_bins=5, strategy="quantile")
    u = fit_ordinal_codec(y, n_bins=5, strategy="uniform")
    assert q.thresholds != u.thresholds


def test_encode_is_binary_and_row_monotone(y_linear):
    codec = fit_ordinal_codec(y_linear, n_bins=6)
    enc = encode(codec, y_linear)
    assert set(np.unique(enc)) <= {0.0, 1.0}
    # A true survival indicator row is non-increasing: once y <= t_m it stays 0.
    assert np.all(np.diff(enc, axis=1) <= 0)


def test_encode_maps_nan_label_to_all_nan_row(y_linear):
    codec = fit_ordinal_codec(y_linear, n_bins=4)
    y = np.array([1.0, np.nan, -3.0])
    enc = encode(codec, y)
    assert np.isnan(enc[1]).all()
    assert not np.isnan(enc[0]).any()
    assert not np.isnan(enc[2]).any()


def test_decode_enforces_monotonicity_frank_hall_does_not_guarantee():
    """Independently-learned columns can violate P(y>t_m) being non-increasing."""
    codec = OrdinalCdfCodec(
        thresholds=(0.0, 1.0, 2.0),
        bin_representatives=(-1.0, 0.5, 1.5, 3.0),
        strategy="manual",
    )
    # Deliberately non-monotone: column 1 exceeds column 0.
    p = np.array([[0.4, 0.9, 0.1]])
    out = decode(codec, p)
    assert np.isfinite(out).all()
    # Running-min turns it into [0.4, 0.4, 0.1]; bin probs stay non-negative.
    padded = np.concatenate([[1.0], np.minimum.accumulate(p[0]), [0.0]])
    assert np.all(np.diff(padded) <= 1e-12)


def test_decode_recovers_bin_representative_for_a_confident_prediction():
    codec = OrdinalCdfCodec(
        thresholds=(0.0, 1.0),
        bin_representatives=(-2.0, 0.5, 4.0),
        strategy="manual",
    )
    # Certain that y > t_0 and y > t_1 -> top bin.
    assert decode(codec, np.array([[1.0, 1.0]]))[0] == pytest.approx(4.0)
    # Certain that y <= t_0 -> bottom bin.
    assert decode(codec, np.array([[0.0, 0.0]]))[0] == pytest.approx(-2.0)
    # Certain y > t_0 but not > t_1 -> middle bin.
    assert decode(codec, np.array([[1.0, 0.0]]))[0] == pytest.approx(0.5)


def test_roundtrip_error_is_bounded_and_shrinks_with_more_bins(y_linear):
    coarse = discretization_ceiling_mae(fit_ordinal_codec(y_linear, n_bins=4), y_linear)
    fine = discretization_ceiling_mae(fit_ordinal_codec(y_linear, n_bins=32), y_linear)
    assert fine < coarse
    assert fine >= 0.0


def test_ceiling_mae_is_the_zero_gpu_gate(y_linear):
    """The floor must be small relative to the data's own spread to be usable."""
    codec = fit_ordinal_codec(y_linear, n_bins=16)
    ceiling = discretization_ceiling_mae(codec, y_linear)
    # Mean |y - median| is ~2.5 for this range; the floor should be far below it.
    assert ceiling < 0.25 * float(np.mean(np.abs(y_linear - np.median(y_linear))))


def test_ceiling_ignores_nan_labels(y_linear):
    codec = fit_ordinal_codec(y_linear, n_bins=8)
    with_nan = np.concatenate([y_linear, [np.nan, np.nan]])
    assert discretization_ceiling_mae(codec, with_nan) == pytest.approx(
        discretization_ceiling_mae(codec, y_linear)
    )


def test_fit_ignores_nan_labels(y_linear):
    padded = np.concatenate([y_linear, np.full(50, np.nan)])
    assert fit_ordinal_codec(padded, n_bins=6).thresholds == pytest.approx(
        fit_ordinal_codec(y_linear, n_bins=6).thresholds
    )


def test_tied_labels_collapse_duplicate_thresholds():
    """Censored/tied assay readouts must not produce zero-width bins."""
    y = np.array([1.0] * 90 + [5.0] * 10)
    codec = fit_ordinal_codec(y, n_bins=8)
    assert np.all(np.diff(np.asarray(codec.thresholds)) > 0)
    assert codec.n_thresholds < 7


def test_all_identical_labels_is_rejected():
    with pytest.raises(ValueError, match="carries no information"):
        fit_ordinal_codec(np.full(50, 3.0), n_bins=4)


def test_fit_rejects_bad_inputs(y_linear):
    with pytest.raises(ValueError, match="n_bins must be >= 2"):
        fit_ordinal_codec(y_linear, n_bins=1)
    with pytest.raises(ValueError, match="must be 1-D"):
        fit_ordinal_codec(y_linear.reshape(-1, 2), n_bins=4)
    with pytest.raises(ValueError, match="at least 2 non-NaN"):
        fit_ordinal_codec(np.array([1.0, np.nan]), n_bins=4)
    with pytest.raises(ValueError, match="unknown strategy"):
        fit_ordinal_codec(y_linear, n_bins=4, strategy="kmeans")  # type: ignore[arg-type]


def test_decode_rejects_column_count_mismatch(y_linear):
    codec = fit_ordinal_codec(y_linear, n_bins=5)
    with pytest.raises(ValueError, match="columns but the codec has"):
        decode(codec, np.zeros((3, 99)))


def test_codec_rejects_inconsistent_representative_count():
    with pytest.raises(ValueError, match="bin_representatives must have"):
        OrdinalCdfCodec(thresholds=(0.0, 1.0), bin_representatives=(1.0,), strategy="x")


def test_codec_rejects_unsorted_thresholds():
    with pytest.raises(ValueError, match="strictly increasing"):
        OrdinalCdfCodec(
            thresholds=(1.0, 0.0), bin_representatives=(0.0, 0.5, 1.0), strategy="x"
        )


def test_codec_dict_roundtrip(y_linear):
    codec = fit_ordinal_codec(y_linear, n_bins=6)
    restored = OrdinalCdfCodec.from_dict(codec.to_dict())
    assert restored == codec
