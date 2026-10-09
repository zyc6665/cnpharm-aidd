"""校验 Docker/OCI 镜像归档并导入内部 Registry。"""

import hashlib
import gzip
import json
import re
import shutil
import tarfile
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from app.config import settings
from app.registry.client import RegistryClient


class ImageArchiveError(ValueError):
    """镜像归档不符合平台导入契约。"""


_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_TAG_RE = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,127}$")
_MAX_ARCHIVE_MEMBERS = 100000
_MAX_METADATA_BLOB_BYTES = 16 * 1024 * 1024


def _digest_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _safe_member(member: tarfile.TarInfo, *, allow_directory: bool = False) -> None:
    path = PurePosixPath(member.name)
    if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
        raise ImageArchiveError("镜像归档包含不安全路径或链接")
    if allow_directory and member.isdir():
        return
    if not member.isfile():
        raise ImageArchiveError("镜像归档只能包含普通文件")


def _read_member(stream) -> bytes:
    chunks: list[bytes] = []
    while chunk := stream.read(1024 * 1024):
        chunks.append(chunk)
    return b"".join(chunks)


def _discard_member(stream) -> None:
    while stream.read(1024 * 1024):
        pass


def _prepare_archive_for_random_access(archive_path: Path, work_dir: Path) -> Path:
    try:
        with archive_path.open("rb") as source:
            is_gzip = source.read(2) == b"\x1f\x8b"
    except OSError as exc:
        raise ImageArchiveError("无法读取镜像归档") from exc
    if not is_gzip:
        return archive_path

    work_dir.mkdir(parents=True, exist_ok=True)
    prepared_path = work_dir / "image.tar"
    try:
        with gzip.open(archive_path, "rb") as source, prepared_path.open("wb") as target:
            shutil.copyfileobj(source, target, length=8 * 1024 * 1024)
    except (OSError, EOFError) as exc:
        prepared_path.unlink(missing_ok=True)
        raise ImageArchiveError("无法解压镜像归档") from exc
    return prepared_path


def _validate_repository(repository: str) -> None:
    if not re.fullmatch(
        r"[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*",
        repository,
    ):
        raise ImageArchiveError("repository 格式无效")
    prefix = settings.IMAGE_IMPORT_ALLOWED_REPOSITORY_PREFIX.strip("/")
    if prefix and not (repository == prefix or repository.startswith(prefix + "/")):
        raise ImageArchiveError("repository 不在平台允许的前缀下")


def _build_image_reference(repository: str, tag: str, digest: str) -> str:
    prefix = settings.IMAGE_REGISTRY_IMAGE_PREFIX.rstrip("/")
    normalized_repository = repository.strip("/")
    prefix_path = prefix.split("/", 1)[1] if "/" in prefix else ""
    if prefix_path and (
        normalized_repository == prefix_path
        or normalized_repository.startswith(f"{prefix_path}/")
    ):
        normalized_repository = normalized_repository[len(prefix_path) :].lstrip("/")
    return f"{prefix}/{normalized_repository}:{tag}@{digest}"


def _load_archive(archive_path: Path, work_dir: Path) -> tuple[dict, dict[str, Path]]:
    try:
        with tarfile.open(archive_path, mode="r:*") as archive:
            members = archive.getmembers()
            if not members or len(members) > _MAX_ARCHIVE_MEMBERS:
                raise ImageArchiveError("镜像归档为空或文件数量超限")
            for member in members:
                _safe_member(member, allow_directory=True)
            manifest_member = next((m for m in members if m.name == "manifest.json"), None)
            if manifest_member is None:
                raise ImageArchiveError("docker save 归档缺少 manifest.json")
            manifest_stream = archive.extractfile(manifest_member)
            if manifest_stream is None:
                raise ImageArchiveError("无法读取 docker save manifest.json")
            manifest = json.loads(manifest_stream.read())
            if not isinstance(manifest, list) or len(manifest) != 1:
                raise ImageArchiveError("只支持单镜像 docker save 归档")
            item = manifest[0]
            config_name = item.get("Config")
            layers = item.get("Layers")
            if not isinstance(config_name, str) or not isinstance(layers, list) or not layers:
                raise ImageArchiveError("docker save manifest 缺少 config 或 layers")
            wanted = [config_name, *layers]
            extracted: dict[str, Path] = {}
            members_by_name = {m.name: m for m in members}
            for name in wanted:
                member = members_by_name.get(name)
                if member is None:
                    raise ImageArchiveError(f"归档缺少文件: {name}")
                target = work_dir / name
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise ImageArchiveError(f"无法读取归档文件: {name}")
                with source, target.open("wb") as output:
                    while chunk := source.read(1024 * 1024):
                        output.write(chunk)
                extracted[name] = target
            return item, extracted
    except ImageArchiveError:
        raise
    except (tarfile.TarError, OSError, json.JSONDecodeError) as exc:
        raise ImageArchiveError(f"无法读取 docker save 归档: {exc}") from exc


