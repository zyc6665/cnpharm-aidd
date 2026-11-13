# backend/app/database/session.py
"""数据库会话管理"""

import logging
import sys
from typing import AsyncGenerator
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from app.config import resolve_database_url, settings


logger = logging.getLogger(__name__)

# Celery 的子命令里只有这两个会「在自己的事件循环里跑数据库任务」。
_CELERY_SUBCOMMANDS = ("worker", "beat")


def celery_runtime() -> str | None:
    """判断当前进程是不是 Celery 的 worker / beat。

    为什么靠命令行判断：Celery 没有给子进程一个稳定的环境变量（threads 池直接在
    MainProcess 里跑；prefork 子进程虽然带 FORKED_BY_MULTIPROCESSING，但默认就是
    threads 池，用不上）。而启动命令是确定的：

        celery -A app.worker.celery_app worker --pool=threads --concurrency=4 -Q ...
        celery -A app.worker.celery_app beat

    返回 `"worker"` / `"beat"`，都不是则返回 None。
    """
    argv = [str(item).lower() for item in sys.argv]
    if not any("celery" in item for item in argv):
        return None
    for item in argv[1:]:
        if item in _CELERY_SUBCOMMANDS:
            return item
    return None


def _engine_kwargs() -> dict:
    """按运行形态决定连接池参数。

    `DB_POOL_MODE=null` 用于 Celery Worker：asyncpg 连接绑定创建它的事件循环，
    而 threads/prefork 池里并发的两个任务可能跑在不同循环上，共享进程级池会拿到
    「绑在别人循环上」的连接。每个会话新建连接是最简单也最不会错的解法。

    默认的 `auto` 靠 `celery_runtime()` 自动判断——照着手册起 worker 的人不该需要
    记住一个环境变量才能不踩这个坑（#113）。显式给 `pooled` / `null` 时以显式值为准。
    """
    mode = settings.DB_POOL_MODE
    if mode == "auto":
        mode = "null" if celery_runtime() else "pooled"

    kwargs: dict = {"echo": settings.DEBUG, "future": True}
    if mode == "null":
        kwargs["poolclass"] = NullPool
        kwargs["pool_pre_ping"] = False
    return kwargs


# 创建异步引擎
engine = create_async_engine(
    resolve_database_url(settings.DATABASE_URL),
    **_engine_kwargs(),
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
