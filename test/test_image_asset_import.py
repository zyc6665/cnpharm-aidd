import hashlib
import gzip
import json
import tarfile
from io import BytesIO
from pathlib import Path

import pytest
from sqlalchemy import UniqueConstraint

from app.models.image_assets import ImageAsset
from app.services import image_asset_import
from app.services.image_asset_import import ImageArchiveError, import_docker_save


def _docker_save(
    path: Path,
    *,
    symlink: bool = False,
    directories: tuple[str, ...] = (),
) -> None:
    config = b'{"architecture":"amd64","os":"linux","rootfs":{"type":"layers","diff_ids":[]}}'
    layer = b"layer contents\n"
    config_name = f"{hashlib.sha256(config).hexdigest()}.json"
    manifest = [{"Config": config_name, "RepoTags": ["example:1"], "Layers": ["layer.tar"]}]
    with tarfile.open(path, "w") as archive:
        for name in directories:
            info = tarfile.TarInfo(name)
            info.type = tarfile.DIRTYPE
            archive.addfile(info)
        for name, content in (
            ("manifest.json", json.dumps(manifest).encode()),
            (config_name, config),
            ("layer.tar", layer),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, __import__("io").BytesIO(content))
        if symlink:
            info = tarfile.TarInfo("bad")
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            archive.addfile(info)


def test_load_docker_save_accepts_safe_directory_entries(tmp_path):
    archive = tmp_path / "image.tar"
    _docker_save(archive, directories=("blobs/", "blobs/sha256/"))

    item, files = image_asset_import._load_archive(archive, tmp_path / "layers")

    assert item["RepoTags"] == ["example:1"]
    assert set(item["Layers"]).issubset(files)


def test_prepare_archive_for_random_access_decompresses_gzip_once(tmp_path):
    source = tmp_path / "image.tar"
    _docker_save(source)
    compressed = tmp_path / "image.tar.gz"
    with source.open("rb") as input_stream, gzip.open(compressed, "wb") as output_stream:
        output_stream.write(input_stream.read())

    prepared = image_asset_import._prepare_archive_for_random_access(
        compressed,
        tmp_path / "work",
    )

    assert prepared != compressed
    assert prepared.is_file()
    assert prepared.read_bytes() == source.read_bytes()


@pytest.mark.asyncio
async def test_import_docker_save_pushes_manifest(monkeypatch, tmp_path):
    source = tmp_path / "image.tar"
    _docker_save(source)
    archive = tmp_path / "image.tar.gz"
    with source.open("rb") as input_stream, gzip.open(archive, "wb") as output_stream:
        output_stream.write(input_stream.read())
    pushed = []

    class FakeClient:
        def __init__(self, *args):
            pass

        async def ensure_blob(self, repository, digest, path):
            pushed.append((repository, digest, path.name))

        async def put_manifest(self, repository, tag, manifest):
            pushed.append((repository, tag, json.loads(manifest)))
            return "sha256:" + "a" * 64

    monkeypatch.setattr(image_asset_import, "RegistryClient", FakeClient)
    payload = archive.read_bytes()
    result = await import_docker_save(
        archive,
        repository="sciminer/example",
        tag="1.0.0",
        archive_sha256=hashlib.sha256(payload).hexdigest(),
        archive_size_bytes=len(payload),
    )

    assert result["manifest_digest"] == "sha256:" + "a" * 64
    assert len(pushed) == 3
    assert pushed[-1][1] == "1.0.0"


@pytest.mark.asyncio
async def test_import_oci_archive_pushes_manifest(monkeypatch, tmp_path):
    config = b'{"architecture":"amd64","os":"linux","rootfs":{"type":"layers","diff_ids":[]}}'
    layer = b"oci layer contents\n"
    config_digest = hashlib.sha256(config).hexdigest()
    layer_digest = hashlib.sha256(layer).hexdigest()
    manifest = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "config": {
            "mediaType": "application/vnd.oci.image.config.v1+json",
            "digest": f"sha256:{config_digest}",
            "size": len(config),
        },
        "layers": [{
            "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
            "digest": f"sha256:{layer_digest}",
            "size": len(layer),
        }],
    }
    manifest_bytes = json.dumps(manifest, separators=(",", ":")).encode()
    manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
    index = {
        "schemaVersion": 2,
        "manifests": [{
            "mediaType": manifest["mediaType"],
            "digest": f"sha256:{manifest_digest}",
            "size": len(manifest_bytes),
            "platform": {"architecture": "amd64", "os": "linux"},
        }],
    }
    archive = tmp_path / "image-oci.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        for name, content in (
            ("oci-layout", b'{"imageLayoutVersion":"1.0.0"}'),
            ("index.json", json.dumps(index).encode()),
            (f"blobs/sha256/{manifest_digest}", manifest_bytes),
            (f"blobs/sha256/{config_digest}", config),
            (f"blobs/sha256/{layer_digest}", layer),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(content)
            output.addfile(info, BytesIO(content))

    pushed = []

    class FakeClient:
        def __init__(self, *args):
            pass

        async def ensure_blob(self, repository, digest, path):
            pushed.append((repository, digest, path.name))

        async def put_manifest(self, repository, tag, manifest, media_type):
            pushed.append((repository, tag, json.loads(manifest), media_type))
            return f"sha256:{manifest_digest}"

    monkeypatch.setattr(image_asset_import, "RegistryClient", FakeClient)
    monkeypatch.setattr(
        image_asset_import.settings,
        "IMAGE_REGISTRY_IMAGE_PREFIX",
        "10.202.2.228:30500/sciminer/",
    )
    payload = archive.read_bytes()
    result = await image_asset_import.import_image_archive(
        archive,
        repository="sciminer/oci-example",
        tag="1.0.0",
        archive_sha256=hashlib.sha256(payload).hexdigest(),
        archive_size_bytes=len(payload),
    )

    assert result["manifest_digest"] == f"sha256:{manifest_digest}"
    assert result["image_reference"] == (
        "10.202.2.228:30500/sciminer/oci-example:1.0.0@"
        f"sha256:{manifest_digest}"
    )
    assert len(pushed) == 3
    assert pushed[-1][3] == "application/vnd.oci.image.manifest.v1+json"


def test_import_rejects_symlink_and_external_repository(tmp_path):
    archive = tmp_path / "bad.tar"
    _docker_save(archive, symlink=True)
    with pytest.raises(ImageArchiveError, match="不安全"):
        image_asset_import._load_archive(archive, tmp_path / "extract")

    with pytest.raises(ImageArchiveError, match="允许的前缀"):
        image_asset_import._validate_repository("docker.io/example")


def test_image_asset_identity_is_repository_and_tag():
    unique_constraints = [
        constraint
        for constraint in ImageAsset.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    ]

    assert len(unique_constraints) == 1
    assert {column.name for column in unique_constraints[0].columns} == {
        "repository",
        "tag",
    }
