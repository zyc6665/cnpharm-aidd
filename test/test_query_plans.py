"""查询计划回归：热点分页查询不得出现 ``TEMP B-TREE``。

为什么单独测"查询计划"而不是测耗时：
耗时测试在 CI（共享 runner、空库、冷缓存）上噪声极大，抖动经常超过收益本身；
而"有没有用上索引"是**布尔事实**——计划里出现 ``USE TEMP B-TREE FOR ORDER BY``
就说明数据库要把全部命中行先排一遍，代价与数据量成正比，这正是 docs/20 §1 实测里
6.26ms→1.10ms、51.07ms→0.69ms 差距的来源。

因此这里断言**计划形态**，不测时间：①不出现 ``TEMP B-TREE``；②出现预期索引名。
索引用 ``Base.metadata`` 建（模型是索引的唯一真源，见 docs/20 §6）。
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

import app.models  # noqa: F401  # 让 Base.metadata 认识全部表
from app.database.base import Base


@pytest.fixture()
def plan_connection(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'plan.db'}")
    Base.metadata.create_all(engine)
    try:
        with engine.connect() as connection:
            yield connection
    finally:
        engine.dispose()


def _plan(connection, sql: str, params: dict) -> str:
    rows = connection.execute(text(f"EXPLAIN QUERY PLAN {sql}"), params).fetchall()
    return "\n".join(str(row[-1]) for row in rows)


@pytest.mark.parametrize(
    ("name", "sql", "params", "expected_index"),
    [
        (
            # 单值等值 + 排序：索引一次区间扫完，不应出现内存排序。
            "结果中心（单终态）：project_id + status + finished_at DESC",
            """
            SELECT id FROM tasks
            WHERE project_id = :project_id AND status = 'SUCCESS'
            ORDER BY finished_at DESC, created_at DESC
            LIMIT 20
            """,
            {"project_id": "p1"},
            "ix_tasks_project_status_finished",
        ),
        (
            "任务列表：user_id + status + created_at DESC",
            """
            SELECT id FROM tasks
            WHERE user_id = :user_id AND status = 'RUNNING'
            ORDER BY created_at DESC
            LIMIT 20
            """,
            {"user_id": "u1"},
            "ix_tasks_user_status_created",
        ),
        (
            "任务列表：project_id + status + created_at DESC",
            """
            SELECT id FROM tasks
            WHERE project_id = :project_id AND status = 'SUCCESS'
            ORDER BY created_at DESC
            LIMIT 20
            """,
            {"project_id": "p1"},
            "ix_tasks_project_status_created",
        ),
        (
            "审计日志：action + 时间范围 + created_at DESC",
            """
            SELECT id FROM audit_logs
            WHERE action = 'login' AND created_at >= :since
            ORDER BY created_at DESC
            LIMIT 50
            """,
            {"since": "2026-01-01 00:00:00"},
            "ix_audit_logs_action_created",
        ),
        (
            "任务日志：task_id + timestamp",
            """
            SELECT id FROM task_logs
            WHERE task_id = :task_id
            ORDER BY timestamp ASC
            LIMIT 100
            """,
            {"task_id": "t1"},
            "ix_task_logs_task_timestamp",
        ),
        (
            # C1 产物列表游标：project_id 等值 + (created_at, id) 行值区间 + 全序 ORDER BY。
            "产物列表（游标）：project_id + (created_at, id) < (?, ?)",
            """
            SELECT id FROM artifacts
            WHERE project_id = :project_id
              AND (created_at, id) < (:last_ts, :last_id)
            ORDER BY created_at DESC, id DESC
            LIMIT 20
            """,
            {"project_id": "p1", "last_ts": "2026-01-01 00:00:00", "last_id": "x"},
            "ix_artifacts_project_created_id",
        ),
        (
            # C1 工作流运行游标（按项目）：project_id 等值 + (created_at, id) 行值区间。
            "工作流运行（游标，按项目）：project_id + (created_at, id) < (?, ?)",
            """
            SELECT id FROM workflow_runs
            WHERE project_id = :project_id
              AND (created_at, id) < (:last_ts, :last_id)
            ORDER BY created_at DESC, id DESC
            LIMIT 20
            """,
            {"project_id": "p1", "last_ts": "2026-01-01 00:00:00", "last_id": "x"},
            "ix_workflow_runs_project_created",
        ),
        (
            # C1 工作流运行游标（按 owner）：owner_id 等值 + (created_at, id) 行值区间。
            "工作流运行（游标，按 owner）：owner_id + (created_at, id) < (?, ?)",
            """
            SELECT id FROM workflow_runs
            WHERE owner_id = :owner_id
              AND (created_at, id) < (:last_ts, :last_id)
            ORDER BY created_at DESC, id DESC
            LIMIT 20
            """,
            {"owner_id": "u1", "last_ts": "2026-01-01 00:00:00", "last_id": "x"},
            "ix_workflow_runs_owner_created",
        ),
    ],
)
def test_hot_pagination_query_uses_index_without_sort(
    plan_connection, name: str, sql: str, params: dict, expected_index: str
) -> None:
    plan = _plan(plan_connection, sql, params)
    assert "TEMP B-TREE" not in plan.upper(), f"{name} 仍在内存排序：\n{plan}"
    assert expected_index in plan, f"{name} 未使用预期索引 {expected_index}：\n{plan}"


def test_result_center_multi_status_still_uses_index(plan_connection) -> None:
    """结果中心的 ``status IN (...)`` 形态：共用同一棵复合索引。

    这条**不断言**没有 TEMP B-TREE，原因是 SQLite 的能力边界而不是索引没建对：
    ``status IN (4 个值)`` 会被拆成多段区间扫描，每段内部有序、跨段不保证整体有序，
    SQLite 只能再排一次。PostgreSQL 会做「分段有序 + 归并」，同一棵索引能保住
    ORDER BY（实测 6.26ms→1.10ms 就是靠它）。因此这里只断言索引被用上，
    性能收益由 docs/20 §1 的实测数据负责。
    """
    plan = _plan(
        plan_connection,
        """
        SELECT id FROM tasks
        WHERE project_id = :project_id
          AND status IN ('SUCCESS', 'FAILURE', 'CANCELED', 'TIMEOUT')
        ORDER BY finished_at DESC, created_at DESC
        LIMIT 20
        """,
        {"project_id": "p1"},
    )
    # 终态多值 IN 现在由部分索引 ix_tasks_project_terminal_finished_id 支撑（status
    # 写进谓词、不进键）。旧的两棵复合索引仍可能被 SQLite 选中（例如偏移模式按
    # created_at 兜底排序时），一并接受。
    used = (
        "ix_tasks_project_terminal_finished_id",
        "ix_tasks_project_status_finished",
        "ix_tasks_project_status_created",
    )
    assert any(name in plan for name in used), plan


def test_result_center_cursor_keyset_uses_index(plan_connection) -> None:
    """结果中心游标查询：单终态走既有复合索引，多终态/默认走部分索引。

    单个终态时：``project_id + status`` 等值 + ``finished_at`` 行值区间，索引一次
    seek；同一毫秒并列行的 ``id`` 兜底由 SQLite 的「RIGHT PART OF ORDER BY」完成
    （只排等值并列组，有界，不是整表排序）。终态多值 IN 时由部分索引
    ``ix_tasks_project_terminal_finished_id`` 支撑（status 进谓词不进键）。因此只
    断言「没有整表 TEMP B-TREE FOR ORDER BY」且用上了预期索引，不要求零临时排序。
    """
    plan = _plan(
        plan_connection,
        """
        SELECT id FROM tasks
        WHERE project_id = :project_id
          AND status = 'SUCCESS'
          AND finished_at IS NOT NULL
          AND (finished_at, id) < (:last_ts, :last_id)
        ORDER BY finished_at DESC, id DESC
        LIMIT 20
        """,
        {"project_id": "p1", "last_ts": "2026-01-01 00:00:00", "last_id": "x"},
    )
    used = (
        "ix_tasks_project_terminal_finished_id",
        "ix_tasks_project_status_finished",
    )
    assert any(name in plan for name in used), plan
    # 收紧到「没有整表排序」：RIGHT PART 的并列组排序不算。
    assert "USE TEMP B-TREE FOR ORDER BY" not in plan, plan


def test_count_subquery_without_order_by_does_not_sort(plan_connection) -> None:
    """``_count_tasks`` 已去掉 ORDER BY：计数子查询不应再排序。"""
    plan = _plan(
        plan_connection,
        """
        SELECT count(*) FROM (
            SELECT id FROM tasks
            WHERE project_id = :project_id AND status = 'SUCCESS'
        )
        """,
        {"project_id": "p1"},
    )
    assert "TEMP B-TREE" not in plan.upper(), plan
