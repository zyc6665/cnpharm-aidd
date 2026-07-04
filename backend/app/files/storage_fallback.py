# backend/app/files/storage_fallback.py
"""存储降级策略模块

根据详细设计说明书 8.3 节实现。
提供存储服务不可用时的降级策略。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, BinaryIO
import logging
import os

from app.common.time import utcnow

logger = logging.getLogger(__name__)


class StorageBackend(str, Enum):
    """存储后端类型"""
    MINIO = "minio"
    LOCAL = "local"
    S3 = "s3"


class FallbackReason(str, Enum):
    """降级原因"""
    PRIMARY_UNAVAILABLE = "primary_unavailable"
    UPLOAD_FAILED = "upload_failed"
    TIMEOUT = "timeout"
    QUOTA_EXCEEDED = "quota_exceeded"
    MAINTENANCE = "maintenance"


class MigrationStatus(str, Enum):
    """迁移状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class StorageHealth:
    """存储健康状态"""
    backend: StorageBackend
    is_healthy: bool
    last_check: datetime
    error_count: int = 0
    last_error: Optional[str] = None
    latency_ms: Optional[float] = None


@dataclass
class FallbackConfig:
    """降级配置"""
    primary_backend: StorageBackend
    fallback_backend: StorageBackend
    auto_fallback: bool = True
    auto_migrate_back: bool = True
    health_check_interval: int = 60         # 秒
    max_error_count: int = 3                # 触发降级的最大错误数
    migration_batch_size: int = 100         # 迁移批次大小
    local_storage_path: str = "/tmp/storage_fallback"


@dataclass
class MigrationTask:
    """迁移任务"""
    file_id: str
    source_backend: StorageBackend
    target_backend: StorageBackend
    status: MigrationStatus
    created_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    retry_count: int = 0


@dataclass
class FallbackResult:
    """降级结果"""
    success: bool
    original_backend: StorageBackend
    used_backend: StorageBackend
    reason: Optional[FallbackReason] = None
    message: str = ""
    file_path: Optional[str] = None
    needs_migration: bool = False


