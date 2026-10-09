# backend/app/files/lifecycle_manager.py
"""文件生命周期管理器

根据详细设计说明书 6.3 节实现。
负责文件过期管理、清理策略、永久保存标记等功能。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import logging
import json

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.time import utcnow
from app.files.file_records import delete_stored_content
from app.models.files import File, FileAccessLog
from app.models.tasks import Task, TaskInput

logger = logging.getLogger(__name__)


@dataclass
class CleanupResult:
    """清理结果"""
    cleaned_count: int
    freed_bytes: int
    errors: List[Dict[str, Any]]
    skipped_in_use: int
    timestamp: str


@dataclass
class FileStatistics:
    """文件统计信息"""
    total_files: int
    total_size_bytes: int
    permanent_files: int
    expiring_soon: int  # 7天内过期
    expired_pending_cleanup: int
    average_file_size: int


class FileLifecycleManager:
    """文件生命周期管理器

    负责：
    1. 延长文件过期时间
    2. 标记文件为永久保存
    3. 清理过期文件（定时任务）
    4. 检查文件是否被任务使用
    5. 获取文件统计信息
    """

    # 默认过期天数
    DEFAULT_EXPIRATION_DAYS = 30

    # 临时文件过期天数
    TEMP_EXPIRATION_DAYS = 7

    # 输出文件过期天数
    OUTPUT_EXPIRATION_DAYS = 90

    # 即将过期的定义（天数）
    EXPIRING_SOON_DAYS = 7

    def __init__(self, db: AsyncSession, storage_backend=None, cache_client=None):
        """初始化文件生命周期管理器

        Args:
            db: 数据库会话
            storage_backend: 存储后端（可选）
            cache_client: 缓存客户端（可选，用于记录清理日志）
        """
        self.db = db
        self.storage = storage_backend
        self.cache = cache_client

    async def extend_expiration(
        self,
        file_id: str,
        days: int,
        user_id: Optional[str] = None
    ) -> File:
        """延长文件过期时间

        Args:
            file_id: 文件ID
            days: 延长天数
            user_id: 操作用户ID（可选）

        Returns:
            File: 更新后的文件对象

        Raises:
            FileNotFoundError: 文件不存在
        """
        result = await self.db.execute(
            select(File).where(
                File.id == file_id,
                File.deleted_at == None
            )
        )
        file = result.scalar_one_or_none()

        if not file:
            raise FileNotFoundError(f"File not found: {file_id}")

        # 计算新的过期时间
        now = utcnow()
        if file.expires_at:
            new_expires_at = max(
                file.expires_at,
                now + timedelta(days=days)
            )
        else:
            new_expires_at = now + timedelta(days=days)

        file.expires_at = new_expires_at
        await self.db.commit()
        await self.db.refresh(file)

        # 记录访问日志
        await self._log_access(
            file_id=file_id,
            user_id=user_id,
            action="extend_expiration"
        )

        logger.info(
            f"Extended file {file_id} expiration to {new_expires_at}",
            extra={
                "file_id": file_id,
                "new_expires_at": new_expires_at.isoformat(),
                "user_id": user_id
            }
        )

        return file

    async def mark_permanent(
        self,
        file_id: str,
        user_id: Optional[str] = None
    ) -> File:
        """标记文件为永久保存

        Args:
            file_id: 文件ID
            user_id: 操作用户ID

        Returns:
            File: 更新后的文件对象

        Raises:
            FileNotFoundError: 文件不存在
        """
        result = await self.db.execute(
            select(File).where(
                File.id == file_id,
                File.deleted_at == None
            )
        )
        file = result.scalar_one_or_none()

        if not file:
            raise FileNotFoundError(f"File not found: {file_id}")

        file.expires_at = None
        file.is_permanent = True
        await self.db.commit()
        await self.db.refresh(file)

        # 记录访问日志
        await self._log_access(
            file_id=file_id,
            user_id=user_id,
            action="mark_permanent"
        )

        logger.info(
            f"Marked file {file_id} as permanent",
            extra={"file_id": file_id, "user_id": user_id}
        )

        return file

    async def remove_permanent(
        self,
        file_id: str,
        expiration_days: int = DEFAULT_EXPIRATION_DAYS,
        user_id: Optional[str] = None
    ) -> File:
        """取消文件永久保存标记

        Args:
            file_id: 文件ID
            expiration_days: 新的过期天数
            user_id: 操作用户ID

        Returns:
            File: 更新后的文件对象
        """
        result = await self.db.execute(
            select(File).where(
                File.id == file_id,
                File.deleted_at == None
            )
        )
        file = result.scalar_one_or_none()

        if not file:
            raise FileNotFoundError(f"File not found: {file_id}")

        file.is_permanent = False
        file.expires_at = utcnow() + timedelta(days=expiration_days)
        await self.db.commit()
        await self.db.refresh(file)

        logger.info(
            f"Removed permanent flag from file {file_id}",
            extra={"file_id": file_id, "user_id": user_id}
        )

        return file

    async def cleanup_expired_files(
        self,
        batch_size: int = 100,
        dry_run: bool = False
    ) -> CleanupResult:
        """清理过期文件（定时任务）

        Args:
            batch_size: 每批处理的文件数
            dry_run: 是否为试运行（不实际删除）

        Returns:
            CleanupResult: 清理结果
        """
        now = utcnow()
        cleaned_count = 0
        freed_bytes = 0
        skipped_in_use = 0
        errors = []

        # 查询过期文件
        result = await self.db.execute(
            select(File).where(
                File.expires_at != None,
                File.expires_at < now,
                File.is_permanent == False,
                File.deleted_at == None  # 未被软删除
            ).limit(batch_size)
        )
        expired_files = result.scalars().all()

        for file in expired_files:
            try:
                # 检查是否有任务正在使用
                tasks_using = await self._check_active_tasks(file.id)
                if tasks_using:
                    logger.info(
                        f"File {file.id} is in use by tasks {tasks_using}, skipping cleanup"
                    )
                    skipped_in_use += 1
                    # 延长过期时间，等待任务完成
                    file.expires_at = now + timedelta(hours=24)
                    continue

                if not dry_run:
                    # 从存储后端删除
                    try:
                        await delete_stored_content(file, self.storage)
                    except Exception as e:
                        logger.warning(
                            f"Failed to delete file from storage: {file.storage_path}, {e}"
                        )

                    # 软删除（设置deleted_at）
                    file.deleted_at = now

                freed_bytes += file.size_bytes
                cleaned_count += 1

            except Exception as e:
                logger.error(f"Failed to cleanup file {file.id}: {e}")
                errors.append({
                    "file_id": file.id,
                    "filename": file.filename,
                    "error": str(e)
                })

        if not dry_run:
            await self.db.commit()

        # 构建结果
        cleanup_result = CleanupResult(
            cleaned_count=cleaned_count,
            freed_bytes=freed_bytes,
            errors=errors,
            skipped_in_use=skipped_in_use,
            timestamp=now.isoformat()
        )

        # 记录清理日志到缓存
        await self._log_cleanup(cleanup_result)

        logger.info(
            f"Cleanup completed: {cleaned_count} files, {freed_bytes // 1024 // 1024}MB freed",
            extra={
                "cleaned_count": cleaned_count,
                "freed_mb": freed_bytes // 1024 // 1024,
                "skipped_in_use": skipped_in_use,
                "errors_count": len(errors),
                "dry_run": dry_run
            }
        )

        return cleanup_result

    async def _check_active_tasks(self, file_id: str) -> List[str]:
        """检查是否有任务正在使用该文件

        Args:
            file_id: 文件ID

        Returns:
            List[str]: 正在使用该文件的任务ID列表
        """
        try:
            # 查询正在执行或等待中的任务
            # 这里假设TaskInput中有file_ids字段存储关联的文件ID
            result = await self.db.execute(
                select(Task.id, TaskInput.file_ids).where(
                    Task.status.in_(["pending", "running", "queued"]),
                ).join(
                    TaskInput, Task.id == TaskInput.task_id
                )
            )
            return [
                str(task_id)
                for task_id, file_ids in result.all()
                if file_id in (file_ids or [])
            ]
        except Exception as e:
            logger.warning(f"Failed to check active tasks for file {file_id}: {e}")
            return []

    async def get_file_statistics(self) -> FileStatistics:
        """获取文件统计信息

        Returns:
            FileStatistics: 文件统计信息
        """
        now = utcnow()

        # 总文件数和大小
        total_result = await self.db.execute(
            select(
                func.count(File.id),
                func.coalesce(func.sum(File.size_bytes), 0)
            ).where(File.deleted_at == None)
        )
        total_count, total_size = total_result.one()

        # 永久文件数
        permanent_result = await self.db.execute(
            select(func.count(File.id)).where(
                File.is_permanent == True,
                File.deleted_at == None
            )
        )
        permanent_count = permanent_result.scalar() or 0

        # 即将过期文件(7天内)
        expiring_soon_result = await self.db.execute(
            select(func.count(File.id)).where(
                File.expires_at != None,
                File.expires_at > now,
                File.expires_at < now + timedelta(days=self.EXPIRING_SOON_DAYS),
                File.is_permanent == False,
                File.deleted_at == None
            )
        )
        expiring_soon = expiring_soon_result.scalar() or 0

        # 已过期待清理文件
        expired_result = await self.db.execute(
            select(func.count(File.id)).where(
                File.expires_at != None,
                File.expires_at < now,
                File.is_permanent == False,
                File.deleted_at == None
            )
        )
        expired_pending = expired_result.scalar() or 0

        # 计算平均文件大小
        avg_size = total_size // total_count if total_count > 0 else 0

        return FileStatistics(
            total_files=total_count or 0,
            total_size_bytes=total_size or 0,
            permanent_files=permanent_count,
            expiring_soon=expiring_soon,
            expired_pending_cleanup=expired_pending,
            average_file_size=avg_size
        )

    async def get_files_expiring_soon(
        self,
        days: int = EXPIRING_SOON_DAYS,
        limit: int = 100
    ) -> List[File]:
        """获取即将过期的文件列表

        Args:
            days: 过期天数阈值
            limit: 返回数量限制

        Returns:
            List[File]: 即将过期的文件列表
        """
        now = utcnow()
        result = await self.db.execute(
            select(File).where(
                File.expires_at != None,
                File.expires_at > now,
                File.expires_at < now + timedelta(days=days),
                File.is_permanent == False,
                File.deleted_at == None
            ).order_by(File.expires_at).limit(limit)
        )
        return list(result.scalars().all())

    async def set_expiration(
        self,
        file_id: str,
        expires_at: datetime,
        user_id: Optional[str] = None
    ) -> File:
        """设置文件过期时间

        Args:
            file_id: 文件ID
            expires_at: 过期时间
            user_id: 操作用户ID

        Returns:
            File: 更新后的文件对象
        """
        result = await self.db.execute(
            select(File).where(
                File.id == file_id,
                File.deleted_at == None
            )
        )
        file = result.scalar_one_or_none()

        if not file:
            raise FileNotFoundError(f"File not found: {file_id}")

        file.expires_at = expires_at
        file.is_permanent = False
        await self.db.commit()
        await self.db.refresh(file)

        logger.info(
            f"Set file {file_id} expiration to {expires_at}",
            extra={"file_id": file_id, "expires_at": expires_at.isoformat()}
        )

        return file

    async def _log_access(
        self,
        file_id: str,
        user_id: Optional[str],
        action: str,
    ) -> None:
        """记录文件访问日志"""
        access_log = FileAccessLog(
            file_id=file_id,
            user_id=user_id,
            action=action,
            accessed_at=utcnow()
        )
        self.db.add(access_log)

    async def _log_cleanup(self, result: CleanupResult) -> None:
        """记录清理日志到缓存"""
        if not self.cache:
            return

        try:
            log_data = {
                "timestamp": result.timestamp,
                "cleaned_count": result.cleaned_count,
                "freed_mb": result.freed_bytes // 1024 // 1024,
                "skipped_in_use": result.skipped_in_use,
                "errors": result.errors
            }

            await self.cache.lpush(
                "file:cleanup:logs",
                json.dumps(log_data)
            )
            await self.cache.ltrim("file:cleanup:logs", 0, 99)  # 保留最近100条
        except Exception as e:
            logger.warning(f"Failed to log cleanup result to cache: {e}")

    async def purge_deleted_files(
        self,
        older_than_days: int = 30,
        batch_size: int = 100
    ) -> int:
        """永久删除软删除的文件（物理删除）

        Args:
            older_than_days: 软删除超过多少天的文件才会被物理删除
            batch_size: 每批处理数量

        Returns:
            int: 删除的文件数
        """
        cutoff = utcnow() - timedelta(days=older_than_days)

        result = await self.db.execute(
            select(File).where(
                File.deleted_at != None,
                File.deleted_at < cutoff
            ).limit(batch_size)
        )
        files_to_purge = result.scalars().all()

        purged_count = 0
        for file in files_to_purge:
            try:
                # 物理删除数据库记录
                await self.db.delete(file)
                purged_count += 1
            except Exception as e:
                logger.error(f"Failed to purge file {file.id}: {e}")

        await self.db.commit()

        logger.info(f"Purged {purged_count} soft-deleted files")
        return purged_count
