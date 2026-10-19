"""Where batch jobs keep their bytes: the uploaded molecules, per-slice results, and the final result.

Two backends behind one small interface, chosen by `BATCH_BLOB_BACKEND`:

* `redis` (default, development): values live in Redis with a TTL. Fine for the stack that
  `docker compose` runs. Not fit for production: Upstash's free plan allows 10 MB per request and
  100 MB per record, and a result is about 2.5 KB per molecule, so Redis holds a few thousand rows at
  most and the 50,000-molecule cap cannot fit.
* `s3` (production): any S3-compatible bucket. Cloudflare R2 in production, MinIO locally. Expiry is
  enforced here as well as by a bucket lifecycle rule: every object carries an `expires-at` stamp and
  a read past it returns nothing, so the 24 h retention holds even if the rule was never configured.
"""

from __future__ import annotations

import asyncio
import time
from typing import Protocol

import redis.asyncio as redis

from app.core.config import Settings, get_settings

RETENTION_SECONDS = 86_400  # 24 h, Module 8 batch retention


class BlobStore(Protocol):
    async def put(self, key: str, data: str, *, ttl_seconds: int = RETENTION_SECONDS) -> None: ...
    async def get(self, key: str) -> str | None: ...
    async def delete(self, *keys: str) -> None: ...


class RedisBlobStore:
    def __init__(self, r: redis.Redis) -> None:
        self._r = r

    @staticmethod
    def _key(key: str) -> str:
        return f"blob:{key}"

    async def put(self, key: str, data: str, *, ttl_seconds: int = RETENTION_SECONDS) -> None:
        await self._r.set(self._key(key), data, ex=ttl_seconds)

    async def get(self, key: str) -> str | None:
        return await self._r.get(self._key(key))

    async def delete(self, *keys: str) -> None:
        if keys:
            await self._r.delete(*(self._key(k) for k in keys))


class S3BlobStore:
    """boto3 is synchronous, so every call runs on a worker thread."""

    def __init__(self, settings: Settings, client=None) -> None:
        self._bucket = settings.s3_bucket_uploads
        self._client = client if client is not None else self._make_client(settings)
        self._checked_bucket = False

    @staticmethod
    def _make_client(settings: Settings):
        import boto3
        from botocore.config import Config

        return boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url or None,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            region_name=settings.s3_region,
            config=Config(retries={"max_attempts": 3}, signature_version="s3v4"),
        )

    def _ensure_bucket(self) -> None:
        """Create the bucket if it is missing (MinIO in development). A refusal is ignored: R2 tokens
        often cannot create buckets, and there the bucket is made once by hand."""
        if self._checked_bucket:
            return
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except Exception:
            try:
                self._client.create_bucket(Bucket=self._bucket)
            except Exception:
                pass
        self._checked_bucket = True

    def _put(self, key: str, data: str, ttl_seconds: int) -> None:
        self._ensure_bucket()
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=data.encode("utf-8"),
            ContentType="application/json",
            Metadata={"expires-at": str(int(time.time()) + ttl_seconds)},
        )

    def _get(self, key: str) -> str | None:
        self._ensure_bucket()
        try:
            obj = self._client.get_object(Bucket=self._bucket, Key=key)
        except self._client.exceptions.NoSuchKey:
            return None
        expires_at = int(obj.get("Metadata", {}).get("expires-at", "0") or 0)
        if expires_at and expires_at < time.time():
            return None
        return obj["Body"].read().decode("utf-8")

    def _delete(self, keys: tuple[str, ...]) -> None:
        for key in keys:
            self._client.delete_object(Bucket=self._bucket, Key=key)

    async def put(self, key: str, data: str, *, ttl_seconds: int = RETENTION_SECONDS) -> None:
        await asyncio.to_thread(self._put, key, data, ttl_seconds)

    async def get(self, key: str) -> str | None:
        return await asyncio.to_thread(self._get, key)

    async def delete(self, *keys: str) -> None:
        if keys:
            await asyncio.to_thread(self._delete, keys)


def get_blob_store(r: redis.Redis) -> BlobStore:
    settings = get_settings()
    if settings.batch_blob_backend == "s3":
        return S3BlobStore(settings)
    return RedisBlobStore(r)


# Key layout, in one place so the runner, the routes and the tests cannot disagree.
def input_key(job_id: str) -> str:
    return f"batch/{job_id}/input.json"


def slice_key(job_id: str, index: int) -> str:
    return f"batch/{job_id}/slice-{index}.json"


def results_key(job_id: str) -> str:
    return f"batch/{job_id}/results.json"
