"""The one place an S3 client is built, for batch blobs and for model artifacts alike."""

from __future__ import annotations

from app.core.config import Settings


def make_s3_client(settings: Settings, *, access_key_id: str = "", secret_access_key: str = ""):
    """A boto3 client for `S3_ENDPOINT_URL` (Cloudflare R2 in production, MinIO locally).

    Checksums are computed only when an operation requires them: newer boto3 adds a CRC32 checksum to
    every upload by default, and reports (not yet reproduced against this project's R2 bucket) say R2
    rejects it; `when_required` is the documented workaround and MinIO does not need the checksum. The
    explicit key pair is for a caller that must use different credentials from the batch store (the
    read-only model-bucket key)."""
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        aws_access_key_id=access_key_id or settings.s3_access_key_id,
        aws_secret_access_key=secret_access_key or settings.s3_secret_access_key,
        region_name=settings.s3_region,
        config=Config(
            retries={"max_attempts": 3},
            signature_version="s3v4",
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )
