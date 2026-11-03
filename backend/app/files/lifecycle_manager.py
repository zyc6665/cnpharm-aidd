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

from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.time import utcnow
from app.models.artifacts import ArtifactVersionFile
from app.models.files import File, FileAccessLog
from app.models.tasks import TaskInput, TaskOutput

logger = logging.getLogger(__name__)

# ``_process_expired_file`` 的处置结果取值（供计数分支使用）。
_OUTCOME_PERMANENT = "skipped_permanent"
_OUTCOME_REFERENCED = "skipped_referenced"
_OUTCOME_SOFT_DELETED = "soft_deleted"
_OUTCOME_ALREADY_DELETED = "skipped_already_deleted"


def _as_id_list(value: Any) -> List[str]:
    """把 JSON 列 ``file_ids`` 归一成字符串列表。

    兼容已反序列化的 list（SQLite/PG 读回）与原始 JSON 字符串（历史脏数据）。
    """
    if not value:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return []
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value]


@dataclass
class CleanupResult:
    """清理结果

    只统计**软删除**，不含物理删除字节数——blob 回收由 ``artifact_gc`` 负责。
    """
    scanned: int
    skipped_referenced: int
    skipped_permanent: int
    soft_deleted: int
    failed: int
    errors: List[Dict[str, Any]]
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

        只做**软删除**（置 ``deleted_at``），绝不删除底层对象存储中的 blob：
        blob 回收统一交给 ``app.services.artifact_gc``（那里已按
        ``ArtifactVersionFile`` 引用做孤儿判定，见 ``artifact_gc.py:78-110``）。

        跳过规则：

        * 仍被 ``ArtifactVersionFile`` / ``TaskInput.file_ids`` /
          ``TaskOutput.file_ids`` 任一引用 → 跳过（计入 ``skipped_referenced``）；
        * ``is_permanent=True`` → 跳过（计入 ``skipped_permanent``）；
        * 已 ``deleted_at`` → 跳过（幂等；不计入任何计数器）。

        单条失败只记日志并继续，不会中断整批。返回值携带
        ``scanned/skipped_referenced/skipped_permanent/soft_deleted/failed``
        及 ``errors`` 明细，供调用方与日志使用。

        Args:
            batch_size: 每批处理的文件数
            dry_run: 是否为试运行（不实际写入 soft-delete 标记）

        Returns:
            CleanupResult: 清理结果
        """
        now = utcnow()
        skipped_referenced = 0
        skipped_permanent = 0
        soft_deleted = 0
        failed = 0
        errors: List[Dict[str, Any]] = []

        # 查询过期文件（不预过滤 is_permanent/deleted_at，以便如实统计跳过原因；
        # 已软删的行只是重复扫描，不会造成副作用，且 purge_deleted_files 会物理回收）。
        result = await self.db.execute(
            select(File).where(
                File.expires_at != None,
                File.expires_at < now,
            ).limit(batch_size)
        )
        expired_files = list(result.scalars().all())
        scanned = len(expired_files)

        # 一次性批量查询引用关系（每张表至多一条 SQL）。
        reference_sources = await self._collect_reference_sources(
            [str(file.id) for file in expired_files]
        )

        for file in expired_files:
            try:
                outcome = await self._process_expired_file(
                    file,
                    reference_sources,
                    now=now,
                    dry_run=dry_run,
                )
            except Exception as e:  # noqa: BLE001 - 单条失败不阻塞整批
                failed += 1
                logger.error(
                    "清理过期文件失败: file_id=%s 错误=%s", file.id, e
                )
                errors.append({
                    "file_id": str(file.id),
                    "filename": file.filename,
                    "error": str(e),
                })
                continue

            if outcome == _OUTCOME_REFERENCED:
                skipped_referenced += 1
            elif outcome == _OUTCOME_PERMANENT:
                skipped_permanent += 1
            elif outcome == _OUTCOME_SOFT_DELETED:
                soft_deleted += 1

        if not dry_run:
            await self.db.commit()

        # 构建结果
        cleanup_result = CleanupResult(
            scanned=scanned,
            skipped_referenced=skipped_referenced,
            skipped_permanent=skipped_permanent,
            soft_deleted=soft_deleted,
            failed=failed,
            errors=errors,
            timestamp=now.isoformat(),
        )

        # 记录清理日志到缓存
        await self._log_cleanup(cleanup_result)

        logger.info(
            "过期文件清理完成: scanned=%s skipped_referenced=%s "
            "skipped_permanent=%s soft_deleted=%s failed=%s dry_run=%s",
            scanned,
            skipped_referenced,
            skipped_permanent,
            soft_deleted,
            failed,
            dry_run,
            extra={
                "scanned": scanned,
                "skipped_referenced": skipped_referenced,
                "skipped_permanent": skipped_permanent,
                "soft_deleted": soft_deleted,
                "failed": failed,
                "dry_run": dry_run,
            },
        )

        return cleanup_result

    async def _process_expired_file(
        self,
        file: File,
        reference_sources: Dict[str, List[str]],
        *,
        now: datetime,
        dry_run: bool,
    ) -> str:
        """处置单个过期文件并返回结果常量（异常由调用方兜底）。"""
        file_id = str(file.id)

        if file.is_permanent:
            logger.info(
                "跳过永久文件，不做清理: file_id=%s",
                file_id,
                extra={"file_id": file_id, "reason": "is_permanent"},
            )
            return _OUTCOME_PERMANENT

        if file.deleted_at is not None:
            # 已经软删除，幂等跳过。
            return _OUTCOME_ALREADY_DELETED

        sources = reference_sources.get(file_id) or []
        if sources:
            logger.info(
                "跳过仍被引用的过期文件: file_id=%s 引用来源=%s",
                file_id,
                ",".join(sources),
                extra={"file_id": file_id, "reference_sources": sources},
            )
            return _OUTCOME_REFERENCED

        if not dry_run:
            # 只置软删除标记，绝不删除 blob（blob 由 artifact_gc 孤儿回收负责）。
            file.deleted_at = now
        logger.info(
            "软删除过期文件（保留 blob）: file_id=%s",
            file_id,
            extra={"file_id": file_id, "action": "soft_delete"},
        )
        return _OUTCOME_SOFT_DELETED

    async def _collect_reference_sources(
        self, file_ids: List[str]
    ) -> Dict[str, List[str]]:
        """返回每个 ``file_id`` 仍被哪些表引用。

        覆盖三张表：``ArtifactVersionFile``、``TaskInput.file_ids``、
        ``TaskOutput.file_ids``。后两者是 JSON 数组且无外键，数据库拦不住删除，
        因此用 ``CAST(json AS TEXT) LIKE`` 预筛后，再在 Python 里按数组成员精确
        判定，避免 ``file-1`` 误命中 ``file-10`` 之类的子串。

        每张表只发一条 SQL（O(1) 往返），不随文件数量线性增长。
        """
        sources: Dict[str, List[str]] = {file_id: [] for file_id in file_ids}
        if not file_ids:
            return sources

        rows = await self.db.execute(
            select(ArtifactVersionFile.file_id).where(
                ArtifactVersionFile.file_id.in_(file_ids)
            )
        )
        for (file_id,) in rows.all():
            key = str(file_id)
            if key in sources and "ArtifactVersionFile" not in sources[key]:
                sources[key].append("ArtifactVersionFile")

        for model, label in ((TaskInput, "TaskInput"), (TaskOutput, "TaskOutput")):
            predicates = [
                cast(model.file_ids, Text).like(f'%"{file_id}"%')
                for file_id in file_ids
            ]
            rows = await self.db.execute(
                select(model.file_ids).where(or_(*predicates))
            )
            blobs = [_as_id_list(row[0]) for row in rows.all()]
            for file_id in file_ids:
                if label in sources[file_id]:
                    continue
                if any(file_id in blob for blob in blobs):
                    sources[file_id].append(label)

        return sources

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
                "scanned": result.scanned,
                "skipped_referenced": result.skipped_referenced,
                "skipped_permanent": result.skipped_permanent,
                "soft_deleted": result.soft_deleted,
                "failed": result.failed,
                "errors": result.errors,
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
