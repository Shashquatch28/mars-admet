"""Ship checklist C8: the batch worker path (slices, blob store, Cloud Tasks queue, worker endpoint).

Everything here runs without Postgres, Redis, MinIO or GCP: the stores are in-memory fakes and the
Cloud Tasks client is a recorder. What this cannot show is a real Cloud Tasks project delivering to a
deployed service; that stays open until the deploy (C6-C8).
"""

from __future__ import annotations

import asyncio
import json
import time

import pytest
from app.core.config import Settings, get_settings
from app.main import app
from app.routers import worker
from app.services import batch_runner
from app.services.blob_store import S3BlobStore, input_key, results_key, slice_key
from app.services.redis_client import get_redis
from app.services.task_queue import CloudTasksQueue, get_job_progress
from fastapi.testclient import TestClient
from mars_contracts import BatchPredictResponse

JOB = "5f0c1f3e-3b52-4a0e-9a53-0d5f2a6f0a11"


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value, ex=None):
        self.data[key] = value


class FakeBlobs:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def put(self, key, data, *, ttl_seconds=86_400):
        self.data[key] = data

    async def get(self, key):
        return self.data.get(key)

    async def delete(self, *keys):
        for k in keys:
            self.data.pop(k, None)


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("BATCH_SLICE_ROWS", "3")
    get_settings.cache_clear()
    marked: list[tuple[str, str]] = []

    async def fake_mark(job_id, status):
        marked.append((job_id, status))

    monkeypatch.setattr(batch_runner, "_mark_job", fake_mark)
    yield FakeRedis(), FakeBlobs(), marked
    get_settings.cache_clear()


def _run(coro):
    return asyncio.run(coro)


def test_a_job_runs_as_a_chain_of_slices_and_finishes_in_order(env):
    r, blobs, marked = env
    smiles = ["CCO", "CCC", "CCN", "CCCC", "CCCl", "CCBr", "CCF"]

    async def go():
        await batch_runner.store_job_input(blobs, JOB, smiles, None)
        order = []
        index = 0
        while index is not None:
            order.append(index)
            index = await batch_runner.run_slice(r, blobs, JOB, index)
        return order

    assert _run(go()) == [0, 1, 2]  # 7 rows at 3 per slice
    final = BatchPredictResponse.model_validate_json(blobs.data[results_key(JOB)])
    assert final.status == "done" and final.total == 7
    assert [row.smiles_input for row in final.results] == smiles
    assert [row.row_index for row in final.results] == list(range(7))
    assert _run(get_job_progress(r, JOB)) == {"job_id": JOB, "status": "done", "total": 7, "completed": 7}
    assert marked == [(JOB, "done")]
    # nothing but the result is kept: the molecules and the slices are cleaned up
    assert set(blobs.data) == {results_key(JOB)}


def test_a_bad_molecule_stays_a_failed_row(env):
    r, blobs, _ = env

    async def go():
        await batch_runner.store_job_input(blobs, JOB, ["CCO", "", "CCC"], None)
        await batch_runner.run_slice(r, blobs, JOB, 0)

    _run(go())
    rows = BatchPredictResponse.model_validate_json(blobs.data[results_key(JOB)]).results
    assert [row.ok for row in rows] == [True, False, True]
    assert rows[1].error == "empty SMILES"


def test_a_retried_slice_is_not_predicted_again(env, monkeypatch):
    r, blobs, _ = env
    calls = []
    real = batch_runner.predict_row

    def counting(i, s, e):
        calls.append(i)
        return real(i, s, e)

    monkeypatch.setattr(batch_runner, "predict_row", counting)

    async def go():
        await batch_runner.store_job_input(blobs, JOB, ["CCO", "CCC", "CCN", "CCCC"], None)
        first = await batch_runner.run_slice(r, blobs, JOB, 0)
        again = await batch_runner.run_slice(r, blobs, JOB, 0)  # a redelivered task
        return first, again

    assert _run(go()) == (1, 1)
    assert calls == [0, 1, 2]  # slice 0 was predicted once


