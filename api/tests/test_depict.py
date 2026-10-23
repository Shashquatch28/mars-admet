"""`POST /depict` (frontend ADR-039): a plain black-line drawing as `image/svg+xml`.

The drawing itself is `ml/serve/depiction.py` (tested in `ml/tests/test_depiction.py`, where rdkit is installed). The root `.venv`
has no rdkit, so here the route is tested two ways: honestly without rdkit (501, never a made-up picture), and with the drawing
functions replaced by fakes that stand in for rdkit, so the route's own work - validation, cache, headers, the rate limit - is
covered. A test that draws for real runs only where rdkit is importable (the built container).
"""

import asyncio
from types import SimpleNamespace

import pytest
from app.core.config import get_settings
from app.services import depiction_service, rate_limit
from app.services.redis_client import get_redis
from fastapi import HTTPException
from tests.conftest import requires_infra

_FAKE_SVG = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 320 220'><path d='M 0 0 L 1 1' stroke='#000000'/></svg>"


def _fake_rdkit(monkeypatch, canonical=lambda s: s.strip().upper()):
    calls = {"draw": 0}

    def draw(c):
        calls["draw"] += 1
        return _FAKE_SVG

    def canon(s):
        if not s.strip():
            raise ValueError("smiles must be a non-empty string")
        if "bad" in s:
            raise ValueError("could not parse the SMILES")
        return canonical(s)

    monkeypatch.setattr(depiction_service, "depiction_available", True)
    monkeypatch.setattr(depiction_service, "DEPICTION_VERSION", "dtest")
    monkeypatch.setattr(depiction_service, "canonical_smiles", canon)
    monkeypatch.setattr(depiction_service, "draw_svg", draw)
    return calls


def _forget(canonical):
    from app.routers.depict import _cache_key

    asyncio.run(get_redis().delete(_cache_key(canonical)))


@requires_infra
def test_without_rdkit_the_route_says_so_and_draws_nothing(client, monkeypatch):
    monkeypatch.setattr(depiction_service, "depiction_available", False)
    r = client.post("/depict", json={"smiles": "CCO"})
    assert r.status_code == 501
    assert "rdkit" in r.json()["detail"]


@requires_infra
def test_a_drawing_is_svg_with_a_locked_down_content_policy(client, monkeypatch):
    _fake_rdkit(monkeypatch)
    _forget("CCO")
    r = client.post("/depict", json={"smiles": "cco"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert r.text == _FAKE_SVG
    assert r.headers["x-content-type-options"] == "nosniff"
    csp = r.headers["content-security-policy"]
    assert "default-src 'none'" in csp and "sandbox" in csp


@requires_infra
def test_the_second_request_for_the_same_molecule_is_a_cache_hit_and_draws_nothing(client, monkeypatch):
    calls = _fake_rdkit(monkeypatch)
    _forget("CCN")
    first = client.post("/depict", json={"smiles": "ccn"})
    second = client.post("/depict", json={"smiles": "CCN"})  # another way of writing it: the fake canonicalises both to CCN
    assert (first.headers["x-depiction-cache"], second.headers["x-depiction-cache"]) == ("miss", "hit")
    assert first.text == second.text == _FAKE_SVG
    assert calls["draw"] == 1


@requires_infra
def test_the_cache_key_carries_the_drawing_version(monkeypatch):
    from app.routers.depict import _cache_key

    monkeypatch.setattr(depiction_service, "DEPICTION_VERSION", "d1")
    first = _cache_key("CCO")
    monkeypatch.setattr(depiction_service, "DEPICTION_VERSION", "d2")
    assert _cache_key("CCO") != first
    assert "CCO" not in first  # the molecule is hashed, never written into a key


@requires_infra
@pytest.mark.parametrize("smiles", ["", "   ", "bad smiles"])
def test_something_that_cannot_be_drawn_is_a_422_with_the_reason(client, monkeypatch, smiles):
    _fake_rdkit(monkeypatch)
    r = client.post("/depict", json={"smiles": smiles})
    assert r.status_code == 422
    assert r.json()["detail"]


@requires_infra
def test_a_missing_smiles_field_is_a_422(client, monkeypatch):
    _fake_rdkit(monkeypatch)
    assert client.post("/depict", json={}).status_code == 422


@requires_infra
def test_the_route_needs_no_account(client, monkeypatch):
    _fake_rdkit(monkeypatch)
    _forget("CCC")
    assert client.post("/depict", json={"smiles": "ccc"}).status_code == 200


@requires_infra
def test_a_real_drawing_is_black_line_art(client):
    pytest.importorskip("rdkit")
    if not depiction_service.depiction_available:
        pytest.skip("the ml stack is not importable here")
    r = client.post("/depict", json={"smiles": "S=C1SC(=Cc2ccc(O)cc2)C(=O)N1"})
    assert r.status_code == 200
    assert r.text.startswith("<svg")
    import re

    assert set(re.findall(r"#[0-9A-Fa-f]{3,8}", r.text)) == {"#000000"}


class _Redis:
    """The two calls the limiter makes, as a counter."""

    def __init__(self):
        self.n = 0

    async def incr(self, key):
        self.n += 1
        return self.n

    async def expire(self, key, seconds):
        return True


def _request():
    return SimpleNamespace(client=SimpleNamespace(host="203.0.113.7"), headers={})


def test_drawings_have_their_own_rate_limit_apart_from_predictions(monkeypatch):
    limit = get_settings().rate_limit_depict_per_minute
    assert limit > get_settings().rate_limit_anon_per_minute  # a page of molecules is drawn at once
    r = _Redis()
    keys = []
    original = r.incr

    async def spy(key):
        keys.append(key)
        return await original(key)

    r.incr = spy
    asyncio.run(rate_limit.enforce_depict_rate_limit(_request(), r))
    assert keys[0].startswith("ratelimit:depict:")  # not the prediction counter


def test_the_depict_limit_answers_429_past_the_number(monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_depict_per_minute", 3, raising=False)
    from app.core import config

    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(rate_limit_depict_per_minute=3, trusted_proxy_hops=0))
    monkeypatch.setattr(rate_limit, "get_settings", lambda: SimpleNamespace(rate_limit_depict_per_minute=3, trusted_proxy_hops=0))
    r = _Redis()
    for _ in range(3):
        asyncio.run(rate_limit.enforce_depict_rate_limit(_request(), r))
    with pytest.raises(HTTPException) as e:
        asyncio.run(rate_limit.enforce_depict_rate_limit(_request(), r))
    assert e.value.status_code == 429
    assert "drawings" in e.value.detail
