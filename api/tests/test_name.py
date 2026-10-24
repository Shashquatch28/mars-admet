"""`POST /name` (frontend ADR-044): the name of a molecule from PubChem, looked up by InChIKey.

The InChIKey itself is `ml/serve/inchikey.py` (tested in `ml/tests/test_inchikey.py`, where rdkit is installed). The root `.venv`
has no rdkit and must not reach the real PubChem, so here the key function is a fake and PubChem is an `httpx.MockTransport`.
What these tests pin: a name is only what the source returned, with its source and record id; "no record" and "the source
failed" are different answers; a failure is never kept; a slow or broken source answers in words and is stopped asking after
repeated failures; and the SMILES never reaches the source.
"""

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from app.core.config import get_settings
from app.routers.name import _cache_key
from app.services import name_service, rate_limit
from app.services.name_service import Breaker, SourceError, Throttle, pick_synonyms
from app.services.redis_client import get_redis
from fastapi import HTTPException
from tests.conftest import requires_infra

ASPIRIN_SMILES = "CC(=O)Oc1ccccc1C(=O)O"
ASPIRIN_KEY = "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"
ALANINE_KEY = "QNAYBMKLOCPYGJ-REOHCLBHSA-N"

_PROPS = {"PropertyTable": {"Properties": [{"CID": 2244, "IUPACName": "2-acetyloxybenzoic acid", "Title": "Aspirin"}]}}
_SYNS = {
    "InformationList": {
        "Information": [
            {
                "CID": 2244,
                "Synonym": [
                    "aspirin",  # repeats the title without case
                    "ACETYLSALICYLIC ACID",
                    "50-78-2",  # a CAS number
                    "2-Acetoxybenzoic acid",
                    "CHEMBL25",  # a database id
                    "Acylpyrin",
                    "UNII-R16CO5Y76E",
                    "O-Acetylsalicylic acid",
                    "Acetophen",
                    "Ecotrin",
                    "Aceticyl",
                ],
            }
        ]
    }
}
_NOT_FOUND = {"Fault": {"Code": "PUGREST.NotFound", "Message": "No CID found"}}


class Upstream:
    """A fake PubChem that records every request it receives."""

    def __init__(self, props=(200, _PROPS), syns=(200, _SYNS), error=None):
        self.props, self.syns, self.error = props, syns, error
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        status, body = self.syns if "/synonyms/" in request.url.path else self.props
        return httpx.Response(status, json=body)

    @property
    def calls(self) -> int:
        return len(self.requests)


@pytest.fixture(autouse=True)
def _isolated_source(monkeypatch):
    """A fresh breaker and throttle per test, no real network, a fast throttle, and the key function standing in for rdkit."""
    settings = get_settings()
    monkeypatch.setattr(settings, "name_lookup_max_per_second", 1000.0, raising=False)
    monkeypatch.setattr(settings, "name_lookup_enabled", True, raising=False)
    monkeypatch.setattr(name_service, "breaker", Breaker())
    monkeypatch.setattr(name_service, "throttle", Throttle())
    monkeypatch.setattr(name_service, "_inflight", {})
    monkeypatch.setattr(name_service, "name_available", True)

    def key_of(smiles: str) -> str:
        if not smiles.strip():
            raise ValueError("smiles must be a non-empty string")
        if "bad" in smiles:
            raise ValueError("could not parse the SMILES")
        return ALANINE_KEY if "@" in smiles else ASPIRIN_KEY

    monkeypatch.setattr(name_service, "inchikey", key_of)
    monkeypatch.setattr(name_service, "_transport", httpx.MockTransport(lambda r: httpx.Response(500)))


def _upstream(monkeypatch, **kw) -> Upstream:
    up = Upstream(**kw)
    monkeypatch.setattr(name_service, "_transport", httpx.MockTransport(up))
    return up


def _forget(key):
    asyncio.run(get_redis().delete(_cache_key(key)))


