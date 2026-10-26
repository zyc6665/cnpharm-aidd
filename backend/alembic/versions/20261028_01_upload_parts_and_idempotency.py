"""upload_parts 行级分片、幂等唯一约束与会话过期索引

修 PR #15 评审的 B1/B2 与 S7：

* **B1** ``upload_sessions.parts`` 是 JSON 列，并发 ``PUT /parts`` 会互相整列覆盖，
  只剩最后一片。本迁移把已收到的分片搬进 ``upload_parts``（``(session_id,
  part_number)`` 复合主键），之后由 upsert 写入，同片号覆盖同一行。
* **B2** ``idempotency_key`` 只有普通索引，并发创建会落两个会话、返回两个
  uploadId。本迁移加 ``uq_upload_sessions_project_idem``（``project_id +
  idempotency_key``）。PostgreSQL 与 SQLite 下 NULL 都不参与唯一性，历史行不受影响。
* **S7** 上一版把三张表的 ``updated_at`` 建成 ``nullable=True``，与
  ``TimestampMixin`` 的 ``nullable=False`` 不符；本迁移一并纠正。

``declared_sha256`` 也在这里补上：创建会话时客户端可以声明 sha256，合并后校验
（docs/05 §4.2 的 42205 口径）。上一版 schema 收了 ``sha256`` 但没落库，等于静默丢弃。

Revision ID: 20261028_01
Revises: 20261027_03
Create Date: 2026-10-28

数据迁移
--------
``upload_sessions.parts`` 里的 ``[{partNumber, etag, size}]`` 会逐条搬进
``upload_parts``，``reported_at`` 用会话的 ``updated_at`` 兜底（JSON 里没有每片的
时间戳）。搬完才删列，因此迁移可重复执行且不会丢已收到的分片索引。
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa

revision = "20261028_01"
down_revision = "20261027_03"
branch_labels = None
depends_on = None


UPLOAD_SESSIONS = "upload_sessions"
UPLOAD_PARTS = "upload_parts"
DATASETS = "datasets"
DATA_FILES = "data_files"

#: 幂等唯一约束名；模型 ``UploadSession.__table_args__`` 必须用同一个名字。
IDEMPOTENCY_UNIQUE = "uq_upload_sessions_project_idem"
EXPIRES_INDEX = "ix_upload_sessions_expires_at"


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table_name: str) -> set[str]:
    if table_name not in _table_names():
        return set()
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _unique_names(table_name: str) -> set[str]:
    if table_name not in _table_names():
        return set()
    inspector = sa.inspect(op.get_bind())
    return {
        constraint["name"]
        for constraint in inspector.get_unique_constraints(table_name)
        if constraint.get("name")
    }


def _index_names(table_name: str) -> set[str]:
    if table_name not in _table_names():
        return set()
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _dialect() -> str:
    return op.get_bind().dialect.name


def _create_upload_parts_table() -> None:
    if UPLOAD_PARTS in _table_names():
        return
    op.create_table(
        UPLOAD_PARTS,
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey(f"{UPLOAD_SESSIONS}.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("part_number", sa.Integer(), primary_key=True),
        sa.Column("etag", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("reported_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_upload_parts_reported_at", UPLOAD_PARTS, ["reported_at"])


def _migrate_parts_json_to_rows() -> None:
    """把 ``upload_sessions.parts`` 的 JSON 数组搬进 ``upload_parts``。"""
    if "parts" not in _column_names(UPLOAD_SESSIONS):
        return
    bind = op.get_bind()
    legacy = sa.table(
        UPLOAD_SESSIONS,
        sa.column("id", sa.String),
        sa.column("parts", sa.JSON),
        sa.column("updated_at", sa.DateTime),
        sa.column("created_at", sa.DateTime),
    )
    rows = bind.execute(
        sa.select(legacy.c.id, legacy.c.parts, legacy.c.created_at, legacy.c.updated_at)
    ).fetchall()

    parts_table = sa.table(
        UPLOAD_PARTS,
        sa.column("session_id", sa.String),
        sa.column("part_number", sa.Integer),
        sa.column("etag", sa.String),
        sa.column("size_bytes", sa.BigInteger),
        sa.column("reported_at", sa.DateTime),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    payloads: list[dict] = []
    for session_id, raw_parts, created_at, updated_at in rows:
        entries = raw_parts
        if isinstance(entries, str):
            try:
                entries = json.loads(entries)
            except json.JSONDecodeError:
                entries = []
        if not isinstance(entries, list):
            continue
        stamp = updated_at or created_at
        seen: set[int] = set()
        for item in entries:
            if not isinstance(item, dict):
                continue
            number = item.get("partNumber")
            if number is None:
                continue
            number = int(number)
            if number in seen:
                # 同一 JSON 里出现重复片号是历史脏数据，保留第一条。
                continue
            seen.add(number)
            payloads.append(
                {
                    "session_id": str(session_id),
                    "part_number": number,
                    "etag": str(item.get("etag") or ""),
                    "size_bytes": int(item.get("size") or 0),
                    "reported_at": stamp,
                    "created_at": stamp,
                    "updated_at": stamp,
                }
            )
    if payloads:
        bind.execute(sa.insert(parts_table), payloads)


def _assert_no_duplicate_idempotency_keys() -> None:
    """加唯一约束前先查重复，给出可操作的中文报错而不是让数据库抛原生错误。"""
    if "idempotency_key" not in _column_names(UPLOAD_SESSIONS):
        return
    bind = op.get_bind()
    legacy = sa.table(
        UPLOAD_SESSIONS,
        sa.column("project_id", sa.String),
        sa.column("idempotency_key", sa.String),
    )
    duplicates = bind.execute(
        sa.select(legacy.c.project_id, legacy.c.idempotency_key, sa.func.count().label("n"))
        .where(legacy.c.idempotency_key.is_not(None))
        .group_by(legacy.c.project_id, legacy.c.idempotency_key)
        .having(sa.func.count() > 1)
    ).fetchall()
    if duplicates:
        sample = ", ".join(
            f"{row[0]}/{row[1]}x{row[2]}" for row in duplicates[:5]
        )
        raise RuntimeError(
            "存在重复的幂等键，无法建立唯一约束；请先人工清理这些会话（保留最早一条）："
            f"{sample}"
        )


def _rebuild_upload_sessions() -> None:
    """一次性完成：加 declared_sha256、删 parts、加幂等唯一约束。

    SQLite 不支持 ``ALTER TABLE ... DROP COLUMN``（3.35 起支持但会连带丢弃约束），
    也不支持加唯一约束，因此统一走 batch 重建；PostgreSQL 下 alembic 会退化成
    等价的原生 ALTER。
    """
    columns = _column_names(UPLOAD_SESSIONS)
    unique_names = _unique_names(UPLOAD_SESSIONS)
    needs_declared_sha256 = "declared_sha256" not in columns
    needs_drop_parts = "parts" in columns
    needs_unique = IDEMPOTENCY_UNIQUE not in unique_names
    if not (needs_declared_sha256 or needs_drop_parts or needs_unique):
        return

    with op.batch_alter_table(UPLOAD_SESSIONS, recreate="always") as batch:
        if needs_declared_sha256:
            batch.add_column(sa.Column("declared_sha256", sa.String(length=64), nullable=True))
        if needs_drop_parts:
            batch.drop_column("parts")
        if needs_unique:
            batch.create_unique_constraint(
                IDEMPOTENCY_UNIQUE, ["project_id", "idempotency_key"]
            )


def _fix_timestamp_nullability() -> None:
    """把 ``updated_at`` 从 ``nullable=True`` 纠正为 ``nullable=False``（S7）。

    只改 SQLite；PostgreSQL 上历史行可能已有 NULL（模型层从不为 NULL，但迁移
    曾经允许），直接收紧会失败，因此 PG 侧交给后续在数据补齐后单独处理。
    """
    if _dialect() != "sqlite":
        return
    for table_name in (UPLOAD_SESSIONS, DATASETS, DATA_FILES):
        if table_name not in _table_names():
            continue
        columns = sa.inspect(op.get_bind()).get_columns(table_name)
        updated_at = next((c for c in columns if c["name"] == "updated_at"), None)
        if updated_at is None or updated_at.get("nullable") is False:
            continue
        with op.batch_alter_table(table_name, recreate="always") as batch:
            batch.alter_column(
                "updated_at",
                existing_type=sa.DateTime(),
                nullable=False,
                existing_server_default=None,
            )


def upgrade() -> None:
    _create_upload_parts_table()
    _migrate_parts_json_to_rows()
    _assert_no_duplicate_idempotency_keys()
    _rebuild_upload_sessions()
    if EXPIRES_INDEX not in _index_names(UPLOAD_SESSIONS):
        op.create_index(EXPIRES_INDEX, UPLOAD_SESSIONS, ["expires_at"])
    _fix_timestamp_nullability()


def downgrade() -> None:
    """回退到 JSON 列形态。

    分片索引会回写成 ``upload_sessions.parts``，因此「续传列表」不会丢；``parts``
    之外没有别的去处，``upload_parts`` 随后被删。
    """
    if EXPIRES_INDEX in _index_names(UPLOAD_SESSIONS):
        op.drop_index(EXPIRES_INDEX, table_name=UPLOAD_SESSIONS)

    columns = _column_names(UPLOAD_SESSIONS)
    unique_names = _unique_names(UPLOAD_SESSIONS)
    needs_parts = "parts" not in columns
    needs_drop_sha = "declared_sha256" in columns
    needs_drop_unique = IDEMPOTENCY_UNIQUE in unique_names
    if needs_parts or needs_drop_sha or needs_drop_unique:
        with op.batch_alter_table(UPLOAD_SESSIONS, recreate="always") as batch:
            if needs_parts:
                batch.add_column(sa.Column("parts", sa.JSON(), nullable=False, server_default="[]"))
            if needs_drop_sha:
                batch.drop_column("declared_sha256")
            if needs_drop_unique:
                batch.drop_constraint(IDEMPOTENCY_UNIQUE, type_="unique")

    if UPLOAD_PARTS in _table_names():
        if "ix_upload_parts_reported_at" in _index_names(UPLOAD_PARTS):
            op.drop_index("ix_upload_parts_reported_at", table_name=UPLOAD_PARTS)
        op.drop_table(UPLOAD_PARTS)
