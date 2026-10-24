"""Module 11 section 5 self-audit report: it states failures, never hides them, and types nothing by hand."""

from __future__ import annotations

from eval.leakage_audit import LeakageAuditReport, LeakageCheckResult
from eval.self_audit import render_markdown


def _report(name: str, *, scaffold_ok: bool) -> LeakageAuditReport:
    return LeakageAuditReport(
        endpoint_key=name,
        checks=[
            LeakageCheckResult("test_disjoint_from_train_val_smiles", True, "no overlap"),
            LeakageCheckResult(
                "test_disjoint_from_train_val_scaffolds",
                scaffold_ok,
                "no overlap" if scaffold_ok else "19 overlapping non-acyclic scaffolds",
            ),
        ],
    )


def _render(reports):
    return render_markdown(
        reports,
        prep_id="snap",
        manifest_sha="abc",
        code_sha="def",
        versions={"numpy": "2.0"},
        sweep={"n_attempted": 70, "n_endpoints": 14, "n_seeds_per_endpoint": 5, "n_completed": 70, "n_failed": 0},
        today="2026-10-24",
    )


def test_a_failing_check_is_counted_named_and_explained():
    text = _render([_report("ames_mutagenicity", scaffold_ok=True), _report("dili_liver_injury", scaffold_ok=False)])
    assert "2 endpoints, 4 checks, 1 failed" in text
    assert "| dili_liver_injury | 1 / 2 | test_disjoint_from_train_val_scaffolds: 19 overlapping" in text
    assert "`dili_liver_injury`" in text.split("Reading the scaffold check")[1]
    assert "does not meet that rule for DILI" in text


def test_the_audit_says_it_ran_no_hyperparameter_search_and_carries_the_run_provenance():
    text = _render([_report("ames_mutagenicity", scaffold_ok=True)])
    assert "not a hyperparameter search" in text
    assert "`snap`" in text and "`abc`" in text and "`def`" in text
    assert "70 training runs" in text