@requires_infra
def test_a_name_comes_with_its_source_and_its_record(client, monkeypatch):
    _upstream(monkeypatch)
    _forget(ASPIRIN_KEY)
    r = client.post("/name", json={"smiles": ASPIRIN_SMILES})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "found"
    assert body["preferred_name"] == "Aspirin"
    assert body["iupac_name"] == "2-acetyloxybenzoic acid"
    assert body["source"] == "PubChem"
    assert body["source_record"] == "CID 2244"
    assert body["source_url"] == "https://pubchem.ncbi.nlm.nih.gov/compound/2244"
    assert body["inchikey"] == ASPIRIN_KEY
    assert body["reason"] is None


@requires_infra
def test_synonyms_are_the_sources_own_in_its_order_without_ids_or_repeats(client, monkeypatch):
    _upstream(monkeypatch)
    _forget(ASPIRIN_KEY)
    body = client.post("/name", json={"smiles": ASPIRIN_SMILES}).json()
    assert body["synonyms"] == ["ACETYLSALICYLIC ACID", "2-Acetoxybenzoic acid", "Acylpyrin", "O-Acetylsalicylic acid", "Acetophen"]


@requires_infra
def test_the_smiles_never_reaches_the_source_only_the_key_does(client, monkeypatch):
    up = _upstream(monkeypatch)
    _forget(ASPIRIN_KEY)
    client.post("/name", json={"smiles": ASPIRIN_SMILES})
    assert up.calls == 2
    for req in up.requests:
        sent = f"{req.url} {req.content.decode()} {dict(req.headers)}"
        assert ASPIRIN_SMILES not in sent
        assert req.method == "GET" and not req.content
    assert ASPIRIN_KEY in str(up.requests[0].url)
    assert "/compound/cid/2244/synonyms/" in str(up.requests[1].url)  # the second ask names the record, still not the structure


@requires_infra
def test_a_key_the_source_does_not_know_is_no_name_found_and_is_kept(client, monkeypatch):
    up = _upstream(monkeypatch, props=(404, _NOT_FOUND))
    _forget(ASPIRIN_KEY)
    first = client.post("/name", json={"smiles": ASPIRIN_SMILES})
    second = client.post("/name", json={"smiles": ASPIRIN_SMILES})
    assert first.status_code == 200
    body = first.json()
    assert body["status"] == "not_found"
    assert body["source"] == "PubChem"
    assert body["preferred_name"] is None and body["iupac_name"] is None and body["synonyms"] == []
    assert body["reason"] is None  # not a failure
    assert (first.headers["x-name-cache"], second.headers["x-name-cache"]) == ("miss", "hit")
    assert up.calls == 1  # the second ask did not reach the source


@requires_infra
def test_the_second_ask_for_a_found_name_is_a_cache_hit_and_asks_nobody(client, monkeypatch):
    up = _upstream(monkeypatch)
    _forget(ASPIRIN_KEY)
    first = client.post("/name", json={"smiles": ASPIRIN_SMILES})
    calls_after_first = up.calls
    second = client.post("/name", json={"smiles": "OC(=O)c1ccccc1OC(C)=O"})  # another way of writing it: the same fake key
    assert (first.headers["x-name-cache"], second.headers["x-name-cache"]) == ("miss", "hit")
    assert second.json() == first.json()
    assert up.calls == calls_after_first == 2


@requires_infra
def test_the_cache_key_carries_the_version_and_hides_the_key(monkeypatch):
    first = _cache_key(ASPIRIN_KEY)
    monkeypatch.setattr(name_service, "NAME_VERSION", "n2")
    assert _cache_key(ASPIRIN_KEY) != first
    assert ASPIRIN_KEY not in first  # the molecule's key is hashed, never written into a cache key