def _load_oci_archive(
    archive_path: Path,
    work_dir: Path,
) -> tuple[dict, dict[str, Path], bytes, str]:
    """Extract one OCI image manifest, config, and layers from an OCI tar archive."""
    index_bytes: bytes | None = None
    small_blobs: dict[str, bytes] = {}
    member_count = 0
    try:
        with tarfile.open(archive_path, mode="r|*") as archive:
            for member in archive:
                member_count += 1
                if member_count > _MAX_ARCHIVE_MEMBERS:
                    raise ImageArchiveError("镜像归档文件数量超限")
                _safe_member(member, allow_directory=True)
                if member.isdir():
                    continue
                stream = archive.extractfile(member)
                if stream is None:
                    raise ImageArchiveError(f"无法读取 OCI 文件: {member.name}")
                if member.name == "index.json":
                    index_bytes = _read_member(stream)
                elif member.name.startswith("blobs/sha256/") and member.size <= _MAX_METADATA_BLOB_BYTES:
                    small_blobs[member.name] = _read_member(stream)
                else:
                    _discard_member(stream)
    except ImageArchiveError:
        raise
    except (tarfile.TarError, OSError) as exc:
        raise ImageArchiveError(f"无法读取 OCI 镜像归档: {exc}") from exc

    if index_bytes is None:
        raise ImageArchiveError("OCI 归档缺少 index.json")
    try:
        index = json.loads(index_bytes)
    except json.JSONDecodeError as exc:
        raise ImageArchiveError("OCI index.json 不是有效 JSON") from exc
    manifests = index.get("manifests") if isinstance(index, dict) else None
    if not isinstance(manifests, list) or len(manifests) != 1:
        raise ImageArchiveError("只支持单镜像 OCI 归档")
    descriptor = manifests[0]
    manifest_digest = descriptor.get("digest") if isinstance(descriptor, dict) else None
    if not isinstance(manifest_digest, str) or not _DIGEST_RE.fullmatch(manifest_digest):
        raise ImageArchiveError("OCI manifest digest 无效")
    manifest_name = f"blobs/sha256/{manifest_digest.removeprefix('sha256:')}"
    manifest_bytes = small_blobs.get(manifest_name)
    if manifest_bytes is None or hashlib.sha256(manifest_bytes).hexdigest() != manifest_digest.removeprefix("sha256:"):
        raise ImageArchiveError("OCI manifest 缺失或摘要不匹配")
    try:
        manifest = json.loads(manifest_bytes)
    except json.JSONDecodeError as exc:
        raise ImageArchiveError("OCI manifest 不是有效 JSON") from exc

    config_descriptor = manifest.get("config") if isinstance(manifest, dict) else None
    raw_layers = manifest.get("layers") if isinstance(manifest, dict) else None
    if not isinstance(config_descriptor, dict) or not isinstance(raw_layers, list) or not raw_layers:
        raise ImageArchiveError("OCI manifest 缺少 config 或 layers")
    config_digest = config_descriptor.get("digest")
    if not isinstance(config_digest, str) or not _DIGEST_RE.fullmatch(config_digest):
        raise ImageArchiveError("OCI config digest 无效")
    config_name = f"blobs/sha256/{config_digest.removeprefix('sha256:')}"
    config_bytes = small_blobs.get(config_name)
    if config_bytes is None or hashlib.sha256(config_bytes).hexdigest() != config_digest.removeprefix("sha256:"):
        raise ImageArchiveError("OCI config 缺失或摘要不匹配")
    try:
        config = json.loads(config_bytes)
    except json.JSONDecodeError as exc:
        raise ImageArchiveError("OCI config 不是有效 JSON") from exc
    platform = f"{config.get('os', 'linux')}/{config.get('architecture', 'amd64')}"
    if platform != "linux/amd64":
        raise ImageArchiveError("当前只支持 linux/amd64 镜像")

    expected_layers: dict[str, dict] = {}
    for layer in raw_layers:
        digest = layer.get("digest") if isinstance(layer, dict) else None
        size = layer.get("size") if isinstance(layer, dict) else None
        if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest) or not isinstance(size, int):
            raise ImageArchiveError("OCI layer descriptor 无效")
        expected_layers[f"blobs/sha256/{digest.removeprefix('sha256:')}"] = layer

    config_path = work_dir / "config.json"
    config_path.write_bytes(config_bytes)
    extracted: dict[str, Path] = {"config": config_path}
    remaining = set(expected_layers)
    try:
        with tarfile.open(archive_path, mode="r|*") as archive:
            for member in archive:
                _safe_member(member, allow_directory=True)
                if member.isdir():
                    continue
                stream = archive.extractfile(member)
                if stream is None:
                    raise ImageArchiveError(f"无法读取 OCI 文件: {member.name}")
                target = expected_layers.get(member.name)
                if target is None:
                    _discard_member(stream)
                    continue
                output = work_dir / member.name.rsplit("/", 1)[-1]
                digest = hashlib.sha256()
                size = 0
                with output.open("wb") as handle:
                    while chunk := stream.read(1024 * 1024):
                        handle.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                expected_digest = member.name.rsplit("/", 1)[-1]
                if digest.hexdigest() != expected_digest or size != target["size"]:
                    raise ImageArchiveError("OCI layer 摘要或大小不匹配")
                extracted[member.name] = output
                remaining.discard(member.name)
    except ImageArchiveError:
        raise
    except (tarfile.TarError, OSError) as exc:
        raise ImageArchiveError(f"无法提取 OCI layer: {exc}") from exc
    if remaining:
        raise ImageArchiveError("OCI 归档缺少声明的 layer")

    item = {
        "Config": "config",
        "Layers": [
            f"blobs/sha256/{layer['digest'].removeprefix('sha256:')}"
            for layer in raw_layers
        ],
    }
    return item, extracted, manifest_bytes, manifest.get(
        "mediaType", "application/vnd.oci.image.manifest.v1+json"
    )


