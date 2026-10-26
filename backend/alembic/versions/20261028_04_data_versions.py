"""data_versions：实体历史版本表（docs/04 §8.3、docs/18 §6.3 G-11）

此前的版本信息只有三处**当前态**字段：``proteins.current_version``（版本号，
无内容）、``artifacts`` 的标准件版本（只覆盖产物）与 ``audit_logs``（只记动作，
不记版本序列）。都不能回答「某个化合物第 3 版长什么样、是谁在什么时候改的」，
G-11 要的是后者：一条实体对应一串只追加的版本行。

建表要点
--------
* **唯一约束 ``uq_data_versions_entity_version``** 落在
  ``(entity_type, entity_id, version)``：版本号由应用层算「当前最大值 + 1」，
  并发下两个写入者会算出同一个 N，唯一约束让其中一个失败（
  ``IntegrityError``），由 ``app.services.data_versions.record_version``
  重算后重试。应用层「先查后插」在并发下必然漏判，这条约束是唯一的真值来源。
* ``ix_data_versions_entity`` 覆盖 ``(entity_type, entity_id, created_at)``：
  列表查询固定按前两列等值过滤、按 ``created_at`` 倒序翻页，索引里带上
  ``created_at`` 可免去回表排序。
* ``operator`` 是可空字符串快照（username / email），**不是外键**：版本历史要在
  用户被改名或停用之后仍然可读（docs/04 §3 note 1，与 ``audit_logs.actor``
  同一口径）。
* ``content_hash`` 存内容 sha256 的 hex（64 位），供「两版内容是否真的不同」
  快速判定；``source_file_urn`` / ``change_summary`` 可空，因为 ``COMPUTE``
  版本没有来源文件，也不是每次都有人写摘要。

Revision ID: 20261028_04
Revises: 20261028_03
Create Date: 2026-10-28

幂等判断
--------
``_existing_tables()`` / ``_index_names()`` 保证重复执行安全：表或索引已存在时跳过，
不会因为「开发环境已经由 ``Base.metadata.create_all`` 建过」而报 ``table already
exists``。downgrade 逆序 drop 索引再 drop 表。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20261028_04"
down_revision = "20261028_03"
branch_labels = None
depends_on = None


DATA_VERSIONS = "data_versions"
ENTITY_VERSION_UNIQUE = "uq_data_versions_entity_version"
ENTITY_INDEX = "ix_data_versions_entity"


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _index_names(table_name: str) -> set[str]:
    if table_name not in _existing_tables():
        return set()
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _create_data_versions_table() -> None:
    if DATA_VERSIONS in _existing_tables():
        return
    op.create_table(
        DATA_VERSIONS,
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_file_urn", sa.String(length=512), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("operator", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "entity_type",
            "entity_id",
            "version",
            name=ENTITY_VERSION_UNIQUE,
        ),
    )


def upgrade() -> None:
    _create_data_versions_table()
    indexes = _index_names(DATA_VERSIONS)
    if ENTITY_INDEX not in indexes:
        op.create_index(
            ENTITY_INDEX,
            DATA_VERSIONS,
            ["entity_type", "entity_id", "created_at"],
        )


def downgrade() -> None:
    if DATA_VERSIONS not in _existing_tables():
        return
    indexes = _index_names(DATA_VERSIONS)
    # 逆序：先撤二级索引，再撤表（唯一约束随表一起消失）。
    if ENTITY_INDEX in indexes:
        op.drop_index(ENTITY_INDEX, table_name=DATA_VERSIONS)
    op.drop_table(DATA_VERSIONS)
