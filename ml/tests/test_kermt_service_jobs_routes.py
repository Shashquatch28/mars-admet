"""The KERMT service's explanation-job routes (ADR-040), with a fake engine: no torch, no checkpoints."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "serve" / "kermt_service"))
try:
    import app as service
except ImportError as exc:  # engine.py needs the service's own dependencies
    pytest.skip(f"service not importable here: {exc}", allow_module_level=True)
from fastapi.testclient import TestClient
from jobs import JobManager


class FakeEngine:
    def __init__(self):
        self.calls = []

    def explainable_models(self, arm, endpoint):
        if arm != "toxicity__cls" or endpoint != "herg_cardiotoxicity":
            raise KeyError(f"{endpoint} is not a target of {arm}")
        return [object(), object(), object()]

    def explain_config(self):
        return {"digest": "abc123"}

    def explain(self, smiles, arm, endpoint, progress=None, cancelled=None, **kw):
        self.calls.append(smiles)
        for i in range(3):
            progress(i, 3, f"seed {i + 1} of 3, 64 steps")
        progress(3, 3, None)
        return {"atom_scores": [0.1], "converged": True}


@pytest.fixture
def client(monkeypatch):
    engine = FakeEngine()
    jobs = JobManager(lambda p, progress, cancelled: engine.explain(p["smiles"], p["arm"], p["endpoint"], progress=progress, cancelled=cancelled))
    monkeypatch.setitem(service._state, "engine", engine)
    monkeypatch.setitem(service._state, "jobs", jobs)
    monkeypatch.setitem(service._state, "ready", True)
    monkeypatch.delenv("KERMT_TOKEN", raising=False)
    yield TestClient(service.app), engine
    jobs.stop()


BODY = {"smiles": "CCO", "arm": "toxicity__cls", "endpoint": "herg_cardiotoxicity"}


def test_a_job_is_started_polled_to_done_and_a_repeat_submit_joins_it(client):
    c, engine = client
    first = c.post("/explain/jobs", json=BODY).json()
    assert first["seeds_total"] == 3 and first["state"] in ("queued", "running", "done")
    assert c.post("/explain/jobs", json=BODY).json()["job_id"] == first["job_id"]
    for _ in range(200):
        snap = c.get(f"/explain/jobs/{first['job_id']}").json()
        if snap["state"] == "done":
            break
        time.sleep(0.01)
    assert snap["state"] == "done" and snap["result"]["converged"] is True
    assert engine.calls == ["CCO"]  # joined, not run twice


def test_job_ids_differ_by_molecule_and_unknown_ones_are_404(client):
    c, _ = client
    a = c.post("/explain/jobs", json=BODY).json()["job_id"]
    b = c.post("/explain/jobs", json={**BODY, "smiles": "CCN"}).json()["job_id"]
    assert a != b
    assert c.get("/explain/jobs/nope").status_code == 404
    assert c.delete("/explain/jobs/nope").status_code == 404


def test_an_arm_or_endpoint_that_cannot_explain_is_422_and_config_carries_the_digest(client):
    c, _ = client
    assert c.post("/explain/jobs", json={**BODY, "endpoint": "bbb_penetration"}).status_code == 422
    assert c.get("/explain/config").json()["digest"] == "abc123"


def test_a_full_queue_is_429(client, monkeypatch):
    c, _ = client
    import threading

    gate = threading.Event()
    full = JobManager(lambda p, progress, cancelled: gate.wait(5) or {}, max_queue=1)
    monkeypatch.setitem(service._state, "jobs", full)
    try:
        c.post("/explain/jobs", json=BODY)  # runs
        time.sleep(0.05)
        assert c.post("/explain/jobs", json={**BODY, "smiles": "CCN"}).status_code == 200  # waits
        assert c.post("/explain/jobs", json={**BODY, "smiles": "CCC"}).status_code == 429
    finally:
        gate.set()
        full.stop()
