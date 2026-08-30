"""Phase 0 contract guards — cheap, deterministic, no ML deps."""

from mars_contracts import (
    ALL_ENDPOINTS,
    ENDPOINT_METADATA,
    ML_ENDPOINTS,
    BatchPredictResponse,
    BatchRowResult,
    CompareRequest,
    Endpoint,
    EndpointPrediction,
    PredictionResponse,
    TaskType,
)


def test_endpoint_counts_match_blueprint():
    # Module 2: 14 endpoints = 13 ML-trained + 1 rule-based (SA score).
    assert len(ALL_ENDPOINTS) == 15  # 14 + SA
    assert len(ML_ENDPOINTS) == 14
    assert Endpoint.SA_SCORE not in ML_ENDPOINTS


def test_every_endpoint_has_metadata():
    for ep in Endpoint:
        assert ep in ENDPOINT_METADATA
        meta = ENDPOINT_METADATA[ep]
        assert "task_type" in meta and "category" in meta and "cluster" in meta


def test_clusters_match_module4():
    clusters: dict[str, set[Endpoint]] = {}
    for ep, meta in ENDPOINT_METADATA.items():
        clusters.setdefault(meta["cluster"], set()).add(ep)
    assert clusters["metabolism"] == {
        Endpoint.CYP3A4, Endpoint.CYP2D6, Endpoint.CYP2C9, Endpoint.CLEARANCE,
    }
    assert clusters["absorption_distribution"] == {
        Endpoint.SOLUBILITY, Endpoint.LIPOPHILICITY, Endpoint.CACO2,
        Endpoint.HIA, Endpoint.PGP, Endpoint.BBB, Endpoint.PPB,
    }
    assert clusters["toxicity"] == {Endpoint.HERG, Endpoint.AMES}
    assert clusters["dili_standalone"] == {Endpoint.DILI}


def test_sa_score_is_rule_based():
    assert ENDPOINT_METADATA[Endpoint.SA_SCORE]["task_type"] == TaskType.RULE_BASED
    assert ENDPOINT_METADATA[Endpoint.SA_SCORE]["cluster"] is None


def test_prediction_response_roundtrips():
    resp = PredictionResponse(
        smiles_input="CCO",
        smiles_standardized="CCO",
        molecule_id="deadbeefdeadbeef",
        predictions=[
            EndpointPrediction(
                endpoint=Endpoint.BBB,
                value=0.73,
                unit=None,
                confidence_low=0.6,
                confidence_high=0.86,
                in_domain=True,
                knn_distance=0.21,
            )
        ],
        model_version="stub-v0",
        served_at="2026-08-30T00:00:00Z",
    )
    assert PredictionResponse.model_validate_json(resp.model_dump_json()) == resp


def test_compare_request_enforces_2_to_3_molecules():
    import pytest

    CompareRequest(smiles=["CCO", "CCC"])
    CompareRequest(smiles=["CCO", "CCC", "CCN"])
    with pytest.raises(ValueError):
        CompareRequest(smiles=["CCO"])
    with pytest.raises(ValueError):
        CompareRequest(smiles=["CCO", "CCC", "CCN", "CCF"])


def test_batch_response_shapes():
    interactive = BatchPredictResponse(
        status="done",
        total=1,
        completed=1,
        results=[BatchRowResult(row_index=0, smiles_input="CCO", ok=False, error="bad valence")],
    )
    assert interactive.job_id is None
    assert interactive.results[0].prediction is None
