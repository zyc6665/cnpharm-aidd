# backend/app/auth/guest_manager.py
"""游客Session管理器

根据详细设计说明书 2.2 节实现。
负责游客Session的创建、验证、配额检查和数据迁移。
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, date
from typing import Any, Dict, Optional, TYPE_CHECKING
import logging

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.users import UserSession

if TYPE_CHECKING:
    from app.cache.base import CacheBackend

logger = logging.getLogger(__name__)


@dataclass
class GuestLimitations:
    """游客限制配置"""
    daily_task_limit: int = 5
    max_file_size_mb: int = 10
    available_tools: int = 3  # 仅允许访问3个核心工具
    max_concurrent_tasks: int = 1
    max_files_per_day: int = 10
    session_ttl_hours: int = 24


@dataclass
class GuestUsage:
    """游客使用统计"""
    tasks_today: int = 0
    files_uploaded_today: int = 0
    concurrent_tasks: int = 0
    last_activity: Optional[str] = None


@dataclass
class GuestSessionData:
    """游客Session数据"""
    session_id: str
    created_at: str
    limitations: Dict[str, Any] = field(default_factory=dict)
    usage: Dict[str, Any] = field(default_factory=dict)
    expires_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "limitations": self.limitations,
            "usage": self.usage,
            "expires_at": self.expires_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GuestSessionData":
        return cls(
            session_id=data["session_id"],
            created_at=data["created_at"],
            limitations=data.get("limitations", {}),
            usage=data.get("usage", {}),
            expires_at=data.get("expires_at", "")
        )


class GuestQuotaExceededError(Exception):
    """游客配额超限错误"""

    def __init__(self, quota_type: str, limit: int, used: int):
        self.quota_type = quota_type
        self.limit = limit
        self.used = used
        message = f"Guest quota exceeded for {quota_type}: used {used}/{limit}"
        super().__init__(message)


class GuestSessionError(Exception):
    """游客Session错误"""
    pass


class GuestManager:
    """游客Session管理器

    负责：
    1. 创建和验证游客Session
    2. 检查和更新游客配额
    3. 迁移游客数据到注册用户
    """

    # 默认配置
    DEFAULT_LIMITATIONS = GuestLimitations()
    GUEST_SESSION_TTL = timedelta(hours=24)
    CACHE_PREFIX = "guest:"

    def __init__(self, cache: Optional["CacheBackend"] = None):
        """初始化游客管理器

        Args:
            cache: 缓存后端（可选，用于Redis缓存）
        """
        self._cache = cache

    @property
    def cache(self) -> Optional["CacheBackend"]:
        """获取缓存实例"""
        if self._cache is None:
            try:
                from app.cache.factory import get_cache
                self._cache = get_cache()
            except Exception:
                pass
        return self._cache

    async def create_guest_session(
        self,
        db: AsyncSession,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Dict[str, Any]:
        """创建游客Session

        Args:
            db: 数据库会话
            ip_address: 客户端IP地址
            user_agent: 客户端User-Agent

        Returns:
            Dict[str, Any]: 包含guest_session_id和limitations的字典
        """
        session_id = str(uuid.uuid4())
        now = datetime.utcnow()
        expires_at = now + self.GUEST_SESSION_TTL

        # 构建Session数据
        session_data = GuestSessionData(
            session_id=session_id,
            created_at=now.isoformat(),
            limitations={
                "daily_task_limit": self.DEFAULT_LIMITATIONS.daily_task_limit,
                "max_file_size_mb": self.DEFAULT_LIMITATIONS.max_file_size_mb,
                "available_tools": self.DEFAULT_LIMITATIONS.available_tools,
                "max_concurrent_tasks": self.DEFAULT_LIMITATIONS.max_concurrent_tasks,
                "max_files_per_day": self.DEFAULT_LIMITATIONS.max_files_per_day,
            },
            usage={
                "tasks_today": 0,
                "files_uploaded_today": 0,
                "concurrent_tasks": 0,
                "last_activity": now.isoformat(),
                "usage_date": now.date().isoformat()
            },
            expires_at=expires_at.isoformat()
        )

        # 存储到缓存
        if self.cache:
            await self.cache.set(
                f"{self.CACHE_PREFIX}{session_id}",
                json.dumps(session_data.to_dict()),
                ttl=int(self.GUEST_SESSION_TTL.total_seconds())
            )

        # 存储到数据库（用于数据持久化和迁移）
        db_session = UserSession(
            id=session_id,
            user_id=None,
            session_token=session_id,
            is_guest=True,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
            session_data=session_data.to_dict(),
            tasks_today=0,
            last_task_date=now
        )
        db.add(db_session)
        await db.commit()

        logger.info(
            f"Created guest session: {session_id}",
            extra={"session_id": session_id, "ip_address": ip_address}
        )

        return {
            "guest_session_id": session_id,
            "limitations": session_data.limitations,
            "expires_at": expires_at.isoformat()
        }

    async def validate_guest_session(
        self,
        session_id: str,
        db: Optional[AsyncSession] = None
    ) -> GuestSessionData:
        """验证游客Session

        Args:
            session_id: Session ID
            db: 数据库会话（可选）

        Returns:
            GuestSessionData: Session数据

        Raises:
            GuestSessionError: Session无效或已过期
        """
        # 优先从缓存获取
        if self.cache:
            cached_data = await self.cache.get(f"{self.CACHE_PREFIX}{session_id}")
            if cached_data:
                try:
                    data = json.loads(cached_data)
                    return GuestSessionData.from_dict(data)
                except (json.JSONDecodeError, KeyError):
                    pass

        # 从数据库获取
        if db:
            result = await db.execute(
                select(UserSession).where(
                    UserSession.id == session_id,
                    UserSession.is_guest == True
                )
            )
            session = result.scalar_one_or_none()

            if session:
                # 检查是否过期
                if session.expires_at and session.expires_at < datetime.utcnow():
                    raise GuestSessionError("Guest session has expired")

                # 重建Session数据
                session_data = GuestSessionData.from_dict(session.session_data or {})
                session_data.session_id = session_id

                # 更新缓存
                if self.cache:
                    ttl = int((session.expires_at - datetime.utcnow()).total_seconds())
                    if ttl > 0:
                        await self.cache.set(
                            f"{self.CACHE_PREFIX}{session_id}",
                            json.dumps(session_data.to_dict()),
                            ttl=ttl
                        )

                return session_data

        raise GuestSessionError("Invalid or expired guest session")

    async def check_guest_quota(
        self,
        session_id: str,
        quota_type: str,
        db: Optional[AsyncSession] = None
    ) -> bool:
        """检查游客配额

        Args:
            session_id: Session ID
            quota_type: 配额类型 (task, file, concurrent_task)
            db: 数据库会话

        Returns:
            bool: 是否在配额内

        Raises:
            GuestQuotaExceededError: 配额超限
        """
        session_data = await self.validate_guest_session(session_id, db)

        # 重置每日计数（如果跨天）
        usage_date = session_data.usage.get("usage_date")
        today = date.today().isoformat()
        if usage_date != today:
            session_data.usage["tasks_today"] = 0
            session_data.usage["files_uploaded_today"] = 0
            session_data.usage["usage_date"] = today
            # 更新缓存
            if self.cache:
                await self.cache.set(
                    f"{self.CACHE_PREFIX}{session_id}",
                    json.dumps(session_data.to_dict()),
                    ttl=int(self.GUEST_SESSION_TTL.total_seconds())
                )

        limitations = session_data.limitations
        usage = session_data.usage

        if quota_type == "task":
            used = usage.get("tasks_today", 0)
            limit = limitations.get("daily_task_limit", self.DEFAULT_LIMITATIONS.daily_task_limit)
            if used >= limit:
                raise GuestQuotaExceededError("task", limit, used)
            return True

        elif quota_type == "file":
            used = usage.get("files_uploaded_today", 0)
            limit = limitations.get("max_files_per_day", self.DEFAULT_LIMITATIONS.max_files_per_day)
            if used >= limit:
                raise GuestQuotaExceededError("file", limit, used)
            return True

        elif quota_type == "concurrent_task":
            used = usage.get("concurrent_tasks", 0)
            limit = limitations.get("max_concurrent_tasks", self.DEFAULT_LIMITATIONS.max_concurrent_tasks)
            if used >= limit:
                raise GuestQuotaExceededError("concurrent_task", limit, used)
            return True

        return True

    async def increment_guest_usage(
        self,
        session_id: str,
        usage_type: str,
        db: Optional[AsyncSession] = None
    ) -> None:
        """增加游客使用计数

        Args:
            session_id: Session ID
            usage_type: 使用类型 (task, file, concurrent_task)
            db: 数据库会话
        """
        session_data = await self.validate_guest_session(session_id, db)

        if usage_type == "task":
            session_data.usage["tasks_today"] = session_data.usage.get("tasks_today", 0) + 1
        elif usage_type == "file":
            session_data.usage["files_uploaded_today"] = session_data.usage.get("files_uploaded_today", 0) + 1
        elif usage_type == "concurrent_task":
            session_data.usage["concurrent_tasks"] = session_data.usage.get("concurrent_tasks", 0) + 1

        session_data.usage["last_activity"] = datetime.utcnow().isoformat()

        # 更新缓存
        if self.cache:
            await self.cache.set(
                f"{self.CACHE_PREFIX}{session_id}",
                json.dumps(session_data.to_dict()),
                ttl=int(self.GUEST_SESSION_TTL.total_seconds())
            )

        # 更新数据库
        if db:
            await db.execute(
                update(UserSession).where(
                    UserSession.id == session_id
                ).values(
                    session_data=session_data.to_dict(),
                    tasks_today=session_data.usage.get("tasks_today", 0),
                    last_task_date=datetime.utcnow()
                )
            )
            await db.commit()

        logger.debug(
            f"Incremented guest usage: {session_id} - {usage_type}",
            extra={"session_id": session_id, "usage_type": usage_type}
        )

    async def decrement_guest_usage(
        self,
        session_id: str,
        usage_type: str,
        db: Optional[AsyncSession] = None
    ) -> None:
        """减少游客使用计数（用于任务完成后释放并发数）

        Args:
            session_id: Session ID
            usage_type: 使用类型 (concurrent_task)
            db: 数据库会话
        """
        session_data = await self.validate_guest_session(session_id, db)

        if usage_type == "concurrent_task":
            current = session_data.usage.get("concurrent_tasks", 0)
            session_data.usage["concurrent_tasks"] = max(0, current - 1)

        # 更新缓存
        if self.cache:
            await self.cache.set(
                f"{self.CACHE_PREFIX}{session_id}",
                json.dumps(session_data.to_dict()),
                ttl=int(self.GUEST_SESSION_TTL.total_seconds())
            )

    async def migrate_guest_data(
        self,
        session_id: str,
        user_id: str,
        db: AsyncSession
    ) -> Dict[str, int]:
        """迁移游客数据到注册用户

        Args:
            session_id: 游客Session ID
            user_id: 目标用户ID
            db: 数据库会话

        Returns:
            Dict[str, int]: 迁移统计（迁移的任务数、文件数等）
        """
        from app.models.tasks import Task
        from app.models.files import File

        migration_stats = {
            "tasks_migrated": 0,
            "files_migrated": 0
        }

        try:
            # 迁移任务
            task_result = await db.execute(
                update(Task).where(
                    Task.session_id == session_id,
                    Task.user_id == None
                ).values(
                    user_id=user_id,
                    session_id=None
                )
            )
            migration_stats["tasks_migrated"] = task_result.rowcount

            # 迁移文件
            file_result = await db.execute(
                update(File).where(
                    File.session_id == session_id,
                    File.owner_id == None
                ).values(
                    owner_id=user_id,
                    session_id=None
                )
            )
            migration_stats["files_migrated"] = file_result.rowcount

            # 删除游客Session记录
            await db.execute(
                delete(UserSession).where(UserSession.id == session_id)
            )

            await db.commit()

            # 删除缓存
            if self.cache:
                await self.cache.delete(f"{self.CACHE_PREFIX}{session_id}")

            logger.info(
                f"Migrated guest data: {session_id} -> {user_id}",
                extra={
                    "session_id": session_id,
                    "user_id": user_id,
                    "stats": migration_stats
                }
            )

            return migration_stats

        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to migrate guest data: {e}")
            raise GuestSessionError(f"Failed to migrate guest data: {str(e)}")

    async def cleanup_expired_sessions(self, db: AsyncSession) -> int:
        """清理过期的游客Session

        Args:
            db: 数据库会话

        Returns:
            int: 清理的Session数量
        """
        now = datetime.utcnow()

        result = await db.execute(
            delete(UserSession).where(
                UserSession.is_guest == True,
                UserSession.expires_at < now
            )
        )
        await db.commit()

        count = result.rowcount
        if count > 0:
            logger.info(f"Cleaned up {count} expired guest sessions")

        return count

    async def get_guest_stats(
        self,
        session_id: str,
        db: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """获取游客使用统计

        Args:
            session_id: Session ID
            db: 数据库会话

        Returns:
            Dict[str, Any]: 使用统计
        """
        session_data = await self.validate_guest_session(session_id, db)

        return {
            "session_id": session_id,
            "created_at": session_data.created_at,
            "expires_at": session_data.expires_at,
            "limitations": session_data.limitations,
            "usage": session_data.usage,
            "remaining": {
                "tasks": (
                    session_data.limitations.get("daily_task_limit", 5) -
                    session_data.usage.get("tasks_today", 0)
                ),
                "files": (
                    session_data.limitations.get("max_files_per_day", 10) -
                    session_data.usage.get("files_uploaded_today", 0)
                )
            }
        }


# 全局实例
guest_manager = GuestManager()
