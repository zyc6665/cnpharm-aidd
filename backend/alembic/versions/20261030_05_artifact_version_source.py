"""Task 3a：产物真值化第一步 —— ``artifact_versions`` 来源字段 + 内容部分唯一索引。

背景
----
``Artifact`` 只有单值的 ``source_task_id``（Artifact 级），``ArtifactVersion`` 完全
没有来源字段，于是无法回答「这个版本是哪次任务、哪次尝试、哪个工具版本产生的」。
本迁移给 ``artifact_versions`` 补齐来源四列，并加一个「同产物下同 sha256 的可用版本
唯一」的 partial 唯一索引，作为幂等写入的数据库兜底。

新列
----
- ``source_task_id`` ``String(36) NULL`` + 索引 ``ix_artifact_versions_source_task_id``
- ``source_attempt_id`` ``String(64) NULL``
- ``source_tool_version_id`` ``String(36) NULL``
- ``storage_tier`` ``String(16) NOT NULL DEFAULT 'standard'``

部分唯一索引
------------
``uq_artifact_versions_artifact_sha256``：``(artifact_id, sha256)``，仅约束
``status = 'available'`` 的行（``sqlite_where`` / ``postgresql_where`` 各写一份，
照 ``backend/app/models/gpu.py`` 的 ``uq_gpu_allocations_active_device`` 写法）。

**建索引前先查重**：若同一 ``(artifact_id, sha256)`` 在 ``status='available'`` 下
已经存在重复行，则不建索引、直接 ``raise RuntimeError`` 并列出前 10 组重复，提示
先人工合并。理由：静默跳过唯一约束会让后续幂等逻辑建立在错误前提上（参照
``20261028_01_upload_parts_and_idempotency.py`` 的 ``_assert_no_duplicate_idempotency_keys``）。

幂等
----
所有加列/加索引都先 ``sa.inspect`` 判断，重复执行安全；表不存在（legacy 恢复场景）
直接跳过。``downgrade`` 逆序撤回；SQLite 删列走 ``op.batch_alter_table``。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20261030_05"
down_revision = "20261030_04"
branch_labels = None
depends_on = None


ARTIFACT_VERSIONS = "artifact_versions"
SOURCE_TASK_INDEX = "ix_artifact_versions_source_task_id"
PARTIAL_UNIQUE_INDEX = "uq_artifact_versions_artifact_sha256"

NEW_COLUMNS = (
    ("source_task_id", sa.String(36), True, None),
    ("source_attempt_id", sa.String(64), True, None),
    ("source_tool_version_id", sa.String(36), True, None),
    ("storage_tier", sa.String(16), False, "standard"),
)


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table_name: str) -> set[str]:
    if table_name not in _table_names():
        return set()
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    if table_name not in _table_names():
        return set()
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _assert_no_duplicate_available_sha() -> None:
    """建部分唯一索引前先查重，给出可操作的中文报错而不是让数据库抛原生错误。"""
    if ARTIFACT_VERSIONS not in _table_names():
        return
    bind = op.get_bind()
    versions = sa.table(
        ARTIFACT_VERSIONS,
        sa.column("artifact_id", sa.String),
        sa.column("sha256", sa.String),
        sa.column("status", sa.String),
    )
    duplicates = bind.execute(
        sa.select(
            versions.c.artifact_id,
            versions.c.sha256,
            sa.func.count().label("n"),
        )
        .where(versions.c.status == "available")
        .group_by(versions.c.artifact_id, versions.c.sha256)
        .having(sa.func.count() > 1)
    ).fetchall()
    if duplicates:
        sample = "; ".join(
            f"{row[0]}/{row[1]}x{row[2]}" for row in duplicates[:10]
        )
        raise RuntimeError(
            "存在重复的可用产物版本 (artifact_id, sha256)，无法建立部分唯一索引；"
            "请先人工合并重复版本（保留一条 available）："
            f"{sample}"
        )


def upgrade() -> None:
    if ARTIFACT_VERSIONS not in _table_names():
        return

    existing_columns = _column_names(ARTIFACT_VERSIONS)
    for name, column_type, nullable, server_default in NEW_COLUMNS:
        if name in existing_columns:
            continue
        op.add_column(
            ARTIFACT_VERSIONS,
            sa.Column(
                name,
                column_type,
                nullable=nullable,
                server_default=(sa.text(server_default) if server_default else None),
            ),
        )

    if SOURCE_TASK_INDEX not in _index_names(ARTIFACT_VERSIONS):
        op.create_index(SOURCE_TASK_INDEX, ARTIFACT_VERSIONS, ["source_task_id"])

    if PARTIAL_UNIQUE_INDEX not in _index_names(ARTIFACT_VERSIONS):
        _assert_no_duplicate_available_sha()
        op.create_index(
            PARTIAL_UNIQUE_INDEX,
            ARTIFACT_VERSIONS,
            ["artifact_id", "sha256"],
            unique=True,
            sqlite_where=sa.text("status = 'available'"),
            postgresql_where=sa.text("status = 'available'"),
        )


def downgrade() -> None:
    if ARTIFACT_VERSIONS not in _table_names():
        return

    if PARTIAL_UNIQUE_INDEX in _index_names(ARTIFACT_VERSIONS):
        op.drop_index(PARTIAL_UNIQUE_INDEX, table_name=ARTIFACT_VERSIONS)
    if SOURCE_TASK_INDEX in _index_names(ARTIFACT_VERSIONS):
        op.drop_index(SOURCE_TASK_INDEX, table_name=ARTIFACT_VERSIONS)

    existing_columns = _column_names(ARTIFACT_VERSIONS)
    to_drop = [
        name for name, _type, _nullable, _default in NEW_COLUMNS if name in existing_columns
    ]
    if to_drop:
        with op.batch_alter_table(ARTIFACT_VERSIONS) as batch_op:
            for name in to_drop:
                batch_op.drop_column(name)