@requires_infra
@pytest.mark.parametrize(
    "error, words",
    [
        (httpx.ReadTimeout("slow"), "did not answer within"),
        (httpx.ConnectError("down"), "could not be reached"),
    ],
)
def test_a_source_that_is_down_or_slow_is_unavailable_in_words_and_not_kept(client, monkeypatch, error, words):
    up = _upstream(monkeypatch, error=error)
    _forget(ASPIRIN_KEY)
    r = client.post("/name", json={"smiles": ASPIRIN_SMILES})
    assert r.status_code == 200  # an answer about the source, not a server error
    body = r.json()
    assert body["status"] == "unavailable"
    assert words in body["reason"]
    assert body["preferred_name"] is None and body["synonyms"] == []
    assert body["source"] == "PubChem"
    # not kept: once the source is back the next ask finds the name
    up.error = None
    again = client.post("/name", json={"smiles": ASPIRIN_SMILES})
    assert again.json()["status"] == "found"
    assert again.headers["x-name-cache"] == "miss"


@requires_infra
@pytest.mark.parametrize("status, words", [(503, "busy (HTTP 503)"), (429, "busy (HTTP 429)"), (500, "error (HTTP 500)")])
def test_an_error_status_is_unavailable_and_says_which(client, monkeypatch, status, words):
    _upstream(monkeypatch, props=(status, {}))
    _forget(ASPIRIN_KEY)
    body = client.post("/name", json={"smiles": ASPIRIN_SMILES}).json()
    assert body["status"] == "unavailable"
    assert words in body["reason"]


@requires_infra
def test_an_answer_in_a_form_that_is_not_understood_is_unavailable_never_a_name(client, monkeypatch):
    _upstream(monkeypatch, props=(200, {"PropertyTable": {"Properties": []}}))
    _forget(ASPIRIN_KEY)
    body = client.post("/name", json={"smiles": ASPIRIN_SMILES}).json()
    assert body["status"] == "unavailable"
    assert body["preferred_name"] is None


@requires_infra
def test_when_only_the_synonyms_fail_the_name_stands_and_the_answer_is_not_kept(client, monkeypatch):
    up = _upstream(monkeypatch, syns=(503, {}))
    _forget(ASPIRIN_KEY)
    first = client.post("/name", json={"smiles": ASPIRIN_SMILES}).json()
    assert first["status"] == "found" and first["preferred_name"] == "Aspirin" and first["synonyms"] == []
    up.syns = (200, _SYNS)
    second = client.post("/name", json={"smiles": ASPIRIN_SMILES})
    assert second.headers["x-name-cache"] == "miss"  # the incomplete answer was not kept
    assert second.json()["synonyms"][0] == "ACETYLSALICYLIC ACID"


@requires_infra
def test_one_key_with_several_records_names_the_lowest_cid_and_says_which(client, monkeypatch):
    two = {
        "PropertyTable": {
            "Properties": [
                {"CID": 7311724, "IUPACName": "(2S)-2-azaniumylpropanoate", "Title": "(2S)-2-ammoniopropanoate"},
                {"CID": 5950, "IUPACName": "(2S)-2-aminopropanoic acid", "Title": "L-Alanine"},
            ]
        }
    }
    _upstream(monkeypatch, props=(200, two))
    _forget(ALANINE_KEY)
    body = client.post("/name", json={"smiles": "C[C@H](N)C(=O)O"}).json()
    assert (body["preferred_name"], body["source_record"]) == ("L-Alanine", "CID 5950")


@requires_infra
def test_the_breaker_stops_asking_after_repeated_failures_and_tries_again_later(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "name_breaker_failures", 3, raising=False)
    monkeypatch.setattr(settings, "name_breaker_open_seconds", 30.0, raising=False)
    now = [1000.0]
    monkeypatch.setattr(name_service, "breaker", Breaker(clock=lambda: now[0]))
    up = _upstream(monkeypatch, error=httpx.ConnectError("down"))
    _forget(ASPIRIN_KEY)
    for _ in range(3):
        assert client.post("/name", json={"smiles": ASPIRIN_SMILES}).json()["status"] == "unavailable"
    assert up.calls == 3
    paused = client.post("/name", json={"smiles": ASPIRIN_SMILES}).json()
    assert paused["status"] == "unavailable" and "paused asking" in paused["reason"]
    assert up.calls == 3  # answered at once, nothing sent
    now[0] += 31  # the pause is over: one probe goes out, and a good answer closes the breaker
    up.error = None
    assert client.post("/name", json={"smiles": ASPIRIN_SMILES}).json()["status"] == "found"
    assert name_service.breaker.is_open is False


