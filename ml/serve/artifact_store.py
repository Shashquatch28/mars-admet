"""Deliver the trained XGBoost artifacts (`ml/artifacts/`, gitignored) to a machine that has no copy.

`ml/artifacts/` is about 200 MB and is not in git or in the image, so a Cloud Run revision starts with
none of it. This module is the delivery path: a developer publishes the tree to an S3-compatible
bucket (Cloudflare R2) once per release, and every API instance downloads and verifies that release
into its own disk before it takes traffic.

A release is immutable and named by the SHA-256 of its manifest:

    <prefix>/<release>/manifest.json       canonical JSON: every file's relative path, size and SHA-256
    <prefix>/<release>/files/<relpath>     the artifact files themselves

Because the release id is the digest of the manifest and the manifest lists every file's digest, a
release id pins the exact bytes. Deploying a different set of models is a different id in
`MODEL_ARTIFACT_RELEASE`; rolling back is putting the old id back.

Nothing here falls back to anything. A missing object, a digest that does not match, an endpoint
without a model, or a directory that already holds other files raises `ArtifactError`, and the caller
lets the process fail to start. Serving a stub because a download failed is exactly what this module
exists to prevent.

The module is standard library plus `mars_contracts`; the S3 client is passed in (a `boto3` client in
production, a fake in tests), so the logic is testable without a network.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from mars_contracts.endpoints import ENDPOINT_METADATA, ML_ENDPOINTS, TaskType

MANIFEST_SCHEMA = 1
MANIFEST_NAME = "manifest.json"
DEFAULT_PREFIX = "models"
DEFAULT_WORKERS = 8
_CHUNK = 1 << 20
_IGNORED_NAMES = {".gitkeep"}


class ArtifactError(RuntimeError):
    """The artifacts are not what the release says they are, or cannot be reached. Never swallowed."""


# --- hashing and the manifest ------------------------------------------------------------------ #
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_artifact(path: Path) -> bool:
    return path.is_file() and path.name not in _IGNORED_NAMES and not path.name.endswith(".part")


def iter_artifact_files(root: Path) -> list[str]:
    """Relative POSIX paths of every artifact file under `root`, sorted."""
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if _is_artifact(p))


def build_manifest(root: Path) -> dict[str, Any]:
    """Hash every file under `root`. The manifest is a plain dict; `manifest_bytes` is its one canonical encoding."""
    files = {rel: {"size": (root / rel).stat().st_size, "sha256": sha256_file(root / rel)} for rel in iter_artifact_files(root)}
    return {"schema": MANIFEST_SCHEMA, "files": files}


def manifest_bytes(manifest: dict[str, Any]) -> bytes:
    return json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")


def release_id(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(manifest_bytes(manifest)).hexdigest()


def _safe_relpath(rel: str) -> str:
    p = PurePosixPath(rel)
    if not rel or p.is_absolute() or ".." in p.parts or "\\" in rel or rel != p.as_posix():
        raise ArtifactError(f"manifest lists an unsafe path: {rel!r}")
    return rel


def parse_manifest(data: bytes, release: str) -> dict[str, Any]:
    """Decode a manifest and prove it is the one `release` names. Rejects paths that could leave the target directory."""
    digest = hashlib.sha256(data).hexdigest()
    if digest != release:
        raise ArtifactError(f"manifest digest {digest[:12]} does not match the release id {release[:12]}: the bucket was altered or the id is wrong")
    try:
        manifest = json.loads(data)
    except ValueError as exc:
        raise ArtifactError(f"manifest is not valid JSON: {exc}") from exc
    if manifest.get("schema") != MANIFEST_SCHEMA or not isinstance(manifest.get("files"), dict) or not manifest["files"]:
        raise ArtifactError("manifest has an unknown schema or lists no files")
    for rel, entry in manifest["files"].items():
        _safe_relpath(rel)
        if not (isinstance(entry.get("size"), int) and isinstance(entry.get("sha256"), str)):
            raise ArtifactError(f"manifest entry for {rel!r} has no size and sha256")
    return manifest


# --- the roster: is every endpoint actually servable? ------------------------------------------ #
def roster_problems(root: Path, *, kermt_regression: Iterable[str] = ()) -> dict[str, list[str]]:
    """What is missing, per endpoint, for all 14 ML endpoints to be served by a real model. Empty = complete.

    An endpoint needs at least one seed with `model.json` and `metadata.json`, its applicability-domain
    index, and the file its task type reads: a Platt calibrator (classification) or the held-out error
    band (regression; without it the row prints no interval). `kermt_regression` names the regression
    endpoints routed to KERMT, which also need `kermt_error_band.json`."""
    kermt_regression = set(kermt_regression)
    problems: dict[str, list[str]] = {}
    for endpoint in ML_ENDPOINTS:
        key = endpoint.value
        ep = root / key
        missing: list[str] = []
        seeds = sorted(d for d in ep.glob("seed_*") if d.is_dir()) if ep.is_dir() else []
        if not seeds:
            missing.append("no seed_* model directory")
        for seed in seeds:
            for name in ("model.json", "metadata.json"):
                if not (seed / name).is_file():
                    missing.append(f"{seed.name}/{name}")
        for name in ("metadata.json", "reference_fingerprints.npy"):
            if not (ep / "ad_index" / name).is_file():
                missing.append(f"ad_index/{name}")
        if ENDPOINT_METADATA[endpoint]["task_type"] == TaskType.CLASSIFICATION:
            if not (ep / "calibrator.json").is_file():
                missing.append("calibrator.json")
        elif not (ep / "error_band.json").is_file():
            missing.append("error_band.json")
        if key in kermt_regression and not (ep / "kermt_error_band.json").is_file():
            missing.append("kermt_error_band.json")
        if missing:
            problems[key] = missing
    return problems


def raise_for_roster(root: Path, *, kermt_regression: Iterable[str] = (), what: str = "model artifacts") -> None:
    problems = roster_problems(root, kermt_regression=kermt_regression)
    if problems:
        lines = "; ".join(f"{key}: {', '.join(items)}" for key, items in problems.items())
        raise ArtifactError(
            f"{what} under {root} do not cover every endpoint ({len(problems)} of {len(ML_ENDPOINTS)} incomplete): {lines}. "
            "Serving them would silently use the stub, so the service will not start."
        )


# --- bucket layout ------------------------------------------------------------------------------ #
def _key(prefix: str, release: str, *parts: str) -> str:
    return "/".join(p for p in (prefix.strip("/"), release, *parts) if p)


def manifest_key(prefix: str, release: str) -> str:
    return _key(prefix, release, MANIFEST_NAME)


def file_key(prefix: str, release: str, rel: str) -> str:
    return _key(prefix, release, "files", rel)


# --- publish ------------------------------------------------------------------------------------ #
@dataclass
class PublishResult:
    release: str
    files: int
    total_bytes: int
    uploaded: int = 0
    skipped: int = 0
    problems: dict[str, list[str]] = field(default_factory=dict)


def publish(
    client: Any,
    bucket: str,
    root: Path,
    *,
    prefix: str = DEFAULT_PREFIX,
    dry_run: bool = False,
    allow_incomplete: bool = False,
    workers: int = DEFAULT_WORKERS,
    log: Callable[[str], None] = lambda _msg: None,
) -> PublishResult:
    """Upload `root` as a new release and return its id. `client` may be None only for a dry run.

    Refuses a tree that does not cover all 14 endpoints unless `allow_incomplete` (a deployed service
    refuses it at start-up anyway). Files go first and `manifest.json` last, so a release whose
    manifest exists is complete; an object already present with the same size is not re-sent."""
    if not root.is_dir():
        raise ArtifactError(f"{root} is not a directory")
    problems = roster_problems(root)
    if problems and not allow_incomplete:
        lines = "; ".join(f"{key}: {', '.join(items)}" for key, items in problems.items())
        raise ArtifactError(f"refusing to publish an incomplete tree: {lines}")
    manifest = build_manifest(root)
    release = release_id(manifest)
    result = PublishResult(release, len(manifest["files"]), sum(e["size"] for e in manifest["files"].values()), problems=problems)
    log(f"release {release}: {result.files} files, {result.total_bytes / 1e6:.1f} MB")
    if dry_run:
        return result
    if client is None:
        raise ArtifactError("no S3 client: only a dry run may omit it")

    def send(item: tuple[str, dict]) -> bool:
        rel, entry = item
        key = file_key(prefix, release, rel)
        try:
            head = client.head_object(Bucket=bucket, Key=key)
            if int(head.get("ContentLength", -1)) == entry["size"] and (head.get("Metadata") or {}).get("sha256") == entry["sha256"]:
                return False
        except Exception as exc:  # absent object: upload it
            if not _is_not_found(exc):
                raise
        with (root / rel).open("rb") as fh:
            client.put_object(Bucket=bucket, Key=key, Body=fh, ContentLength=entry["size"], Metadata={"sha256": entry["sha256"]})
        return True

    with ThreadPoolExecutor(max_workers=workers) as pool:
        sent = list(pool.map(send, sorted(manifest["files"].items())))
    result.uploaded, result.skipped = sum(sent), len(sent) - sum(sent)
    client.put_object(
        Bucket=bucket, Key=manifest_key(prefix, release), Body=manifest_bytes(manifest), ContentType="application/json"
    )
    log(f"uploaded {result.uploaded}, already present {result.skipped}; manifest written last")
    return result


def _is_not_found(exc: Exception) -> bool:
    code = str(getattr(exc, "response", {}).get("Error", {}).get("Code", ""))
    return code in {"404", "NoSuchKey", "NotFound"} or type(exc).__name__ in {"NoSuchKey", "NotFound"}


def check_remote(client: Any, bucket: str, release: str, *, prefix: str = DEFAULT_PREFIX) -> list[str]:
    """Problems with a published release without downloading it: the manifest must match its id and every
    object must exist with the recorded size. Empty list = the release is intact."""
    try:
        data = client.get_object(Bucket=bucket, Key=manifest_key(prefix, release))["Body"].read()
        manifest = parse_manifest(data, release)
    except ArtifactError as exc:
        return [str(exc)]
    except Exception as exc:
        return [f"manifest unreadable: {type(exc).__name__}: {exc}"]
    bad: list[str] = []
    for rel, entry in manifest["files"].items():
        try:
            head = client.head_object(Bucket=bucket, Key=file_key(prefix, release, rel))
            if int(head["ContentLength"]) != entry["size"]:
                bad.append(f"{rel}: size {head['ContentLength']} != {entry['size']}")
        except Exception as exc:
            bad.append(f"{rel}: {type(exc).__name__}")
    return bad


# --- fetch -------------------------------------------------------------------------------------- #
@dataclass
class FetchReport:
    release: str
    files: int
    total_bytes: int
    downloaded: int
    kept: int


def _download(client: Any, bucket: str, key: str, target: Path, entry: dict) -> None:
    """Stream one object to a temp file beside `target`, verify size and SHA-256, then move it into place."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.part")
    h, size = hashlib.sha256(), 0
    try:
        body = client.get_object(Bucket=bucket, Key=key)["Body"]
        with tmp.open("wb") as fh:
            for chunk in iter(lambda: body.read(_CHUNK), b""):
                fh.write(chunk)
                h.update(chunk)
                size += len(chunk)
        if size != entry["size"] or h.hexdigest() != entry["sha256"]:
            raise ArtifactError(f"{key}: downloaded {size} bytes with sha256 {h.hexdigest()[:12]}, the release says {entry['size']} bytes and {entry['sha256'][:12]}")
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)


