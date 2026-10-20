"""`GET /molecule/{id}/explain` (Module 6, ADR-029): status codes, caching, and that a failure is never
cached or replaced by another model's explanation. No Redis or RDKit needed: the explainer and the
cache are replaced with small stand-ins, so this runs in the fast tier."""

from __future__ import annotations

import pytest
from app.main import app
from app.routers import molecule as molecule_router
from app.services import rate_limit
from app.services.redis_client import get_redis
from fastapi.testclient import TestClient
from mars_contracts import ExplainMethod, ExplainOutputSpace, ExplainResponse

MOLECULE_ID = "0123456789abcdef"


class _Redis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value


def _response(endpoint) -> ExplainResponse:
    return ExplainResponse(
        molecule_id=MOLECULE_ID,
        endpoint=endpoint,
        method=ExplainMethod.TREE_SHAP,
        model_id="mars-xgboost-ecfp-desc-v1",
        output_space=ExplainOutputSpace.LOG_ODDS,
        unit=None,
        n_seeds=5,
        base_value=0.0,
        output_value=0.5,
        baseline="test",
        atom_attributions=[0.1, 0.2],
        fragment_attributions=[],
        whole_molecule_attributions=[],
        whole_molecule_rest=0.2,
        structure_total=0.3,
        whole_molecule_total=0.2,
        unmapped_total=0.0,
        completeness_error=0.0,
        n_steps=None,
        model_version="v-test",
    )


@pytest.fixture
def env(monkeypatch):
    fake = _Redis()
    calls: list[tuple] = []

    async def lookup(_r, molecule_id):
        return "CCO" if molecule_id == MOLECULE_ID else None

    def explain(molecule_id, smiles, endpoint):
        calls.append((molecule_id, smiles, endpoint))
        return _response(endpoint)

    monkeypatch.setattr(molecule_router, "lookup_molecule_smiles", lookup)
    monkeypatch.setattr(molecule_router, "explain", explain)
    monkeypatch.setattr(molecule_router, "explain_available", True)
    monkeypatch.setattr(molecule_router, "serving_version", lambda: "v-test")
    app.dependency_overrides[get_redis] = lambda: fake
    app.dependency_overrides[rate_limit.enforce_predict_rate_limit] = lambda: None
    try:
        yield TestClient(app), fake, calls
    finally:
        app.dependency_overrides.pop(get_redis, None)
        app.dependency_overrides.pop(rate_limit.enforce_predict_rate_limit, None)


def test_explains_and_caches_per_version_molecule_and_endpoint(env):
    client, fake, calls = env
    first = client.get(f"/molecule/{MOLECULE_ID}/explain", params={"endpoint": "solubility_logs"})
    assert first.status_code == 200
    body = ExplainResponse.model_validate(first.json())
    assert body.method is ExplainMethod.TREE_SHAP and body.model_id == "mars-xgboost-ecfp-desc-v1"
    second = client.get(f"/molecule/{MOLECULE_ID}/explain", params={"endpoint": "solubility_logs"})
    assert second.status_code == 200 and second.json() == first.json()
    assert len(calls) == 1  # the second answer came from the cache
    assert list(fake.store) == [f"explain_cache:v-test:{MOLECULE_ID}:solubility_logs"]
    other = client.get(f"/molecule/{MOLECULE_ID}/explain", params={"endpoint": "ames_mutagenicity"})
    assert other.status_code == 200 and len(calls) == 2  # another endpoint is another entry


def test_unknown_or_expired_molecule_is_404(env):
    client, _, calls = env
    r = client.get("/molecule/ffffffffffffffff/explain", params={"endpoint": "solubility_logs"})
    assert r.status_code == 404 and not calls


def test_unknown_endpoint_is_422(env):
    client, _, _ = env
    assert client.get(f"/molecule/{MOLECULE_ID}/explain", params={"endpoint": "not_an_endpoint"}).status_code == 422
    assert client.get(f"/molecule/{MOLECULE_ID}/explain").status_code == 422


def test_rule_based_score_has_nothing_to_explain(env):
    client, _, calls = env
    r = client.get(f"/molecule/{MOLECULE_ID}/explain", params={"endpoint": "synthetic_accessibility"})
    assert r.status_code == 409 and not calls
    assert "nothing to explain" in r.json()["detail"]


def test_without_the_ml_stack_it_is_501_not_a_made_up_answer(env, monkeypatch):
    client, _, calls = env
    monkeypatch.setattr(molecule_router, "explain_available", False)
    r = client.get(f"/molecule/{MOLECULE_ID}/explain", params={"endpoint": "solubility_logs"})
    assert r.status_code == 501 and not calls


@pytest.mark.parametrize(
    ("exc_name", "status"),
    [("NothingToExplain", 409), ("ExplainUnavailable", 503), ("ValueError", 422)],
)
def test_failures_map_to_status_codes_and_are_never_cached(env, monkeypatch, exc_name, status):
    client, fake, _ = env
    exc = {
        "NothingToExplain": molecule_router.NothingToExplain,
        "ExplainUnavailable": molecule_router.ExplainUnavailable,
        "ValueError": ValueError,
    }[exc_name]

    def boom(*_a):
        raise exc("because")

    monkeypatch.setattr(molecule_router, "explain", boom)
    r = client.get(f"/molecule/{MOLECULE_ID}/explain", params={"endpoint": "herg_cardiotoxicity"})
    assert r.status_code == status and r.json()["detail"] == "because"
    assert fake.store == {}
