# backend/app/tools/version_manager.py
"""工具版本管理器

根据详细设计说明书 3.2 节实现。
负责工具版本的切换、废弃、回滚等操作。
"""

from typing import List, Optional, TYPE_CHECKING
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.time import utcnow
from app.models.tools import Tool, ToolVersion

if TYPE_CHECKING:
    from app.cache.base import CacheBackend

logger = logging.getLogger(__name__)


class VersionError(Exception):
    """版本管理错误"""

    def __init__(self, message: str, code: str = "VERSION_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class ToolVersionManager:
    """工具版本管理器

    负责：
    1. 切换当前版本
    2. 废弃版本
    3. 回滚版本
    4. 版本比较
    """

    CACHE_PREFIX = "tool:"
    CACHE_TTL = 3600  # 1小时

    def __init__(self, db: AsyncSession, cache: Optional["CacheBackend"] = None):
        """初始化版本管理器

        Args:
            db: 数据库会话
            cache: 缓存后端（可选）
        """
        self.db = db
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

    async def _get_tool(self, tool_id: str) -> Tool:
        """获取工具"""
        result = await self.db.execute(
            select(Tool).where(Tool.id == tool_id)
        )
        tool = result.scalar_one_or_none()
        if not tool:
            raise VersionError(f"Tool not found: {tool_id}", "TOOL_NOT_FOUND")
        return tool

    async def _get_version(self, version_id: str) -> ToolVersion:
        """获取版本"""
        result = await self.db.execute(
            select(ToolVersion).where(ToolVersion.id == version_id)
        )
        version = result.scalar_one_or_none()
        if not version:
            raise VersionError(f"Version not found: {version_id}", "VERSION_NOT_FOUND")
        return version

    async def _clear_tool_cache(self, tool_id: str) -> None:
        """清除工具缓存"""
        if self.cache:
            await self.cache.delete(f"{self.CACHE_PREFIX}detail:{tool_id}")
            await self.cache.delete(f"{self.CACHE_PREFIX}versions:{tool_id}")

    async def switch_current_version(
        self,
        tool_id: str,
        version_id: str,
        user_id: Optional[str] = None
    ) -> Tool:
        """切换当前版本

        Args:
            tool_id: 工具ID
            version_id: 目标版本ID
            user_id: 操作用户ID（用于权限验证）

        Returns:
            Tool: 更新后的工具对象

        Raises:
            VersionError: 当工具或版本不存在，或版本不属于该工具时
        """
        tool = await self._get_tool(tool_id)
        version = await self._get_version(version_id)

        # 验证版本属于该工具
        if version.tool_id != tool_id:
            raise VersionError(
                "Version does not belong to this tool",
                "VERSION_MISMATCH"
            )

        # 验证版本未废弃
        if version.deprecated:
            raise VersionError(
                "Cannot switch to a deprecated version",
                "VERSION_DEPRECATED"
            )

        # 验证版本是否激活
        if not version.is_active:
            raise VersionError(
                "Cannot switch to an inactive version",
                "VERSION_INACTIVE"
            )

        old_version_id = tool.current_version_id

        # 更新当前版本
        tool.current_version_id = version_id
        await self.db.commit()
        await self.db.refresh(tool)

        # 清除缓存
        await self._clear_tool_cache(tool_id)

        logger.info(
            f"Switched tool {tool_id} version: {old_version_id} -> {version_id}",
            extra={
                "tool_id": tool_id,
                "old_version_id": old_version_id,
                "new_version_id": version_id,
                "user_id": user_id
            }
        )

        return tool

    async def deprecate_version(
        self,
        version_id: str,
        reason: Optional[str] = None
    ) -> ToolVersion:
        """废弃版本

        Args:
            version_id: 版本ID
            reason: 废弃原因

        Returns:
            ToolVersion: 更新后的版本对象

        Raises:
            VersionError: 当版本不存在或为当前版本时
        """
        version = await self._get_version(version_id)
        tool = await self._get_tool(version.tool_id)

        # 检查是否为当前版本
        if tool.current_version_id == version_id:
            raise VersionError(
                "Cannot deprecate current version. Switch to another version first.",
                "CANNOT_DEPRECATE_CURRENT"
            )

        # 检查是否已废弃
        if version.deprecated:
            raise VersionError(
                "Version is already deprecated",
                "ALREADY_DEPRECATED"
            )

        # 标记为废弃
        version.deprecated = True
        version.deprecated_at = utcnow()
        version.is_active = False

        # 可以在notes中记录废弃原因
        if reason:
            version.notes = f"{version.notes or ''}\n[Deprecated: {reason}]".strip()

        await self.db.commit()
        await self.db.refresh(version)

        # 清除缓存
        await self._clear_tool_cache(version.tool_id)

        logger.info(
            f"Deprecated version {version_id}",
            extra={"version_id": version_id, "tool_id": version.tool_id, "reason": reason}
        )

        return version

    async def rollback_version(self, tool_id: str) -> Tool:
        """回滚到上一个版本

        Args:
            tool_id: 工具ID

        Returns:
            Tool: 更新后的工具对象

        Raises:
            VersionError: 当没有可用的历史版本时
        """
        tool = await self._get_tool(tool_id)

        # 查询版本历史（按创建时间降序）
        result = await self.db.execute(
            select(ToolVersion)
            .where(
                ToolVersion.tool_id == tool_id,
                ToolVersion.deprecated == False,
                ToolVersion.is_active == True
            )
            .order_by(ToolVersion.created_at.desc())
            .limit(2)
        )
        versions = result.scalars().all()

        if len(versions) < 2:
            raise VersionError(
                "No previous version available for rollback",
                "NO_PREVIOUS_VERSION"
            )

        # 找到非当前版本的最新版本
        previous_version = None
        for v in versions:
            if v.id != tool.current_version_id:
                previous_version = v
                break

        if not previous_version:
            raise VersionError(
                "No previous version available for rollback",
                "NO_PREVIOUS_VERSION"
            )

        # 切换到上一个版本
        return await self.switch_current_version(tool_id, previous_version.id)

    async def create_version(
        self,
        tool_id: str,
        version: str,
        config: dict,
        notes: Optional[str] = None,
        set_as_current: bool = True
    ) -> ToolVersion:
        """创建新版本

        Args:
            tool_id: 工具ID
            version: 版本号
            config: 版本配置
            notes: 版本说明
            set_as_current: 是否设为当前版本

        Returns:
            ToolVersion: 新创建的版本对象
        """
        tool = await self._get_tool(tool_id)

        # 检查版本号是否已存在
        result = await self.db.execute(
            select(ToolVersion).where(
                ToolVersion.tool_id == tool_id,
                ToolVersion.version == version
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            raise VersionError(
                f"Version {version} already exists for this tool",
                "VERSION_EXISTS"
            )

        # 创建新版本
        new_version = ToolVersion(
            tool_id=tool_id,
            version=version,
            config=config,
            notes=notes,
            is_active=True,
            deprecated=False
        )
        self.db.add(new_version)
        await self.db.flush()

        # 设为当前版本
        if set_as_current:
            tool.current_version_id = new_version.id

        await self.db.commit()
        await self.db.refresh(new_version)

        # 清除缓存
        await self._clear_tool_cache(tool_id)

        logger.info(
            f"Created new version {version} for tool {tool_id}",
            extra={
                "tool_id": tool_id,
                "version": version,
                "version_id": new_version.id
            }
        )

        return new_version

    async def get_version_history(
        self,
        tool_id: str,
        include_deprecated: bool = False,
        limit: int = 10
    ) -> List[ToolVersion]:
        """获取版本历史

        Args:
            tool_id: 工具ID
            include_deprecated: 是否包含已废弃版本
            limit: 返回数量限制

        Returns:
            List[ToolVersion]: 版本列表
        """
        query = select(ToolVersion).where(ToolVersion.tool_id == tool_id)

        if not include_deprecated:
            query = query.where(ToolVersion.deprecated == False)

        query = query.order_by(ToolVersion.created_at.desc()).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def compare_versions(
        self,
        version_id_1: str,
        version_id_2: str
    ) -> dict:
        """比较两个版本

        Args:
            version_id_1: 版本1 ID
            version_id_2: 版本2 ID

        Returns:
            dict: 版本差异
        """
        version1 = await self._get_version(version_id_1)
        version2 = await self._get_version(version_id_2)

        if version1.tool_id != version2.tool_id:
            raise VersionError(
                "Cannot compare versions from different tools",
                "TOOL_MISMATCH"
            )

        # 比较配置差异
        config1 = version1.config or {}
        config2 = version2.config or {}

        added_keys = set(config2.keys()) - set(config1.keys())
        removed_keys = set(config1.keys()) - set(config2.keys())
        modified_keys = {
            k for k in set(config1.keys()) & set(config2.keys())
            if config1[k] != config2[k]
        }

        return {
            "version1": {
                "id": version1.id,
                "version": version1.version,
                "created_at": version1.created_at.isoformat() if version1.created_at else None
            },
            "version2": {
                "id": version2.id,
                "version": version2.version,
                "created_at": version2.created_at.isoformat() if version2.created_at else None
            },
            "differences": {
                "added": list(added_keys),
                "removed": list(removed_keys),
                "modified": list(modified_keys)
            }
        }

    async def get_current_version(self, tool_id: str) -> Optional[ToolVersion]:
        """获取工具当前版本

        Args:
            tool_id: 工具ID

        Returns:
            Optional[ToolVersion]: 当前版本，如果没有则返回None
        """
        tool = await self._get_tool(tool_id)

        if not tool.current_version_id:
            return None

        return await self._get_version(tool.current_version_id)
