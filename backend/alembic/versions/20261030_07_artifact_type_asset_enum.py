"""Task 5 §7.1：把 ``artifacts.artifact_type`` 收敛为受控资产枚举。

背景
----
``artifact_type`` 原来是自由 ``String(100)``，上传、标准产物、执行回传等所有写入
路径都能写任意字符串。一旦值域不受控，「数据资产页按类别检索」就无法稳定成立，下游
绑定解析/谱系也拿不到可穷举的类型集合。

本迁移给 ``artifacts.artifact_type`` 加一条命名 CHECK 约束，值域与
``app.artifact_standards.asset_types.ASSET_ARTIFACT_TYPES`` 同源（单一真源）：

    compound_set / protein_structure / binding_pocket / ligand_structure /
    molecule_table / md_trajectory / run_report / dataset

历史非法值的兼容策略（不静默丢弃）
----------------------------------
1. **已知识别别名**：``LEGACY_SEMANTIC_TYPE_ALIASES`` 里的旧名（``protein_pdb``、
   ``database_query_result`` …）与两个渲染旧名（``pocket_result`` → ``binding_pocket``、
   ``file`` → ``run_report``）做**语义等价归一**（只改类型名，不动版本/文件）。
2. **无法归一的值**：迁移**显式失败**并列出 offending 值，要求人工确认后再迁移。
   不做「猜一个最近的类型」式静默映射——那会把 ``document`` 之类错误归到
   ``run_report``，制造看不出错的语义污染。

SQLite 不支持 ``ALTER TABLE ... ADD CONSTRAINT``，因此加/删约束都走
``batch_alter_table`` 重建表并带命名约束。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.artifact_standards.asset_types import (
    ASSET_ARTIFACT_TYPE_CHECK_SQL,
    normalize_asset_artifact_type,
)

revision = "20261030_07"
down_revision = "20261030_06"
branch_labels = None
depends_on = None

ARTIFACTS = "artifacts"
CONSTRAINT_NAME = "ck_artifacts_artifact_type_asset_enum"


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


def _probe_and_normalize() -> None:
    """探测历史值：已知别名就地归一，归不动的显式报错。"""
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(f"SELECT DISTINCT artifact_type FROM {ARTIFACTS}")
    ).fetchall()
    distinct = {row[0] for row in rows if row[0] is not None}

    unknown = sorted(value for value in distinct if normalize_asset_artifact_type(value) is None)
    if unknown:
        raise RuntimeError(
            "artifacts.artifact_type 存在无法归一到受控资产枚举的历史值："
            f"{unknown}。请人工确认语义后再迁移（本迁移刻意不静默改写/丢弃数据）。"
        )

    for value in sorted(distinct):
        normalized = normalize_asset_artifact_type(value)
        if normalized is not None and normalized != value:
            bind.execute(
                sa.text(
                    f"UPDATE {ARTIFACTS} SET artifact_type = :new WHERE artifact_type = :old"
                ),
                {"new": normalized, "old": value},
            )


def upgrade() -> None:
    if ARTIFACTS not in _table_names():
        return
    _probe_and_normalize()
    if CONSTRAINT_NAME in _check_constraint_names():
        return
    with op.batch_alter_table(ARTIFACTS) as batch_op:
        batch_op.create_check_constraint(CONSTRAINT_NAME, ASSET_ARTIFACT_TYPE_CHECK_SQL)


def downgrade() -> None:
    if ARTIFACTS not in _table_names():
        return
    if CONSTRAINT_NAME not in _check_constraint_names():
        return
    with op.batch_alter_table(ARTIFACTS) as batch_op:
        batch_op.drop_constraint(CONSTRAINT_NAME, type_="check")