async def import_image_archive(
    archive_path: Path,
    *,
    repository: str,
    tag: str,
    archive_sha256: str,
    archive_size_bytes: int,
) -> dict:
    _validate_repository(repository)
    if not _TAG_RE.fullmatch(tag):
        raise ImageArchiveError("tag 格式无效")
    if archive_size_bytes > settings.IMAGE_IMPORT_MAX_SIZE_MB * 1024 * 1024:
        raise ImageArchiveError("镜像归档超过平台大小限制")

    with TemporaryDirectory(prefix="sciminer-image-import-") as temporary:
        work_dir = Path(temporary)
        seekable_archive = _prepare_archive_for_random_access(archive_path, work_dir)
        try:
            with tarfile.open(seekable_archive, mode="r:*") as archive:
                names = {member.name for member in archive.getmembers() if member.isfile()}
        except (tarfile.TarError, OSError) as exc:
            raise ImageArchiveError("无法读取镜像归档") from exc

        if "index.json" in names and "oci-layout" in names:
            item, files, source_manifest, manifest_media_type = _load_oci_archive(
                seekable_archive, work_dir
            )
            is_oci = True
        else:
            item, files = _load_archive(seekable_archive, work_dir)
            source_manifest = None
            manifest_media_type = "application/vnd.docker.distribution.manifest.v2+json"
            is_oci = False

        config_path = files[item["Config"]]
        config_digest, config_size = _digest_file(config_path)
        config = json.loads(config_path.read_text())
        platform = f"{config.get('os', 'linux')}/{config.get('architecture', 'amd64')}"
        if platform != "linux/amd64":
            raise ImageArchiveError("当前只支持 linux/amd64 镜像")

        layers = []
        for layer_name in item["Layers"]:
            layer_path = files[layer_name]
            digest, size = _digest_file(layer_path)
            layers.append(
                {
                    "mediaType": (
                        "application/vnd.oci.image.layer.v1.tar+gzip"
                        if is_oci
                        else "application/vnd.docker.image.rootfs.diff.tar"
                    ),
                    "size": size,
                    "digest": f"sha256:{digest}",
                    "path": layer_path,
                }
            )

        manifest = {
            "schemaVersion": 2,
            "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
            "config": {
                "mediaType": "application/vnd.docker.container.image.v1+json",
                "size": config_size,
                "digest": f"sha256:{config_digest}",
            },
            "layers": [
                {key: value for key, value in layer.items() if key != "path"}
                for layer in layers
            ],
        }
        client = RegistryClient(
            settings.IMAGE_REGISTRY_ENDPOINT,
            settings.IMAGE_REGISTRY_USERNAME,
            settings.IMAGE_REGISTRY_PASSWORD,
        )
        await client.ensure_blob(repository, manifest["config"]["digest"], config_path)
        for layer in layers:
            await client.ensure_blob(repository, layer["digest"], layer["path"])
        manifest_bytes = source_manifest or json.dumps(manifest, separators=(",", ":")).encode()
        if is_oci:
            returned_digest = await client.put_manifest(
                repository, tag, manifest_bytes, manifest_media_type
            )
        else:
            returned_digest = await client.put_manifest(repository, tag, manifest_bytes)
        local_digest = hashlib.sha256(manifest_bytes).hexdigest()
        digest = returned_digest if _DIGEST_RE.fullmatch(returned_digest) else f"sha256:{local_digest}"
        return {
            "repository": repository,
            "tag": tag,
            "manifest_digest": digest,
            "archive_sha256": archive_sha256,
            "archive_size_bytes": archive_size_bytes,
            "platform": platform,
            "image_reference": _build_image_reference(repository, tag, digest),
        }


async def import_docker_save(*args, **kwargs) -> dict:
    """Backward-compatible name for callers that used the original Docker-only importer."""
    return await import_image_archive(*args, **kwargs)
