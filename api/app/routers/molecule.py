"""Module 8 `GET /molecule/{id}/3d` — lazy, cached, no account required
(per `contracts/API_ROUTES.md`'s route table). `{id}` only makes sense if
`/predict` has already been called for that molecule in this cache window
(that's how the id -> SMILES mapping gets registered — see
`services/molecule_lookup.py`); a cold/unknown id is a clear 404, not a
guess."""

from __future__ import annotations

import json
import time
import warnings
from datetime import UTC, datetime

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from mars_contracts import (
    ConformerResponse,
    Endpoint,
    ExplainJobState,
    ExplainJobStatus,
    ExplainResponse,
)

from app.core.config import get_settings
from app.services.conformer_service import conformer_available, get_conformer
from app.services.explanation_service import (
    ExplainJobLost,
    ExplainUnavailable,
    NothingToExplain,
    explain,
    explain_available,
    kermt_cancel,
    kermt_digest,
    kermt_finish,
    kermt_serves,
    kermt_status,
    kermt_submit,
)
from app.services.molecule_lookup import lookup_molecule_smiles
from app.services.prediction_pool import run_explanation
from app.services.prediction_service import serving_version
from app.services.rate_limit import client_ip, enforce_predict_rate_limit
from app.services.redis_client import get_redis

router = APIRouter()

_CACHE_PREFIX = "conformer_cache:"


@router.get("/{molecule_id}/3d", response_model=ConformerResponse)
async def get_molecule_3d(
    molecule_id: str,
    r: redis.Redis = Depends(get_redis),
) -> ConformerResponse:
    cache_key = f"{_CACHE_PREFIX}{molecule_id}"
    try:
        cached = await r.get(cache_key)
        if cached is not None:
            return ConformerResponse.model_validate_json(cached)
    except redis.RedisError as exc:
        warnings.warn(f"Conformer cache unavailable, treating as a miss: {exc}", stacklevel=2)

    smiles = await lookup_molecule_smiles(r, molecule_id)
    if smiles is None:
        raise HTTPException(
            status_code=404,
            detail="Unknown molecule_id — call /predict for this molecule first (or its cache entry expired)",
        )

    if not conformer_available:
        raise HTTPException(
            status_code=501, detail="Conformer generation needs rdkit, which is not installed in this environment"
        )

    try:
        response = get_conformer(molecule_id, smiles)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        await r.set(cache_key, response.model_dump_json(), ex=get_settings().prediction_cache_ttl_seconds)
    except redis.RedisError as exc:
        warnings.warn(f"Could not cache conformer: {exc}", stacklevel=2)

    return response


_EXPLAIN_PREFIX = "explain_cache:"
_JOB_PREFIX = "explain_job:"  # the job this (version, digest, molecule, endpoint) has, who started it, or why it failed
_IP_PREFIX = "explain_ip:"  # the one job an address may have running (ADR-040 item 3)
_JOB_TTL_SECONDS = 2 * 60 * 60  # a running job; longer than the slowest measured explanation (about 18 min)
_FAILED_TTL_SECONDS = 10 * 60
_RETRY_AFTER_SECONDS = "3"
_NOT_FOUND = "Unknown molecule_id — call /predict for this molecule first (or its cache entry expired)"
_NEEDS_CACHE = "Explanations need the cache (Redis), which is unreachable right now."


def _explain_cache_key(molecule_id: str, endpoint: Endpoint, digest: str | None = None) -> str:
    version = serving_version() if digest is None else f"{serving_version()}:{digest}"
    return f"{_EXPLAIN_PREFIX}{version}:{molecule_id}:{endpoint.value}"


def _check_explainable(endpoint: Endpoint) -> None:
    if endpoint == Endpoint.SA_SCORE:
        raise HTTPException(status_code=409, detail="synthetic_accessibility is a computed rule, not a model: there is nothing to explain")
    if not explain_available:
        raise HTTPException(status_code=501, detail="Explanations need the ml stack (rdkit, xgboost), which is not installed in this environment")


