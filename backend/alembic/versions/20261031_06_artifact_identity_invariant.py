"""三列身份收口（A）：归一存量 Artifact 身份并加 DB 不变量。

背景
----
``artifacts`` 用三列表达一个逻辑资产的身份：``artifact_type``（受控 8 值资产类型）、
``semantic_type``（语义标签）、``standard_type``（标准类型，可空）。历史上各写入路径
各自拼三列，导致「A 写、B 降级、C 拒收」。应用层已统一到
``app.services.artifact_identity.resolve_identity*``；本迁移负责：

1. **幂等归一存量行**（仅做有证据、可逆推的归一）：
   - ``semantic_type`` 带 ``@vN`` 后缀且其基名等于 ``artifact_type`` → 剥离后缀，
     版本落到 ``standard_version``（版本只由 ``standard_version`` 承载）；
   - 由「带版本后缀」或「已有 ``standard_version``」可判定为标准行、但
     ``standard_type`` 为空的 → 用 ``artifact_type`` 补齐 ``standard_type``。
2. **加 DB CHECK**：``standard_type IS NULL OR standard_type = artifact_type``。
   （``semantic_type == artifact_type`` 只在服务层守护，不做 DB CHECK：存量历史行/
   测试夹具合法地用 ``type@vN`` 表达版本，硬 CHECK 会拒绝它们；数据事实见
   ``backend/app/services/artifact_identity.py`` 模块文档。）
3. **脏行不丢数据**：无法自动判定 / 自相冲突的行**记录日志并原样保留**，绝不删除。
   若仍存在违反 CHECK 的行（``standard_type`` 非空且 != ``artifact_type``），则本次
   **跳过加 CHECK** 并告警，等待人工确认——迁移成功但不会因脏行而失败或丢数据。

幂等
----
- 归一 UPDATE 均有 ``WHERE`` 条件，重复执行不再命中；
- 加 CHECK 前先探测同名约束，已存在则跳过；重复 upgrade 不报错。
- downgrade 只删约束，**不回滚归一**（``type@vN`` 的原始写法无法从归一结果还原，
  见 downgrade 注释）。

SQLite 用 ``batch_alter_table`` 重建表加/删约束；PostgreSQL 用
``ALTER TABLE ... ADD/DROP CONSTRAINT``。

Revision ID: 20261031_06
Revises: 20261031_05
Create Date: 2026-10-31
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

from app.artifact_standards.asset_types import normalize_asset_artifact_type

revision = "20261031_06"
down_revision = "20261031_05"
branch_labels = None
depends_on = None

ARTIFACTS = "artifacts"
CONSTRAINT_NAME = "ck_artifacts_standard_type_matches_artifact"
CHECK_SQL = "standard_type IS NULL OR standard_type = artifact_type"

logger = logging.getLogger("alembic.artifact_identity")


def _dialect() -> str:
    return op.get_bind().dialect.name


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _check_constraint_names() -> set[str]:
    if ARTIFACTS not in _table_names():
        return set()
    return {
        item["name"]
        for item in sa.inspect(op.get_bind()).get_check_constraints(ARTIFACTS)
        if item.get("name")
    }


def _split_version(value: object) -> tuple[str | None, int | None, str | None]:
    """Return ``(base, version, error)`` for a ``semantic_type`` value.

    Tolerant by design: a malformed suffix returns an ``error`` string so the caller
    can log it and keep the row untouched instead of aborting the whole migration.
    """
    if not isinstance(value, str):
        return None, None, None
    candidate = value.strip()
    if "@" not in candidate:
        return candidate or None, None, None
    base, _, raw_version = candidate.partition("@")
    base = base.strip()
    raw_version = raw_version.strip()
    if not raw_version:
        return base or None, None, None
    try:
        version = int(raw_version)
    except ValueError:
        return base or None, None, f"非整数版本后缀: {value!r}"
    if version < 1:
        return base or None, None, f"版本后缀 < 1: {value!r}"
    return base or None, version, None


def _normalize_rows() -> list[str]:
    """Normalise what is provably normalisable; return conflict descriptions."""
    bind = op.get_bind()
    conflicts: list[str] = []

    # 1) Strip "@vN" from semantic_type where the base is the artifact type.
    rows = bind.execute(
        sa.text(
            f"SELECT artifact_type, semantic_type, standard_type, standard_version "
            f"FROM {ARTIFACTS} WHERE semantic_type LIKE '%@%'"
        )
    ).fetchall()
    for artifact_type, semantic_type, standard_type, standard_version in rows:
        base, embedded_version, error = _split_version(semantic_type)
        if error is not None:
            conflicts.append(f"semantic_type={semantic_type!r} 无法解析（{error}）")
            continue
        if embedded_version is None:
            continue  # trailing "@" with no version: nothing to move.
        normalized_base = normalize_asset_artifact_type(base) if base else None
        if normalized_base != artifact_type:
            conflicts.append(
                f"semantic_type={semantic_type!r} 的基名 {base!r} 与 "
                f"artifact_type={artifact_type!r} 不一致"
            )
            continue
        if standard_version is not None and standard_version != embedded_version:
            conflicts.append(
                f"semantic_type={semantic_type!r} 的 @ 版本 {embedded_version} 与 "
                f"standard_version={standard_version} 冲突"
            )
            continue
        new_standard_type = standard_type or artifact_type
        new_version = standard_version if standard_version is not None else embedded_version
        # ``IS :param`` is not portable to PostgreSQL for non-NULL values, so spell out
        # the NULL / equality predicates explicitly for both nullable columns.
        where_parts = ["artifact_type = :at", "semantic_type = :old"]
        params = {
            "sem": artifact_type,
            "st": new_standard_type,
            "sv": new_version,
            "at": artifact_type,
            "old": semantic_type,
        }
        if standard_type is None:
            where_parts.append("standard_type IS NULL")
        else:
            where_parts.append("standard_type = :oldst")
            params["oldst"] = standard_type
        if standard_version is None:
            where_parts.append("standard_version IS NULL")
        else:
            where_parts.append("standard_version = :oldsv")
            params["oldsv"] = standard_version
        bind.execute(
            sa.text(
                f"UPDATE {ARTIFACTS} SET semantic_type = :sem, standard_type = :st, "
                f"standard_version = :sv WHERE " + " AND ".join(where_parts)
            ),
            params,
        )

    # 2) Standard rows that only carry a version: fill standard_type from artifact_type.
    bind.execute(
        sa.text(
            f"UPDATE {ARTIFACTS} SET standard_type = artifact_type "
            f"WHERE standard_type IS NULL AND standard_version IS NOT NULL"
        )
    )

    return conflicts


def _probe_standard_type_conflicts() -> list[str]:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            f"SELECT DISTINCT artifact_type, standard_type FROM {ARTIFACTS} "
            f"WHERE standard_type IS NOT NULL AND standard_type != artifact_type"
        )
    ).fetchall()
    return [
        f"(artifact_type={artifact_type!r}, standard_type={standard_type!r})"
        for artifact_type, standard_type in rows
    ]


def _add_check_constraint() -> None:
    if _dialect() == "postgresql":
        op.execute(
            f'ALTER TABLE "{ARTIFACTS}" ADD CONSTRAINT "{CONSTRAINT_NAME}" '
            f"CHECK ({CHECK_SQL})"
        )
        return
    with op.batch_alter_table(ARTIFACTS) as batch_op:
        batch_op.create_check_constraint(CONSTRAINT_NAME, CHECK_SQL)


def _drop_check_constraint() -> None:
    if _dialect() == "postgresql":
        op.execute(
            f'ALTER TABLE "{ARTIFACTS}" DROP CONSTRAINT IF EXISTS "{CONSTRAINT_NAME}"'
        )
        return
    with op.batch_alter_table(ARTIFACTS) as batch_op:
        batch_op.drop_constraint(CONSTRAINT_NAME, type_="check")


def upgrade() -> None:
    if ARTIFACTS not in _table_names():
        # 精简基线库可能从未建过 artifacts；本项目其它迁移负责建表，这里安全跳过。
        return

    conflicts = _normalize_rows()
    for description in conflicts:
        logger.warning(
            "artifact identity migration: 保留脏行（未自动归一）: %s", description
        )

    if CONSTRAINT_NAME in _check_constraint_names():
        return

    violating = _probe_standard_type_conflicts()
    if violating:
        for description in violating:
            logger.warning(
                "artifact identity migration: standard_type 与 artifact_type 冲突，跳过加 CHECK: %s",
                description,
            )
        logger.warning(
            "artifact identity migration: 存在无法自动判定的标准类型冲突，"
            "本次未添加约束 %s（数据已保留，待人工确认后重跑）",
            CONSTRAINT_NAME,
        )
        return

    _add_check_constraint()


def downgrade() -> None:
    if ARTIFACTS not in _table_names():
        return
    if CONSTRAINT_NAME not in _check_constraint_names():
        return
    # 刻意不回滚 backfill：JSON 里没有保留 "type@vN" 的原始语义，无法无损还原；
    # 强行还原会重新制造不一致的三列身份。约束只约束未来写入，故反向仅删约束。
    _drop_check_constraint()
