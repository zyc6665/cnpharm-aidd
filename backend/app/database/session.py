# backend/app/database/session.py
"""数据库会话管理"""

import logging
from typing import AsyncGenerator
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.config import resolve_database_url, settings


logger = logging.getLogger(__name__)

# 创建异步引擎
engine = create_async_engine(
    resolve_database_url(settings.DATABASE_URL),
    echo=settings.DEBUG,
    future=True,
)

# 创建异步会话工厂
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话（依赖注入）"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """获取异步数据库会话（用于非依赖注入场景）"""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """初始化数据库。

    开发环境保留 create_all 作为缺表兜底，生产和预发布环境依赖 Alembic 迁移。
    """
    from app.database.base import Base
    # 导入模型包以便注册所有声明的表。
    from importlib import import_module

    import_module("app.models")

    if settings.ENVIRONMENT != "development":
        logger.info("Skip create_all outside development; rely on Alembic migrations")
        return

    def _create_missing_tables(sync_conn) -> None:
        inspector = inspect(sync_conn)
        existing_tables = set(inspector.get_table_names())
        metadata_tables = set(Base.metadata.tables.keys())
        missing_tables = sorted(metadata_tables - existing_tables)
        if not missing_tables:
            return

        Base.metadata.create_all(
            bind=sync_conn,
            tables=[Base.metadata.tables[name] for name in missing_tables],
            checkfirst=True,
        )
        logger.warning(
            "Development fallback created missing tables via create_all: %s",
            ", ".join(missing_tables),
        )

    async with engine.begin() as conn:
        await conn.run_sync(_create_missing_tables)