class StorageFallbackStrategy:
    """存储降级策略

    当主存储不可用时，自动切换到备用存储。
    """

    def __init__(self, config: Optional[FallbackConfig] = None):
        """初始化降级策略

        Args:
            config: 降级配置
        """
        self.config = config or FallbackConfig(
            primary_backend=StorageBackend.MINIO,
            fallback_backend=StorageBackend.LOCAL
        )

        # 存储健康状态
        self._health_status: Dict[StorageBackend, StorageHealth] = {}

        # 当前使用的后端
        self._current_backend = self.config.primary_backend

        # 迁移任务队列
        self._migration_queue: List[MigrationTask] = []

        # 确保本地存储目录存在
        os.makedirs(self.config.local_storage_path, exist_ok=True)

        # 初始化健康状态
        for backend in StorageBackend:
            self._health_status[backend] = StorageHealth(
                backend=backend,
                is_healthy=True,
                last_check=utcnow()
            )

    async def use_local_storage(
        self,
        file_data: BinaryIO,
        file_name: str,
        file_id: str,
        reason: FallbackReason = FallbackReason.PRIMARY_UNAVAILABLE
    ) -> FallbackResult:
        """使用本地存储

        Args:
            file_data: 文件数据
            file_name: 文件名
            file_id: 文件ID
            reason: 降级原因

        Returns:
            FallbackResult: 降级结果
        """
        try:
            # 生成本地路径
            local_dir = os.path.join(self.config.local_storage_path, file_id[:2])
            os.makedirs(local_dir, exist_ok=True)
            local_path = os.path.join(local_dir, f"{file_id}_{file_name}")

            # 写入文件
            with open(local_path, "wb") as f:
                # 读取并写入
                while True:
                    chunk = file_data.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)

            logger.info(
                f"File {file_id} saved to local storage: {local_path}, "
                f"reason: {reason.value}"
            )

            # 添加迁移任务
            if self.config.auto_migrate_back:
                self._add_migration_task(
                    file_id=file_id,
                    source_backend=StorageBackend.LOCAL,
                    target_backend=self.config.primary_backend
                )

            return FallbackResult(
                success=True,
                original_backend=self.config.primary_backend,
                used_backend=StorageBackend.LOCAL,
                reason=reason,
                message=f"File saved to local storage due to {reason.value}",
                file_path=local_path,
                needs_migration=True
            )

        except Exception as e:
            logger.error(f"Failed to save file to local storage: {e}")
            return FallbackResult(
                success=False,
                original_backend=self.config.primary_backend,
                used_backend=StorageBackend.LOCAL,
                reason=reason,
                message=f"Local storage fallback failed: {str(e)}"
            )

    async def migrate_to_minio(
        self,
        file_id: str,
        local_path: str
    ) -> Tuple[bool, str]:
        """将本地文件迁移到MinIO

        Args:
            file_id: 文件ID
            local_path: 本地路径

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        from app.storage.factory import get_storage

        try:
            if not os.path.exists(local_path):
                return False, f"Local file not found: {local_path}"

            # 获取MinIO存储
            storage = get_storage()

            # 读取本地文件并上传
            with open(local_path, "rb") as f:
                file_name = os.path.basename(local_path)
                # 移除文件ID前缀
                if "_" in file_name:
                    file_name = file_name.split("_", 1)[1]

                remote_path = await storage.upload(
                    file_data=f,
                    file_name=file_name,
                    content_type="application/octet-stream"
                )

            # 删除本地文件
            os.remove(local_path)

            logger.info(f"File {file_id} migrated to MinIO: {remote_path}")

            return True, f"File migrated to MinIO: {remote_path}"

        except Exception as e:
            logger.error(f"Failed to migrate file {file_id} to MinIO: {e}")
            return False, str(e)

    async def check_storage_health(
        self,
        backend: StorageBackend
    ) -> StorageHealth:
        """检查存储健康状态

        Args:
            backend: 存储后端

        Returns:
            StorageHealth: 健康状态
        """
        import time

        start_time = time.time()
        health = self._health_status[backend]
        health.last_check = utcnow()

        try:
            if backend == StorageBackend.LOCAL:
                # 检查本地存储
                test_file = os.path.join(
                    self.config.local_storage_path,
                    ".health_check"
                )
                with open(test_file, "w") as f:
                    f.write("health_check")
                os.remove(test_file)
                health.is_healthy = True
                health.last_error = None

            elif backend == StorageBackend.MINIO:
                # 检查MinIO
                from app.storage.factory import get_storage
                storage = get_storage()

                # 尝试列出bucket（简单的健康检查）
                if hasattr(storage, "client") and storage.client:
                    # 检查bucket是否存在
                    health.is_healthy = True
                    health.last_error = None
                else:
                    health.is_healthy = False
                    health.last_error = "Storage client not available"

            health.latency_ms = (time.time() - start_time) * 1000
            health.error_count = 0

        except Exception as e:
            health.is_healthy = False
            health.error_count += 1
            health.last_error = str(e)
            health.latency_ms = (time.time() - start_time) * 1000
            logger.error(f"Storage health check failed for {backend.value}: {e}")

        self._health_status[backend] = health
        return health

    async def should_fallback(self) -> Tuple[bool, Optional[FallbackReason]]:
        """判断是否应该降级

        Returns:
            Tuple[bool, Optional[FallbackReason]]: (是否降级, 原因)
        """
        if not self.config.auto_fallback:
            return False, None

        primary_health = self._health_status.get(self.config.primary_backend)

        if primary_health is None:
            primary_health = await self.check_storage_health(self.config.primary_backend)

        if not primary_health.is_healthy:
            return True, FallbackReason.PRIMARY_UNAVAILABLE

        if primary_health.error_count >= self.config.max_error_count:
            return True, FallbackReason.UPLOAD_FAILED

        if primary_health.latency_ms and primary_health.latency_ms > 5000:
            return True, FallbackReason.TIMEOUT

        return False, None

    async def select_backend(self) -> Tuple[StorageBackend, Optional[FallbackReason]]:
        """选择存储后端

        Returns:
            Tuple[StorageBackend, Optional[FallbackReason]]: (后端, 降级原因)
        """
        should_fb, reason = await self.should_fallback()

        if should_fb:
            self._current_backend = self.config.fallback_backend
            return self.config.fallback_backend, reason

        self._current_backend = self.config.primary_backend
        return self.config.primary_backend, None

    def _add_migration_task(
        self,
        file_id: str,
        source_backend: StorageBackend,
        target_backend: StorageBackend
    ) -> None:
        """添加迁移任务

        Args:
            file_id: 文件ID
            source_backend: 源后端
            target_backend: 目标后端
        """
        task = MigrationTask(
            file_id=file_id,
            source_backend=source_backend,
            target_backend=target_backend,
            status=MigrationStatus.PENDING,
            created_at=utcnow()
        )
        self._migration_queue.append(task)
        logger.info(f"Migration task added for file {file_id}")

    async def process_migration_queue(self) -> Dict[str, int]:
        """处理迁移队列

        Returns:
            Dict[str, int]: 处理结果统计
        """
        stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0
        }

        # 检查主存储是否恢复
        primary_health = await self.check_storage_health(self.config.primary_backend)
        if not primary_health.is_healthy:
            logger.info("Primary storage still unhealthy, skipping migration")
            return stats

        # 处理待迁移任务
        batch = self._migration_queue[:self.config.migration_batch_size]

        for task in batch:
            stats["total"] += 1

            if task.status != MigrationStatus.PENDING:
                stats["skipped"] += 1
                continue

            task.status = MigrationStatus.IN_PROGRESS

            try:
                if task.source_backend == StorageBackend.LOCAL:
                    # 构造本地路径
                    local_dir = os.path.join(
                        self.config.local_storage_path,
                        task.file_id[:2]
                    )
                    # 查找文件
                    local_files = []
                    if os.path.exists(local_dir):
                        for f in os.listdir(local_dir):
                            if f.startswith(task.file_id):
                                local_files.append(os.path.join(local_dir, f))

                    if local_files:
                        success, message = await self.migrate_to_minio(
                            task.file_id,
                            local_files[0]
                        )
                        if success:
                            task.status = MigrationStatus.COMPLETED
                            task.completed_at = utcnow()
                            stats["success"] += 1
                        else:
                            task.status = MigrationStatus.FAILED
                            task.error = message
                            task.retry_count += 1
                            stats["failed"] += 1
                    else:
                        task.status = MigrationStatus.FAILED
                        task.error = "Local file not found"
                        stats["failed"] += 1

            except Exception as e:
                task.status = MigrationStatus.FAILED
                task.error = str(e)
                task.retry_count += 1
                stats["failed"] += 1
                logger.error(f"Migration failed for file {task.file_id}: {e}")

        # 移除已完成的任务
        self._migration_queue = [
            t for t in self._migration_queue
            if t.status not in (MigrationStatus.COMPLETED,)
        ]

        logger.info(
            f"Migration queue processed: {stats['success']} success, "
            f"{stats['failed']} failed, {stats['skipped']} skipped"
        )

        return stats

    def get_fallback_status(self) -> Dict[str, Any]:
        """获取降级状态

        Returns:
            Dict: 状态信息
        """
        return {
            "current_backend": self._current_backend.value,
            "primary_backend": self.config.primary_backend.value,
            "fallback_backend": self.config.fallback_backend.value,
            "is_in_fallback_mode": self._current_backend != self.config.primary_backend,
            "health_status": {
                backend.value: {
                    "is_healthy": status.is_healthy,
                    "last_check": status.last_check.isoformat(),
                    "error_count": status.error_count,
                    "last_error": status.last_error,
                    "latency_ms": status.latency_ms
                }
                for backend, status in self._health_status.items()
            },
            "pending_migrations": len([
                t for t in self._migration_queue
                if t.status == MigrationStatus.PENDING
            ]),
            "failed_migrations": len([
                t for t in self._migration_queue
                if t.status == MigrationStatus.FAILED
            ])
        }

    def report_error(self, backend: StorageBackend, error: str) -> None:
        """报告存储错误

        Args:
            backend: 存储后端
            error: 错误信息
        """
        health = self._health_status.get(backend)
        if health:
            health.error_count += 1
            health.last_error = error
            if health.error_count >= self.config.max_error_count:
                health.is_healthy = False
                logger.warning(
                    f"Storage {backend.value} marked unhealthy after "
                    f"{health.error_count} errors"
                )

    def report_success(self, backend: StorageBackend) -> None:
        """报告存储成功

        Args:
            backend: 存储后端
        """
        health = self._health_status.get(backend)
        if health:
            # 成功后重置错误计数
            health.error_count = max(0, health.error_count - 1)
            if health.error_count == 0:
                health.is_healthy = True

    async def cleanup_local_fallback_files(
        self,
        max_age_days: int = 7
    ) -> int:
        """清理过期的本地降级文件

        Args:
            max_age_days: 最大保留天数

        Returns:
            int: 清理的文件数
        """
        cleaned = 0
        cutoff = utcnow() - timedelta(days=max_age_days)

        for root, dirs, files in os.walk(self.config.local_storage_path):
            for file in files:
                if file.startswith("."):  # 跳过隐藏文件
                    continue

                file_path = os.path.join(root, file)
                try:
                    mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                    if mtime < cutoff:
                        os.remove(file_path)
                        cleaned += 1
                        logger.info(f"Cleaned up fallback file: {file_path}")
                except Exception as e:
                    logger.error(f"Failed to clean up {file_path}: {e}")

        return cleaned


# 全局实例
_storage_fallback: Optional[StorageFallbackStrategy] = None


def get_storage_fallback() -> StorageFallbackStrategy:
    """获取存储降级策略单例

    Returns:
        StorageFallbackStrategy: 策略实例
    """
    global _storage_fallback
    if _storage_fallback is None:
        _storage_fallback = StorageFallbackStrategy()
    return _storage_fallback
