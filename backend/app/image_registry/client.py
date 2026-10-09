"""Docker Registry HTTP API v2 client for pushing one image."""

from __future__ import annotations

import hashlib
import json
import tarfile
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx

from app.image_registry.archive import DockerSaveImage


class RegistryClientError(RuntimeError):
    """Raised when a registry push cannot be completed."""


@dataclass(frozen=True)
class RegistryPushResult:
    repository: str
    tag: str
    digest: str
    reference: str
    manifest_size: int


class RegistryClient:
    def __init__(
        self,
        endpoint: str,
        *,
        timeout: float = 120.0,
        username: str | None = None,
        password: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        normalized = endpoint.rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("Registry endpoint 必须使用 http 或 https")
        self.endpoint = normalized
        self.timeout = timeout
        self.auth = httpx.BasicAuth(username, password) if username and password else None
        self._client = client

    async def push(self, image: DockerSaveImage) -> RegistryPushResult:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.timeout, auth=self.auth)
        try:
            await self._ensure_blob(client, image.repository, image.config_digest, image.config_bytes)
            with tarfile.open(image.archive_path, mode="r:*") as archive:
                for layer in image.layers:
                    content = _read_layer(archive, layer.member_name)
                    await self._ensure_blob(client, image.repository, layer.digest, content)

            manifest = {
                "schemaVersion": 2,
                "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
                "config": {
                    "mediaType": "application/vnd.docker.container.image.v1+json",
                    "size": len(image.config_bytes),
                    "digest": image.config_digest,
                },
                "layers": [
                    {
                        "mediaType": layer.media_type,
                        "size": layer.size,
                        "digest": layer.digest,
                    }
                    for layer in image.layers
                ],
            }
            manifest_bytes = json.dumps(
                manifest, ensure_ascii=True, separators=(",", ":")
            ).encode("utf-8")
            response = await client.put(
                self._url(f"/v2/{image.repository}/manifests/{image.tag}"),
                content=manifest_bytes,
                headers={
                    "Content-Type": "application/vnd.docker.distribution.manifest.v2+json",
                },
            )
            if response.status_code not in {200, 201, 202}:
                raise RegistryClientError(
                    f"Registry manifest push failed with HTTP {response.status_code}"
                )
            digest = response.headers.get("Docker-Content-Digest") or _sha256(manifest_bytes)
            return RegistryPushResult(
                repository=image.repository,
                tag=image.tag,
                digest=digest,
                reference=f"{self.endpoint}/{image.repository}@{digest}",
                manifest_size=len(manifest_bytes),
            )
        finally:
            if owns_client:
                await client.aclose()

    async def _ensure_blob(
        self,
        client: httpx.AsyncClient,
        repository: str,
        digest: str,
        content: bytes,
    ) -> None:
        blob_url = self._url(f"/v2/{repository}/blobs/{digest}")
        head = await client.head(blob_url)
        if head.status_code == 200:
            return
        if head.status_code not in {404, 405}:
            raise RegistryClientError(f"Registry blob check failed with HTTP {head.status_code}")
        start = await client.post(self._url(f"/v2/{repository}/blobs/uploads/"))
        if start.status_code != 202:
            raise RegistryClientError(f"Registry upload start failed with HTTP {start.status_code}")
        location = start.headers.get("Location")
        if not location:
            raise RegistryClientError("Registry upload response missing Location")
        uploaded = await client.put(
            _with_digest(urljoin(self.endpoint + "/", location), digest),
            content=content,
            headers={"Content-Type": "application/octet-stream"},
        )
        if uploaded.status_code not in {201, 202}:
            raise RegistryClientError(
                f"Registry blob upload failed with HTTP {uploaded.status_code}"
            )

    def _url(self, path: str) -> str:
        return f"{self.endpoint}{path}"


def _read_layer(archive: tarfile.TarFile, member_name: str) -> bytes:
    member = archive.getmember(member_name)
    extracted = archive.extractfile(member)
    if extracted is None:
        raise RegistryClientError(f"无法读取镜像 layer: {member_name}")
    return extracted.read()


def _with_digest(url: str, digest: str) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["digest"] = digest
    return urlunparse(parsed._replace(query=urlencode(query)))


def _sha256(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"
