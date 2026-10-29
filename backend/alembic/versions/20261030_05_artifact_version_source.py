"""Task 3a：产物真值化第一步 —— ``artifact_versions`` 来源字段。

背景
----
``Artifact`` 只有单值的 ``source_task_id``（Artifact 级），``ArtifactVersion`` 完全
没有来源字段，于是无法回答「这个版本是哪次任务、哪次尝试、哪个工具版本产生的」。
本迁移给 ``artifact_versions`` 补齐来源四列。

新列
----
- ``source_task_id`` ``String(36) NULL`` + 索引 ``ix_artifact_versions_source_task_id``
- ``source_attempt_id`` ``String(64) NULL``
- ``source_tool_version_id`` ``String(36) NULL``
- ``storage_tier`` ``String(16) NOT NULL DEFAULT 'standard'``

关于「内容唯一」取舍
--------------------
本迁移刻意**不加** ``(artifact_id, sha256)`` 唯一约束：``artifact_versions`` 是只追加
的生产留痕表，不同任务产出相同字节时必须各自留下一行来源（version）；而存储层按
内容寻址，同内容的不同版本指向同一个存储 blob（``storage_key`` 相同），并不会多存
一份字节。即「每次生产都留痕」与「内容唯一」不可兼得，这里选择前者（见设计文档
``04`` §9、``12`` TC-M7 的追溯口径）。仅保留 ``(artifact_id, version)`` 唯一约束，
那是并发取号的正确性要求。

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


def downgrade() -> None:
    if ARTIFACT_VERSIONS not in _table_names():
        return

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
