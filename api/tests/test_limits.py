"""GET /limits (frontend ADR-034 item 8): the policy numbers come from the settings the service enforces,
and the batch blob store keeps results for the configured period, not a constant."""

import asyncio

from app.core.config import get_settings
from app.main import app
from app.services.blob_store import RedisBlobStore, retention_seconds
from fastapi.testclient import TestClient

client = TestClient(app, base_url="http://testserver/api")


def test_limits_reports_the_deployed_settings_without_a_session(monkeypatch):
    monkeypatch.setenv("BATCH_SIZE_CAP", "7000")
    monkeypatch.setenv("BATCH_INTERACTIVE_THRESHOLD", "20")
    monkeypatch.setenv("BATCH_UPLOAD_RETENTION_HOURS", "12")
    monkeypatch.setenv("RATE_LIMIT_ANON_PER_MINUTE", "30")
    get_settings.cache_clear()
    try:
        r = client.get("/limits")  # no cookie: anonymous like /predict
        assert r.status_code == 200
        assert r.json() == {
            "batch_size_cap": 7000,
            "batch_interactive_threshold": 20,
            "batch_result_retention_hours": 12,
            "anon_predict_rate_per_minute": 30,
        }
    finally:
        get_settings.cache_clear()


def test_limits_defaults_match_the_settings_defaults():
    get_settings.cache_clear()
    s = get_settings()
    assert client.get("/limits").json() == {
        "batch_size_cap": s.batch_size_cap,
        "batch_interactive_threshold": s.batch_interactive_threshold,
        "batch_result_retention_hours": s.batch_upload_retention_hours,
        "anon_predict_rate_per_minute": s.rate_limit_anon_per_minute,
    }


def test_blob_retention_follows_the_setting(monkeypatch):
    monkeypatch.setenv("BATCH_UPLOAD_RETENTION_HOURS", "6")
    get_settings.cache_clear()
    try:
        assert retention_seconds() == 6 * 3600
    finally:
        get_settings.cache_clear()


def test_redis_blob_put_uses_the_configured_retention_unless_told_otherwise(monkeypatch):
    monkeypatch.setenv("BATCH_UPLOAD_RETENTION_HOURS", "6")
    get_settings.cache_clear()

    class FakeRedis:
        def __init__(self):
            self.calls = []

        async def set(self, key, data, ex=None):
            self.calls.append((key, ex))

    try:
        fake = FakeRedis()
        store = RedisBlobStore(fake)  # type: ignore[arg-type]
        asyncio.run(store.put("a", "x"))
        asyncio.run(store.put("b", "x", ttl_seconds=60))
        assert fake.calls == [("blob:a", 6 * 3600), ("blob:b", 60)]
    finally:
        get_settings.cache_clear()
