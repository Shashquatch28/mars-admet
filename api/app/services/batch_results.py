"""Batch result storage — dev/local stand-in for the blueprint's R2 bucket.

Real target (Module 8/10): results land in Cloudflare R2, auto-deleted 24h
after job completion. Storing the JSON result blob in Redis instead is a
deliberate local-dev simplification (docker-compose already runs Redis;
wiring boto3 + MinIO for this specific blob is a follow-up, not yet done) —
functionally equivalent for the 24h-retention contract this session can
actually test, but not the real object-storage path. Flagged here rather
than silently presented as "R2 done."
"""

from __future__ import annotations

import redis.asyncio as redis

_RESULT_TTL_SECONDS = 86_400  # 24h, matches Module 8 batch-upload retention


def _result_key(job_id: str) -> str:
    return f"batch_results:{job_id}"


async def store_batch_results(r: redis.Redis, job_id: str, results_json: str) -> None:
    await r.set(_result_key(job_id), results_json, ex=_RESULT_TTL_SECONDS)


async def load_batch_results(r: redis.Redis, job_id: str) -> str | None:
    return await r.get(_result_key(job_id))