def test_a_duplicate_delivery_after_the_job_finished_is_a_no_op(env, monkeypatch):
    r, blobs, marked = env

    async def go():
        await batch_runner.store_job_input(blobs, JOB, ["CCO"], None)
        await batch_runner.run_slice(r, blobs, JOB, 0)
        monkeypatch.setattr(batch_runner, "predict_row", lambda *a: pytest.fail("predicted after done"))
        return await batch_runner.run_slice(r, blobs, JOB, 0)

    assert _run(go()) is None
    assert marked == [(JOB, "done")]


def test_missing_input_fails_the_job(env):
    r, blobs, marked = env
    assert _run(batch_runner.run_slice(r, blobs, JOB, 0)) is None
    assert marked == [(JOB, "failed")]
    assert _run(get_job_progress(r, JOB))["status"] == "failed"


def test_run_job_writes_back_a_crash_as_failed(env, monkeypatch):
    r, blobs, marked = env

    async def boom(*_a):
        raise RuntimeError("model exploded")

    monkeypatch.setattr(batch_runner, "run_slice", boom)
    _run(batch_runner.run_job(r, blobs, JOB))
    assert marked == [(JOB, "failed")]


# --- Cloud Tasks queue -------------------------------------------------------------------------


class RecordingTasksClient:
    def __init__(self, fail_with: Exception | None = None) -> None:
        self.requests: list[dict] = []
        self._fail = fail_with

    def queue_path(self, project, location, queue):
        return f"projects/{project}/locations/{location}/queues/{queue}"

    async def create_task(self, request):
        if self._fail:
            raise self._fail
        self.requests.append(request)


def _cloud_settings(monkeypatch, **overrides) -> Settings:
    base = {
        "GCP_PROJECT_ID": "mars-proj",
        "GCP_REGION": "us-central1",
        "CLOUD_TASKS_QUEUE": "mars-batch",
        "WORKER_BASE_URL": "https://mars.example.run.app/",
        "BATCH_WORKER_SECRET": "s3cret",
    }
    base.update(overrides)
    for k, v in base.items():
        monkeypatch.setenv(k, v)
    return Settings()


def test_cloud_tasks_task_targets_the_worker_endpoint(monkeypatch):
    client = RecordingTasksClient()
    queue = CloudTasksQueue(_cloud_settings(monkeypatch), client)
    _run(queue.enqueue(JOB, 4))
    (request,) = client.requests
    task = request["task"]
    assert request["parent"] == "projects/mars-proj/locations/us-central1/queues/mars-batch"
    assert task["name"] == f"projects/mars-proj/locations/us-central1/queues/mars-batch/tasks/{JOB}-s4"
    http = task["http_request"]
    assert http["url"] == "https://mars.example.run.app/api/internal/batch/run"
    assert http["http_method"] == "POST"
    assert http["headers"]["X-MARS-Worker-Secret"] == "s3cret"
    assert json.loads(http["body"]) == {"job_id": JOB, "index": 4}
    assert len(http["body"]) < 1_000  # the molecules never travel in the task (Cloud Tasks caps it at 100 KB)
    assert task["dispatch_deadline"] == {"seconds": 900}


@pytest.mark.parametrize("missing", ["GCP_PROJECT_ID", "WORKER_BASE_URL", "BATCH_WORKER_SECRET"])
def test_cloud_tasks_refuses_to_run_half_configured(monkeypatch, missing):
    settings = _cloud_settings(monkeypatch, **{missing: ""})
    with pytest.raises(RuntimeError, match=missing):
        _run(CloudTasksQueue(settings, RecordingTasksClient()).enqueue(JOB, 0))


def test_enqueueing_the_same_slice_twice_is_not_an_error(monkeypatch):
    class AlreadyExists(Exception):
        pass

    queue = CloudTasksQueue(_cloud_settings(monkeypatch), RecordingTasksClient(AlreadyExists()))
    _run(queue.enqueue(JOB, 1))  # does not raise