@requires_infra
def test_a_failed_probe_opens_the_breaker_again(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "name_breaker_failures", 2, raising=False)
    monkeypatch.setattr(settings, "name_breaker_open_seconds", 30.0, raising=False)
    now = [0.0]
    monkeypatch.setattr(name_service, "breaker", Breaker(clock=lambda: now[0]))
    up = _upstream(monkeypatch, error=httpx.ConnectError("down"))
    _forget(ASPIRIN_KEY)
    for _ in range(2):
        client.post("/name", json={"smiles": ASPIRIN_SMILES})
    now[0] += 31
    client.post("/name", json={"smiles": ASPIRIN_SMILES})  # the probe, which fails
    assert up.calls == 3
    client.post("/name", json={"smiles": ASPIRIN_SMILES})
    assert up.calls == 3  # paused again


@requires_infra
def test_a_no_record_answer_does_not_count_against_the_source(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "name_breaker_failures", 2, raising=False)
    _upstream(monkeypatch, props=(404, _NOT_FOUND))
    for key_smiles in (ASPIRIN_SMILES, "C[C@H](N)C(=O)O", ASPIRIN_SMILES, "C[C@H](N)C(=O)O"):
        _forget(ASPIRIN_KEY)
        _forget(ALANINE_KEY)
        assert client.post("/name", json={"smiles": key_smiles}).json()["status"] == "not_found"
    assert name_service.breaker.is_open is False


@requires_infra
def test_switched_off_it_asks_nobody_and_says_so(client, monkeypatch):
    up = _upstream(monkeypatch)
    monkeypatch.setattr(get_settings(), "name_lookup_enabled", False, raising=False)
    _forget(ASPIRIN_KEY)
    body = client.post("/name", json={"smiles": ASPIRIN_SMILES}).json()
    assert body["status"] == "unavailable"
    assert "switched off" in body["reason"]
    assert up.calls == 0


@requires_infra
def test_without_rdkit_the_route_says_so_and_asks_nobody(client, monkeypatch):
    up = _upstream(monkeypatch)
    monkeypatch.setattr(name_service, "name_available", False)
    r = client.post("/name", json={"smiles": ASPIRIN_SMILES})
    assert r.status_code == 501
    assert "rdkit" in r.json()["detail"]
    assert up.calls == 0


@requires_infra
@pytest.mark.parametrize("smiles", ["", "   ", "bad smiles"])
def test_something_that_cannot_be_parsed_is_a_422_and_asks_nobody(client, monkeypatch, smiles):
    up = _upstream(monkeypatch)
    r = client.post("/name", json={"smiles": smiles})
    assert r.status_code == 422
    assert r.json()["detail"]
    assert up.calls == 0


@requires_infra
def test_a_missing_smiles_field_is_a_422(client):
    assert client.post("/name", json={}).status_code == 422


@requires_infra
def test_the_route_needs_no_account(client, monkeypatch):
    _upstream(monkeypatch)
    _forget(ASPIRIN_KEY)
    assert client.post("/name", json={"smiles": ASPIRIN_SMILES}).status_code == 200


