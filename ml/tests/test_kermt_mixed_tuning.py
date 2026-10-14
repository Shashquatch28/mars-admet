"""CPU tests for the pre-registered tuning protocol and post-hoc epoch re-scoring."""

from __future__ import annotations

import json

import numpy as np
import pytest
from train.kermt_mixed import posthoc, tuning
from train.kermt_mixed.scaling import ColumnScaler
from train.kermt_mixed.tuning import Axis, Protocol, ProtocolError


def _proto(**kw):
    """A protocol for TESTS. The numbers are fixtures, not recommendations."""
    base = dict(
        name="t-kendall",
        cluster="metabolism",
        arm="kendall",
        space=(
            Axis("epochs", "choice", values=(7, 15, 30, 45)),
            Axis("max_lr", "loguniform", low=1e-5, high=1e-3),
            Axis("min_per_task", "int", low=0, high=6),
        ),
        reference={"epochs": 30, "max_lr": 1e-4, "min_per_task": 0},
        n_trials=6,
        sampling_seed=11,
        tuning_seeds=(0, 1),
        objective="val_selection_loss",
        lower_is_better=True,
        min_improvement_in_stds=1.0,
        notes="fixture",
    )
    base.update(kw)
    return Protocol(**base)


# ---- no defaults --------------------------------------------------------------


def test_protocol_has_no_defaults_every_field_must_be_stated():
    with pytest.raises(TypeError):
        Protocol(name="x", cluster="c", arm="kendall")  # type: ignore[call-arg]


def test_one_tuning_seed_is_refused_because_there_is_no_noise_estimate():
    with pytest.raises(ProtocolError, match=">= 2 seeds"):
        _proto(tuning_seeds=(0,))


def test_reference_must_cover_exactly_the_searched_parameters():
    with pytest.raises(ProtocolError, match="exactly the searched"):
        _proto(reference={"epochs": 30})
    with pytest.raises(ProtocolError, match="unknown parameter"):
        Axis("learning_rate", "uniform", low=0.0, high=1.0)


# ---- enumeration --------------------------------------------------------------


def test_trial_zero_is_the_reference_and_the_rest_reproducible_and_distinct():
    p = _proto()
    a, b = tuning.enumerate_trials(p), tuning.enumerate_trials(p)
    assert [t.params for t in a] == [t.params for t in b]
    assert a[0].is_reference and dict(a[0].params) == dict(p.reference)
    assert len(a) == p.n_trials
    keys = {json.dumps(t.params, sort_keys=True) for t in a}
    assert len(keys) == len(a)
    for t in a[1:]:
        assert 1e-5 <= t.params["max_lr"] <= 1e-3 and 0 <= t.params["min_per_task"] <= 6


def test_a_space_too_small_for_the_budget_is_an_error_not_a_shorter_search():
    tiny = _proto(
        space=(Axis("epochs", "choice", values=(7, 30)),),
        reference={"epochs": 30},
        n_trials=5,
    )
    with pytest.raises(ProtocolError, match="too small"):
        tuning.enumerate_trials(tiny)


# ---- registration --------------------------------------------------------------


def test_registration_is_idempotent_and_refuses_a_changed_protocol(tmp_path):
    path = tmp_path / "reg" / "p.json"
    p = _proto()
    h = tuning.preregister(p, path)
    assert tuning.preregister(p, path) == h  # same protocol: fine
    tuning.verify_registration(p, path)
    with pytest.raises(ProtocolError, match="not edited"):
        tuning.preregister(_proto(n_trials=9), path)  # widening the search after the fact
    with pytest.raises(ProtocolError):
        tuning.verify_registration(_proto(min_improvement_in_stds=0.0), path)


def test_source_tag_ties_a_run_to_the_registered_protocol_and_trial():
    p = _proto()
    tag = tuning.source_tag(p, 3)
    assert tag == f"tuning:{p.sha256()[:12]}:3"


def test_split_trial_params_routes_to_kermt_config_and_mixed_trainer():
    cfg, mixed = tuning.split_trial_params(
        {"epochs": 7, "max_lr": 3e-4, "min_per_task": 2, "gradnorm_alpha": 0.5, "gradnorm_lr": 0.01}
    )
    assert cfg == {"epochs": 7, "max_lr": 3e-4}
    assert mixed == {"min_per_task": 2, "gradnorm_alpha": 0.5, "gradnorm_lr": 0.01}
    with pytest.raises(ProtocolError):
        tuning.split_trial_params({"bogus": 1})


# ---- selection -----------------------------------------------------------------


def _results(p, ref, others):
    out = {0: ref}
    for i, v in enumerate(others, start=1):
        out[i] = v
    for t in tuning.enumerate_trials(p):
        out.setdefault(t.trial_id, [ref[0] + 0.5, ref[1] + 0.5])
    return out


def test_selection_stays_on_the_reference_when_the_gain_is_within_seed_noise():
    p = _proto()
    # seed noise ~0.05; best candidate is only 0.02 better.
    sel = tuning.select(p, _results(p, [1.00, 1.10], [[1.07, 1.05]]))
    assert sel.chosen_trial == 0 and not sel.moved_off_reference
    assert "No evidence" in sel.reason


