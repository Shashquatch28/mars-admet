"""Delivery of trained artifacts to a machine with none (ship checklist C7): publish a release, fetch it,
and prove every way it can go wrong fails loudly instead of serving something else."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from mars_contracts.endpoints import ENDPOINT_METADATA, ML_ENDPOINTS, TaskType
from serve import artifact_store as store
from serve.artifact_store import ArtifactError

BUCKET = "mars-models"


class FakeNotFound(Exception):
    response = {"Error": {"Code": "404"}}


class FakeS3:
    """The four calls the store makes, over a dict."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, dict]] = {}
        self.puts = 0

    def put_object(self, *, Bucket, Key, Body, Metadata=None, **_kw):
        data = Body.read() if hasattr(Body, "read") else Body
        self.objects[Key] = (data, dict(Metadata or {}))
        self.puts += 1

    def get_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise FakeNotFound(Key)
        return {"Body": io.BytesIO(self.objects[Key][0])}

    def head_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise FakeNotFound(Key)
        data, meta = self.objects[Key]
        return {"ContentLength": len(data), "Metadata": meta}


def make_tree(root: Path, *, skip: tuple[str, ...] = ()) -> Path:
    """A minimal artifact tree that satisfies the roster for all 14 ML endpoints. `skip` drops one relative path."""
    for ep in ML_ENDPOINTS:
        key = ep.value
        files = {
            f"{key}/seed_0/model.json": f"model-{key}-0",
            f"{key}/seed_0/metadata.json": json.dumps({"seed": 0}),
            f"{key}/seed_1/model.json": f"model-{key}-1",
            f"{key}/seed_1/metadata.json": json.dumps({"seed": 1}),
            f"{key}/ad_index/metadata.json": "{}",
            f"{key}/ad_index/reference_fingerprints.npy": f"fp-{key}",
        }
        if ENDPOINT_METADATA[ep]["task_type"] == TaskType.CLASSIFICATION:
            files[f"{key}/calibrator.json"] = "{}"
        else:
            files[f"{key}/error_band.json"] = "{}"
        for rel, text in files.items():
            if rel in skip:
                continue
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    return root


@pytest.fixture
def tree(tmp_path) -> Path:
    return make_tree(tmp_path / "artifacts")


@pytest.fixture
def published(tree):
    client = FakeS3()
    result = store.publish(client, BUCKET, tree)
    return client, result


# --- roster ------------------------------------------------------------------------------------- #
def test_complete_tree_has_no_problems(tree):
    assert store.roster_problems(tree) == {}


def test_a_missing_endpoint_is_named(tmp_path):
    tree = make_tree(tmp_path / "a", skip=("herg_cardiotoxicity/seed_0/model.json",))
    problems = store.roster_problems(tree)
    assert list(problems) == ["herg_cardiotoxicity"]
    assert "seed_0/model.json" in problems["herg_cardiotoxicity"]
    with pytest.raises(ArtifactError, match="herg_cardiotoxicity"):
        store.raise_for_roster(tree)


def test_classification_needs_a_calibrator_and_regression_an_error_band(tmp_path):
    tree = make_tree(tmp_path / "a", skip=("ames_mutagenicity/calibrator.json", "caco2_permeability/error_band.json"))
    problems = store.roster_problems(tree)
    assert problems["ames_mutagenicity"] == ["calibrator.json"]
    assert problems["caco2_permeability"] == ["error_band.json"]


def test_kermt_regression_endpoints_also_need_the_kermt_band(tree):
    assert store.roster_problems(tree, kermt_regression=["clearance_microsomal"]) == {"clearance_microsomal": ["kermt_error_band.json"]}
    (tree / "clearance_microsomal" / "kermt_error_band.json").write_text("{}")
    assert store.roster_problems(tree, kermt_regression=["clearance_microsomal"]) == {}


def test_an_empty_directory_misses_all_fourteen(tmp_path):
    assert len(store.roster_problems(tmp_path)) == 14


# --- manifest and release id -------------------------------------------------------------------- #
def test_release_id_is_deterministic_and_tracks_every_byte(tree, tmp_path):
    first = store.release_id(store.build_manifest(tree))
    assert first == store.release_id(store.build_manifest(tree))
    (tree / "ames_mutagenicity" / "seed_0" / "model.json").write_text("changed")
    assert store.release_id(store.build_manifest(tree)) != first


def test_gitkeep_and_part_files_are_not_artifacts(tree):
    (tree / ".gitkeep").write_text("")
    (tree / "x.json.part").write_text("half")
    assert not any(r.endswith(".part") or r == ".gitkeep" for r in store.build_manifest(tree)["files"])


def test_parse_manifest_rejects_a_tampered_manifest(tree):
    manifest = store.build_manifest(tree)
    release = store.release_id(manifest)
    tampered = store.manifest_bytes({**manifest, "files": {**manifest["files"], "evil": {"size": 1, "sha256": "0" * 64}}})
    with pytest.raises(ArtifactError, match="does not match the release id"):
        store.parse_manifest(tampered, release)


@pytest.mark.parametrize("rel", ["../outside.json", "/etc/passwd", "a/../../b", "a\\b", ""])
def test_parse_manifest_rejects_paths_that_could_leave_the_directory(rel):
    manifest = {"schema": 1, "files": {rel: {"size": 1, "sha256": "0" * 64}}}
    data = store.manifest_bytes(manifest)
    with pytest.raises(ArtifactError, match="unsafe path"):
        store.parse_manifest(data, store.release_id(manifest))


