# backend/app/storage/base.py
"""存储后端抽象基类"""

from abc import ABC, abstractmethod
from typing import Optional, BinaryIO
from dataclasses import dataclass


@dataclass
class StorageFile:
    """存储文件信息"""
    path: str
    size: int
    content_type: Optional[str] = None
    etag: Optional[str] = None


class StorageBackend(ABC):
    """存储后端抽象基类"""

    @abstractmethod
    async def upload(
        self,
        file_data: bytes,
        path: str,
        content_type: Optional[str] = None
    ) -> StorageFile:
        """
        上传文件

        Args:
            file_data: 文件二进制数据
            path: 存储路径
            content_type: 文件MIME类型

        Returns:
            StorageFile: 存储文件信息
        """
        pass

    @abstractmethod
    async def upload_stream(
        self,
        file_stream: BinaryIO,
        path: str,
        size: int,
        content_type: Optional[str] = None
    ) -> StorageFile:
        """
        流式上传文件

        Args:
            file_stream: 文件流
            path: 存储路径
            size: 文件大小
            content_type: 文件MIME类型

        Returns:
            StorageFile: 存储文件信息
        """
        pass

    @abstractmethod
    async def download(self, path: str) -> bytes:
        """
        下载文件

        Args:
            path: 存储路径

        Returns:
            bytes: 文件内容
        """
        pass

    @abstractmethod
    async def delete(self, path: str) -> bool:
        """
        删除文件

        Args:
            path: 存储路径

        Returns:
            bool: 是否成功
        """
        pass

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """
        检查文件是否存在

        Args:
            path: 存储路径

        Returns:
            bool: 是否存在
        """
        pass

    @abstractmethod
    async def get_url(self, path: str, expires_in: int = 3600) -> str:
        """
        获取文件访问URL

        Args:
            path: 存储路径
            expires_in: URL过期时间（秒）

        Returns:
            str: 访问URL
        """
        pass

    @abstractmethod
    async def get_info(self, path: str) -> Optional[StorageFile]:
        """
        获取文件信息

        Args:
            path: 存储路径

        Returns:
            StorageFile: 文件信息，不存在返回None
        """
        pass
