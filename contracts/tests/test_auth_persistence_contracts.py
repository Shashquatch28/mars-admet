"""M3 contract guards for Module 13 auth + persistence shapes."""

import pytest
from mars_contracts import (
    DeleteAccountRequest,
    Endpoint,
    EndpointPrediction,
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequestModel,
    PredictionResponse,
    RegisterRequest,
    SaveMoleculeRequest,
    SaveReportRequest,
)


def _prediction_response() -> PredictionResponse:
    return PredictionResponse(
        smiles_input="CCO",
        smiles_standardized="CCO",
        molecule_id="deadbeefdeadbeef",
        predictions=[
            EndpointPrediction(
                endpoint=Endpoint.BBB,
                value=0.73,
                confidence_low=0.6,
                confidence_high=0.86,
                in_domain=True,
                knn_distance=0.21,
            )
        ],
        model_version="stub-v0",
        served_at="2026-08-30T00:00:00Z",
    )


def test_endpoint_prediction_model_id_defaults_to_stub():
    pred = EndpointPrediction(
        endpoint=Endpoint.BBB, value=0.5, confidence_low=0.4, confidence_high=0.6,
        in_domain=True, knn_distance=0.1,
    )
    assert pred.model_id == "stub-v0"


def test_endpoint_prediction_model_id_can_be_overridden():
    pred = EndpointPrediction(
        endpoint=Endpoint.HIA, value=0.9, confidence_low=0.9, confidence_high=0.9,
        in_domain=True, knn_distance=0.05, model_id="mars-xgboost-ecfp-desc-v1",
    )
    assert pred.model_id == "mars-xgboost-ecfp-desc-v1"


def test_register_request_rejects_short_password():
    RegisterRequest(email="a@b.com", password="longenough1", turnstile_token="tok")
    with pytest.raises(ValueError):
        RegisterRequest(email="a@b.com", password="short", turnstile_token="tok")


def test_register_request_rejects_bad_email():
    with pytest.raises(ValueError):
        RegisterRequest(email="not-an-email", password="longenough1", turnstile_token="tok")


def test_login_request_roundtrips():
    req = LoginRequest(email="a@b.com", password="whatever1")
    assert LoginRequest.model_validate_json(req.model_dump_json()) == req


def test_password_reset_shapes():
    PasswordResetRequestModel(email="a@b.com")
    PasswordResetConfirmRequest(token="sometoken", new_password="longenough1")


def test_save_molecule_request_snapshots_prediction():
    req = SaveMoleculeRequest(prediction=_prediction_response(), label="my mol", tags=["favorite"])
    assert req.prediction.molecule_id == "deadbeefdeadbeef"
    assert req.tags == ["favorite"]


def test_save_report_request_accepts_single_prediction():
    req = SaveReportRequest(type="single", results=_prediction_response(), molecule_ids=["deadbeefdeadbeef"])
    assert req.type == "single"


def test_delete_account_requires_password():
    with pytest.raises(ValueError):
        DeleteAccountRequest()
