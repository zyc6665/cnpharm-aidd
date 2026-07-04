# backend/app/exceptions/storage.py
"""存储服务异常处理

根据详细设计说明书 8.3 节实现。
负责处理存储服务相关的异常和降级策略。
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, Optional
import asyncio
import hashlib
import logging

from app.common.exceptions import AppException

logger = logging.getLogger(__name__)


class StorageException(AppException):
    """存储异常基类"""

    def __init__(
        self,
        message: str,
        storage_backend: Optional[str] = None,
        file_path: Optional[str] = None,
        operation: Optional[str] = None
    ):
        detail = {"storage_backend": storage_backend, "file_path": file_path, "operation": operation}
        detail = {k: v for k, v in detail.items() if v is not None}
        super().__init__(message, code=500, detail=detail or None)
        self.storage_backend = storage_backend
        self.file_path = file_path
        self.operation = operation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "storage_backend": self.storage_backend,
            "file_path": self.file_path,
            "operation": self.operation
        }


class StorageUploadException(StorageException):
    """上传异常"""
    pass


class StorageDownloadException(StorageException):
    """下载异常"""
    pass


class StorageDeleteException(StorageException):
    """删除异常"""
    pass


class StorageQuotaException(StorageException):
    """配额超限异常"""

    def __init__(
        self,
        message: str,
        quota_limit: int,
        current_usage: int,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.quota_limit = quota_limit
        self.current_usage = current_usage


class StorageCorruptionException(StorageException):
    """文件损坏异常"""

    def __init__(
        self,
        message: str,
        expected_hash: Optional[str] = None,
        actual_hash: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash


@dataclass
class StorageRetryConfig:
    """存储重试配置"""
    max_retries: int = 3
    base_delay: float = 0.5
    max_delay: float = 30.0


class StorageExceptionHandler:
    """存储异常处理器

    功能：
    1. 上传失败处理
    2. 下载失败处理
    3. 文件完整性验证
    4. 本地存储降级
    """

    def __init__(
        self,
        primary_storage=None,
        fallback_storage=None,
        retry_config: Optional[StorageRetryConfig] = None
    ):
        """初始化存储异常处理器

        Args:
            primary_storage: 主存储后端
            fallback_storage: 降级存储后端
            retry_config: 重试配置
        """
        self.primary = primary_storage
        self.fallback = fallback_storage
        self.retry_config = retry_config or StorageRetryConfig()

    async def handle_upload_failure(
        self,
        file_content: bytes,
        file_path: str,
        error: StorageException,
        use_fallback: bool = True
    ) -> Dict[str, Any]:
        """处理上传失败

        Args:
            file_content: 文件内容
            file_path: 目标路径
            error: 异常对象
            use_fallback: 是否使用降级存储

        Returns:
            Dict[str, Any]: 处理结果
        """
        logger.error(
            f"Upload failed: {error.message}",
            extra={
                "file_path": file_path,
                "error": error.to_dict()
            }
        )

        # 重试上传
        for attempt in range(self.retry_config.max_retries):
            try:
                delay = min(
                    self.retry_config.base_delay * (2 ** attempt),
                    self.retry_config.max_delay
                )
                await asyncio.sleep(delay)

                if self.primary:
                    await self.primary.upload(file_content, file_path)
                    logger.info(
                        f"Upload succeeded on retry {attempt + 1}",
                        extra={"file_path": file_path}
                    )
                    return {
                        "success": True,
                        "storage_backend": "primary",
                        "retries": attempt + 1
                    }

            except Exception as e:
                logger.warning(f"Retry {attempt + 1} failed: {e}")
                continue

        # 尝试降级存储
        if use_fallback and self.fallback:
            try:
                await self.fallback.upload(file_content, file_path)
                logger.info(
                    f"Upload succeeded using fallback storage",
                    extra={"file_path": file_path}
                )
                return {
                    "success": True,
                    "storage_backend": "fallback",
                    "degraded": True
                }
            except Exception as e:
                logger.error(f"Fallback upload also failed: {e}")

        return {
            "success": False,
            "error": error.message,
            "retries": self.retry_config.max_retries
        }

    async def handle_download_failure(
        self,
        file_path: str,
        error: StorageException,
        use_fallback: bool = True
    ) -> Dict[str, Any]:
        """处理下载失败

        Args:
            file_path: 文件路径
            error: 异常对象
            use_fallback: 是否使用降级存储

        Returns:
            Dict[str, Any]: 处理结果
        """
        logger.error(
            f"Download failed: {error.message}",
            extra={
                "file_path": file_path,
                "error": error.to_dict()
            }
        )

        # 重试下载
        for attempt in range(self.retry_config.max_retries):
            try:
                delay = min(
                    self.retry_config.base_delay * (2 ** attempt),
                    self.retry_config.max_delay
                )
                await asyncio.sleep(delay)

                if self.primary:
                    content = await self.primary.download(file_path)
                    logger.info(
                        f"Download succeeded on retry {attempt + 1}",
                        extra={"file_path": file_path}
                    )
                    return {
                        "success": True,
                        "content": content,
                        "storage_backend": "primary",
                        "retries": attempt + 1
                    }

            except Exception as e:
                logger.warning(f"Retry {attempt + 1} failed: {e}")
                continue

        # 尝试降级存储
        if use_fallback and self.fallback:
            try:
                content = await self.fallback.download(file_path)
                logger.info(
                    f"Download succeeded using fallback storage",
                    extra={"file_path": file_path}
                )
                return {
                    "success": True,
                    "content": content,
                    "storage_backend": "fallback",
                    "degraded": True
                }
            except Exception as e:
                logger.error(f"Fallback download also failed: {e}")

        return {
            "success": False,
            "error": error.message,
            "retries": self.retry_config.max_retries
        }

    async def verify_file_integrity(
        self,
        content: bytes,
        expected_hash: str,
        algorithm: str = "sha256"
    ) -> bool:
        """验证文件完整性

        Args:
            content: 文件内容
            expected_hash: 期望的哈希值
            algorithm: 哈希算法

        Returns:
            bool: 是否完整

        Raises:
            StorageCorruptionException: 文件损坏
        """
        if algorithm == "sha256":
            actual_hash = hashlib.sha256(content).hexdigest()
        elif algorithm == "md5":
            actual_hash = hashlib.md5(content).hexdigest()
        else:
            raise ValueError(f"Unsupported hash algorithm: {algorithm}")

        if actual_hash != expected_hash:
            raise StorageCorruptionException(
                message="File integrity check failed",
                expected_hash=expected_hash,
                actual_hash=actual_hash
            )

        return True

    async def migrate_to_fallback(
        self,
        file_path: str
    ) -> bool:
        """将文件迁移到降级存储

        Args:
            file_path: 文件路径

        Returns:
            bool: 是否成功
        """
        if not self.primary or not self.fallback:
            return False

        try:
            # 从主存储下载
            content = await self.primary.download(file_path)

            # 上传到降级存储
            await self.fallback.upload(content, file_path)

            logger.info(
                f"File migrated to fallback storage",
                extra={"file_path": file_path}
            )
            return True

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            return False

    async def migrate_to_primary(
        self,
        file_path: str
    ) -> bool:
        """将文件从降级存储迁移回主存储

        Args:
            file_path: 文件路径

        Returns:
            bool: 是否成功
        """
        if not self.primary or not self.fallback:
            return False

        try:
            # 从降级存储下载
            content = await self.fallback.download(file_path)

            # 上传到主存储
            await self.primary.upload(content, file_path)

            # 删除降级存储中的文件
            try:
                await self.fallback.delete(file_path)
            except Exception as e:
                logger.warning(
                    "Failed to delete fallback file after primary migration for %s: %s",
                    file_path,
                    e,
                    extra={"file_path": file_path},
                )

            logger.info(
                f"File migrated back to primary storage",
                extra={"file_path": file_path}
            )
            return True

        except Exception as e:
            logger.error(f"Migration to primary failed: {e}")
            return False


class StorageFallbackStrategy:
    """存储降级策略

    当MinIO不可用时，使用本地存储作为降级方案。
    """

    def __init__(self, local_storage_path: str = "/tmp/storage_fallback"):
        """初始化降级策略

        Args:
            local_storage_path: 本地存储路径
        """
        self.local_path = local_storage_path
        self._use_local = False

    async def use_local_storage(self) -> None:
        """启用本地存储降级"""
        import os
        os.makedirs(self.local_path, exist_ok=True)
        self._use_local = True
        logger.warning("Switched to local storage fallback")

    async def restore_primary(self) -> None:
        """恢复使用主存储"""
        self._use_local = False
        logger.info("Restored to primary storage")

    def is_degraded(self) -> bool:
        """检查是否处于降级状态"""
        return self._use_local
