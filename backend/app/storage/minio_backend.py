# backend/app/storage/minio_backend.py
"""MinIO 存储后端"""

import io
import logging
import asyncio
from collections.abc import AsyncIterator
from typing import Optional, BinaryIO
from datetime import timedelta

from app.storage.base import StorageBackend, StorageFile
from app.config import settings

logger = logging.getLogger(__name__)


class MinIOStorageBackend(StorageBackend):
    """MinIO 对象存储后端"""

    def __init__(
        self,
        endpoint: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        bucket: Optional[str] = None,
        secure: bool | None = None
    ):
        # 延迟导入，避免未安装 minio 时报错
        try:
            from minio import Minio
        except ImportError:
            raise ImportError("请安装 minio: pip install minio")

        self.endpoint = endpoint or settings.MINIO_ENDPOINT
        self.access_key = access_key or settings.MINIO_ACCESS_KEY
        self.secret_key = secret_key or settings.MINIO_SECRET_KEY
        self.bucket = bucket or settings.MINIO_BUCKET
        self.secure = settings.MINIO_SECURE if secure is None else secure

        self.client = Minio(
            self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure
        )

    async def upload(
        self,
        file_data: bytes,
        path: str,
        content_type: Optional[str] = None
    ) -> StorageFile:
        """上传文件"""
        data_stream = io.BytesIO(file_data)
        size = len(file_data)

        result = await asyncio.to_thread(
            self.client.put_object,
            self.bucket,
            path,
            data_stream,
            size,
            content_type=content_type or "application/octet-stream",
        )

        return StorageFile(
            path=path,
            size=size,
            content_type=content_type,
            etag=result.etag
        )

    async def upload_stream(
        self,
        file_stream: BinaryIO,
        path: str,
        size: int,
        content_type: Optional[str] = None
    ) -> StorageFile:
        """流式上传文件"""
        result = await asyncio.to_thread(
            self.client.put_object,
            self.bucket,
            path,
            file_stream,
            size,
            content_type=content_type or "application/octet-stream",
        )

        return StorageFile(
            path=path,
            size=size,
            content_type=content_type,
            etag=result.etag
        )

    async def download(self, path: str) -> bytes:
        """下载文件"""
        return await asyncio.to_thread(self._download_sync, path)

    def _download_sync(self, path: str) -> bytes:
        response = self.client.get_object(self.bucket, path)
        try:
            return response.read()
        finally:
            self._close_response(response, path)

    def open_stream(self, path: str, chunk_size: int = 1024 * 1024) -> AsyncIterator[bytes]:
        """按块流式读取 MinIO 对象，迭代结束/异常时释放连接。

        ``get_object`` 返回的是 urllib3 响应，必须显式 ``close`` + ``release_conn``，
        否则连接池会被慢速下载逐个占满；复用 ``_download_sync`` 同一套关闭逻辑。
        """

        async def _iter() -> AsyncIterator[bytes]:
            response = await asyncio.to_thread(
                self.client.get_object, self.bucket, path
            )
            try:
                while True:
                    chunk = await asyncio.to_thread(response.read, chunk_size)
                    if not chunk:
                        break
                    yield chunk
            finally:
                await asyncio.to_thread(self._close_response, response, path)

        return _iter()

    async def delete(self, path: str) -> bool:
        """删除文件"""
        try:
            await asyncio.to_thread(self.client.remove_object, self.bucket, path)
            return True
        except Exception as e:
            logger.warning(
                "Failed to delete MinIO object %s/%s: %s",
                self.bucket,
                path,
                e,
            )
            if _is_missing_object_error(e):
                return False
            raise

    async def exists(self, path: str) -> bool:
        """检查文件是否存在"""
        try:
            await asyncio.to_thread(self.client.stat_object, self.bucket, path)
            return True
        except Exception as e:
            if _is_missing_object_error(e):
                return False
            raise

    async def get_url(self, path: str, expires_in: int = 3600) -> str:
        """获取预签名URL"""
        url = await asyncio.to_thread(
            self.client.presigned_get_object,
            self.bucket,
            path,
            expires=timedelta(seconds=expires_in),
        )
        return url

    async def get_info(self, path: str) -> Optional[StorageFile]:
        """获取文件信息"""
        try:
            stat = await asyncio.to_thread(self.client.stat_object, self.bucket, path)
            return StorageFile(
                path=path,
                size=stat.size,
                content_type=stat.content_type,
                etag=stat.etag
            )
        except Exception as e:
            if _is_missing_object_error(e):
                return None
            raise

    async def get_bucket_lifecycle(self, bucket: Optional[str] = None):
        """读取桶的生命周期配置；未配置时返回 ``None``（不是空配置）。

        刻意不放进 ``StorageBackend`` 抽象基类：本地后端没有「桶」这个概念，塞进
        基类会逼本地实现写两个 ``raise NotImplementedError``，反而让调用方失去
        「先问这个后端有没有该能力」的机会。能力探测在 ``app.storage.lifecycle``。
        """

        target = bucket or self.bucket
        return await asyncio.to_thread(self.client.get_bucket_lifecycle, target)

    async def set_bucket_lifecycle(self, bucket: str, config) -> None:
        """写入桶的生命周期配置（整体覆盖；合并逻辑在 ``app.storage.lifecycle``）。

        参数顺序刻意与 minio SDK 保持一致（``bucket`` 在前、``config`` 在后）：
        第一版写成了 ``(config, bucket=None)``，调用方按 SDK 习惯传
        ``(target, config)`` 时就静默互换了两个参数，SDK 在
        ``check_bucket_name`` 里拿 ``LifecycleConfig`` 当桶名，
        报 ``TypeError: expected string or bytes-like object``。
        单元测试的替身若采用同样的顺序就发现不了，只有真 MinIO 才能暴露。
        """

        await asyncio.to_thread(self.client.set_bucket_lifecycle, bucket, config)

    async def delete_bucket_lifecycle(self, bucket: str) -> None:
        """删除桶的生命周期配置。

        真 MinIO 上实测：``set_bucket_lifecycle`` 传空规则会被拒绝并报
        ``InvalidArgument: Lifecycle configuration should have at least one rule``。
        「一条规则都不需要」在 S3 语义里对应的是**删除配置**，不是写一份空配置。
        """

        await asyncio.to_thread(self.client.delete_bucket_lifecycle, bucket)

    async def get_bucket_versioning(self, bucket: Optional[str] = None):
        """读取桶的版本化状态（决定 ``NoncurrentVersionExpiration`` 是否有意义）。"""

        target = bucket or self.bucket
        return await asyncio.to_thread(self.client.get_bucket_versioning, target)

    def _close_response(self, response, path: str) -> None:
        """释放 MinIO 响应连接，避免清理失败掩盖下载结果。"""
        try:
            response.close()
        except Exception as e:
            logger.warning(
                "Failed to close MinIO response for %s/%s: %s",
                self.bucket,
                path,
                e,
            )

        try:
            response.release_conn()
        except Exception as e:
            logger.warning(
                "Failed to release MinIO response connection for %s/%s: %s",
                self.bucket,
                path,
                e,
            )


def _is_missing_object_error(error: Exception) -> bool:
    return getattr(error, "code", None) in {"NoSuchKey", "NoSuchObject"}
