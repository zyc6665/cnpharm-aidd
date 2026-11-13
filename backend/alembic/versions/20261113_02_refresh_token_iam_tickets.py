"""refresh_tokens 表携带统一身份认证（IAM）票据密文。

背景
----
对接甲方 IAM 后，平台会话除了自己的 refresh JWT，还要能替用户访问 IAM
（``checkAccessToken`` / ``refreshToken``）。票据以 Fernet 密文挂在平台会话行上，
与 jti 同生共死：轮换、登出、复用入侵吊销都是一个事务，不会出现「Cookie 里是新
jti、库里是旧票据」的撕裂状态；也不新增任何 Cookie（避开 4KB 上限）。

本迁移步骤（幂等，可重复执行）
------------------------------
``refresh_tokens`` 增加四个可空列，历史行不受影响：

1. ``iam_access_token_enc``（``Text``）：IAM accessToken 密文。
2. ``iam_refresh_token_enc``（``Text``）：IAM refreshToken 密文。
3. ``iam_access_expires_at``（``DateTime``）：accessToken 过期时间（naive UTC）。
4. ``iam_checked_at``（``DateTime``）：最近一次校验**成功**的时间，也是「IAM 不可达
   时宽限放行」的锚点；宽限放行时**不得**刷新该列，否则故障期会无限期放行。

downgrade
---------
对称删除四列；同样先判存在，可重复执行。

不在迁移里 import 应用模型，纯 ``sa`` / ``op``；SQLite 的删列需要重建表，加/删都走
``batch_alter_table``，一次 batch 完成全部列变更。

Revision ID: 20261113_02
Revises: 20261113_01
Create Date: 2026-11-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261113_02"
down_revision = "20261113_01"
branch_labels = None
depends_on = None

TABLE = "refresh_tokens"

#: 四列按固定顺序增删；类型全部可空，兼容存量会话行。
IAM_COLUMNS = (
    ("iam_access_token_enc", sa.Text()),
    ("iam_refresh_token_enc", sa.Text()),
    ("iam_access_expires_at", sa.DateTime()),
    ("iam_checked_at", sa.DateTime()),
)


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _table_exists() -> bool:
    return TABLE in set(_inspector().get_table_names())


def _column_names() -> set[str]:
    if not _table_exists():
        return set()
    return {column["name"] for column in _inspector().get_columns(TABLE)}


def _foreign_targets_present() -> bool:
    """本表外键指向的表是否都在。

    SQLite 删列必须重建表，而重建要反射外键：``user_id`` 指向 ``users``，
    若目标表缺失（手工拼的精简基线库，如 ``test/test_task_project_aggregate.py``），
    反射会直接抛 ``NoSuchTableError: users``。真实部署里两表由同一批迁移创建，
    不会出现这种组合，这里只是让精简库的回滚路径不炸。
    """
    if not _table_exists():
        return False
    tables = set(_inspector().get_table_names())
    return all(
        fk.get("referred_table") in tables for fk in _inspector().get_foreign_keys(TABLE)
    )


def upgrade() -> None:
    if not _table_exists():
        # 精简基线库可能从未建过 refresh_tokens；建表由 20261031_08 负责，这里安全跳过。
        return
    existing = _column_names()
    missing = [(name, type_) for name, type_ in IAM_COLUMNS if name not in existing]
    if not missing:
        return
    with op.batch_alter_table(TABLE) as batch:
        for name, type_ in missing:
            batch.add_column(sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    if not _table_exists():
        return
    existing = _column_names()
    present = [name for name, _ in IAM_COLUMNS if name in existing]
    if not present:
        return
    if not _foreign_targets_present():
        # 外键目标表缺失的精简库无法走 batch 重建（反射会失败），改用原生 DDL 删列：
        # 这类库没有历史数据要保，SQLite 3.35+/PostgreSQL 都支持直接 DROP COLUMN。
        for name in present:
            op.drop_column(TABLE, name)
        return
    with op.batch_alter_table(TABLE) as batch:
        for name in present:
            batch.drop_column(name)
