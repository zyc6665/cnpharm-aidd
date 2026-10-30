"""用户表补充企业内网 LDAP 认证所需列（username / auth_source / ldap_dn / last_login_at）。

背景
----
设计见 ``docs/superpowers/specs/2026-10-30-enterprise-ldap-auth-design.md`` §6.1：
登录标识从 email 改为 username，认证源由 ``auth_source`` 决定，email 降级为可选
联系方式，LDAP 用户不保存本地口令（``password_hash`` 可空），
登录成功回填 ``ldap_dn`` 与 ``last_login_at``。

本迁移步骤（幂等，可重复执行）
------------------------------
1. 加四列（先 nullable）：``username`` / ``auth_source`` / ``ldap_dn`` / ``last_login_at``。
2. 回填 ``username``：email 本地部分小写、仅保留 ``[A-Za-z0-9._-]``、截断到 56；
   重名按 ``id`` 排序追加 ``_<id 前 8 位>``；空 email 或非法字符清洗后为空用
   ``user_<id 前 8 位>``；回填后仍以大小写不敏感去重，保证 ≤64。``auth_source``
   回填 ``'local'``。
3. 建唯一函数索引 ``uq_users_username_lower``（PG ``lower(username)``；
   SQLite ``username COLLATE NOCASE``）与 ``ldap_dn`` 部分唯一索引
   ``uq_users_ldap_dn``（``WHERE ldap_dn IS NOT NULL``，两方言均支持）。
4. ``username`` / ``auth_source`` 改 NOT NULL；``email`` / ``password_hash`` 改可空；
   去掉 email 的唯一约束/索引，保留普通索引。
5. 加 ``auth_source`` CHECK ``IN ('local','ldap')``。

downgrade 对称：删两个索引、CHECK、四列，恢复 email NOT NULL + 唯一索引与
``password_hash`` NOT NULL；若存在空 email / 空 hash / 重复 email，记录 warning
并尽力恢复，不静默吞错。

不在迁移里 import 应用模型，纯 SQL / ``op``；SQLite 需要改约束/列时用
``batch_alter_table`` 重建表，PostgreSQL 直接 ``ALTER TABLE``。

Revision ID: 20261031_07
Revises: 20261031_06
Create Date: 2026-10-31
"""

from __future__ import annotations

import logging
import re
import uuid

import sqlalchemy as sa
from alembic import op


revision = "20261031_07"
down_revision = "20261031_06"
branch_labels = None
depends_on = None

USERS = "users"
HASH_COL = "password_hash"
USERNAME_INDEX = "uq_users_username_lower"
LDAP_DN_INDEX = "uq_users_ldap_dn"
AUTH_SOURCE_CHECK = "ck_users_auth_source"
AUTH_SOURCE_SQL = "auth_source IN ('local', 'ldap')"

#: (列名, 类型, 添加时是否可空)。先全部 nullable，随后再把 username/auth_source 收紧。
NEW_COLUMNS = (
    ("username", sa.String(64), True),
    ("auth_source", sa.String(16), True),
    ("ldap_dn", sa.String(512), True),
    ("last_login_at", sa.DateTime(timezone=True), True),
)

_INVALID_USERNAME_CHARS = re.compile(r"[^A-Za-z0-9._-]")

logger = logging.getLogger("alembic.users_ldap_auth")


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


def _column_nullable(table: str, column: str) -> bool | None:
    if table not in _table_names():
        return None
    for item in sa.inspect(_bind()).get_columns(table):
        if item["name"] == column:
            return bool(item.get("nullable"))
    return None


def _index_names(table: str) -> set[str]:
    if table not in _table_names():
        return set()
    return {index["name"] for index in sa.inspect(_bind()).get_indexes(table) if index.get("name")}


def _check_constraint_names(table: str) -> set[str]:
    if table not in _table_names():
        return set()
    return {
        item["name"]
        for item in sa.inspect(_bind()).get_check_constraints(table)
        if item.get("name")
    }