def test_selection_moves_only_for_a_gain_larger_than_the_noise_threshold():
    p = _proto()
    sel = tuning.select(p, _results(p, [1.00, 1.10], [[0.70, 0.74]]))
    assert sel.chosen_trial == 1 and sel.moved_off_reference


def test_selection_respects_direction_for_higher_is_better_objectives():
    p = _proto(lower_is_better=False)
    res = {t.trial_id: [0.80, 0.82] for t in tuning.enumerate_trials(p)}
    res[2] = [0.90, 0.92]
    assert tuning.select(p, res).chosen_trial == 2
    res[2] = [0.70, 0.72]  # worse for higher-is-better -> stay
    assert tuning.select(p, res).chosen_trial == 0


def test_selection_refuses_partial_or_malformed_results():
    p = _proto()
    full = {t.trial_id: [1.0, 1.1] for t in tuning.enumerate_trials(p)}
    partial = dict(full)
    partial.pop(3)
    with pytest.raises(ProtocolError, match="exactly the registered trials"):
        tuning.select(p, partial)
    bad = dict(full)
    bad[1] = [1.0]
    with pytest.raises(ProtocolError, match="one per tuning seed"):
        tuning.select(p, bad)
    nan = dict(full)
    nan[2] = [1.0, float("nan")]
    with pytest.raises(ProtocolError, match="non-finite"):
        tuning.select(p, nan)


def test_a_zero_variance_reference_cannot_make_noise_look_like_signal():
    p = _proto()
    res = {t.trial_id: [1.0, 1.4] for t in tuning.enumerate_trials(p)}  # candidates noisy
    res[0] = [1.2, 1.2]  # reference happens to have zero spread
    res[1] = [1.1, 1.3]  # tiny gain relative to the other trials' spread
    sel = tuning.select(p, res)
    assert sel.chosen_trial == 0


def test_equal_budget_rule_catches_an_arm_with_extra_trials():
    kendall = _proto()
    gradnorm = _proto(arm="gradnorm", n_trials=10)
    with pytest.raises(ProtocolError, match="unequal tuning budget"):
        tuning.assert_equal_budget([kendall, gradnorm])
    tuning.assert_equal_budget([kendall, _proto(arm="fixed_task")])


# ---- post-hoc re-scoring ---------------------------------------------------------


def _auc(y, p):
    order = np.argsort(p)
    ranks = np.empty(len(p))
    ranks[order] = np.arange(1, len(p) + 1)
    pos = y == 1
    return float((ranks[pos].sum() - pos.sum() * (pos.sum() + 1) / 2) / (pos.sum() * (~pos).sum()))


def _mae(y, p):
    return float(np.mean(np.abs(y - p)))


def test_views_roundtrip_to_served_units_and_epoch_scores(tmp_path):
    rng = np.random.default_rng(0)
    n = 200
    y = np.stack([(rng.random(n) < 0.5).astype(float), 100 + 20 * rng.normal(size=n)], axis=1)
    scaler = ColumnScaler.fit(y, ["c", "r"], [False, True])
    flags = [True, False]

    arrays = {}
    for e, noise in enumerate([3.0, 1.0, 0.3, 0.8]):  # epoch 2 is the cleanest
        logit = (y[:, 0] * 2 - 1) * 2.0 + noise * rng.normal(size=n)
        reg = scaler.transform(y)[:, 1] + noise * 0.2 * rng.normal(size=n)
        arrays[f"atom_e{e:03d}"] = np.stack([logit, reg], axis=1)
        arrays[f"bond_e{e:03d}"] = np.stack([logit, reg], axis=1)
    npz = tmp_path / "val_views.npz"
    np.savez_compressed(npz, **arrays)

    preds = posthoc.epoch_predictions(npz, scaler, flags)
    assert sorted(preds) == [0, 1, 2, 3]
    assert ((preds[0][:, 0] > 0) & (preds[0][:, 0] < 1)).all()  # probabilities
    assert 60 < preds[0][:, 1].mean() < 140  # raw units

    epochs, scores = posthoc.per_epoch_task_scores(
        preds, y, flags, cls_metric=_auc, reg_metric=_mae
    )
    assert epochs == [0, 1, 2, 3] and scores.shape == (4, 2)
    assert posthoc.best_epoch(epochs, scores, flags, rule="mean_rank") == 2
    assert posthoc.best_epoch(epochs, scores, flags, rule="task:0") == 2
    assert posthoc.best_epoch(epochs, scores, flags, rule="task:1") == 2
    with pytest.raises(ValueError):
        posthoc.best_epoch(epochs, scores, flags, rule="nope")


def test_mean_rank_lets_auroc_and_mae_be_combined_without_choosing_weights():
    flags = [True, False]
    # epoch 0 wins AUROC but is worst on MAE; epoch 1 the reverse; epoch 3 is second on both.
    scores = np.array([[0.90, 30.0], [0.80, 10.0], [0.85, 20.0], [0.88, 15.0]])
    assert posthoc.best_epoch([0, 1, 2, 3], scores, flags, rule="mean_rank") == 3
    assert posthoc.best_epoch([0, 1, 2, 3], scores, flags, rule="task:0") == 0
    assert posthoc.best_epoch([0, 1, 2, 3], scores, flags, rule="task:1") == 1
