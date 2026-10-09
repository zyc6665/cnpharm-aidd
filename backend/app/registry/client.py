"""用于管理员镜像导入的最小 Docker Distribution 客户端。"""

from pathlib import Path
from typing import AsyncIterator
from urllib.parse import urljoin

import httpx


class RegistryError(RuntimeError):
    """Registry 操作失败。"""


async def _file_chunks(path: Path, chunk_size: int = 1024 * 1024) -> AsyncIterator[bytes]:
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            yield chunk


class RegistryClient:
    def __init__(self, endpoint: str, username: str | None = None, password: str | None = None):
        self.endpoint = endpoint.rstrip("/") + "/"
        self.auth = (username, password) if username and password else None

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        kwargs.setdefault("timeout", httpx.Timeout(300.0, connect=10.0))
        async with httpx.AsyncClient(auth=self.auth, follow_redirects=True) as client:
            response = await client.request(method, urljoin(self.endpoint, path.lstrip("/")), **kwargs)
        if response.status_code >= 400:
            raise RegistryError(f"Registry {method} {path} failed with HTTP {response.status_code}")
        return response

    async def ensure_blob(self, repository: str, digest: str, path: Path) -> None:
        blob_path = f"/v2/{repository}/blobs/{digest}"
        async with httpx.AsyncClient(auth=self.auth, follow_redirects=True) as client:
            response = await client.head(
                urljoin(self.endpoint, blob_path.lstrip("/")),
                timeout=httpx.Timeout(30.0, connect=10.0),
            )
        if response.status_code == 200:
            return

        async with httpx.AsyncClient(auth=self.auth, follow_redirects=True) as client:
            start = await client.post(
                urljoin(self.endpoint, f"v2/{repository}/blobs/uploads/"),
                timeout=httpx.Timeout(30.0, connect=10.0),
            )
            if start.status_code >= 400 or not start.headers.get("location"):
                raise RegistryError(f"Registry blob upload start failed with HTTP {start.status_code}")
            upload_url = urljoin(str(start.url), start.headers["location"])
            separator = "&" if "?" in upload_url else "?"
            uploaded = await client.put(
                f"{upload_url}{separator}digest={digest}",
                content=_file_chunks(path),
                timeout=httpx.Timeout(1800.0, connect=10.0),
            )
            if uploaded.status_code >= 400:
                raise RegistryError(f"Registry blob upload failed with HTTP {uploaded.status_code}")

    async def put_manifest(
        self,
        repository: str,
        tag: str,
        manifest: bytes,
        media_type: str = "application/vnd.docker.distribution.manifest.v2+json",
    ) -> str:
        response = await self._request(
            "PUT",
            f"/v2/{repository}/manifests/{tag}",
            content=manifest,
            headers={"Content-Type": media_type},
        )
        return response.headers.get("Docker-Content-Digest", "")
