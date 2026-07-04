# backend/app/storage/minio_backend.py
"""MinIO 存储后端"""

import io
import logging
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
        secure: bool = False
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
        self.secure = secure or settings.MINIO_SECURE

        self.client = Minio(
            self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure
        )

        # 确保 bucket 存在
        self._ensure_bucket()

    def _ensure_bucket(self):
        """确保存储桶存在"""
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    async def upload(
        self,
        file_data: bytes,
        path: str,
        content_type: Optional[str] = None
    ) -> StorageFile:
        """上传文件"""
        data_stream = io.BytesIO(file_data)
        size = len(file_data)

        result = self.client.put_object(
            self.bucket,
            path,
            data_stream,
            size,
            content_type=content_type or "application/octet-stream"
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
        result = self.client.put_object(
            self.bucket,
            path,
            file_stream,
            size,
            content_type=content_type or "application/octet-stream"
        )

        return StorageFile(
            path=path,
            size=size,
            content_type=content_type,
            etag=result.etag
        )

    async def download(self, path: str) -> bytes:
        """下载文件"""
        response = self.client.get_object(self.bucket, path)
        try:
            return response.read()
        finally:
            self._close_response(response, path)

    async def delete(self, path: str) -> bool:
        """删除文件"""
        try:
            self.client.remove_object(self.bucket, path)
            return True
        except Exception as e:
            logger.warning(
                "Failed to delete MinIO object %s/%s: %s",
                self.bucket,
                path,
                e,
            )
            return False

    async def exists(self, path: str) -> bool:
        """检查文件是否存在"""
        try:
            self.client.stat_object(self.bucket, path)
            return True
        except Exception as e:
            logger.debug(
                "Failed to stat MinIO object %s/%s: %s",
                self.bucket,
                path,
                e,
            )
            return False

    async def get_url(self, path: str, expires_in: int = 3600) -> str:
        """获取预签名URL"""
        url = self.client.presigned_get_object(
            self.bucket,
            path,
            expires=timedelta(seconds=expires_in)
        )
        return url

    async def get_info(self, path: str) -> Optional[StorageFile]:
        """获取文件信息"""
        try:
            stat = self.client.stat_object(self.bucket, path)
            return StorageFile(
                path=path,
                size=stat.size,
                content_type=stat.content_type,
                etag=stat.etag
            )
        except Exception as e:
            logger.debug(
                "Failed to read MinIO object info %s/%s: %s",
                self.bucket,
                path,
                e,
            )
            return None

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
