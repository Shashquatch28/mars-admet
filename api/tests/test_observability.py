"""Ship checklist C9: Sentry reports crashes but never what users sent."""

from __future__ import annotations

import json

import pytest
from app.core.config import Settings
from app.observability import init_sentry, scrub_event

sentry_sdk = pytest.importorskip("sentry_sdk")

SMILES = "CC(=O)Oc1ccccc1C(=O)O"
COOKIE = "mars_session=super-secret-session-token"


def _settings(monkeypatch, dsn="https://publickey@o0.ingest.sentry.io/1") -> Settings:
    monkeypatch.setenv("SENTRY_DSN", dsn)
    monkeypatch.setenv("SENTRY_ENVIRONMENT", "test")
    return Settings()


def test_sentry_stays_off_without_a_dsn(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "")
    called = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: called.append(kw))
    assert init_sentry(Settings()) is False
    assert called == []


def test_init_turns_every_data_collection_switch_off(monkeypatch):
    seen = {}
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: seen.update(kw))
    assert init_sentry(_settings(monkeypatch)) is True
    assert seen["send_default_pii"] is False
    assert seen["max_request_body_size"] == "never"
    assert seen["include_local_variables"] is False
    assert seen["traces_sample_rate"] == 0.0
    assert seen["before_send"] is scrub_event
    assert seen["environment"] == "test"


def test_scrub_removes_user_data_and_keeps_the_stack():
    event = {
        "request": {
            "url": "https://mars.example/api/predict",
            "method": "POST",
            "data": {"smiles": SMILES},
            "cookies": {"mars_session": "x"},
            "query_string": "smiles=" + SMILES,
            "headers": {"Cookie": COOKIE, "Authorization": "Bearer t", "X-MARS-Worker-Secret": "s", "Accept": "*/*"},
        },
        "user": {"email": "a@b.c"},
        "extra": {"smiles": SMILES},
        "breadcrumbs": {"values": [{"message": "predict", "data": {"smiles": SMILES}}]},
        "exception": {"values": [{"type": "KeyError", "stacktrace": {"frames": [{"function": "f", "vars": {"smiles": SMILES}}]}}]},
    }
    out = json.dumps(scrub_event(event))
    assert SMILES not in out and COOKIE not in out and "a@b.c" not in out and "Bearer" not in out
    assert "KeyError" in out and '"function": "f"' in out and "/api/predict" in out and "Accept" in out


def test_a_real_crash_is_reported_without_the_request_body_or_cookie(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sentry_sdk.transport import Transport

    sent: list[dict] = []

    class Capture(Transport):
        def capture_envelope(self, envelope):
            for item in envelope.items:
                if item.headers.get("type") == "event":
                    sent.append(item.payload.json)

    assert init_sentry(_settings(monkeypatch), transport=Capture())
    try:
        app = FastAPI()

        @app.post("/boom")
        def boom(payload: dict):
            smiles = payload["smiles"]  # a local that would hold the molecule
            raise RuntimeError(f"model failed on {len(smiles)} characters")

        client = TestClient(app, raise_server_exceptions=False)
        r = client.post("/boom", json={"smiles": SMILES}, headers={"Cookie": COOKIE})
        assert r.status_code == 500
        sentry_sdk.flush()
    finally:
        sentry_sdk.get_client().close()

    assert sent, "the crash was not reported"
    wire = json.dumps(sent)
    assert "model failed on 21 characters" in wire  # the error itself is reported
    assert SMILES not in wire and "super-secret-session-token" not in wire