def fetch(
    client: Any,
    bucket: str,
    release: str,
    dest: Path,
    *,
    prefix: str = DEFAULT_PREFIX,
    workers: int = DEFAULT_WORKERS,
    kermt_regression: Iterable[str] = (),
    log: Callable[[str], None] = lambda _msg: None,
) -> FetchReport:
    """Make `dest` hold exactly release `release`, verified, and prove it covers all 14 endpoints.

    `dest` must be empty or already hold files of this release; any other file, or a same-named file with
    different bytes, raises instead of being overwritten, so pointing this at a directory of hand-trained
    artifacts can never destroy them. Files that already match are kept (hash-checked). Every error
    names the object or endpoint at fault."""
    try:
        data = client.get_object(Bucket=bucket, Key=manifest_key(prefix, release))["Body"].read()
    except Exception as exc:
        raise ArtifactError(f"cannot read release {release[:12]} from bucket {bucket!r} under {prefix!r}: {type(exc).__name__}: {exc}") from exc
    manifest = parse_manifest(data, release)
    files: dict[str, dict] = manifest["files"]

    dest.mkdir(parents=True, exist_ok=True)
    extra = [rel for rel in iter_artifact_files(dest) if rel not in files]
    if extra:
        raise ArtifactError(f"{dest} already holds {len(extra)} file(s) that are not in release {release[:12]} (first: {extra[0]}); refusing to mix. Use an empty directory.")
    for part in dest.rglob("*.part"):
        part.unlink(missing_ok=True)

    todo: list[str] = []
    for rel, entry in files.items():
        local = dest / rel
        if local.is_file():
            if local.stat().st_size != entry["size"] or sha256_file(local) != entry["sha256"]:
                raise ArtifactError(f"{local} exists with different bytes from release {release[:12]}; refusing to overwrite. Use an empty directory.")
        else:
            todo.append(rel)

    def get(rel: str) -> None:
        _download(client, bucket, file_key(prefix, release, rel), dest / rel, files[rel])

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for future in [pool.submit(get, rel) for rel in todo]:
            future.result()  # first failure propagates, naming its object

    raise_for_roster(dest, kermt_regression=kermt_regression, what=f"release {release[:12]}")
    report = FetchReport(release, len(files), sum(e["size"] for e in files.values()), len(todo), len(files) - len(todo))
    log(f"release {release[:12]} ready in {dest}: {report.files} files, {report.total_bytes / 1e6:.1f} MB ({report.downloaded} downloaded, {report.kept} already present)")
    return report
