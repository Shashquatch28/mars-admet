"""Background explanation jobs for the KERMT service (ADR-035). No torch, no KERMT: a small in-memory queue.

Why here. An Integrated Gradients run takes minutes, so nothing may hold a request open for it, and a job
needs a home that outlasts a request. The service is the one long-lived process that already holds the model.

What it does. One worker thread runs one job at a time (the model's matmuls already use every CPU; running two
at once is slower, not faster). A bounded queue sits behind it. A job id is deterministic, so submitting the
same (molecule, endpoint, parameters) again joins the existing job instead of queueing a second one.

What it does not do. Jobs live in memory: a restart loses them, and the API reports that as a lost job to start
again (ADR-035 item 7). Progress is a seed counter and a stage in words, never a percentage or an estimate: the
step count escalates adaptively, so the total is not known in advance.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from explain.graph_ig import IGCancelled

logger = logging.getLogger("mars.kermt_jobs")

QUEUED, RUNNING, DONE, FAILED, CANCELLED = "queued", "running", "done", "failed", "cancelled"
_TERMINAL = {DONE, FAILED, CANCELLED}

# (payload, progress, cancelled) -> result dict. progress(seeds_done, seeds_total, stage_text).
Runner = Callable[[dict, Callable[[int, int, str | None], None], Callable[[], bool]], dict]


class QueueFull(Exception):
    """The bounded queue behind the worker is full."""


@dataclass
class Job:
    job_id: str
    payload: dict
    submitted_at: float  # monotonic
    submitted_wall: float  # epoch seconds, for the API to report
    state: str = QUEUED
    seeds_done: int = 0
    seeds_total: int = 0
    stage: str | None = None
    error: str | None = None
    error_kind: str | None = None  # unexplainable | internal
    result: dict | None = None
    finished_at: float | None = None
    cancel: threading.Event = field(default_factory=threading.Event)


class JobManager:
    def __init__(
        self,
        runner: Runner,
        *,
        max_queue: int = 8,
        retention_seconds: float = 3600.0,
        max_jobs: int = 64,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._runner = runner
        self._max_queue = max_queue
        self._retention = retention_seconds
        self._max_jobs = max_jobs
        self._clock = clock
        self._jobs: dict[str, Job] = {}
        self._queue: deque[str] = deque()
        self._cv = threading.Condition()
        self._stopping = False
        self._worker = threading.Thread(target=self._loop, name="kermt-explain-worker", daemon=True)
        self._worker.start()

    # ------------------------------------------------------------------ public

    def submit(self, job_id: str, payload: dict, *, seeds_total: int = 0) -> Job:
        """Start the job, or join it if the same one is queued, running or finished. Raises QueueFull."""
        with self._cv:
            self._purge()
            existing = self._jobs.get(job_id)
            if existing is not None and existing.state in (QUEUED, RUNNING, DONE):
                return existing
            if len(self._queue) >= self._max_queue:
                raise QueueFull(f"the explanation queue is full ({self._max_queue} waiting)")
            job = Job(job_id=job_id, payload=payload, submitted_at=self._clock(), submitted_wall=time.time(), seeds_total=seeds_total)
            self._jobs[job_id] = job  # replaces a failed or cancelled one
            self._queue.append(job_id)
            self._cv.notify()
            return job

    def get(self, job_id: str) -> Job | None:
        with self._cv:
            self._purge()
            return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> Job | None:
        """Queued: cancelled at once. Running: asked to stop between chunks; it reports cancelled when it does."""
        with self._cv:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.state == QUEUED:
                self._queue.remove(job_id)
                job.state, job.finished_at = CANCELLED, self._clock()
            elif job.state == RUNNING:
                job.cancel.set()
            return job

    def snapshot(self, job: Job) -> dict:
        """The wire shape the API reads. `result` only once done."""
        with self._cv:
            position = None
            if job.state == QUEUED:
                position = list(self._queue).index(job.job_id) + 1
            return {
                "job_id": job.job_id,
                "state": job.state,
                "queue_position": position,
                "seeds_done": job.seeds_done,
                "seeds_total": job.seeds_total,
                "stage": job.stage,
                "elapsed_seconds": round((self._clock() if job.finished_at is None else job.finished_at) - job.submitted_at, 1),
                "submitted_at": job.submitted_wall,
                "error": job.error,
                "error_kind": job.error_kind,
                "result": job.result if job.state == DONE else None,
            }

    def stop(self) -> None:
        with self._cv:
            self._stopping = True
            self._cv.notify_all()

    # ------------------------------------------------------------------ worker

    def _loop(self) -> None:
        while True:
            with self._cv:
                while not self._queue and not self._stopping:
                    self._cv.wait()
                if self._stopping:
                    return
                job = self._jobs[self._queue.popleft()]
                job.state = RUNNING
            self._run(job)

    def _run(self, job: Job) -> None:
        def progress(done: int, total: int, stage: str | None) -> None:
            with self._cv:
                job.seeds_done, job.seeds_total, job.stage = done, total, stage

        try:
            result = self._runner(job.payload, progress, job.cancel.is_set)
            outcome = (DONE, result, None, None)
        except IGCancelled:
            outcome = (CANCELLED, None, None, None)
        except (ValueError, KeyError) as exc:  # the molecule or endpoint cannot be explained: not retryable as is
            outcome = (FAILED, None, str(exc).strip("'\""), "unexplainable")
        except Exception:  # noqa: BLE001 - a worker must survive one bad job; the cause is logged
            logger.exception("explanation job %s failed", job.job_id)
            outcome = (FAILED, None, "The service failed while explaining this molecule.", "internal")
        with self._cv:
            job.state, job.result, job.error, job.error_kind = outcome
            job.finished_at = self._clock()
            job.stage = None

    def _purge(self) -> None:
        """Forget terminal jobs older than the retention, and the oldest terminal ones beyond `max_jobs`."""
        now = self._clock()
        for jid in [j for j, job in self._jobs.items() if job.state in _TERMINAL and job.finished_at is not None and now - job.finished_at > self._retention]:
            del self._jobs[jid]
        if len(self._jobs) > self._max_jobs:
            terminal = sorted((j for j in self._jobs.values() if j.state in _TERMINAL), key=lambda j: 0.0 if j.finished_at is None else j.finished_at)
            for job in terminal[: len(self._jobs) - self._max_jobs]:
                del self._jobs[job.job_id]
