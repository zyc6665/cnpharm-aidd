# backend/app/storage/local.py
"""本地文件存储后端"""

import os
import aiofiles
from pathlib import Path
from typing import Optional, BinaryIO

from app.storage.base import StorageBackend, StorageFile
from app.config import settings


class LocalStorageBackend(StorageBackend):
    """本地文件存储后端"""

    def __init__(self, base_path: Optional[str] = None):
        self.base_path = Path(base_path or settings.STORAGE_PATH)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_full_path(self, path: str) -> Path:
        """获取完整文件路径"""
        # 使用路径前两个字符作为子目录，避免单目录文件过多
        if len(path) >= 2:
            subdir = path[:2]
            return self.base_path / subdir / path
        return self.base_path / path

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
        if os.path.isabs(path):
            full_path = Path(path)
        else:
            full_path = self._get_full_path(path)

        if not full_path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")

        async with aiofiles.open(full_path, "rb") as f:
            return await f.read()

    async def delete(self, path: str) -> bool:
        """删除文件"""
        if os.path.isabs(path):
            full_path = Path(path)
        else:
            full_path = self._get_full_path(path)

        if full_path.exists():
            os.remove(full_path)
            return True
        return False

    async def exists(self, path: str) -> bool:
        """检查文件是否存在"""
        if os.path.isabs(path):
            full_path = Path(path)
        else:
            full_path = self._get_full_path(path)
        return full_path.exists()

    async def get_url(self, path: str, expires_in: int = 3600) -> str:
        """获取文件访问URL（本地存储返回API路径）"""
        # 本地存储通过API下载，不支持预签名URL
        return f"/api/v1/files/download/{path}"

    async def get_info(self, path: str) -> Optional[StorageFile]:
        """获取文件信息"""
        if os.path.isabs(path):
            full_path = Path(path)
        else:
            full_path = self._get_full_path(path)

        if not full_path.exists():
            return None

        stat = full_path.stat()
        return StorageFile(
            path=str(full_path),
            size=stat.st_size
        )