async def _cached(r: redis.Redis, key: str) -> ExplainResponse | None:
    try:
        cached = await r.get(key)
        if cached is not None:
            return ExplainResponse.model_validate_json(cached)
    except redis.RedisError as exc:
        warnings.warn(f"Explanation cache unavailable, treating as a miss: {exc}", stacklevel=2)
    return None


async def _store(r: redis.Redis, key: str, response: ExplainResponse) -> None:
    try:
        await r.set(key, response.model_dump_json(), ex=get_settings().prediction_cache_ttl_seconds)
    except redis.RedisError as exc:
        warnings.warn(f"Could not cache explanation: {exc}", stacklevel=2)


async def _smiles_or_404(r: redis.Redis, molecule_id: str) -> str:
    smiles = await lookup_molecule_smiles(r, molecule_id)
    if smiles is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return smiles


async def _explain_now(r: redis.Redis, molecule_id: str, endpoint: Endpoint, cache_key: str) -> ExplainResponse:
    """The synchronous path (XGBoost-served endpoints, which take milliseconds). Never cached on failure."""
    smiles = await _smiles_or_404(r, molecule_id)
    try:
        response = await run_explanation(explain, molecule_id, smiles, endpoint)
    except NothingToExplain as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ExplainUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await _store(r, cache_key, response)
    return response


# ---- KERMT-served endpoints: background jobs (ADR-040) ----


def _job_key(molecule_id: str, endpoint: Endpoint, digest: str) -> str:
    return _explain_cache_key(molecule_id, endpoint, digest).replace(_EXPLAIN_PREFIX, _JOB_PREFIX, 1)


async def _digest_or_503() -> str:
    try:
        return await run_explanation(kermt_digest)
    except ExplainUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


async def _read_record(r: redis.Redis, job_key: str) -> dict | None:
    raw = await r.get(job_key)
    return None if raw is None else json.loads(raw)


async def _write_record(r: redis.Redis, job_key: str, record: dict, ttl: int) -> None:
    await r.set(job_key, json.dumps(record), ex=ttl)


async def _release_slot(r: redis.Redis, ip: str, job_key: str) -> None:
    if await r.get(f"{_IP_PREFIX}{ip}") == job_key:
        await r.delete(f"{_IP_PREFIX}{ip}")


async def _claim_slot(r: redis.Redis, ip: str, job_key: str) -> None:
    """One running explanation per address. A holder that has finished (or vanished) does not count."""
    slot = f"{_IP_PREFIX}{ip}"
    if await r.set(slot, job_key, ex=_JOB_TTL_SECONDS, nx=True):
        return
    holder = await r.get(slot)
    if holder not in (None, job_key):
        other = await _read_record(r, holder)
        if other is not None and "failed" not in other:
            try:
                snap = await run_explanation(kermt_status, other["job_id"])
                active = snap.state in (ExplainJobState.QUEUED.value, ExplainJobState.RUNNING.value)
            except (ExplainJobLost, ExplainUnavailable):
                active = False
            if active:
                raise HTTPException(
                    status_code=429,
                    detail="You already have an explanation running. Wait for it to finish, or cancel it, before starting another.",
                )
    await r.set(slot, job_key, ex=_JOB_TTL_SECONDS)


def _status_response(snap, molecule_id: str, endpoint: Endpoint, record: dict) -> JSONResponse:
    body = ExplainJobStatus(
        job_id=snap.job_id,
        molecule_id=molecule_id,
        endpoint=endpoint,
        state=ExplainJobState(snap.state),
        queue_position=snap.queue_position,
        seeds_done=snap.seeds_done,
        seeds_total=snap.seeds_total,
        stage=snap.stage,
        elapsed_seconds=snap.elapsed_seconds,
        submitted_at=datetime.fromtimestamp(record["submitted_at"], tz=UTC),
        error=snap.error,
    )
    active = body.state in (ExplainJobState.QUEUED, ExplainJobState.RUNNING)
    return JSONResponse(
        status_code=202 if active else 200,
        content=json.loads(body.model_dump_json()),
        headers={"Retry-After": _RETRY_AFTER_SECONDS} if active else None,
    )


