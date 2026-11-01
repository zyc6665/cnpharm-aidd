# backend/app/storage/local.py
"""本地文件存储后端"""

import os
import asyncio
import aiofiles
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Optional, BinaryIO

from app.storage.base import StorageBackend, StorageFile
from app.config import settings


def _open_local(path: Path):
    """打开本地文件句柄（独立函数便于测试替换）。"""
    return open(path, "rb")


class LocalStorageBackend(StorageBackend):
    """本地文件存储后端"""

    def __init__(self, base_path: Optional[str] = None):
        self.base_path = Path(base_path or settings.STORAGE_PATH)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _ensure_within_root(self, full_path: Path, original: str) -> None:
        """断言 ``full_path`` 解析后仍在 ``base_path`` 内，否则判为越界。"""
        base_resolved = self.base_path.resolve()
        try:
            resolved = full_path.resolve()
        except OSError as exc:  # pragma: no cover - 解析异常归为越界
            raise ValueError(f"存储路径无法解析: {original}") from exc
        if not resolved.is_relative_to(base_resolved):
            raise ValueError(f"存储路径越界，不在存储根内: {original}")

    def _get_full_path(self, path: str) -> Path:
        """由逻辑相对键解析完整路径，并做存储根约束（纵深防御）。

        - 拒绝空路径与绝对路径：逻辑键必须相对，绝对路径会让 ``/`` 运算直接
          丢掉基目录（``Path(base) / "/etc/passwd" == Path("/etc/passwd")``）；
        - 解析 ``..`` 与符号链接后必须仍在 ``base_path`` 内，否则视为越界。
        """
        if not path:
            raise ValueError("存储路径不能为空")
        if Path(path).is_absolute():
            raise ValueError(f"不允许绝对存储路径: {path}")
        # 使用路径前两个字符作为子目录，避免单目录文件过多
        if len(path) >= 2:
            full_path = self.base_path / path[:2] / path
        else:
            full_path = self.base_path / path
        self._ensure_within_root(full_path, path)
        return full_path

    def _resolve_read_path(self, path: str) -> Path:
        """解析读取/删除/存在性/元信息用的路径；绝对路径也必须落在根内。"""
        if Path(path).is_absolute():
            self._ensure_within_root(Path(path), path)
            return Path(path)
        return self._get_full_path(path)

    async def upload(
        self,
        file_data: bytes,
        path: str,
        content_type: Optional[str] = None
    ) -> StorageFile:
        """上传文件"""
        full_path = self._get_full_path(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(full_path, "wb") as f:
            await f.write(file_data)

        return StorageFile(
            path=str(full_path),
            size=len(file_data),
            content_type=content_type
        )

    async def upload_stream(
        self,
        file_stream: BinaryIO,
        path: str,
        size: int,
        content_type: Optional[str] = None
    ) -> StorageFile:
        """流式上传文件"""
        full_path = self._get_full_path(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(full_path, "wb") as f:
            # 分块读取写入
            chunk_size = 8192
            while True:
                chunk = file_stream.read(chunk_size)
                if not chunk:
                    break
                await f.write(chunk)

        return StorageFile(
            path=str(full_path),
            size=size,
            content_type=content_type
        )

    async def download(self, path: str) -> bytes:
        """下载文件"""
        # 支持绝对路径和相对路径
        full_path = self._resolve_read_path(path)

        if not full_path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")

        async with aiofiles.open(full_path, "rb") as f:
            return await f.read()

    async def delete(self, path: str) -> bool:
        """删除文件"""
        full_path = self._resolve_read_path(path)

        if full_path.exists():
            os.remove(full_path)
            return True
        return False

    def open_stream(self, path: str, chunk_size: int = 1024 * 1024) -> AsyncIterator[bytes]:
        """按块流式读取本地文件，文件句柄随迭代结束关闭。

        读文件放到 ``asyncio.to_thread``：同步 ``read`` 不会阻塞事件循环。
        """

        async def _iter() -> AsyncIterator[bytes]:
            full_path = self._resolve_read_path(path)
            if not full_path.exists():
                raise FileNotFoundError(f"文件不存在: {path}")
            handle = await asyncio.to_thread(_open_local, full_path)
            try:
                while True:
                    chunk = await asyncio.to_thread(handle.read, chunk_size)
                    if not chunk:
                        break
                    yield chunk
            finally:
                await asyncio.to_thread(handle.close)

        return _iter()

    async def exists(self, path: str) -> bool:
        """检查文件是否存在"""
        full_path = self._resolve_read_path(path)
        return full_path.exists()

    async def get_url(self, path: str, expires_in: int = 3600) -> str:
        """获取文件访问URL（本地存储返回API路径）"""
        # 本地存储通过API下载，不支持预签名URL
        return f"/api/v1/files/download/{path}"

    async def get_info(self, path: str) -> Optional[StorageFile]:
        """获取文件信息"""
        full_path = self._resolve_read_path(path)

        if not full_path.exists():
            return None

        stat = full_path.stat()
        return StorageFile(
            path=str(full_path),
            size=stat.st_size
        )
