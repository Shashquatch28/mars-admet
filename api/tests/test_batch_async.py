"""Module 8 async batch tier — forces the interactive threshold down to 1 so
a 3-row CSV takes the enqueue path, then polls /batch/progress and
/batch/results. Real Postgres + Redis required."""

import io
import time

from app.core.config import get_settings
from tests.conftest import requires_infra

_CSV = b"smiles\nCCO\nCCC\nCCN\n"


@requires_infra
def test_batch_predict_async_tier_completes(registered_user, monkeypatch):
    monkeypatch.setenv("BATCH_INTERACTIVE_THRESHOLD", "1")
    get_settings.cache_clear()
    try:
        client = registered_user["client"]
        r = client.post("/batch/predict", files={"file": ("molecules.csv", io.BytesIO(_CSV), "text/csv")})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["job_id"] is not None
        assert body["status"] == "queued"
        assert body["results"] is None
        job_id = body["job_id"]

        deadline = time.monotonic() + 10
        final = None
        while time.monotonic() < deadline:
            r = client.get(f"/batch/results/{job_id}")
            if r.status_code == 200:
                final = r.json()
                break
            assert r.status_code == 409  # still running
            time.sleep(0.2)

        assert final is not None, "async batch job did not complete within 10s"
        assert final["status"] == "done"
        assert final["total"] == 3
        assert len(final["results"]) == 3
    finally:
        get_settings.cache_clear()


@requires_infra
def test_batch_progress_sse_reports_completion(registered_user, monkeypatch):
    monkeypatch.setenv("BATCH_INTERACTIVE_THRESHOLD", "1")
    get_settings.cache_clear()
    try:
        client = registered_user["client"]
        r = client.post("/batch/predict", files={"file": ("molecules.csv", io.BytesIO(_CSV), "text/csv")})
        job_id = r.json()["job_id"]

        with client.stream("GET", f"/batch/progress/{job_id}") as stream:
            statuses = []
            for line in stream.iter_lines():
                if not line.startswith("data: "):
                    continue
                import json

                payload = json.loads(line[len("data: ") :])
                statuses.append(payload["status"])
                if payload["status"] in ("done", "failed"):
                    break
        assert statuses[-1] == "done"
    finally:
        get_settings.cache_clear()


@requires_infra
def test_batch_results_404_for_other_users_job(client, monkeypatch):
    import uuid

    monkeypatch.setenv("BATCH_INTERACTIVE_THRESHOLD", "1")
    get_settings.cache_clear()
    try:
        email_a = f"user-a-{uuid.uuid4().hex[:8]}@example.com"
        password = "correct-horse-battery"
        client.post("/auth/register", json={"email": email_a, "password": password, "turnstile_token": "t"})
        client.post("/auth/login", json={"email": email_a, "password": password})
        r = client.post("/batch/predict", files={"file": ("molecules.csv", io.BytesIO(_CSV), "text/csv")})
        job_id = r.json()["job_id"]
        client.request("DELETE", "/account", json={"password": password})

        email_b = f"user-b-{uuid.uuid4().hex[:8]}@example.com"
        client.post("/auth/register", json={"email": email_b, "password": password, "turnstile_token": "t"})
        client.post("/auth/login", json={"email": email_b, "password": password})
        r = client.get(f"/batch/results/{job_id}")
        assert r.status_code == 404
        client.request("DELETE", "/account", json={"password": password})
    finally:
        get_settings.cache_clear()
