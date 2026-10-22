"""ADR-025: one origin. Every API route lives under /api; the built frontend is served at /."""

from __future__ import annotations

import pytest
from app import main as main_module
from app.main import app
from app.spa import mount_spa
from fastapi import FastAPI
from fastapi.testclient import TestClient

api = TestClient(app, base_url="http://testserver")  # no prefix: these tests spell the paths out


def test_health_lives_under_api():
    assert api.get("/api/health").json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/health", "/predict", "/batch/predict", "/auth/me", "/molecules", "/generations"])
def test_unprefixed_api_routes_no_longer_exist(path):
    # Without the frontend bundle mounted (development, CI) these are plain 404s.
    assert api.get(path).status_code == 404


def test_every_registered_route_is_under_api():
    paths = {getattr(r, "path", "") for r in app.routes}
    outside = {p for p in paths if p and not p.startswith("/api")}
    # the only non-/api paths are the SPA catch-all (when mounted); none in a dev/test app
    assert not outside, outside


def test_docs_move_under_api():
    assert api.get("/api/openapi.json").status_code == 200
    assert api.get("/api/docs").status_code == 200


@pytest.fixture
def spa_client(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>MARS</title>")
    (tmp_path / "assets" / "app-abc123.js").write_text("console.log(1)")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    (tmp_path.parent / "secret.txt").write_text("outside the bundle")

    shell = FastAPI()

    @shell.get("/api/health")
    def health():
        return {"status": "ok"}

    mount_spa(shell, tmp_path)
    return TestClient(shell)


def test_client_routes_get_index_html(spa_client):
    for route in ["/", "/predict", "/batch", "/compare", "/library", "/predict/deep/link"]:
        r = spa_client.get(route)
        assert r.status_code == 200 and "<title>MARS</title>" in r.text, route
        assert r.headers["cache-control"] == "no-cache"


def test_real_files_are_served_and_hashed_assets_cached_forever(spa_client):
    asset = spa_client.get("/assets/app-abc123.js")
    assert asset.status_code == 200 and "immutable" in asset.headers["cache-control"]
    assert spa_client.get("/favicon.svg").text == "<svg/>"


def test_missing_file_is_404_not_index_html(spa_client):
    assert spa_client.get("/assets/old-hash.js").status_code == 404


def test_api_routes_win_and_unknown_api_paths_are_404(spa_client):
    assert spa_client.get("/api/health").json() == {"status": "ok"}
    r = spa_client.get("/api/nothing-here")
    assert r.status_code == 404 and r.headers["content-type"].startswith("application/json")


def test_paths_cannot_escape_the_bundle(spa_client):
    r = spa_client.get("/..%2fsecret.txt")
    assert "outside the bundle" not in r.text
    r = spa_client.get("/%2e%2e/secret.txt")
    assert "outside the bundle" not in r.text


def test_insecure_cookie_warning_when_serving_the_bundle(monkeypatch, caplog):
    monkeypatch.setenv("STATIC_DIR", "/app/static")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    main_module.get_settings.cache_clear()
    try:
        with caplog.at_level("WARNING", logger="mars.startup"):
            main_module._warn_on_insecure_config()
    finally:
        main_module.get_settings.cache_clear()
    assert any("SESSION_COOKIE_SECURE" in m for m in caplog.messages)
