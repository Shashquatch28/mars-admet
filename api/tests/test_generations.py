"""GET /generations (ADR-026): the deployed generation, anonymous, and no choice that is not real."""

from app.core.config import get_settings
from app.main import app
from app.services import prediction_service as ps
from fastapi.testclient import TestClient

client = TestClient(app, base_url="http://testserver/api")


def test_generations_reports_only_the_deployed_generation_without_a_session():
    active = get_settings().model_version
    r = client.get("/generations")  # no cookie: anonymous like /predict
    assert r.status_code == 200
    assert r.json() == {"active": active, "available": [active], "kermt_endpoints": []}


class _Routing:
    def as_dict(self) -> dict[str, str]:
        return {"bbb_permeability": "kermt", "solubility_logs": "xgboost", "clearance_microsomal": "kermt"}


class _Router:
    routing = _Routing()

    def served_by_kermt(self) -> frozenset[str]:
        return frozenset({"bbb_permeability", "clearance_microsomal"})


def test_generations_names_the_same_version_predictions_carry_and_the_kermt_endpoints(monkeypatch):
    monkeypatch.setattr(ps, "_get_kermt_router", lambda: _Router())
    body = client.get("/generations").json()
    assert body["active"] == ps.serving_version()
    assert "+kermt." in body["active"]
    assert body["available"] == [body["active"]]
    assert body["kermt_endpoints"] == ["bbb_permeability", "clearance_microsomal"]
