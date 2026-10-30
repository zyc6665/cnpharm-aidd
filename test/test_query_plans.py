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
            "结果中心：project_id + 终态 + finished_at DESC",
            """
            SELECT id FROM tasks
            WHERE project_id = :project_id
              AND status IN ('SUCCESS', 'FAILURE', 'CANCELED', 'TIMEOUT')
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
    ],
)
def test_hot_pagination_query_uses_index_without_sort(
    plan_connection, name: str, sql: str, params: dict, expected_index: str
) -> None:
    plan = _plan(plan_connection, sql, params)
    assert "TEMP B-TREE" not in plan.upper(), f"{name} 仍在内存排序：\n{plan}"
    assert expected_index in plan, f"{name} 未使用预期索引 {expected_index}：\n{plan}"


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
