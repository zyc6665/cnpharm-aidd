# backend/app/files/reference_manager.py
"""文件引用计数管理器

负责管理文件的引用计数，支持：
1. 增加引用计数
2. 减少引用计数
3. 获取引用计数
4. 尝试早期清理（引用计数为0时）
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.files import File, FileAccessLog

logger = logging.getLogger(__name__)


class ReferenceManagerError(Exception):
    """引用管理器错误"""
    pass


class FileReferenceManager:
    """文件引用计数管理器

    管理文件的引用计数，当引用计数降为0时，
    根据策略决定是否立即删除或等待过期。
    """

    # 引用计数为0后的保留时间（天）
    ZERO_REFERENCE_RETENTION_DAYS = 7

    def __init__(self, db: AsyncSession, storage_backend=None):
        """初始化引用管理器

        Args:
            db: 数据库会话
            storage_backend: 存储后端（可选）
        """
        self.db = db
        self.storage = storage_backend

    async def increment_reference(
        self,
        file_id: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        reason: str = "reference"
    ) -> int:
        """增加文件引用计数

        Args:
            file_id: 文件ID
            user_id: 用户ID（可选）
            session_id: 会话ID（可选）
            reason: 引用原因

        Returns:
            int: 新的引用计数

        Raises:
            ReferenceManagerError: 文件不存在或已删除
        """
        result = await self.db.execute(
            select(File).where(
                File.id == file_id,
                File.deleted_at == None
            )
        )
        file = result.scalar_one_or_none()

        if not file:
            raise ReferenceManagerError(f"File not found or deleted: {file_id}")

        # 增加引用计数
        new_count = (file.reference_count or 0) + 1
        file.reference_count = new_count

        # 更新最后访问时间
        file.last_accessed_at = datetime.utcnow()

        # 记录访问日志
        access_log = FileAccessLog(
            file_id=file_id,
            user_id=user_id,
            session_id=session_id,
            action=f"increment_reference:{reason}",
            accessed_at=datetime.utcnow()
        )
        self.db.add(access_log)

        await self.db.commit()

        logger.debug(
            f"Incremented reference count for file {file_id}: {new_count}",
            extra={
                "file_id": file_id,
                "reference_count": new_count,
                "reason": reason
            }
        )

        return new_count

    async def decrement_reference(
        self,
        file_id: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        reason: str = "dereference",
        auto_cleanup: bool = False
    ) -> int:
        """减少文件引用计数

        Args:
            file_id: 文件ID
            user_id: 用户ID（可选）
            session_id: 会话ID（可选）
            reason: 解除引用原因
            auto_cleanup: 是否在引用计数为0时自动清理

        Returns:
            int: 新的引用计数

        Raises:
            ReferenceManagerError: 文件不存在
        """
        result = await self.db.execute(
            select(File).where(
                File.id == file_id,
                File.deleted_at == None
            )
        )
        file = result.scalar_one_or_none()

        if not file:
            raise ReferenceManagerError(f"File not found or deleted: {file_id}")

        # 减少引用计数（最小为0）
        new_count = max(0, (file.reference_count or 1) - 1)
        file.reference_count = new_count

        # 记录访问日志
        access_log = FileAccessLog(
            file_id=file_id,
            user_id=user_id,
            session_id=session_id,
            action=f"decrement_reference:{reason}",
            accessed_at=datetime.utcnow()
        )
        self.db.add(access_log)

        await self.db.commit()

        logger.debug(
            f"Decremented reference count for file {file_id}: {new_count}",
            extra={
                "file_id": file_id,
                "reference_count": new_count,
                "reason": reason
            }
        )

        # 尝试早期清理
        if auto_cleanup and new_count == 0:
            await self._try_early_cleanup(file)

        return new_count

    async def get_reference_count(self, file_id: str) -> int:
        """获取文件引用计数

        Args:
            file_id: 文件ID

        Returns:
            int: 引用计数

        Raises:
            ReferenceManagerError: 文件不存在
        """
        result = await self.db.execute(
            select(File.reference_count).where(
                File.id == file_id,
                File.deleted_at == None
            )
        )
        count = result.scalar_one_or_none()

        if count is None:
            raise ReferenceManagerError(f"File not found or deleted: {file_id}")

        return count or 0

    async def _try_early_cleanup(self, file: File) -> bool:
        """尝试早期清理（当引用计数为0时）

        只有满足以下条件时才会执行早期清理：
        1. 引用计数为0
        2. 不是永久文件
        3. 文件已过期 或 设置了短期过期

        Args:
            file: 文件对象

        Returns:
            bool: 是否执行了清理
        """
        # 永久文件不清理
        if file.is_permanent:
            return False

        # 引用计数不为0不清理
        if (file.reference_count or 0) > 0:
            return False

        now = datetime.utcnow()

        # 如果已过期，设置为软删除
        if file.expires_at and file.expires_at < now:
            file.deleted_at = now

            # 尝试从存储删除
            if self.storage:
                try:
                    await self.storage.delete(file.storage_path)
                except Exception as e:
                    logger.warning(
                        f"Failed to delete file from storage during early cleanup: {e}"
                    )

            await self.db.commit()

            logger.info(
                f"Early cleanup executed for file {file.id}",
                extra={"file_id": file.id, "filename": file.filename}
            )
            return True

        # 如果没有过期时间，设置短期过期
        if not file.expires_at:
            file.expires_at = now + timedelta(days=self.ZERO_REFERENCE_RETENTION_DAYS)
            await self.db.commit()

            logger.info(
                f"Set short-term expiration for zero-reference file {file.id}",
                extra={
                    "file_id": file.id,
                    "expires_at": file.expires_at.isoformat()
                }
            )

        return False

    async def batch_increment(
        self,
        file_ids: list[str],
        user_id: Optional[str] = None,
        reason: str = "batch_reference"
    ) -> Dict[str, int]:
        """批量增加引用计数

        Args:
            file_ids: 文件ID列表
            user_id: 用户ID
            reason: 引用原因

        Returns:
            Dict[str, int]: 文件ID到新引用计数的映射
        """
        results = {}

        for file_id in file_ids:
            try:
                count = await self.increment_reference(
                    file_id=file_id,
                    user_id=user_id,
                    reason=reason
                )
                results[file_id] = count
            except ReferenceManagerError as e:
                logger.warning(f"Failed to increment reference for {file_id}: {e}")
                results[file_id] = -1  # -1 表示错误

        return results

    async def batch_decrement(
        self,
        file_ids: list[str],
        user_id: Optional[str] = None,
        reason: str = "batch_dereference",
        auto_cleanup: bool = False
    ) -> Dict[str, int]:
        """批量减少引用计数

        Args:
            file_ids: 文件ID列表
            user_id: 用户ID
            reason: 解除引用原因
            auto_cleanup: 是否自动清理

        Returns:
            Dict[str, int]: 文件ID到新引用计数的映射
        """
        results = {}

        for file_id in file_ids:
            try:
                count = await self.decrement_reference(
                    file_id=file_id,
                    user_id=user_id,
                    reason=reason,
                    auto_cleanup=auto_cleanup
                )
                results[file_id] = count
            except ReferenceManagerError as e:
                logger.warning(f"Failed to decrement reference for {file_id}: {e}")
                results[file_id] = -1

        return results

    async def get_zero_reference_files(
        self,
        limit: int = 100
    ) -> list[File]:
        """获取引用计数为0的文件列表

        Args:
            limit: 返回数量限制

        Returns:
            list[File]: 文件列表
        """
        result = await self.db.execute(
            select(File).where(
                File.reference_count == 0,
                File.deleted_at == None,
                File.is_permanent == False
            ).limit(limit)
        )
        return list(result.scalars().all())

    async def get_reference_info(self, file_id: str) -> Dict[str, Any]:
        """获取文件引用详情

        Args:
            file_id: 文件ID

        Returns:
            Dict[str, Any]: 引用详情
        """
        result = await self.db.execute(
            select(File).where(
                File.id == file_id,
                File.deleted_at == None
            )
        )
        file = result.scalar_one_or_none()

        if not file:
            raise ReferenceManagerError(f"File not found: {file_id}")

        # 获取最近的引用日志
        logs_result = await self.db.execute(
            select(FileAccessLog).where(
                FileAccessLog.file_id == file_id,
                FileAccessLog.action.like("%reference%")
            ).order_by(FileAccessLog.accessed_at.desc()).limit(10)
        )
        logs = logs_result.scalars().all()

        return {
            "file_id": file.id,
            "filename": file.filename,
            "reference_count": file.reference_count or 0,
            "is_permanent": file.is_permanent,
            "expires_at": file.expires_at.isoformat() if file.expires_at else None,
            "last_accessed_at": file.last_accessed_at.isoformat() if file.last_accessed_at else None,
            "recent_reference_logs": [
                {
                    "action": log.action,
                    "user_id": log.user_id,
                    "accessed_at": log.accessed_at.isoformat()
                }
                for log in logs
            ]
        }
