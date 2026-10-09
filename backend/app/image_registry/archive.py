"""Parser for single-image docker save archives."""

from __future__ import annotations

import hashlib
import json
import re
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class DockerSaveArchiveError(ValueError):
    """Raised when an uploaded archive is not a supported docker save image."""


@dataclass(frozen=True)
class DockerSaveLayer:
    member_name: str
    digest: str
    size: int
    media_type: str


@dataclass(frozen=True)
class DockerSaveImage:
    archive_path: Path
    repository: str
    tag: str
    config_digest: str
    config_bytes: bytes
    layers: tuple[DockerSaveLayer, ...]
    architecture: str
    operating_system: str

    @property
    def reference(self) -> str:
        return f"{self.repository}:{self.tag}"


_REPOSITORY = re.compile(
    r"^[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*$"
)
_TAG = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")


def parse_docker_save_archive(
    archive_path: str | Path,
    *,
    repository: str | None = None,
    tag: str | None = None,
) -> DockerSaveImage:
    """Parse one linux/amd64 image from a docker save tar archive."""
    path = Path(archive_path)
    if not path.is_file():
        raise DockerSaveArchiveError("镜像归档文件不存在")

    try:
        with tarfile.open(path, mode="r:*") as archive:
            manifest = _read_json_member(archive, "manifest.json")
            if not isinstance(manifest, list) or len(manifest) != 1:
                raise DockerSaveArchiveError("仅支持包含一个镜像的 docker save 归档")
            entry = manifest[0]
            if not isinstance(entry, dict):
                raise DockerSaveArchiveError("manifest.json 格式无效")

            resolved_repository, resolved_tag = _resolve_reference(
                entry.get("RepoTags"), repository, tag
            )
            config_name = _safe_member_name(entry.get("Config"), "镜像配置")
            config_bytes = _read_member_bytes(archive, config_name)
            try:
                config = json.loads(config_bytes)
            except json.JSONDecodeError as exc:
                raise DockerSaveArchiveError("镜像配置不是有效 JSON") from exc
            if config.get("architecture") != "amd64" or config.get("os") != "linux":
                raise DockerSaveArchiveError("仅支持 linux/amd64 镜像")

            raw_layers = entry.get("Layers")
            if not isinstance(raw_layers, list) or not raw_layers:
                raise DockerSaveArchiveError("镜像归档缺少 layer")
            layers = tuple(
                _build_layer_descriptor(archive, _safe_member_name(item, "镜像 layer"))
                for item in raw_layers
            )
    except DockerSaveArchiveError:
        raise
    except (tarfile.TarError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise DockerSaveArchiveError("无法读取 docker save 归档") from exc

    return DockerSaveImage(
        archive_path=path,
        repository=resolved_repository,
        tag=resolved_tag,
        config_digest=_sha256(config_bytes),
        config_bytes=config_bytes,
        layers=layers,
        architecture="amd64",
        operating_system="linux",
    )


def _resolve_reference(
    repo_tags: Any,
    repository: str | None,
    tag: str | None,
) -> tuple[str, str]:
    archive_reference = None
    if isinstance(repo_tags, list) and len(repo_tags) == 1 and isinstance(repo_tags[0], str):
        archive_reference = repo_tags[0]
    if repository is None or tag is None:
        if archive_reference is None or ":" not in archive_reference.rsplit("/", 1)[-1]:
            raise DockerSaveArchiveError("请提供镜像 repository 和 tag")
        archive_repository, archive_tag = archive_reference.rsplit(":", 1)
        repository = repository or archive_repository
        tag = tag or archive_tag
    if not repository or not _REPOSITORY.fullmatch(repository):
        raise DockerSaveArchiveError("镜像 repository 格式无效")
    if not tag or not _TAG.fullmatch(tag):
        raise DockerSaveArchiveError("镜像 tag 格式无效")
    return repository, tag


def _build_layer_descriptor(archive: tarfile.TarFile, member_name: str) -> DockerSaveLayer:
    member = archive.getmember(member_name)
    if not member.isfile():
        raise DockerSaveArchiveError("镜像 layer 必须是普通文件")
    return DockerSaveLayer(
        member_name=member_name,
        digest=_sha256_stream(archive, member),
        size=member.size,
        media_type=(
            "application/vnd.docker.image.rootfs.diff.tar.gzip"
            if _is_gzip(archive, member)
            else "application/vnd.docker.image.rootfs.diff.tar"
        ),
    )


def _read_json_member(archive: tarfile.TarFile, member_name: str) -> Any:
    return json.loads(_read_member_bytes(archive, member_name))


def _read_member_bytes(archive: tarfile.TarFile, member_name: str) -> bytes:
    member = archive.getmember(member_name)
    if not member.isfile():
        raise DockerSaveArchiveError(f"归档成员不是普通文件: {member_name}")
    extracted = archive.extractfile(member)
    if extracted is None:
        raise DockerSaveArchiveError(f"无法读取归档成员: {member_name}")
    return extracted.read()


def _sha256_stream(archive: tarfile.TarFile, member: tarfile.TarInfo) -> str:
    extracted = archive.extractfile(member)
    if extracted is None:
        raise DockerSaveArchiveError(f"无法读取镜像 layer: {member.name}")
    digest = hashlib.sha256()
    while chunk := extracted.read(1024 * 1024):
        digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _is_gzip(archive: tarfile.TarFile, member: tarfile.TarInfo) -> bool:
    extracted = archive.extractfile(member)
    if extracted is None:
        return False
    return extracted.read(2) == b"\x1f\x8b"


def _sha256(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _safe_member_name(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value.startswith("/"):
        raise DockerSaveArchiveError(f"{label}名称无效")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise DockerSaveArchiveError(f"{label}路径无效")
    return value
