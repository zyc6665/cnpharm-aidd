from __future__ import annotations

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

load_dotenv(BACKEND_ROOT / ".env", override=False)

from app.config import resolve_database_url, settings
from app.database.base import Base
from app.models import files, statistics, tasks, tools, users, verification, workflows  # noqa: F401,E402


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", resolve_database_url(settings.DATABASE_URL))
target_metadata = Base.metadata


# 由迁移手写 DDL 持有、禁止 autogenerate 参与比对的索引。
# ``ix_tasks_project_status_finished`` 在 PostgreSQL 上必须是
# ``(project_id, status, finished_at DESC NULLS LAST, created_at DESC)``，而
# ``NULLS LAST`` 无法用 SQLAlchemy 声明式无损表达（写了会破坏 SQLite 的
# create_all / 迁移 dry-run）。因此模型里只保留升序列顺序（服务
# test_index_governance 的列名断言），真正的排序定义由迁移 20261031_01/03 持有。
# 若不排除，``alembic check`` / autogenerate 会把它判成 "changed index" 并生成
# 重建语句，把生产库的 NULLS LAST 排序覆盖掉——这正是要避免的双真源漂移。
MIGRATION_OWNED_INDEXES = frozenset({"ix_tasks_project_status_finished"})


def include_object(object, name, type_, reflected, compare_to):  # noqa: A002
    if type_ == "index" and name in MIGRATION_OWNED_INDEXES:
        return False
    return True


def _render_as_batch() -> bool:
    return config.get_main_option("sqlalchemy.url").startswith("sqlite")


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=_render_as_batch(),
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=_render_as_batch(),
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