def test_other_cloud_tasks_errors_propagate(monkeypatch):
    queue = CloudTasksQueue(_cloud_settings(monkeypatch), RecordingTasksClient(PermissionError("denied")))
    with pytest.raises(PermissionError):
        _run(queue.enqueue(JOB, 1))


# --- worker endpoint ---------------------------------------------------------------------------


@pytest.fixture
def worker_client(monkeypatch):
    monkeypatch.setenv("BATCH_QUEUE_BACKEND", "cloud_tasks")
    monkeypatch.setenv("BATCH_WORKER_SECRET", "s3cret")
    monkeypatch.setenv("BATCH_TASK_MAX_ATTEMPTS", "3")
    get_settings.cache_clear()
    app.dependency_overrides[get_redis] = lambda: FakeRedis()
    monkeypatch.setattr(worker, "get_blob_store", lambda r: FakeBlobs())
    yield TestClient(app, base_url="http://testserver/api")
    app.dependency_overrides.pop(get_redis, None)
    get_settings.cache_clear()


def _post(client, secret="s3cret", retry=None, index=0, job=JOB):
    headers = {}
    if secret is not None:
        headers["X-MARS-Worker-Secret"] = secret
    if retry is not None:
        headers["X-CloudTasks-TaskRetryCount"] = str(retry)
    return client.post("/internal/batch/run", json={"job_id": job, "index": index}, headers=headers)


def test_worker_does_not_exist_on_the_local_backend(monkeypatch):
    monkeypatch.setenv("BATCH_QUEUE_BACKEND", "local")
    get_settings.cache_clear()
    try:
        assert _post(TestClient(app, base_url="http://testserver/api")).status_code == 404
    finally:
        get_settings.cache_clear()


def test_worker_refuses_everything_while_its_secret_is_unset(worker_client, monkeypatch):
    monkeypatch.setenv("BATCH_WORKER_SECRET", "")
    get_settings.cache_clear()
    assert _post(worker_client, secret="").status_code == 503


@pytest.mark.parametrize("secret", [None, "", "wrong", "s3cret "])
def test_worker_rejects_a_bad_secret(worker_client, secret):
    assert _post(worker_client, secret=secret).status_code == 403


def test_worker_rejects_a_job_id_that_is_not_a_uuid(worker_client):
    assert _post(worker_client, job="../../etc").status_code == 422


def test_worker_runs_the_slice_and_enqueues_the_next(worker_client, monkeypatch):
    enqueued = []

    async def fake_slice(r, blobs, job_id, index):
        return index + 1

    class Q:
        async def enqueue(self, job_id, index=0):
            enqueued.append((job_id, index))

    monkeypatch.setattr(worker, "run_slice", fake_slice)
    monkeypatch.setattr(worker, "get_task_queue", lambda: Q())
    r = _post(worker_client, index=2)
    assert r.status_code == 200 and r.json() == {"next": 3}
    assert enqueued == [(JOB, 3)]


def test_worker_on_the_last_slice_enqueues_nothing(worker_client, monkeypatch):
    async def fake_slice(*_a):
        return None

    monkeypatch.setattr(worker, "run_slice", fake_slice)
    monkeypatch.setattr(worker, "get_task_queue", lambda: pytest.fail("enqueued after the last slice"))
    assert _post(worker_client).json() == {"next": None}


def test_worker_error_is_retried_until_the_last_attempt_then_the_job_fails(worker_client, monkeypatch):
    failed = []

    async def boom(*_a):
        raise RuntimeError("model exploded")

    async def record_fail(r, job_id, total=0):
        failed.append(job_id)

    monkeypatch.setattr(worker, "run_slice", boom)
    monkeypatch.setattr(worker, "fail_job", record_fail)
    quiet = TestClient(app, base_url="http://testserver/api", raise_server_exceptions=False)
    assert _post(quiet, retry=0).status_code == 500  # attempt 1 of 3: Cloud Tasks will retry
    assert _post(quiet, retry=1).status_code == 500
    assert failed == []
    last = _post(quiet, retry=2)  # attempt 3 of 3
    assert last.status_code == 200 and last.json() == {"next": None, "failed": True}
    assert failed == [JOB]


