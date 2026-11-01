"""新增 refresh_tokens 表（refresh jti 存储 / 轮换 / 复用检测）。

背景
----
``docs/22`` P2 认证授权：此前 refresh token 无状态、logout 不失效。改造后每个
refresh 的 ``jti`` 落库，refresh 时轮换（旧 jti 标记吊销并写 ``replaced_by``），
已吊销 jti 再次使用视为复用入侵并吊销该用户全部 refresh。

本迁移步骤（幂等）
------------------
1. 若 ``refresh_tokens`` 不存在则建表：``jti`` 主键、``user_id`` 外键级联、
   ``expires_at`` / ``revoked_at`` / ``replaced_by`` / ``created_at`` /
   ``user_agent`` / ``ip_address``。
2. 建 ``ix_refresh_tokens_user_id`` 与 ``ix_refresh_tokens_expires_at`` 索引。

downgrade 对称：先删索引再删表。

不在迁移里 import 应用模型，纯 ``op``；两端（SQLite/PostgreSQL）语法一致。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261031_08"
down_revision = "20261031_07"
branch_labels = None
depends_on = None

TABLE = "refresh_tokens"
USER_ID_INDEX = "ix_refresh_tokens_user_id"
EXPIRES_INDEX = "ix_refresh_tokens_expires_at"


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _index_names(table: str) -> set[str]:
    if table not in _table_names():
        return set()
    return {
        index["name"]
        for index in sa.inspect(op.get_bind()).get_indexes(table)
        if index.get("name")
    }


def upgrade() -> None:
    if TABLE not in _table_names():
        op.create_table(
            TABLE,
            sa.Column("jti", sa.String(36), primary_key=True),
            sa.Column(
                "user_id",
                sa.String(36),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("replaced_by", sa.String(36), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("user_agent", sa.String(512), nullable=True),
            sa.Column("ip_address", sa.String(64), nullable=True),
        )

    existing = _index_names(TABLE)
    if USER_ID_INDEX not in existing:
        op.create_index(USER_ID_INDEX, TABLE, ["user_id"])
    if EXPIRES_INDEX not in existing:
        op.create_index(EXPIRES_INDEX, TABLE, ["expires_at"])


def downgrade() -> None:
    if TABLE not in _table_names():
        return
    existing = _index_names(TABLE)
    if EXPIRES_INDEX in existing:
        op.drop_index(EXPIRES_INDEX, table_name=TABLE)
    if USER_ID_INDEX in existing:
        op.drop_index(USER_ID_INDEX, table_name=TABLE)
    op.drop_table(TABLE)