def _sanitize_id(uid: str | None) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", uid or "")
    return cleaned or "user"


def _derive_base_username(email: str | None, uid: str | None) -> str:
    local = (email or "").split("@", 1)[0].strip().lower()
    local = _INVALID_USERNAME_CHARS.sub("_", local)[:56]
    if local:
        return local
    return f"user_{_sanitize_id(uid)[:8]}"


def _candidate_with_suffix(base: str, uid: str | None, attempt: int) -> str:
    if attempt == 1:
        suffix = _sanitize_id(uid)[:8]
    else:
        suffix = uuid.uuid4().hex[:8]
    return (f"{base[:55]}_{suffix}")[:64]


def _add_columns() -> None:
    existing = _column_names(USERS)
    for name, column_type, _nullable in NEW_COLUMNS:
        if name in existing:
            continue
        kwargs: dict[str, object] = {}
        if name == "auth_source":
            kwargs["server_default"] = sa.text("'local'")
        op.add_column(USERS, sa.Column(name, column_type, nullable=True, **kwargs))


def _backfill_auth_source() -> None:
    if "auth_source" not in _column_names(USERS):
        return
    _bind().execute(sa.text(f"UPDATE {USERS} SET auth_source = 'local' WHERE auth_source IS NULL"))


def _backfill_usernames() -> None:
    if "username" not in _column_names(USERS):
        return
    bind = _bind()
    has_email = "email" in _column_names(USERS)
    if has_email:
        rows = bind.execute(
            sa.text(f"SELECT id, email FROM {USERS} WHERE username IS NULL ORDER BY id")
        ).fetchall()
    else:
        rows = [
            (row[0], None)
            for row in bind.execute(
                sa.text(f"SELECT id FROM {USERS} WHERE username IS NULL ORDER BY id")
            ).fetchall()
        ]
    if not rows:
        return

    used = {
        (value or "").lower()
        for (value,) in bind.execute(
            sa.text(f"SELECT username FROM {USERS} WHERE username IS NOT NULL")
        ).fetchall()
    }

    updates: list[dict[str, object]] = []
    for uid, email in rows:
        base = _derive_base_username(email, uid)
        candidate = base
        attempt = 0
        while candidate.lower() in used:
            attempt += 1
            candidate = _candidate_with_suffix(base, uid, attempt)
        used.add(candidate.lower())
        updates.append({"u": candidate, "i": uid})

    if updates:
        bind.execute(sa.text(f"UPDATE {USERS} SET username = :u WHERE id = :i"), updates)


def _drop_email_unique_and_ensure_plain_index() -> None:
    if "email" not in _column_names(USERS):
        return
    inspector = sa.inspect(_bind())

    for constraint in inspector.get_unique_constraints(USERS):
        columns = constraint.get("column_names") or []
        name = constraint.get("name")
        if columns == ["email"] and name:
            if _dialect() == "postgresql":
                op.execute(f'ALTER TABLE "{USERS}" DROP CONSTRAINT IF EXISTS "{name}"')
            else:
                with op.batch_alter_table(USERS) as batch:
                    batch.drop_constraint(name, type_="unique")

    for index in sa.inspect(_bind()).get_indexes(USERS):
        if not index.get("unique"):
            continue
        if (index.get("column_names") or []) != ["email"]:
            continue
        name = index.get("name")
        if name and not name.startswith("sqlite_autoindex"):
            op.drop_index(name, table_name=USERS)

    plain_email_index = any(
        (index.get("column_names") or []) == ["email"] and not index.get("unique")
        for index in sa.inspect(_bind()).get_indexes(USERS)
    )
    if not plain_email_index:
        op.create_index("ix_users_email", USERS, ["email"])


def _set_nullable_pg(column: str, nullable: bool, column_type: sa.types.TypeEngine) -> None:
    if column not in _column_names(USERS):
        return
    current = _column_nullable(USERS, column)
    if current is None or current == nullable:
        return
    action = "DROP NOT NULL" if nullable else "SET NOT NULL"
    op.execute(f'ALTER TABLE "{USERS}" ALTER COLUMN "{column}" {action}')


