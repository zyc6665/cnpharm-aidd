"""data_versions 增加内容快照列 content（docs/05 §4 版本历史/差异对比）

G-3 要的是两个只读接口：``GET /compounds/{id}/versions`` 与
``GET /compounds/{id}/diff?from=1&to=3``。前者靠 ``20261028_04`` 建的表就能做，
后者做不出来：那张表只有 ``content_hash``，两个版本摆在一起只有两个哈希，能回答
「变没变」，回答不了「哪个字段从什么变成了什么」。

为什么必须加列而不是「读的时候现算」
------------------------------------
历史内容不存在别处可查：``compounds`` 只保留当前态，``props`` 每次 refresh 都被整块
覆盖；``audit_logs`` 记动作不记内容。所以第 1 版长什么样，只可能在写入当时被记下来。
事后补不出来——这不是「加个查询」能解决的问题，是账本少了一列。

为什么可空、且不回填
--------------------
本迁移之前产生的版本行**没有**快照，也无法重建（内容已随当前态覆盖而消失）。用当前
实体行去回填会写出「第 1 版等于今天的样子」这种伪造历史，比留空更有害。故列可空，
历史行保持 NULL，读接口遇到 NULL 时显式告知「该版本无法比对字段」而不是装作没差异。

为什么是 JSON 而不是 TEXT
-------------------------
PostgreSQL 下 ``JSON`` 走 ``json`` 类型（可索引、可查询），SQLite 下退化为 TEXT 但
SQLAlchemy 负责编解码；写成 TEXT 则两种库上的读写路径不一致，diff 时还得自己
``json.loads``，把方言差异漏到业务层。

SQLite 的处理
-------------
``ALTER TABLE ... ADD COLUMN`` 在 SQLite 是原生支持的，且新增可空列不需要重建表，
因此 upgrade 走原生 ``add_column``；downgrade 的 ``DROP COLUMN`` 在 SQLite 上要到
3.35 才有、且会连带丢约束，故用 ``batch_alter_table``（项目 ``alembic/env.py`` 在
SQLite 下已设 ``render_as_batch=True``，PostgreSQL 下自动退化为原生 ``ALTER``）。
两个方向都先查列是否存在，重复执行安全（与 ``20261028_04`` 的幂等风格一致）。

Revision ID: 20261028_06
Revises: 20261028_05
Create Date: 2026-10-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20261028_06"
down_revision = "20261028_05"
branch_labels = None
depends_on = None


DATA_VERSIONS = "data_versions"
CONTENT_COLUMN = "content"


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table_name: str) -> set[str]:
    if table_name not in _table_names():
        return set()
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    if DATA_VERSIONS not in _table_names():
        # 表由 20261028_04 建；缺表说明版本链被手工改过，此时建列没有意义。
        return
    if CONTENT_COLUMN in _column_names(DATA_VERSIONS):
        return
    op.add_column(
        DATA_VERSIONS,
        sa.Column(CONTENT_COLUMN, sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    if CONTENT_COLUMN not in _column_names(DATA_VERSIONS):
        return
    with op.batch_alter_table(DATA_VERSIONS) as batch:
        batch.drop_column(CONTENT_COLUMN)
