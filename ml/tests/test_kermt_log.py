"""Tests for ml/eval/kermt_log.py — saved-epoch identification from KERMT's finetune.log.

Synthetic logs only: no real ``finetune.log`` exists on the laptop. The shape of the main case mirrors
what the 2026-09-30 session note reports for three workstation runs (KERMT's final "best validation"
line names a later epoch than the one whose score it quotes). See decisions.md 2026-09-30 D1.
"""

from __future__ import annotations

import json

import pytest
from eval.kermt_log import (
    SOURCE_DERIVED,
    SOURCE_SAVING_LINE,
    SOURCE_UNAVAILABLE,
    parse_epoch_rows,
    parse_logged_best,
    parse_saving_epochs,
    resolve_saved_epoch,
    resolve_saved_epoch_from_file,
)


def _epoch_line(epoch: int, auc: float) -> str:
    return (
        f"Epoch: {epoch} loss_train: 0.9000 loss_val: 0.8000 auc_val: {auc:.4f} "
        "cur_lr: 0.0001 t_time: 5.0s v_time: 1.0s"
    )


def _log(aucs, *, logged: tuple[int, float] | None = None, saving: list[int] | None = None) -> str:
    lines = [_epoch_line(e, a) for e, a in enumerate(aucs)]
    lines += [f"Saving model at epoch {n}" for n in (saving or [])]
    if logged is not None:
        lines.append(f"best validation auc = {logged[1]:.4f} on epoch {logged[0]}")
    return "\n".join(lines) + "\n"


def _rising_then_drifting(n: int = 30, peak_epoch: int = 18, peak: float = 0.93) -> list[float]:
    """auc_val climbs to `peak` at `peak_epoch`, then drifts slightly lower (the overfitting shape)."""
    return [peak - 0.004 * abs(peak_epoch - e) for e in range(n)]


def test_observed_shape_saved_epoch_is_the_best_auc_row_not_the_logged_epoch():
    aucs = _rising_then_drifting()
    text = _log(aucs, logged=(29, max(aucs)))  # KERMT logs epoch 29 but quotes the epoch-18 score
    r = resolve_saved_epoch(text)
    assert r.epoch == 18
    assert r.source == SOURCE_DERIVED
    assert r.logged_best_epoch == 29
    assert r.logged_best_auc == pytest.approx(max(aucs), abs=1e-4)
    assert r.consistent_with_logged_best_score is True
    assert any("logged best epoch (29) differs from the saved epoch (18)" in n for n in r.notes)


def test_no_note_when_logged_epoch_already_equals_the_saved_epoch():
    aucs = _rising_then_drifting()
    r = resolve_saved_epoch(_log(aucs, logged=(18, max(aucs))))
    assert r.epoch == 18 and r.consistent_with_logged_best_score is True
    assert not any("differs from the saved epoch" in n for n in r.notes)


def test_ties_resolve_to_the_first_epoch_with_the_best_score():
    r = resolve_saved_epoch(_log([0.80, 0.90, 0.90, 0.85], logged=(1, 0.90)))
    assert r.epoch == 1


def test_saving_line_that_agrees_is_recorded_without_a_warning():
    aucs = _rising_then_drifting()
    r = resolve_saved_epoch(_log(aucs, logged=(29, max(aucs)), saving=[5, 12, 18]))
    assert r.epoch == 18 and r.saving_line_epoch == 18
    assert not any("Saving model at epoch" in n for n in r.notes)


def test_saving_line_that_disagrees_is_reported_not_silently_adopted():
    aucs = _rising_then_drifting()
    r = resolve_saved_epoch(_log(aucs, logged=(29, max(aucs)), saving=[5, 12, 17]))
    assert r.epoch == 18 and r.source == SOURCE_DERIVED  # numbering of the per-epoch rows wins
    assert r.saving_line_epoch == 17
    assert any("last 'Saving model at epoch' line says 17" in n for n in r.notes)


def test_only_a_saving_line_available_is_used_and_labelled_as_such():
    r = resolve_saved_epoch("Saving model at epoch 7\n")
    assert r.epoch == 7 and r.source == SOURCE_SAVING_LINE
    assert r.consistent_with_logged_best_score is None


def test_nothing_parseable_yields_unavailable_not_a_guess():
    r = resolve_saved_epoch("some unrelated text\n")
    assert r.epoch is None and r.source == SOURCE_UNAVAILABLE
    assert r.consistent_with_logged_best_score is None


def test_a_regression_shaped_log_is_unavailable_because_no_auc_rows_exist():
    text = "\n".join(
        f"Epoch: {e} loss_train: 0.9 loss_val: 0.8 mae_val: {0.5 - 0.01 * e:.4f} cur_lr: 0.0001 t_time: 5.0s v_time: 1.0s"
        for e in range(5)
    )
    assert parse_epoch_rows(text) == []
    assert resolve_saved_epoch(text).epoch is None


def test_logged_score_that_does_not_match_the_saved_epoch_is_flagged_as_inconsistent():
    aucs = _rising_then_drifting()
    r = resolve_saved_epoch(_log(aucs, logged=(29, max(aucs) + 0.02)))
    assert r.epoch == 18
    assert r.consistent_with_logged_best_score is False
    assert any("STOP and report" in n for n in r.notes)


def test_score_tolerance_is_respected():
    aucs = _rising_then_drifting()
    ok = resolve_saved_epoch(_log(aucs, logged=(29, max(aucs) + 0.0005)))
    assert ok.consistent_with_logged_best_score is True
    tight = resolve_saved_epoch(_log(aucs, logged=(29, max(aucs) + 0.0005)), tolerance=1e-5)
    assert tight.consistent_with_logged_best_score is False


def test_parsers_on_their_own():
    text = _log([0.5, 0.6], logged=(3, 0.6), saving=[0, 1])
    rows = parse_epoch_rows(text)
    assert [r["epoch"] for r in rows] == [0, 1] and rows[1]["auc_val"] == pytest.approx(0.6)
    assert parse_logged_best(text) == (3, pytest.approx(0.6))
    assert parse_logged_best("nothing") == (None, None)
    assert parse_saving_epochs(text) == [0, 1]


def test_result_is_json_serialisable_and_file_variant_matches(tmp_path):
    aucs = _rising_then_drifting()
    text = _log(aucs, logged=(29, max(aucs)), saving=[18])
    path = tmp_path / "finetune.log"
    path.write_text(text, encoding="utf-8")
    from_file = resolve_saved_epoch_from_file(path)
    assert from_file == resolve_saved_epoch(text)
    d = json.loads(json.dumps(from_file.to_dict()))
    assert d["epoch"] == 18 and d["source"] == SOURCE_DERIVED and isinstance(d["notes"], list)


def test_tier0_artifacts_parse_finetune_log_keeps_its_signature(tmp_path):
    pytest.importorskip("matplotlib")  # tier0_artifacts imports matplotlib at module level
    from eval.tier0_artifacts import parse_finetune_log

    aucs = _rising_then_drifting()
    path = tmp_path / "finetune.log"
    path.write_text(_log(aucs, logged=(29, max(aucs))), encoding="utf-8")
    rows, logged_epoch, logged_auc = parse_finetune_log(path)
    assert len(rows) == 30 and logged_epoch == 29 and logged_auc == pytest.approx(max(aucs), abs=1e-4)
