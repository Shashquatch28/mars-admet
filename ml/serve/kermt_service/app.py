"""HTTP front for `KermtEngine`: the KERMT inference service the API calls.

    POST /predict   {"smiles": [...standardized...], "arms": ["toxicity__cls", ...]}   (arms optional = all loaded)
    POST /explain/jobs, GET /explain/jobs/{id}, DELETE /explain/jobs/{id}, GET /explain/config   background Integrated Gradients (ADR-035)
    POST /explain   {"smiles": "...standardized...", "arm": "toxicity__cls", "endpoint": "herg_cardiotoxicity"}   Integrated Gradients (ADR-031)
    GET  /health    readiness (200 only once every discovered checkpoint is loaded)
    GET  /models    arm -> model_id, task_type, targets, seeds, model.pt SHA-256 per seed

The service is internal. It takes SMILES the API has already standardized and returns raw
per-seed values; ensembling, the AD flag, the held-out error band and the `model_id` on a
response row are the API side's job, exactly as for XGBoost (`serve/predictor.py`).

Environment:
    KERMT_MODELS_DIR   serving layout root (default /models)
    KERMT_ARMS         comma list of arms to load (default: every arm found)
    KERMT_SEEDS        comma list of seeds to load per arm (default: every seed found)
    KERMT_THREADS      torch intra-op threads (default: the CPUs this container may use, read from its cgroup)
    KERMT_BATCH_SIZE   inference batch size (default 32, KERMT's own default)
    KERMT_TOKEN        if set, /predict and /models require header `X-Kermt-Token: <value>`
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import threading
import time
from contextlib import asynccontextmanager

import numpy as np
from engine import DEFAULT_BATCH_SIZE, KermtEngine, env_int
from fastapi import FastAPI, Header, HTTPException
from jobs import JobManager, QueueFull
from pydantic import BaseModel, Field

logger = logging.getLogger("mars.kermt_service")
MAX_MOLECULES = 256

_state: dict = {"engine": None, "ready": False, "error": None, "loaded": 0, "expected": 0, "jobs": None}


def _csv_env(name: str) -> list[str] | None:
    raw = os.environ.get(name, "").strip()
    return [p.strip() for p in raw.split(",") if p.strip()] or None


def _load_in_background() -> None:
    try:
        seeds = _csv_env("KERMT_SEEDS")
        engine = KermtEngine(
            os.environ.get("KERMT_MODELS_DIR", "/models"),
            arms=_csv_env("KERMT_ARMS"),
            seeds=[int(s) for s in seeds] if seeds else None,
            batch_size=int(os.environ.get("KERMT_BATCH_SIZE", DEFAULT_BATCH_SIZE)),
            threads=env_int("KERMT_THREADS"),
        )
        found = engine.discover()
        _state["expected"] = len(found)
        if not found:
            raise RuntimeError("no checkpoints found under KERMT_MODELS_DIR")
        t0 = time.perf_counter()
        for arm, seed, seed_dir in found:
            engine._load_one(arm, seed, seed_dir)
            _state["loaded"] += 1
        _state["engine"] = engine
        _state["jobs"] = JobManager(
            lambda p, progress, cancelled: engine.explain(p["smiles"], p["arm"], p["endpoint"], progress=progress, cancelled=cancelled),
            max_queue=int(os.environ.get("KERMT_EXPLAIN_QUEUE", "8")),
        )
        _state["ready"] = True
        logger.info("KERMT engine ready: %d checkpoints in %.0fs", _state["loaded"], time.perf_counter() - t0)
    except Exception as exc:  # surfaced on /health, never swallowed
        logger.exception("KERMT engine failed to load")
        _state["error"] = f"{type(exc).__name__}: {exc}"


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Load off the event loop so /health answers (503, with progress) while checkpoints load.
    threading.Thread(target=_load_in_background, name="kermt-load", daemon=True).start()
    yield


app = FastAPI(title="MARS KERMT inference", lifespan=lifespan)


def _auth(token: str | None) -> None:
    expected = os.environ.get("KERMT_TOKEN")
    if expected and not (token and hmac.compare_digest(token, expected)):
        raise HTTPException(status_code=401, detail="bad or missing X-Kermt-Token")


def _engine() -> KermtEngine:
    if not _state["ready"]:
        raise HTTPException(status_code=503, detail=_state["error"] or "models still loading")
    return _state["engine"]


class PredictRequest(BaseModel):
    smiles: list[str] = Field(min_length=1, max_length=MAX_MOLECULES)
    arms: list[str] | None = None


class ExplainRequest(BaseModel):
    smiles: str = Field(min_length=1)
    arm: str
    endpoint: str
    steps: list[int] | None = Field(default=None, description="Override the interpolation-step schedule (increasing)")


@app.post("/explain")
def explain(req: ExplainRequest, x_kermt_token: str | None = Header(default=None)):
    """Integrated Gradients for one endpoint (ADR-031). Slow (seconds); holds the engine lock only per chunk."""
    _auth(x_kermt_token)
    engine = _engine()
    try:
        return engine.explain(req.smiles, req.arm, req.endpoint, schedule=tuple(req.steps) if req.steps else None)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _job_id(req: ExplainRequest, digest: str) -> str:
    return hashlib.sha256(f"{req.smiles}|{req.arm}|{req.endpoint}|{digest}".encode()).hexdigest()[:24]


@app.get("/explain/config")
def explain_config(x_kermt_token: str | None = Header(default=None)):
    """The parameters an explanation depends on and their digest (ADR-035): cache-key material for the API."""
    _auth(x_kermt_token)
    return _engine().explain_config()


@app.post("/explain/jobs")
def submit_explain_job(req: ExplainRequest, x_kermt_token: str | None = Header(default=None)):
    """Start or join the background job for this molecule and endpoint (idempotent). 429 when the queue is full."""
    _auth(x_kermt_token)
    engine = _engine()
    try:
        n_seeds = len(engine.explainable_models(req.arm, req.endpoint))
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc).strip("'\"")) from exc
    jobs = _state["jobs"]
    try:
        job = jobs.submit(_job_id(req, engine.explain_config()["digest"]), req.model_dump(), seeds_total=n_seeds)
    except QueueFull as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return jobs.snapshot(job)


@app.get("/explain/jobs/{job_id}")
def get_explain_job(job_id: str, x_kermt_token: str | None = Header(default=None)):
    _auth(x_kermt_token)
    _engine()
    jobs = _state["jobs"]
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown explanation job (it finished long ago, or the service restarted)")
    return jobs.snapshot(job)


@app.delete("/explain/jobs/{job_id}")
def cancel_explain_job(job_id: str, x_kermt_token: str | None = Header(default=None)):
    _auth(x_kermt_token)
    _engine()
    jobs = _state["jobs"]
    job = jobs.cancel(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown explanation job")
    return jobs.snapshot(job)


@app.get("/health")
def health():
    body = {"ready": _state["ready"], "loaded": _state["loaded"], "expected": _state["expected"], "error": _state["error"]}
    if not _state["ready"]:
        raise HTTPException(status_code=503, detail=body)
    return body


@app.get("/models")
def models(x_kermt_token: str | None = Header(default=None)):
    _auth(x_kermt_token)
    return _engine().describe()


@app.post("/predict")
def predict(req: PredictRequest, x_kermt_token: str | None = Header(default=None)):
    _auth(x_kermt_token)
    engine = _engine()
    try:
        results = engine.predict(req.smiles, req.arms)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    arms = {}
    for arm, res in results.items():
        seeds = sorted(res.by_seed)
        stacked = np.stack([res.by_seed[s] for s in seeds], axis=-1)  # (molecule, target, seed)
        arms[arm] = {
            "model_id": res.model_id,
            "task_type": res.task_type,
            "seeds": seeds,
            "values": {
                name: [[None if np.isnan(v) else float(v) for v in stacked[i, j]] for i in range(len(req.smiles))]
                for j, name in enumerate(res.target_names)
            },
        }
    return {"arms": arms}