def _apply_sqlite_table_changes() -> None:
    columns = _column_names(USERS)
    email_nullable = _column_nullable(USERS, "email")
    hash_nullable = _column_nullable(USERS, HASH_COL)
    auth_source_nullable = _column_nullable(USERS, "auth_source")
    username_nullable = _column_nullable(USERS, "username")
    has_check = AUTH_SOURCE_CHECK in _check_constraint_names(USERS)

    with op.batch_alter_table(USERS) as batch:
        if "email" in columns and email_nullable is False:
            batch.alter_column(
                "email", existing_type=sa.String(255), existing_nullable=False, nullable=True
            )
        if HASH_COL in columns and hash_nullable is False:
            batch.alter_column(
                HASH_COL, existing_type=sa.String(255), existing_nullable=False, nullable=True
            )
        if "auth_source" in columns and auth_source_nullable is True:
            batch.alter_column(
                "auth_source",
                existing_type=sa.String(16),
                existing_nullable=True,
                nullable=False,
            )
        if "username" in columns and username_nullable is True:
            batch.alter_column(
                "username", existing_type=sa.String(64), existing_nullable=True, nullable=False
            )
        if not has_check:
            batch.create_check_constraint(AUTH_SOURCE_CHECK, AUTH_SOURCE_SQL)


def _ensure_auth_source_check_pg() -> None:
    if AUTH_SOURCE_CHECK in _check_constraint_names(USERS):
        return
    op.execute(
        f'ALTER TABLE "{USERS}" ADD CONSTRAINT "{AUTH_SOURCE_CHECK}" CHECK ({AUTH_SOURCE_SQL})'
    )


def _create_username_index() -> None:
    if USERNAME_INDEX in _index_names(USERS):
        return
    if _dialect() == "postgresql":
        op.execute(
            f'CREATE UNIQUE INDEX IF NOT EXISTS "{USERNAME_INDEX}" '
            f'ON "{USERS}" (lower(username))'
        )
    else:
        op.execute(
            f'CREATE UNIQUE INDEX IF NOT EXISTS "{USERNAME_INDEX}" '
            f'ON "{USERS}" (username COLLATE NOCASE)'
        )


def _create_ldap_dn_index() -> None:
    if LDAP_DN_INDEX in _index_names(USERS):
        return
    op.execute(
        f'CREATE UNIQUE INDEX IF NOT EXISTS "{LDAP_DN_INDEX}" '
        f'ON "{USERS}" (ldap_dn) WHERE ldap_dn IS NOT NULL'
    )


def _ensure_plain_username_index() -> None:
    """模型层 ``username index=True`` 生成的普通索引（非唯一）。

    全新库由基线 ``create_all`` 建出，但 downgrade 删列后再次 upgrade 时它已随列
    被删除，故这里补建，保证升级后 schema 与模型一致。
    """
    if "ix_users_username" in _index_names(USERS):
        return
    op.create_index("ix_users_username", USERS, ["username"])


def upgrade() -> None:
    if USERS not in _table_names():
        # 精简基线库可能从未建过 users；其它迁移负责建表，这里安全跳过。
        return

    _add_columns()
    _backfill_auth_source()
    _backfill_usernames()
    _drop_email_unique_and_ensure_plain_index()

    if _dialect() == "postgresql":
        _set_nullable_pg("email", True, sa.String(255))
        _set_nullable_pg(HASH_COL, True, sa.String(255))
        _set_nullable_pg("auth_source", False, sa.String(16))
        _set_nullable_pg("username", False, sa.String(64))
        _ensure_auth_source_check_pg()
    else:
        _apply_sqlite_table_changes()

    # 唯一/部分索引必须在 SQLite 的 batch 重建之后创建，重建不会保留自定义表达式索引。
    _create_username_index()
    _create_ldap_dn_index()
    _ensure_plain_username_index()