def test_the_worker_endpoint_is_not_advertised(worker_client):
    assert "/api/internal/batch/run" not in worker_client.get("/openapi.json").text


# --- blob store --------------------------------------------------------------------------------


class FakeS3:
    """Just enough of boto3's client for S3BlobStore."""

    class exceptions:  # noqa: N801 - mirrors boto3's attribute name
        class NoSuchKey(Exception):
            pass

    def __init__(self) -> None:
        self.objects: dict[str, dict] = {}

    def head_bucket(self, Bucket):  # noqa: N803
        return {}

    def put_object(self, Bucket, Key, Body, ContentType, Metadata):  # noqa: N803
        self.objects[Key] = {"Body": Body, "Metadata": Metadata}

    def get_object(self, Bucket, Key):  # noqa: N803
        if Key not in self.objects:
            raise self.exceptions.NoSuchKey()
        obj = self.objects[Key]

        class Body:
            def read(_self):  # noqa: N805
                return obj["Body"]

        return {"Body": Body(), "Metadata": obj["Metadata"]}

    def delete_object(self, Bucket, Key):  # noqa: N803
        self.objects.pop(Key, None)


def test_s3_blob_round_trip_and_delete():
    store = S3BlobStore(Settings(), client=FakeS3())

    async def go():
        await store.put("batch/a/results.json", '{"x": 1}')
        got = await store.get("batch/a/results.json")
        await store.delete("batch/a/results.json", "batch/a/never-existed.json")
        return got, await store.get("batch/a/results.json")

    assert _run(go()) == ('{"x": 1}', None)


def test_s3_blob_past_its_expiry_reads_as_gone():
    fake = FakeS3()
    store = S3BlobStore(Settings(), client=fake)
    _run(store.put("k", "v", ttl_seconds=60))
    assert _run(store.get("k")) == "v"
    fake.objects["k"]["Metadata"]["expires-at"] = str(int(time.time()) - 1)
    assert _run(store.get("k")) is None  # 24 h retention holds even without a bucket lifecycle rule


def test_key_layout_is_per_job():
    assert input_key(JOB) == f"batch/{JOB}/input.json"
    assert slice_key(JOB, 3) == f"batch/{JOB}/slice-3.json"
    assert results_key(JOB) == f"batch/{JOB}/results.json"


def _minio_reachable() -> bool:
    import socket
    from urllib.parse import urlparse

    url = urlparse(Settings().s3_endpoint_url)
    try:
        with socket.create_connection((url.hostname, url.port or 80), timeout=1):
            return True
    except OSError:
        return False


@pytest.mark.skipif(not _minio_reachable(), reason="MinIO not reachable; `docker compose up -d minio`")
def test_s3_blob_store_against_real_minio(monkeypatch):
    import uuid

    monkeypatch.setenv("S3_BUCKET_UPLOADS", f"mars-test-{uuid.uuid4().hex[:12]}")  # a throwaway bucket
    settings = Settings()
    store = S3BlobStore(settings)
    big = json.dumps({"rows": ["CC(=O)Oc1ccccc1C(=O)O"] * 50_000})  # a few MB, past what Redis should hold

    async def go():
        await store.put("batch/j/results.json", big)
        got = await store.get("batch/j/results.json")
        await store.delete("batch/j/results.json")
        return got, await store.get("batch/j/results.json")

    try:
        got, after = _run(go())
        assert got == big and after is None
    finally:
        client = store._client
        try:
            client.delete_bucket(Bucket=settings.s3_bucket_uploads)
        except Exception:
            pass
