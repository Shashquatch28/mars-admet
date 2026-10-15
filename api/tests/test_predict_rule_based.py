"""Synthetic-accessibility (rule-based) handling in the prediction service.

The root `.venv` has no RDKit, so the ml-gated names (`compute_sa_score`,
`standardize_or_raise`, ...) do not exist here. These tests patch them in to
exercise the service logic; the scorer itself is covered in
`ml/tests/test_rule_based.py`, and the real end-to-end path is exercised in the
Docker image.
"""

from __future__ import annotations

import pytest
from app.services import prediction_service as svc
from mars_contracts import ALL_ENDPOINTS, ML_ENDPOINTS, Endpoint


@pytest.fixture
def ml_stack(monkeypatch):
    """Pretend the ml stack is present, with a fixed SA score and no registry."""
    monkeypatch.setattr(svc, "_ml_available", True)
    monkeypatch.setattr(svc, "standardize_or_raise", lambda s: s.strip(), raising=False)
    monkeypatch.setattr(svc, "_get_registry", lambda: None)
    monkeypatch.setattr(svc, "SA_MODEL_ID", "rdkit-sascore", raising=False)
    monkeypatch.setattr(svc, "SA_UNIT", "SA score", raising=False)
    calls = {"n": 0, "score": 2.84}

    def fake_score(smiles):
        calls["n"] += 1
        return calls["score"]

    monkeypatch.setattr(svc, "compute_sa_score", fake_score, raising=False)
    return calls


def test_default_request_includes_sa_when_ml_stack_present(ml_stack):
    resp = svc.predict("CCO")
    eps = [p.endpoint for p in resp.predictions]
    assert set(eps) == set(ALL_ENDPOINTS)
    assert len(eps) == 15
    sa = resp.predictions[-1]
    assert sa.endpoint is Endpoint.SA_SCORE
    assert sa.value == 2.84
    assert (sa.confidence_low, sa.confidence_high) == (2.84, 2.84)
    assert sa.unit == "SA score"
    assert sa.model_id == "rdkit-sascore"


def test_sa_is_not_stubbed_without_ml_stack():
    # Root .venv: no rdkit -> the SA score is absent, never fabricated.
    resp = svc.predict("CCO")
    assert [p.endpoint for p in resp.predictions] == list(ML_ENDPOINTS)
    assert all(p.endpoint is not Endpoint.SA_SCORE for p in resp.predictions)


def test_explicit_subset_without_sa_does_not_compute_it(ml_stack):
    resp = svc.predict("CCO", [Endpoint.BBB])
    assert [p.endpoint for p in resp.predictions] == [Endpoint.BBB]
    assert ml_stack["n"] == 0


def test_sa_only_request(ml_stack):
    resp = svc.predict("CCO", [Endpoint.SA_SCORE])
    assert [p.endpoint for p in resp.predictions] == [Endpoint.SA_SCORE]


def test_explicit_request_order_is_preserved(ml_stack):
    resp = svc.predict("CCO", [Endpoint.SA_SCORE, Endpoint.BBB])
    assert [p.endpoint for p in resp.predictions] == [Endpoint.SA_SCORE, Endpoint.BBB]


def test_uncomputable_sa_is_omitted_not_defaulted(ml_stack, monkeypatch):
    monkeypatch.setattr(svc, "compute_sa_score", lambda s: None, raising=False)
    resp = svc.predict("CCO")
    assert [p.endpoint for p in resp.predictions] == list(ML_ENDPOINTS)


def test_sa_survives_real_inference_failure(ml_stack, monkeypatch):
    # If the model path raises ValueError and the service falls back to the stub,
    # the rule-based score (independent of any model) must still be returned.
    monkeypatch.setattr(svc, "_get_registry", lambda: object())

    def boom(*a, **k):
        raise ValueError("featurization failed")

    monkeypatch.setattr(svc, "predict_endpoints", boom, raising=False)
    with pytest.warns(UserWarning, match="falling back to stub"):
        resp = svc.predict("CCO")
    assert resp.predictions[-1].endpoint is Endpoint.SA_SCORE