def _restore_not_null(column: str, column_type: sa.types.TypeEngine) -> None:
    if column not in _column_names(USERS):
        return
    if _column_nullable(USERS, column) is False:
        return
    null_count = _bind().execute(
        sa.text(f'SELECT count(*) FROM {USERS} WHERE "{column}" IS NULL')
    ).scalar()
    if null_count:
        logger.warning(
            "downgrade 20261031_07: %s 列存在 %s 行为空，无法恢复 NOT NULL，保留可空。",
            column,
            null_count,
        )
        return
    if _dialect() == "postgresql":
        op.execute(f'ALTER TABLE "{USERS}" ALTER COLUMN "{column}" SET NOT NULL')
    else:
        with op.batch_alter_table(USERS) as batch:
            batch.alter_column(
                column, existing_type=column_type, existing_nullable=True, nullable=False
            )


def _restore_email_constraints() -> None:
    if "email" not in _column_names(USERS):
        return
    bind = _bind()
    null_count = bind.execute(
        sa.text(f"SELECT count(*) FROM {USERS} WHERE email IS NULL")
    ).scalar()
    if null_count:
        logger.warning(
            "downgrade 20261031_07: email 存在 %s 行为空，无法恢复 NOT NULL，保留可空。",
            null_count,
        )
    else:
        _restore_not_null("email", sa.String(255))

    duplicate_groups = bind.execute(
        sa.text(
            f"SELECT count(*) FROM ("
            f"SELECT email FROM {USERS} WHERE email IS NOT NULL "
            f"GROUP BY email HAVING count(*) > 1) AS dup"
        )
    ).scalar()
    if duplicate_groups:
        logger.warning(
            "downgrade 20261031_07: email 存在 %s 组重复值，跳过恢复唯一索引。",
            duplicate_groups,
        )
        return

    for index in sa.inspect(bind).get_indexes(USERS):
        if (index.get("column_names") or []) != ["email"]:
            continue
        name = index.get("name")
        if name and not name.startswith("sqlite_autoindex"):
            op.drop_index(name, table_name=USERS)
    op.create_index("ix_users_email", USERS, ["email"], unique=True)


def downgrade() -> None:
    if USERS not in _table_names():
        return

    for index_name in (USERNAME_INDEX, LDAP_DN_INDEX):
        if index_name in _index_names(USERS):
            op.execute(f'DROP INDEX IF EXISTS "{index_name}"')

    if AUTH_SOURCE_CHECK in _check_constraint_names(USERS):
        if _dialect() == "postgresql":
            op.execute(
                f'ALTER TABLE "{USERS}" DROP CONSTRAINT IF EXISTS "{AUTH_SOURCE_CHECK}"'
            )
        else:
            with op.batch_alter_table(USERS) as batch:
                batch.drop_constraint(AUTH_SOURCE_CHECK, type_="check")

    _restore_email_constraints()
    _restore_not_null(HASH_COL, sa.String(255))

    existing = _column_names(USERS)
    to_drop = [name for name, _type, _nullable in NEW_COLUMNS if name in existing]
    if not to_drop:
        return

    # 先删掉引用这些列的普通索引（如 ix_users_username），否则 SQLite batch 重建表时
    # 会尝试为已删除的列重建索引而报 "no such column: username"。
    drop_set = set(to_drop)
    for index in sa.inspect(_bind()).get_indexes(USERS):
        name = index.get("name")
        columns = set(index.get("column_names") or [])
        if name and not name.startswith("sqlite_autoindex") and columns & drop_set:
            op.drop_index(name, table_name=USERS)

    if _dialect() == "postgresql":
        for column in to_drop:
            op.execute(f'ALTER TABLE "{USERS}" DROP COLUMN IF EXISTS "{column}"')
    else:
        with op.batch_alter_table(USERS) as batch:
            for column in to_drop:
                batch.drop_column(column)
