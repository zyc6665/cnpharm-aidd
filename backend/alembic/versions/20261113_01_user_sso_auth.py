"""用户表支持甲方统一身份认证（SSO）登录。

背景
----
对接《统一身份认证与管理系统-统一认证接口规范 v1》的 WEB 非网关模式
（标准 OAuth2 授权码，见 ``docs/03-接口/32-统一身份认证对接方案.md``）：
平台不保存 SSO 用户口令，``auth_source`` 增加 ``sso``；``sso_uid`` 存统一认证
``getUserInfo`` 返回的 ``userId``，用于幂等匹配——改名/换部门后仍能认出同一人，
不会重复开户。

本迁移步骤（幂等，可重复执行）
------------------------------
1. 加可空列 ``sso_uid``（``String(128)``），本地/LDAP 用户保持 NULL。
2. 扩展 ``ck_users_auth_source`` 为 ``auth_source IN ('local','ldap','sso')``
   （PostgreSQL 直接 ALTER；SQLite 走 batch 重建表）。
3. 建部分唯一索引 ``uq_users_sso_uid``（``WHERE sso_uid IS NOT NULL``），
   两方言均支持；NULL 不参与唯一性，故本地/LDAP 用户互不冲突。

downgrade
---------
删索引与列，并把 CHECK 收窄回 ``('local','ldap')``。若库中仍有
``auth_source='sso'`` 的行，收窄会直接失败——此时**保留宽松 CHECK**并记录
warning（不静默吞错，也不删数据）；这类账号回滚后不再可登录，需重新接入或
由管理员重置口令。

不在迁移里 import 应用模型，纯 SQL / ``op``；SQLite 需要改约束/列时用
``batch_alter_table`` 重建表，重建不会保留自定义表达式索引，故重建后必须
重新创建 ``uq_users_username_lower`` / ``uq_users_ldap_dn`` / ``ix_users_username``。

Revision ID: 20261113_01
Revises: 20261112_01
Create Date: 2026-11-13
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op


revision = "20261113_01"
down_revision = "20261112_01"
branch_labels = None
depends_on = None

USERS = "users"
SSO_UID_COL = "sso_uid"
SSO_UID_INDEX = "uq_users_sso_uid"
AUTH_SOURCE_CHECK = "ck_users_auth_source"
AUTH_SOURCE_WIDE = "auth_source IN ('local', 'ldap', 'sso')"
AUTH_SOURCE_NARROW = "auth_source IN ('local', 'ldap')"

#: SQLite 的 batch 重建不保留自定义表达式索引，重建后按原定义补回。
EXPRESSION_INDEXES = (
    (
        "uq_users_username_lower",
        'CREATE UNIQUE INDEX IF NOT EXISTS "uq_users_username_lower" '
        'ON "users" (lower(username))',
        'CREATE UNIQUE INDEX IF NOT EXISTS "uq_users_username_lower" '
        'ON "users" (username COLLATE NOCASE)',
    ),
    (
        "uq_users_ldap_dn",
        'CREATE UNIQUE INDEX IF NOT EXISTS "uq_users_ldap_dn" '
        'ON "users" (ldap_dn) WHERE ldap_dn IS NOT NULL',
        'CREATE UNIQUE INDEX IF NOT EXISTS "uq_users_ldap_dn" '
        'ON "users" (ldap_dn) WHERE ldap_dn IS NOT NULL',
    ),
)

logger = logging.getLogger("alembic.users_sso_auth")


def _bind():
    return op.get_bind()


def _dialect() -> str:
    return _bind().dialect.name


def _table_names() -> set[str]:
    return set(sa.inspect(_bind()).get_table_names())


def _column_names(table: str) -> set[str]:
    if table not in _table_names():
        return set()
    return {column["name"] for column in sa.inspect(_bind()).get_columns(table)}


def _index_names(table: str) -> set[str]:
    if table not in _table_names():
        return set()
    return {
        index["name"]
        for index in sa.inspect(_bind()).get_indexes(table)
        if index.get("name")
    }


def _check_sql(table: str) -> str | None:
    """返回 ``ck_users_auth_source`` 的 SQL 文本；不存在则 None。"""
    if table not in _table_names():
        return None
    for item in sa.inspect(_bind()).get_check_constraints(table):
        if item.get("name") == AUTH_SOURCE_CHECK:
            return " ".join(str(item.get("sqltext") or "").split())
    return None


def _create_sso_uid_index() -> None:
    if SSO_UID_INDEX in _index_names(USERS):
        return
    op.execute(
        f'CREATE UNIQUE INDEX IF NOT EXISTS "{SSO_UID_INDEX}" '
        f'ON "{USERS}" ({SSO_UID_COL}) WHERE {SSO_UID_COL} IS NOT NULL'
    )


def _recreate_expression_indexes() -> None:
    """SQLite batch 重建表之后补回表达式索引与普通索引。"""
    is_sqlite = _dialect() != "postgresql"
    existing = _index_names(USERS)
    for name, pg_sql, sqlite_sql in EXPRESSION_INDEXES:
        if name in existing:
            continue
        op.execute(sqlite_sql if is_sqlite else pg_sql)
    if "ix_users_username" not in _index_names(USERS):
        op.create_index("ix_users_username", USERS, ["username"])


def _ensure_auth_source_check_pg(sql: str) -> None:
    current = _check_sql(USERS)
    if current == " ".join(sql.split()):
        return
    op.execute(
        f'ALTER TABLE "{USERS}" DROP CONSTRAINT IF EXISTS "{AUTH_SOURCE_CHECK}"'
    )
    op.execute(
        f'ALTER TABLE "{USERS}" ADD CONSTRAINT "{AUTH_SOURCE_CHECK}" CHECK ({sql})'
    )


def _ensure_auth_source_check_sqlite(sql: str, *, drop_column: bool = False) -> None:
    """SQLite 改 CHECK 只能重建表；顺带可一并删列，避免两次重建。"""
    current = _check_sql(USERS)
    if current == " ".join(sql.split()):
        if drop_column and SSO_UID_COL in _column_names(USERS):
            with op.batch_alter_table(USERS) as batch:
                batch.drop_column(SSO_UID_COL)
        return
    with op.batch_alter_table(USERS) as batch:
        batch.drop_constraint(AUTH_SOURCE_CHECK, type_="check")
        batch.create_check_constraint(AUTH_SOURCE_CHECK, sql)
        if drop_column and SSO_UID_COL in _column_names(USERS):
            batch.drop_column(SSO_UID_COL)


def _add_sso_uid_column() -> None:
    if SSO_UID_COL in _column_names(USERS):
        return
    op.add_column(USERS, sa.Column(SSO_UID_COL, sa.String(128), nullable=True))


def _drop_sso_uid_column_pg() -> None:
    if SSO_UID_COL not in _column_names(USERS):
        return
    op.drop_column(USERS, SSO_UID_COL)


def _count_sso_users() -> int:
    if "auth_source" not in _column_names(USERS):
        return 0
    return int(
        _bind()
        .execute(sa.text(f"SELECT count(*) FROM {USERS} WHERE auth_source = 'sso'"))
        .scalar()
        or 0
    )


def upgrade() -> None:
    if USERS not in _table_names():
        # 精简基线库可能从未建过 users；其它迁移负责建表，这里安全跳过。
        return

    _add_sso_uid_column()

    if _dialect() == "postgresql":
        _ensure_auth_source_check_pg(AUTH_SOURCE_WIDE)
    else:
        # SQLite 重建表会丢表达式索引，重建后再统一补回。
        _ensure_auth_source_check_sqlite(AUTH_SOURCE_WIDE)
        _recreate_expression_indexes()

    _create_sso_uid_index()


def downgrade() -> None:
    if USERS not in _table_names():
        return

    if SSO_UID_INDEX in _index_names(USERS):
        op.execute(f'DROP INDEX IF EXISTS "{SSO_UID_INDEX}"')

    sso_users = _count_sso_users()
    if sso_users:
        logger.warning(
            "downgrade 20261113_01: 仍存在 %s 个 auth_source='sso' 的账号，"
            "保留宽松 CHECK（local/ldap/sso），这些账号回滚后不再可登录。",
            sso_users,
        )
        target_check = AUTH_SOURCE_WIDE
    else:
        target_check = AUTH_SOURCE_NARROW

    if _dialect() == "postgresql":
        _ensure_auth_source_check_pg(target_check)
        _drop_sso_uid_column_pg()
    else:
        # 删列与改 CHECK 同一次重建完成，减少一次全表拷贝。
        _ensure_auth_source_check_sqlite(target_check, drop_column=True)
        _recreate_expression_indexes()
