"""Start-up delivery of the trained models (ship checklist C7): the settings glue around `serve.artifact_store`,
and that a bad delivery stops the service instead of letting it serve the stub."""

from __future__ import annotations

import asyncio
import io
import json
import sys
from pathlib import Path

import pytest
from app.core.config import Settings
from app.services import model_artifacts

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ml"))
from mars_contracts.endpoints import ENDPOINT_METADATA, ML_ENDPOINTS, TaskType  # noqa: E402
from serve import artifact_store as store  # noqa: E402

BUCKET = "mars-models"


class NotFound(Exception):
    response = {"Error": {"Code": "404"}}


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, dict]] = {}

    def put_object(self, *, Bucket, Key, Body, Metadata=None, **_kw):
        self.objects[Key] = (Body.read() if hasattr(Body, "read") else Body, dict(Metadata or {}))

    def get_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise NotFound(Key)
        return {"Body": io.BytesIO(self.objects[Key][0])}

    def head_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise NotFound(Key)
        data, meta = self.objects[Key]
        return {"ContentLength": len(data), "Metadata": meta}


def make_tree(root: Path) -> Path:
    for ep in ML_ENDPOINTS:
        files = {"seed_0/model.json": "m", "seed_0/metadata.json": json.dumps({"seed": 0}), "ad_index/metadata.json": "{}", "ad_index/reference_fingerprints.npy": "f"}
        files["calibrator.json" if ENDPOINT_METADATA[ep]["task_type"] == TaskType.CLASSIFICATION else "error_band.json"] = "{}"
        for rel, text in files.items():
            path = root / ep.value / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    return root


def settings(tmp_path, **overrides) -> Settings:
    return Settings(model_artifact_dir=str(tmp_path / "served"), _env_file=None, **overrides)


def published(tmp_path) -> tuple[FakeS3, str]:
    client = FakeS3()
    return client, store.publish(client, BUCKET, make_tree(tmp_path / "src")).release


def test_nothing_is_fetched_without_a_bucket(tmp_path):
    assert model_artifacts.ensure_model_artifacts(settings(tmp_path)) is None
    assert not (tmp_path / "served").exists()


def test_a_bucket_without_a_release_is_an_error(tmp_path):
    with pytest.raises(store.ArtifactError, match="MODEL_ARTIFACT_RELEASE"):
        model_artifacts.ensure_model_artifacts(settings(tmp_path, model_artifact_bucket=BUCKET), client=FakeS3())


def test_the_release_is_downloaded_into_the_artifact_dir(tmp_path):
    client, release = published(tmp_path)
    cfg = settings(tmp_path, model_artifact_bucket=BUCKET, model_artifact_release=release)
    report = model_artifacts.ensure_model_artifacts(cfg, client=client)
    assert report.release == release and report.downloaded == report.files
    assert store.roster_problems(tmp_path / "served") == {}


def test_a_bad_release_id_stops_start_up_with_a_message(tmp_path):
    client, _ = published(tmp_path)
    cfg = settings(tmp_path, model_artifact_bucket=BUCKET, model_artifact_release="0" * 64)
    with pytest.raises(store.ArtifactError, match="cannot read release"):
        model_artifacts.ensure_model_artifacts(cfg, client=client)


def test_strict_mode_without_a_bucket_names_the_missing_endpoints(tmp_path):
    (tmp_path / "served").mkdir()
    with pytest.raises(RuntimeError) as err:  # ArtifactError, or the ml-stack error in an environment without rdkit
        model_artifacts.ensure_model_artifacts(settings(tmp_path, require_real_models=True))
    assert "ml stack" in str(err.value) or "solubility_logs" in str(err.value)


def test_the_app_refuses_to_start_when_the_release_cannot_be_delivered(tmp_path, monkeypatch):
    """The lifespan is what the platform runs: an exception there means the revision never becomes ready."""
    from app import main
    from app.core.config import get_settings

    monkeypatch.setenv("MODEL_ARTIFACT_BUCKET", BUCKET)
    monkeypatch.setenv("MODEL_ARTIFACT_RELEASE", "")
    monkeypatch.setenv("MODEL_ARTIFACT_DIR", str(tmp_path / "served"))
    get_settings.cache_clear()
    try:
        async def start():
            async with main.lifespan(main.app):
                pass

        with pytest.raises(store.ArtifactError):
            asyncio.run(start())
    finally:
        get_settings.cache_clear()


def test_the_model_bucket_can_use_its_own_read_only_key(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(model_artifacts, "make_s3_client", lambda s, **kw: seen.update(kw) or FakeS3())
    cfg = settings(tmp_path, model_artifact_bucket=BUCKET, model_artifact_release="0" * 64,
                   model_artifact_access_key_id="ro-key", model_artifact_secret_access_key="ro-secret")
    with pytest.raises(store.ArtifactError):
        model_artifacts.ensure_model_artifacts(cfg)
    assert seen == {"access_key_id": "ro-key", "secret_access_key": "ro-secret"}
