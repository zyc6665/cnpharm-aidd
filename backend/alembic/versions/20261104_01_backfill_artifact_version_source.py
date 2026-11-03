"""Task 3a 补齐：回填 ``artifact_versions.source_task_id``（历史行，best-effort）。

背景
----
``20261030_05`` 已经给 ``artifact_versions`` 加上 ``source_task_id`` /
``source_attempt_id`` 等来源列，但**只加列不回填**——迁移前的历史版本这些列全是
``NULL``。于是 ``artifact_lineage_graph.produced_by`` 对历史版本只能回退到
``Artifact.source_task_id``（artifact 级），无法回答「哪次执行产出了这一版」。

本迁移对历史行做一次 best-effort 回填：把每个版本所属 artifact 的
``source_task_id`` 复制到该版本上。

回填策略与局限（务必知悉）
--------------------------
- **只回填 ``source_task_id``，绝不回填 ``source_attempt_id``**：历史数据里没有
  「这是该任务的第几次尝试/重试」的信息。硬填一个 ``attempt_id`` 会让「哪次执行」
  看起来有答案、实则是错的，比留 ``NULL`` 更糟。故 ``source_attempt_id`` 保持 ``NULL``。
- **只能退化到 artifact 级**：当一个 artifact 由多个任务产出多个版本时，历史行全部
  被写成同一个 ``Artifact.source_task_id``（即首建者），**无法区分多任务**。这是
  历史数据缺失导致的不可逆损失，回填只是让旧行至少有一个实体级来源，不是真值。
- **幂等**：``WHERE source_task_id IS NULL`` + ``EXISTS(... source_task_id IS NOT NULL)``，
  重复执行不改变任何已回填行；对 artifact 本身也无 ``source_task_id`` 的行直接跳过
  （写 ``NULL`` 无意义）。
- ``downgrade`` 为**空操作**：回填是把 ``NULL`` 变成非空，无法区分「回填得来的值」和
  「本就有值」，逆向清空会破坏真实数据，因此故意不撤销数据（仅列/索引由
  ``20261030_05`` 负责撤回）。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20261104_01"
down_revision = "20261103_01"
branch_labels = None
depends_on = None


# 关联子查询回填：把所属 artifact 的 source_task_id 复制到 source_task_id 仍为 NULL
# 的版本行。EXISTS 守卫确保只触碰「artifact 本身有来源」的行，且天然幂等。
# 该语句在 SQLite 与 PostgreSQL 上语义一致（标准 SQL 关联子查询 UPDATE）。
BACKFILL_SQL = """
UPDATE artifact_versions
SET source_task_id = (
    SELECT artifacts.source_task_id
    FROM artifacts
    WHERE artifacts.id = artifact_versions.artifact_id
)
WHERE source_task_id IS NULL
  AND EXISTS (
    SELECT 1
    FROM artifacts
    WHERE artifacts.id = artifact_versions.artifact_id
      AND artifacts.source_task_id IS NOT NULL
  )
"""


def _has_table(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    # legacy 恢复场景下表可能不存在，直接跳过（与 20261030_05 的守卫同口径）。
    if not _has_table("artifact_versions") or not _has_table("artifacts"):
        return
    op.execute(sa.text(BACKFILL_SQL))


def downgrade() -> None:
    # 空操作：数据回填不可逆（见模块 docstring「回填策略与局限」）。
    pass
