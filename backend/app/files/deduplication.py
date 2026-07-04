# backend/app/files/deduplication.py
"""文件去重管理器

根据详细设计说明书 6.2 节实现。
负责基于内容哈希的文件去重，避免重复存储。
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Optional
import hashlib
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.time import utcnow
from app.models.files import File, FileAccessLog

logger = logging.getLogger(__name__)


@dataclass
class DeduplicationResult:
    """去重结果"""
    is_duplicate: bool
    file: Optional[File]
    original_file_id: Optional[str] = None
    space_saved_bytes: int = 0


class FileDeduplicator:
    """文件去重管理器

    基于SHA256哈希值进行文件去重：
    1. 计算文件哈希
    2. 查找是否存在相同哈希的文件
    3. 如果存在，创建引用而非重复存储
    4. 维护文件引用计数
    """

    # 默认文件保留时间
    DEFAULT_RETENTION_DAYS = 30

    def __init__(self, db: AsyncSession):
        """初始化去重管理器

        Args:
            db: 数据库会话
        """
        self.db = db

    @staticmethod
    def calculate_hash(content: bytes) -> str:
        """计算文件内容的SHA256哈希

        Args:
            content: 文件内容

        Returns:
            str: SHA256哈希值（十六进制字符串）
        """
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    async def calculate_hash_streaming(file_stream, chunk_size: int = 8192) -> str:
        """流式计算文件哈希（适用于大文件）

        Args:
            file_stream: 文件流对象
            chunk_size: 块大小

        Returns:
            str: SHA256哈希值
        """
        sha256 = hashlib.sha256()

        while True:
            chunk = await file_stream.read(chunk_size)
            if not chunk:
                break
            sha256.update(chunk)

        # 重置流位置
        await file_stream.seek(0)

        return sha256.hexdigest()

    async def deduplicate(
        self,
        sha256: str,
        new_owner_id: Optional[str] = None,
        session_id: Optional[str] = None,
        extend_retention: bool = True
    ) -> DeduplicationResult:
        """文件去重

        检查是否存在相同哈希的文件：
        - 如果存在：返回现有文件，创建用户引用
        - 如果不存在：返回None，调用方需要继续上传

        Args:
            sha256: 文件SHA256哈希
            new_owner_id: 新所有者用户ID
            session_id: 游客Session ID
            extend_retention: 是否延长保留时间

        Returns:
            DeduplicationResult: 去重结果
        """
        # 查找已有文件
        existing = await self._find_by_hash(sha256)

        if not existing:
            return DeduplicationResult(
                is_duplicate=False,
                file=None
            )

        # 记录访问（创建用户引用）
        await self._create_user_reference(
            existing.id,
            new_owner_id,
            session_id
        )

        # 延长文件过期时间
        if extend_retention and existing.expires_at:
            new_expires_at = max(
                existing.expires_at,
                utcnow() + timedelta(days=self.DEFAULT_RETENTION_DAYS)
            )
            existing.expires_at = new_expires_at

        # 增加引用计数
        existing.reference_count = (existing.reference_count or 1) + 1

        await self.db.commit()
        await self.db.refresh(existing)

        logger.info(
            f"File deduplicated: {sha256[:16]}... -> {existing.id}",
            extra={
                "file_id": existing.id,
                "sha256": sha256,
                "owner_id": new_owner_id,
                "reference_count": existing.reference_count
            }
        )

        return DeduplicationResult(
            is_duplicate=True,
            file=existing,
            original_file_id=existing.id,
            space_saved_bytes=existing.size
        )

    async def _find_by_hash(self, sha256: str) -> Optional[File]:
        """根据SHA256查找文件

        Args:
            sha256: SHA256哈希值

        Returns:
            Optional[File]: 找到的文件，或None
        """
        result = await self.db.execute(
            select(File).where(
                File.sha256 == sha256,
                File.deleted_at == None  # 未删除的文件
            )
        )
        return result.scalar_one_or_none()

    async def _create_user_reference(
        self,
        file_id: str,
        user_id: Optional[str],
        session_id: Optional[str]
    ) -> None:
        """创建用户文件引用（通过访问日志记录）

        Args:
            file_id: 文件ID
            user_id: 用户ID
            session_id: 游客Session ID
        """
        access_log = FileAccessLog(
            file_id=file_id,
            user_id=user_id,
            session_id=session_id,
            action="reference",
            accessed_at=utcnow()
        )
        self.db.add(access_log)

    async def check_exists(self, sha256: str) -> bool:
        """检查文件是否已存在

        Args:
            sha256: SHA256哈希值

        Returns:
            bool: 是否存在
        """
        result = await self.db.execute(
            select(File.id).where(
                File.sha256 == sha256,
                File.deleted_at == None
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def get_duplicate_info(self, sha256: str) -> Optional[dict]:
        """获取重复文件信息

        Args:
            sha256: SHA256哈希值

        Returns:
            Optional[dict]: 文件信息字典，或None
        """
        file = await self._find_by_hash(sha256)
        if not file:
            return None

        return {
            "file_id": file.id,
            "filename": file.filename,
            "size": file.size,
            "reference_count": file.reference_count or 1,
            "created_at": file.created_at.isoformat() if file.created_at else None,
            "expires_at": file.expires_at.isoformat() if file.expires_at else None
        }

    async def decrement_reference(self, file_id: str) -> int:
        """减少文件引用计数

        Args:
            file_id: 文件ID

        Returns:
            int: 新的引用计数
        """
        result = await self.db.execute(
            select(File).where(File.id == file_id)
        )
        file = result.scalar_one_or_none()

        if not file:
            return 0

        new_count = max(0, (file.reference_count or 1) - 1)
        file.reference_count = new_count

        await self.db.commit()

        logger.debug(
            f"Decremented reference count for file {file_id}: {new_count}",
            extra={"file_id": file_id, "reference_count": new_count}
        )

        return new_count

    async def can_delete(self, file_id: str) -> bool:
        """检查文件是否可以删除

        文件只有在引用计数为0且已过期时才能删除。

        Args:
            file_id: 文件ID

        Returns:
            bool: 是否可以删除
        """
        result = await self.db.execute(
            select(File).where(File.id == file_id)
        )
        file = result.scalar_one_or_none()

        if not file:
            return False

        # 检查引用计数
        if (file.reference_count or 1) > 0:
            return False

        # 检查是否过期
        if file.expires_at and file.expires_at > utcnow():
            return False

        return True

    async def get_storage_stats(self) -> dict:
        """获取存储统计

        Returns:
            dict: 存储统计信息
        """
        from sqlalchemy import func

        # 总文件数和大小
        total_result = await self.db.execute(
            select(
                func.count(File.id),
                func.sum(File.size)
            ).where(File.deleted_at == None)
        )
        total_count, total_size = total_result.one()

        # 去重节省的空间（引用计数>1的文件）
        dedup_result = await self.db.execute(
            select(
                func.sum(File.size * (File.reference_count - 1))
            ).where(
                File.deleted_at == None,
                File.reference_count > 1
            )
        )
        space_saved = dedup_result.scalar() or 0

        return {
            "total_files": total_count or 0,
            "total_size_bytes": total_size or 0,
            "space_saved_bytes": space_saved,
            "deduplication_ratio": (
                space_saved / (total_size + space_saved) * 100
                if total_size else 0
            )
        }