# --- publish ------------------------------------------------------------------------------------ #
def test_dry_run_needs_no_client_and_uploads_nothing(tree):
    result = store.publish(None, BUCKET, tree, dry_run=True)
    assert result.files == len(store.iter_artifact_files(tree)) and result.uploaded == 0


def test_publish_refuses_an_incomplete_tree(tmp_path):
    tree = make_tree(tmp_path / "a", skip=("ppb_binding/error_band.json",))
    with pytest.raises(ArtifactError, match="ppb_binding"):
        store.publish(FakeS3(), BUCKET, tree)


def test_publish_writes_the_manifest_last_and_resending_is_a_no_op(tree):
    client = FakeS3()
    order: list[str] = []
    original = client.put_object
    client.put_object = lambda **kw: (order.append(kw["Key"]), original(**kw))[1]
    first = store.publish(client, BUCKET, tree)
    assert order[-1].endswith("/manifest.json") and first.uploaded == first.files
    puts = client.puts
    again = store.publish(client, BUCKET, tree)
    assert again.release == first.release and again.uploaded == 0 and again.skipped == again.files
    assert client.puts == puts + 1  # only the manifest is rewritten
    assert store.check_remote(client, BUCKET, first.release) == []


def test_check_remote_finds_a_missing_object(published):
    client, result = published
    victim = next(k for k in client.objects if "/files/" in k)
    del client.objects[victim]
    assert any(victim.split("/files/")[1] in problem for problem in store.check_remote(client, BUCKET, result.release))


# --- fetch -------------------------------------------------------------------------------------- #
def test_fetch_reproduces_the_tree_byte_for_byte(published, tree, tmp_path):
    client, result = published
    dest = tmp_path / "served"
    report = store.fetch(client, BUCKET, result.release, dest)
    assert report.downloaded == result.files and report.kept == 0
    assert store.build_manifest(dest) == store.build_manifest(tree)
    assert store.roster_problems(dest) == {}
    assert not list(dest.rglob("*.part"))


def test_a_second_fetch_into_the_same_directory_downloads_nothing(published, tmp_path):
    client, result = published
    dest = tmp_path / "served"
    store.fetch(client, BUCKET, result.release, dest)
    again = store.fetch(client, BUCKET, result.release, dest)
    assert again.downloaded == 0 and again.kept == result.files


def test_a_corrupted_object_fails_and_names_it(published, tmp_path):
    client, result = published
    key = next(k for k in client.objects if k.endswith("cyp2d6_inhibition/seed_1/model.json"))
    client.objects[key] = (b"tampered-bytes", client.objects[key][1])
    dest = tmp_path / "served"
    with pytest.raises(ArtifactError, match="cyp2d6_inhibition/seed_1/model.json"):
        store.fetch(client, BUCKET, result.release, dest)
    assert not (dest / "cyp2d6_inhibition" / "seed_1" / "model.json").exists()
    assert not list(dest.rglob("*.part"))


def test_a_missing_object_fails(published, tmp_path):
    client, result = published
    del client.objects[next(k for k in client.objects if k.endswith("hia_absorption/calibrator.json"))]
    with pytest.raises(Exception, match="hia_absorption/calibrator.json"):
        store.fetch(client, BUCKET, result.release, tmp_path / "served")


def test_an_unknown_release_fails_with_a_clear_message(published, tmp_path):
    client, _ = published
    with pytest.raises(ArtifactError, match="cannot read release"):
        store.fetch(client, BUCKET, "f" * 64, tmp_path / "served")


def test_a_swapped_manifest_is_refused(published, tmp_path):
    client, result = published
    key = next(k for k in client.objects if k.endswith("/manifest.json"))
    client.objects[key] = (client.objects[key][0] + b" ", client.objects[key][1])
    with pytest.raises(ArtifactError, match="does not match the release id"):
        store.fetch(client, BUCKET, result.release, tmp_path / "served")


def test_a_release_that_misses_an_endpoint_fails_naming_it(tmp_path):
    incomplete = make_tree(tmp_path / "a", skip=("bbb_permeability/ad_index/reference_fingerprints.npy",))
    client = FakeS3()
    result = store.publish(client, BUCKET, incomplete, allow_incomplete=True)
    with pytest.raises(ArtifactError, match="bbb_permeability: ad_index/reference_fingerprints.npy"):
        store.fetch(client, BUCKET, result.release, tmp_path / "served")


def test_fetch_never_mixes_into_a_directory_that_holds_other_files(published, tmp_path):
    client, result = published
    dest = tmp_path / "served"
    (dest / "ames_mutagenicity").mkdir(parents=True)
    (dest / "ames_mutagenicity" / "seed_9.json").write_text("hand-trained")
    with pytest.raises(ArtifactError, match="not in release"):
        store.fetch(client, BUCKET, result.release, dest)
    assert (dest / "ames_mutagenicity" / "seed_9.json").read_text() == "hand-trained"


def test_fetch_never_overwrites_a_same_named_file_with_different_bytes(published, tmp_path):
    client, result = published
    dest = tmp_path / "served"
    victim = dest / "ames_mutagenicity" / "seed_0" / "model.json"
    victim.parent.mkdir(parents=True)
    victim.write_text("my own model")
    with pytest.raises(ArtifactError, match="different bytes"):
        store.fetch(client, BUCKET, result.release, dest)
    assert victim.read_text() == "my own model"


def test_fetch_with_a_matching_local_tree_is_accepted(published, tree):
    """The docker-compose bind mount: the directory already is the release, so nothing is downloaded."""
    client, result = published
    report = store.fetch(client, BUCKET, result.release, tree)
    assert report.downloaded == 0
