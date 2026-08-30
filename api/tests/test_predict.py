"""API smoke + contract-conformance tests for the M0 stub predictor."""

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_predict_returns_all_14_ml_endpoints():
    r = client.post("/predict", json={"smiles": "CCO", "endpoints": None})
    assert r.status_code == 200
    body = r.json()
    assert len(body["predictions"]) == 14  # 13 ML + DILI standalone, SA excluded
    assert body["model_version"]
    assert body["smiles_standardized"] == "CCO"
    for p in body["predictions"]:
        assert {"confidence_low", "confidence_high", "in_domain", "knn_distance"} <= p.keys()
        assert p["confidence_low"] <= p["value"] <= p["confidence_high"]


def test_predict_is_deterministic_per_molecule():
    a = client.post("/predict", json={"smiles": "CCO"}).json()
    b = client.post("/predict", json={"smiles": "CCO"}).json()
    assert a["predictions"] == b["predictions"]
    assert a["molecule_id"] == b["molecule_id"]


def test_predict_subset_of_endpoints():
    r = client.post("/predict", json={"smiles": "CCO", "endpoints": ["bbb_permeability"]})
    assert r.status_code == 200
    preds = r.json()["predictions"]
    assert [p["endpoint"] for p in preds] == ["bbb_permeability"]


def test_empty_smiles_rejected():
    assert client.post("/predict", json={"smiles": "   "}).status_code == 422
    assert client.post("/predict", json={"smiles": ""}).status_code == 422
