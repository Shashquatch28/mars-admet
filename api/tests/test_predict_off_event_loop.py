"""Prediction work must not run on the event loop (2026-10-18).

`POST /predict` used to call the synchronous, CPU-bound `predict()` (RDKit + 70 XGBoost
predicts) directly inside an `async def`, so the whole API stopped answering for the
duration of every prediction. A deliberately slow `predict()` stands in for the real one:
if it ran on the loop, `/health` could not be served until it returned.
"""

from __future__ import annotations

import asyncio
import time

import httpx
from app.main import app
from app.routers import predict as predict_router
from app.services import rate_limit
from app.services.redis_client import get_redis
from app.services.stub_predictor import predict_stub
from mars_contracts import ALL_ENDPOINTS

SLOW_SECONDS = 0.8


def _slow_predict(smiles, endpoints=None):
    time.sleep(SLOW_SECONDS)  # blocking, like RDKit/XGBoost
    return predict_stub(smiles, endpoints or ALL_ENDPOINTS)


async def _none(*_a, **_k):
    return None


def test_health_answers_while_a_prediction_is_running(monkeypatch):
    monkeypatch.setattr(predict_router, "predict_service", _slow_predict)
    monkeypatch.setattr(predict_router, "get_cached_prediction", _none)
    monkeypatch.setattr(predict_router, "set_cached_prediction", _none)
    monkeypatch.setattr(predict_router, "register_molecule", _none)
    app.dependency_overrides[get_redis] = lambda: object()
    app.dependency_overrides[rate_limit.enforce_predict_rate_limit] = lambda: None

    async def scenario() -> tuple[float, float, bool, int]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            started = time.perf_counter()
            slow = asyncio.create_task(client.post("/predict", json={"smiles": "CCO"}))
            await asyncio.sleep(0.1)  # let the prediction start
            r = await client.get("/health")
            health_done = time.perf_counter() - started
            still_running = not slow.done()
            assert r.status_code == 200
            resp = await slow
            return health_done, time.perf_counter() - started, still_running, resp.status_code

    try:
        health_done, predict_seconds, still_running, status = asyncio.run(scenario())
    finally:
        app.dependency_overrides.pop(get_redis, None)
        app.dependency_overrides.pop(rate_limit.enforce_predict_rate_limit, None)

    assert status == 200
    assert predict_seconds >= SLOW_SECONDS  # the slow path really ran
    # /health was answered while the prediction was still in flight, not queued behind it
    assert still_running
    assert health_done < SLOW_SECONDS / 2
