"""Publish the trained XGBoost artifacts (`ml/artifacts/`) to the model bucket as one immutable release.

Run it yourself, in your own terminal, with the bucket credentials in your environment. It reads them and never
prints them. Nothing is written to disk; the manifest goes to the bucket.

    # from the repository root, in the root .venv (boto3 and mars_contracts installed)
    $env:S3_ENDPOINT_URL   = "https://<account-id>.r2.cloudflarestorage.com"
    $env:S3_REGION         = "auto"
    $env:MODEL_PUBLISH_ACCESS_KEY_ID     = "<write-capable R2 key>"      # set these two by typing them yourself
    $env:MODEL_PUBLISH_SECRET_ACCESS_KEY = "<its secret>"

    python infra/scripts/publish_model_artifacts.py --bucket mars-models --dry-run      # hashes only, no network
    python infra/scripts/publish_model_artifacts.py --bucket mars-models                # upload
    python infra/scripts/publish_model_artifacts.py --bucket mars-models --verify <release-id>   # re-check a release

The last line it prints is the release id; that is the value of `MODEL_ARTIFACT_RELEASE` on the service.
A tree that does not cover all 14 endpoints (a model, its applicability-domain index, and a calibrator or
error band) is refused, because a service started from it would refuse to start.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "api"), str(REPO / "ml")]

from serve import artifact_store  # noqa: E402


def make_client():
    """Write credentials come from MODEL_PUBLISH_*; the endpoint and region come from the usual S3_* settings."""
    from app.core.config import Settings
    from app.services.s3_client import make_s3_client

    key, secret = os.environ.get("MODEL_PUBLISH_ACCESS_KEY_ID", ""), os.environ.get("MODEL_PUBLISH_SECRET_ACCESS_KEY", "")
    if not key or not secret:
        raise SystemExit("Set MODEL_PUBLISH_ACCESS_KEY_ID and MODEL_PUBLISH_SECRET_ACCESS_KEY in this shell first (or use --dry-run).")
    settings = Settings()
    print(f"endpoint: {settings.s3_endpoint_url}", file=sys.stderr)
    return make_s3_client(settings, access_key_id=key, secret_access_key=secret)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--artifacts-dir", type=Path, default=REPO / "ml" / "artifacts")
    parser.add_argument("--bucket", default=os.environ.get("MODEL_ARTIFACT_BUCKET", ""))
    parser.add_argument("--prefix", default=os.environ.get("MODEL_ARTIFACT_PREFIX", artifact_store.DEFAULT_PREFIX))
    parser.add_argument("--dry-run", action="store_true", help="hash the tree and print the release id; touch no network")
    parser.add_argument("--verify", metavar="RELEASE", help="check a published release (manifest and object sizes) without uploading")
    parser.add_argument("--allow-incomplete", action="store_true", help="publish a tree that misses endpoints (the service will refuse it)")
    args = parser.parse_args(argv)

    if not args.dry_run and not args.bucket:
        parser.error("--bucket (or MODEL_ARTIFACT_BUCKET) is required unless --dry-run")
    try:
        if args.verify:
            bad = artifact_store.check_remote(make_client(), args.bucket, args.verify, prefix=args.prefix)
            for line in bad:
                print(f"PROBLEM: {line}", file=sys.stderr)
            print("release intact" if not bad else f"{len(bad)} problem(s)")
            return 1 if bad else 0
        client = None if args.dry_run else make_client()
        result = artifact_store.publish(
            client, args.bucket, args.artifacts_dir, prefix=args.prefix, dry_run=args.dry_run,
            allow_incomplete=args.allow_incomplete, log=print,
        )
    except artifact_store.ArtifactError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.dry_run:
        print("dry run: nothing was uploaded")
    else:
        bad = artifact_store.check_remote(client, args.bucket, result.release, prefix=args.prefix)
        if bad:
            for line in bad:
                print(f"PROBLEM: {line}", file=sys.stderr)
            return 1
        print("verified in the bucket: manifest matches its id and every object has the recorded size")
    print(f"MODEL_ARTIFACT_RELEASE={result.release}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
