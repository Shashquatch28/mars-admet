"""KERMT serving at the API boundary: the version string follows the routing, and a degraded answer is not cached.

No ml stack or service is needed: the router is replaced by a stand-in with the two methods the service reads.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.core.config import get_settings
from app.services import prediction_service as ps
from mars_contracts import Endpoint, EndpointPrediction, PredictionResponse


class _Routing:
    def __init__(self, table: dict[str, str]):
        self._table = table

    def as_dict(self) -> dict[str, str]:
        return dict(self._table)


class _Router:
    def __init__(self, table: dict[str, str]):
        self.routing = _Routing(table)
        self._kermt = frozenset(e for e, m in table.items() if m == "kermt")

    def served_by_kermt(self) -> frozenset[str]:
        return self._kermt


def _install(monkeypatch, router) -> None:
    # The router is only consulted when a service URL is configured; the cached settings must see it.
    if router is not None:
        monkeypatch.setenv("KERMT_SERVICE_URL", "http://kermt.test:8100")
    else:
        monkeypatch.delenv("KERMT_SERVICE_URL", raising=False)
    get_settings.cache_clear()
    monkeypatch.setattr(ps, "_ml_available", True)
    monkeypatch.setattr(ps, "_kermt_router", router)
    monkeypatch.setattr(ps, "_kermt_router_built", True)


def _response(model_ids: dict[Endpoint, str]) -> PredictionResponse:
    return PredictionResponse(
        smiles_input="CCO",
        smiles_standardized="CCO",
        molecule_id="m",
        predictions=[
            EndpointPrediction(endpoint=ep, value=0.5, confidence_low=0.4, confidence_high=0.6, in_domain=True,
                               knn_distance=0.1, model_id=mid)
            for ep, mid in model_ids.items()
        ],
        model_version="v",
        served_at=datetime.now(UTC),
    )


def test_version_is_the_plain_setting_when_kermt_is_off(monkeypatch):
    _install(monkeypatch, None)
    assert ps.serving_version() == ps.get_settings().model_version


def test_version_changes_when_routing_changes(monkeypatch):
    _install(monkeypatch, _Router({"herg_cardiotoxicity": "kermt", "ames_mutagenicity": "xgboost"}))
    a = ps.serving_version()
    _install(monkeypatch, _Router({"herg_cardiotoxicity": "xgboost", "ames_mutagenicity": "xgboost"}))
    b = ps.serving_version()
    _install(monkeypatch, _Router({"herg_cardiotoxicity": "kermt", "ames_mutagenicity": "xgboost"}))
    assert a == ps.serving_version() != b  # deterministic, and sensitive to the table
    assert a.startswith(ps.get_settings().model_version + "+kermt.")


def test_kermt_routed_endpoint_answered_by_xgboost_is_degraded(monkeypatch):
    _install(monkeypatch, _Router({"herg_cardiotoxicity": "kermt", "ames_mutagenicity": "xgboost"}))
    healthy = _response({Endpoint.HERG: "mars-kermt-multitask-v1", Endpoint.AMES: "mars-xgboost-ecfp-desc-v1"})
    fallback = _response({Endpoint.HERG: "mars-xgboost-ecfp-desc-v1", Endpoint.AMES: "mars-xgboost-ecfp-desc-v1"})
    assert not ps.is_degraded(healthy)
    assert ps.is_degraded(fallback)


def test_xgboost_routed_endpoints_never_make_a_response_degraded(monkeypatch):
    _install(monkeypatch, _Router({"herg_cardiotoxicity": "kermt", "ames_mutagenicity": "xgboost"}))
    only_ames = _response({Endpoint.AMES: "mars-xgboost-ecfp-desc-v1"})
    assert not ps.is_degraded(only_ames)  # herg was not asked for


def test_nothing_is_degraded_without_a_router(monkeypatch):
    _install(monkeypatch, None)
    assert not ps.is_degraded(_response({Endpoint.HERG: "mars-xgboost-ecfp-desc-v1"}))


@pytest.mark.parametrize("url", ["", "http://kermt:8100"])
def test_settings_default_keeps_kermt_off(url):
    from app.core.config import Settings

    assert Settings(kermt_service_url=url).kermt_service_url == url
    assert Settings().kermt_timeout_seconds > 0


@pytest.fixture(autouse=True)
def _fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