def test_asks_for_one_key_at_once_share_one_flight(monkeypatch):
    up = Upstream()

    async def slow(request):
        await asyncio.sleep(0.05)
        return up(request)

    monkeypatch.setattr(name_service, "_transport", httpx.MockTransport(slow))

    async def go():
        return await asyncio.gather(*(name_service.lookup(ASPIRIN_KEY) for _ in range(6)))

    results = asyncio.run(go())
    assert all(x.response.preferred_name == "Aspirin" for x in results)
    assert up.calls == 2  # six asks, one lookup: the properties and the synonyms once each
    assert name_service._inflight == {}


def test_a_slow_source_is_stopped_at_its_timeout(monkeypatch):
    monkeypatch.setattr(get_settings(), "name_lookup_timeout_seconds", 0.05, raising=False)

    async def hang(request):
        await asyncio.sleep(5)
        return httpx.Response(200, json=_PROPS)

    monkeypatch.setattr(name_service, "_transport", httpx.MockTransport(hang))
    result = asyncio.run(asyncio.wait_for(name_service.lookup(ASPIRIN_KEY), timeout=3))
    assert result.response.status.value == "unavailable"
    assert "did not answer within 0.05 s" in result.response.reason
    assert result.cacheable is False


def test_pick_synonyms_leaves_out_ids_and_repeats_and_keeps_the_sources_order():
    listed = ["Aspirin", "aspirin", "50-78-2", "DTXSID5020108", "NSC-27223", "EC 200-064-1", "AKOS000000", "Acetylsalicylic acid",
              "ASA", "  ", "Acetylsalicylic Acid", "Vitamin B12", "ACETYLSALICYLIC ACID", "2-Acetoxybenzoic acid"]
    out = pick_synonyms(listed, ["Aspirin", "2-acetyloxybenzoic acid"], 4)
    assert out == ["Acetylsalicylic acid", "ASA", "Vitamin B12", "2-Acetoxybenzoic acid"]


def test_the_throttle_spaces_requests_and_refuses_rather_than_queues(monkeypatch):
    monkeypatch.setattr(get_settings(), "name_lookup_max_per_second", 2.0, raising=False)  # 0.5 s apart
    now = [10.0]
    t = Throttle(clock=lambda: now[0])
    slept = []

    async def fake_sleep(s):
        slept.append(s)

    monkeypatch.setattr(name_service.asyncio, "sleep", fake_sleep)

    async def go():
        await t.wait(1.0)  # at once
        await t.wait(1.0)  # 0.5 s later
        await t.wait(1.0)  # 1.0 s later
        with pytest.raises(SourceError) as e:
            await t.wait(1.0)  # would wait 1.5 s: past its budget
        assert "as often as it is allowed" in e.value.reason
        assert e.value.counts is False

    asyncio.run(go())
    assert slept == [0.5, 1.0]


class _Redis:
    """The two calls the limiter makes, as a counter."""

    def __init__(self):
        self.n = 0
        self.keys = []

    async def incr(self, key):
        self.keys.append(key)
        self.n += 1
        return self.n

    async def expire(self, key, seconds):
        return True


def _request():
    return SimpleNamespace(client=SimpleNamespace(host="203.0.113.7"), headers={})


def test_name_lookups_have_their_own_rate_limit_apart_from_predictions():
    assert get_settings().rate_limit_name_per_minute > get_settings().rate_limit_anon_per_minute  # a page of molecules is named at once
    r = _Redis()
    asyncio.run(rate_limit.enforce_name_rate_limit(_request(), r))
    assert r.keys[0].startswith("ratelimit:name:")  # not the prediction counter


def test_the_name_limit_answers_429_past_the_number(monkeypatch):
    stub = SimpleNamespace(rate_limit_name_per_minute=3, trusted_proxy_hops=0)
    monkeypatch.setattr(rate_limit, "get_settings", lambda: stub)
    r = _Redis()
    for _ in range(3):
        asyncio.run(rate_limit.enforce_name_rate_limit(_request(), r))
    with pytest.raises(HTTPException) as e:
        asyncio.run(rate_limit.enforce_name_rate_limit(_request(), r))
    assert e.value.status_code == 429
    assert "name lookups" in e.value.detail
