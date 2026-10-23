"""The KERMT service's background explanation jobs (ADR-035). No torch: a fake runner stands in for the engine."""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest
from explain.graph_ig import IGCancelled

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "serve" / "kermt_service"))
import jobs  # noqa: E402
from jobs import CANCELLED, DONE, FAILED, QUEUED, RUNNING, JobManager, QueueFull  # noqa: E402


def wait_for(cond, timeout=5.0):
    t = time.time()
    while time.time() - t < timeout:
        if cond():
            return
        time.sleep(0.01)
    raise AssertionError("timed out waiting")


class Gate:
    """A runner that blocks until released, so a test can look at the queue while a job is running."""

    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls: list[dict] = []

    def __call__(self, payload, progress, cancelled):
        self.calls.append(payload)
        progress(0, 3, "seed 1 of 3, 64 steps")
        self.started.set()
        while not self.release.is_set():
            if cancelled():
                raise IGCancelled()
            time.sleep(0.005)
        progress(3, 3, None)
        return {"answer": payload["n"]}


@pytest.fixture
def manager():
    made = []

    def make(runner, **kw):
        m = JobManager(runner, **kw)
        made.append(m)
        return m

    yield make
    for m in made:
        m.stop()


def test_a_job_runs_reports_progress_and_returns_its_result_only_when_done(manager):
    gate = Gate()
    m = manager(gate)
    job = m.submit("a", {"n": 1})
    gate.started.wait(5)
    snap = m.snapshot(job)
    assert snap["state"] == RUNNING and snap["queue_position"] is None
    assert (snap["seeds_done"], snap["seeds_total"], snap["stage"]) == (0, 3, "seed 1 of 3, 64 steps")
    assert snap["result"] is None  # not until done
    gate.release.set()
    wait_for(lambda: m.get("a").state == DONE)
    snap = m.snapshot(m.get("a"))
    assert snap["result"] == {"answer": 1} and snap["seeds_done"] == 3 and snap["error"] is None
    assert set(snap) >= {"job_id", "state", "queue_position", "seeds_done", "seeds_total", "stage", "elapsed_seconds", "submitted_at", "error", "error_kind", "result"}


def test_queue_positions_a_bound_and_the_same_job_joins_instead_of_running_twice(manager):
    gate = Gate()
    m = manager(gate, max_queue=2)
    first = m.submit("first", {"n": 1})
    gate.started.wait(5)
    second, third = m.submit("second", {"n": 2}), m.submit("third", {"n": 3})
    assert m.snapshot(second)["queue_position"] == 1 and m.snapshot(third)["queue_position"] == 2
    with pytest.raises(QueueFull):
        m.submit("fourth", {"n": 4})
    assert m.submit("first", {"n": 1}) is first  # joins the running job
    assert m.submit("second", {"n": 2}) is second  # joins the queued one
    gate.release.set()
    wait_for(lambda: all(m.get(j).state == DONE for j in ("first", "second", "third")))
    assert [c["n"] for c in gate.calls] == [1, 2, 3]  # each ran exactly once, in order


def test_a_finished_job_is_returned_again_until_it_is_forgotten(manager):
    now = [0.0]
    gate = Gate()
    gate.release.set()
    m = manager(gate, retention_seconds=100, clock=lambda: now[0])
    m.submit("a", {"n": 1})
    wait_for(lambda: m.get("a").state == DONE)
    assert m.submit("a", {"n": 1}).state == DONE  # no second run
    assert len(gate.calls) == 1
    now[0] = 500.0
    assert m.get("a") is None  # past the retention: gone, so a lost job is a 404 to the API


def test_cancelling_a_queued_job_is_immediate_and_a_running_one_stops_between_chunks(manager):
    gate = Gate()
    m = manager(gate)
    m.submit("run", {"n": 1})
    gate.started.wait(5)
    queued = m.submit("wait", {"n": 2})
    assert m.cancel("wait").state == CANCELLED and m.snapshot(queued)["queue_position"] is None
    m.cancel("run")
    wait_for(lambda: m.get("run").state == CANCELLED)
    assert m.cancel("never-existed") is None
    assert [c["n"] for c in gate.calls] == [1]  # the cancelled queued job never ran


def test_a_molecule_that_cannot_be_explained_fails_with_its_reason_and_the_worker_survives(manager):
    def runner(payload, progress, cancelled):
        if payload["n"] == 1:
            raise ValueError("KERMT cannot explain this molecule: its descriptor vector has non-finite values")
        if payload["n"] == 2:
            raise RuntimeError("boom")
        return {"ok": True}

    m = manager(runner)
    m.submit("a", {"n": 1})
    m.submit("b", {"n": 2})
    m.submit("c", {"n": 3})
    wait_for(lambda: m.get("c").state == DONE)
    a, b = m.snapshot(m.get("a")), m.snapshot(m.get("b"))
    assert a["state"] == FAILED and a["error_kind"] == "unexplainable" and "non-finite" in a["error"]
    assert b["state"] == FAILED and b["error_kind"] == "internal" and "boom" not in b["error"]  # the cause is logged, not shown


def test_a_failed_or_cancelled_job_can_be_started_again(manager):
    attempts = []

    def runner(payload, progress, cancelled):
        attempts.append(1)
        if len(attempts) == 1:
            raise ValueError("no")
        return {"ok": True}

    m = manager(runner)
    m.submit("a", {"n": 1})
    wait_for(lambda: m.get("a").state == FAILED)
    m.submit("a", {"n": 1})
    wait_for(lambda: m.get("a").state == DONE)
    assert len(attempts) == 2


def test_the_oldest_finished_jobs_are_dropped_past_the_cap(manager):
    now = [0.0]

    def runner(payload, progress, cancelled):
        return {"n": payload["n"]}

    m = manager(runner, max_jobs=3, clock=lambda: now[0])
    for i in range(5):
        now[0] += 1
        m.submit(f"j{i}", {"n": i})
        wait_for(lambda i=i: m.get(f"j{i}") is not None and m.get(f"j{i}").state == DONE)
    assert m.get("j0") is None and m.get("j4") is not None


def test_module_exposes_the_states_the_contract_names():
    assert (jobs.QUEUED, jobs.RUNNING, jobs.DONE, jobs.FAILED, jobs.CANCELLED) == ("queued", "running", "done", "failed", "cancelled")
    assert QUEUED == "queued"