def _raise_failed(error: str, kind: str | None) -> None:
    """A failed job answers with its error. A molecule the model cannot take is 422; anything else is 503."""
    raise HTTPException(status_code=422 if kind == "unexplainable" else 503, detail=error)


async def _answer(
    r: redis.Redis, snap, molecule_id: str, smiles: str, endpoint: Endpoint, job_key: str, cache_key: str, record: dict
) -> Response:
    """Turn the service's view of a job into the response, finalising it (cache, free the address's slot) when it ended."""
    if snap.state == ExplainJobState.DONE.value:
        try:
            response = await run_explanation(kermt_finish, molecule_id, smiles, endpoint, snap)
        except ExplainUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        await _store(r, cache_key, response)
        await r.delete(job_key)
        await _release_slot(r, record["ip"], job_key)
        return JSONResponse(content=json.loads(response.model_dump_json()))
    if snap.state == ExplainJobState.FAILED.value:
        message = snap.error or "The explanation failed."
        await _write_record(r, job_key, {**record, "failed": {"error": message, "kind": snap.error_kind}}, _FAILED_TTL_SECONDS)
        await _release_slot(r, record["ip"], job_key)
        _raise_failed(message, snap.error_kind)
    if snap.state == ExplainJobState.CANCELLED.value:
        await r.delete(job_key)
        await _release_slot(r, record["ip"], job_key)
        return Response(status_code=204)
    return _status_response(snap, molecule_id, endpoint, record)


async def _forget(r: redis.Redis, job_key: str, record: dict) -> None:
    """The service no longer knows the job: drop our record and free the address's slot."""
    await r.delete(job_key)
    await _release_slot(r, record["ip"], job_key)


@router.post("/{molecule_id}/explain", response_model=ExplainResponse, responses={202: {"model": ExplainJobStatus}})
async def start_molecule_explanation(
    molecule_id: str,
    endpoint: Endpoint,
    request: Request,
    r: redis.Redis = Depends(get_redis),
    _rate_limit: None = Depends(enforce_predict_rate_limit),
):
    """Module 6 / ADR-031, ADR-040: start (or join) the explanation of the value the serving model gave this endpoint.

    XGBoost-served: answered now, 200. KERMT-served: a background job; 202 with its status while it runs, 200 with the
    result once it is cached or done. 404 unknown or expired molecule; 409 nothing to explain; 422 the molecule cannot be
    explained; 429 rate limit, or you already have one running; 501 no ml stack; 503 the serving model cannot explain
    right now or the queue is full (never swapped for a different model's explanation, never cached on failure).
    """
    _check_explainable(endpoint)
    if not kermt_serves(endpoint):
        cache_key = _explain_cache_key(molecule_id, endpoint)
        return await _cached(r, cache_key) or await _explain_now(r, molecule_id, endpoint, cache_key)

    digest = await _digest_or_503()
    cache_key = _explain_cache_key(molecule_id, endpoint, digest)
    if (hit := await _cached(r, cache_key)) is not None:
        return hit
    smiles = await _smiles_or_404(r, molecule_id)
    job_key, ip = _job_key(molecule_id, endpoint, digest), client_ip(request)
    try:
        record = await _read_record(r, job_key)
        if record is not None and "failed" not in record:  # join the job already there
            try:
                snap = await run_explanation(kermt_status, record["job_id"])
                return await _answer(r, snap, molecule_id, smiles, endpoint, job_key, cache_key, record)
            except ExplainJobLost:
                await _forget(r, job_key, record)
            except ExplainUnavailable as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
        await _claim_slot(r, ip, job_key)
        try:
            snap = await run_explanation(kermt_submit, smiles, endpoint)
        except ExplainUnavailable as exc:  # includes ExplainBusy: the queue is full
            await _release_slot(r, ip, job_key)
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            await _release_slot(r, ip, job_key)
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        record = {"job_id": snap.job_id, "ip": ip, "submitted_at": time.time()}
        await _write_record(r, job_key, record, _JOB_TTL_SECONDS)
        return await _answer(r, snap, molecule_id, smiles, endpoint, job_key, cache_key, record)
    except redis.RedisError as exc:
        raise HTTPException(status_code=503, detail=_NEEDS_CACHE) from exc


