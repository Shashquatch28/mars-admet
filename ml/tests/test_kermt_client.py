"""KermtClient: parses the service reply; every failure is KermtUnavailable, never a partial answer."""

from __future__ import annotations

import httpx
import pytest
from serve.kermt_client import KermtClient, KermtUnavailable


def _reply(arms: dict) -> httpx.Response:
    return httpx.Response(200, json={"arms": arms})


def _arm(values: dict, seeds=(0, 1), task="classification", model_id="mars-kermt-multitask-v1") -> dict:
    return {"model_id": model_id, "task_type": task, "seeds": list(seeds), "values": values}


def _client(handler, **kw) -> KermtClient:
    return KermtClient("http://kermt.test", transport=httpx.MockTransport(handler), **kw)


def test_parses_one_molecule_per_target_and_seed():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read()
        return _reply({"toxicity__cls": _arm({"herg_cardiotoxicity": [[0.8, 0.6]], "ames_mutagenicity": [[0.1, None]]})})

    out = _client(handler).predict("CCO", ["toxicity__cls"])["toxicity__cls"]
    assert out.model_id == "mars-kermt-multitask-v1"
    assert out.values["herg_cardiotoxicity"] == [0.8, 0.6]
    assert out.values["ames_mutagenicity"] == [0.1, None]
    assert b'"smiles":["CCO"]' in seen["body"].replace(b" ", b"")


def test_token_header_is_sent_when_configured():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["token"] = request.headers.get("x-kermt-token")
        return _reply({"a": _arm({"t": [[1.0]]})})

    _client(handler, token="s3cret").predict("C", ["a"])
    assert seen["token"] == "s3cret"


def test_no_arms_means_no_call():
    def handler(request):  # pragma: no cover - must not be called
        raise AssertionError("no request expected")

    assert _client(handler).predict("C", []) == {}


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503, json={"detail": "models still loading"}),
        httpx.Response(200, json={"nope": 1}),
        httpx.Response(200, json={"arms": {}}),  # asked arm missing from the reply
        httpx.Response(200, json={"arms": {"a": {"model_id": "m", "task_type": "classification", "seeds": [0], "values": {"t": []}}}}),
    ],
)
def test_bad_replies_raise_unavailable(response):
    with pytest.raises(KermtUnavailable):
        _client(lambda request: response).predict("C", ["a"])


def test_transport_error_raises_unavailable():
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(KermtUnavailable):
        _client(handler).predict("C", ["a"])


def test_circuit_opens_after_a_failure_and_closes_after_the_cooldown(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(500, text="boom") if calls["n"] == 1 else _reply({"a": _arm({"t": [[0.5]]})})

    clock = {"t": 1000.0}
    monkeypatch.setattr("serve.kermt_client.time.monotonic", lambda: clock["t"])
    client = _client(handler, cooldown_seconds=10.0)
    with pytest.raises(KermtUnavailable):
        client.predict("C", ["a"])
    with pytest.raises(KermtUnavailable, match="circuit open"):
        client.predict("C", ["a"])
    assert calls["n"] == 1  # the second call never reached the service
    clock["t"] += 11
    assert client.predict("C", ["a"])["a"].values["t"] == [0.5]
