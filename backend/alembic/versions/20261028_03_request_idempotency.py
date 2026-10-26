"""idempotency_keys：请求级幂等表（docs/04 §5.5、docs/05 §12、docs/18 §6.3 G-10）

此前的幂等只有两处**专用**实现：``ExecutionRecord.idempotency_key``
（``{task}:{id}:attempt:{key}`` 内部标识）与 ``upload_sessions.idempotency_key``
（上传会话唯一约束）。两者都不能承担「任意写接口 + ``X-Idempotency-Key`` 请求头」
的通用重放语义，G-10 要求的是后者。

建表要点
--------
* **复合主键 ``(scope, key)``**：唯一性交给数据库，写入用
  ``INSERT ... ON CONFLICT (scope, key) DO NOTHING`` 一次原子判定。应用层「先查后
  插」在并发重试下必然漏判（两个事务都查到不存在，再各插一行）。复合主键同时让
  ``(scope, key)`` 的等值查询走主键索引，不需要额外索引。
* ``request_hash`` NOT NULL：同键异体必须被拒绝（40905），只有哈希才能逐字节判定
  「这次请求和上次是不是同一个」。
* ``response_body`` JSON NULL：``IN_PROGRESS`` 期间为空，``COMPLETED`` 后存首响
  快照，重放时原样返回（含 ``taskId``）。
* 两个二级索引：``expires_at``（过期清理唯一的扫描条件）与 ``user_id``（排查用）。

Revision ID: 20261028_03
Revises: 20261028_02
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

revision = "20261028_03"
down_revision = "20261028_02"
branch_labels = None
depends_on = None


IDEMPOTENCY_KEYS = "idempotency_keys"
EXPIRES_INDEX = "ix_idempotency_keys_expires_at"
USER_INDEX = "ix_idempotency_keys_user_id"


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _index_names(table_name: str) -> set[str]:
    if table_name not in _existing_tables():
        return set()
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _create_idempotency_keys_table() -> None:
    if IDEMPOTENCY_KEYS in _existing_tables():
        return
    op.create_table(
        IDEMPOTENCY_KEYS,
        sa.Column("scope", sa.String(length=255), primary_key=True),
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="IN_PROGRESS"),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.JSON(), nullable=True),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )


def upgrade() -> None:
    _create_idempotency_keys_table()
    indexes = _index_names(IDEMPOTENCY_KEYS)
    if EXPIRES_INDEX not in indexes:
        op.create_index(EXPIRES_INDEX, IDEMPOTENCY_KEYS, ["expires_at"])
    if USER_INDEX not in indexes:
        op.create_index(USER_INDEX, IDEMPOTENCY_KEYS, ["user_id"])


def downgrade() -> None:
    if IDEMPOTENCY_KEYS not in _existing_tables():
        return
    indexes = _index_names(IDEMPOTENCY_KEYS)
    # 逆序：先撤二级索引，再撤表（主键索引随表一起消失）。
    if USER_INDEX in indexes:
        op.drop_index(USER_INDEX, table_name=IDEMPOTENCY_KEYS)
    if EXPIRES_INDEX in indexes:
        op.drop_index(EXPIRES_INDEX, table_name=IDEMPOTENCY_KEYS)
    op.drop_table(IDEMPOTENCY_KEYS)