@router.get(
    "/{molecule_id}/explain",
    response_model=ExplainResponse,
    responses={202: {"model": ExplainJobStatus}, 204: {"description": "Nothing started and nothing cached"}},
)
async def get_molecule_explanation(
    molecule_id: str,
    endpoint: Endpoint,
    r: redis.Redis = Depends(get_redis),
):
    """Read the explanation, with no side effect (ADR-040): the cached result (200), the running job (202), or
    nothing (204). Polled by the browser; not rate limited. Errors as for POST, plus the failure of a job that failed."""
    _check_explainable(endpoint)
    if not kermt_serves(endpoint):
        if (hit := await _cached(r, _explain_cache_key(molecule_id, endpoint))) is not None:
            return hit
        await _smiles_or_404(r, molecule_id)
        return Response(status_code=204)

    digest = await _digest_or_503()
    cache_key = _explain_cache_key(molecule_id, endpoint, digest)
    if (hit := await _cached(r, cache_key)) is not None:
        return hit
    smiles = await _smiles_or_404(r, molecule_id)
    job_key = _job_key(molecule_id, endpoint, digest)
    try:
        record = await _read_record(r, job_key)
        if record is None:
            return Response(status_code=204)
        if "failed" in record:
            _raise_failed(record["failed"]["error"], record["failed"]["kind"])
        try:
            snap = await run_explanation(kermt_status, record["job_id"])
        except ExplainJobLost:
            await _forget(r, job_key, record)
            raise HTTPException(
                status_code=503, detail="The explanation was lost (the service restarted while it ran). Start it again."
            ) from None
        except ExplainUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return await _answer(r, snap, molecule_id, smiles, endpoint, job_key, cache_key, record)
    except redis.RedisError as exc:
        raise HTTPException(status_code=503, detail=_NEEDS_CACHE) from exc


@router.delete("/{molecule_id}/explain", responses={200: {"model": ExplainJobStatus}, 204: {"description": "No job to cancel"}})
async def cancel_molecule_explanation(
    molecule_id: str,
    endpoint: Endpoint,
    request: Request,
    r: redis.Redis = Depends(get_redis),
):
    """Ask the running job to stop (it stops between chunks, within a second or so). Only the address that started it
    may cancel it, because other people may be waiting on the same job. 204 when there is nothing to cancel."""
    _check_explainable(endpoint)
    if not kermt_serves(endpoint):
        return Response(status_code=204)
    job_key = _job_key(molecule_id, endpoint, await _digest_or_503())
    try:
        record = await _read_record(r, job_key)
        if record is None or "failed" in record:
            return Response(status_code=204)
        if record["ip"] != client_ip(request):
            raise HTTPException(status_code=403, detail="Only the visitor who started this explanation can cancel it.")
        try:
            snap = await run_explanation(kermt_cancel, record["job_id"])
        except ExplainJobLost:
            await _forget(r, job_key, record)
            return Response(status_code=204)
        except ExplainUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if snap.state == ExplainJobState.CANCELLED.value:
            await _forget(r, job_key, record)
        return _status_response(snap, molecule_id, endpoint, record)
    except redis.RedisError as exc:
        raise HTTPException(status_code=503, detail=_NEEDS_CACHE) from exc
