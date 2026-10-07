"""CORS policy: an explicit origin list with credentials (the SPA's session cookie is
HttpOnly, so its requests are credentialed), never `*` together with credentials —
a browser rejects that combination outright."""

from types import SimpleNamespace

import pytest
from app import main
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

DEV_ORIGIN = "http://localhost:5173"


def _preflight(origin: str):
    return client.options(
        "/predict",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )


def test_allowed_origin_gets_a_credentialed_response():
    r = _preflight(DEV_ORIGIN)
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == DEV_ORIGIN  # echoed, not "*"
    assert r.headers["access-control-allow-credentials"] == "true"


def test_actual_request_from_allowed_origin_is_credentialed_too():
    r = client.post("/predict", json={"smiles": "CCO"}, headers={"Origin": DEV_ORIGIN})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == DEV_ORIGIN
    assert r.headers["access-control-allow-credentials"] == "true"


def test_unlisted_origin_is_not_allowed():
    r = _preflight("https://evil.example")
    assert r.status_code == 400
    assert "access-control-allow-origin" not in r.headers


@pytest.mark.parametrize(
    ("configured", "origins", "credentials"),
    [
        ("http://localhost:5173,http://127.0.0.1:5173", ["http://localhost:5173", "http://127.0.0.1:5173"], True),
        (" https://app.mars.example/ , ", ["https://app.mars.example"], True),  # trims, drops trailing slash
        ("*", ["*"], False),  # wildcard is tolerated for anonymous use, never with credentials
        ("https://app.mars.example,*", ["https://app.mars.example", "*"], False),
    ],
)
def test_cors_policy_parsing(monkeypatch, configured, origins, credentials):
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(cors_allow_origins=configured))
    assert main.cors_policy() == (origins, credentials)
