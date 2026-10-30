"""索引治理守护测试（静态，不连数据库）。

用 ``Base.metadata`` 做静态断言，防止后续改动把本轮索引硬化悄悄改回去：

* 13 个必需复合索引必须存在，且**列顺序**完全一致（等值列在前、排序列在后）。
* 不允许出现「某单列索引被更长复合索引 / 唯一约束以真前缀覆盖」的新增冗余；
  历史遗留的冗余索引集中登记在 ``ALLOWED_REDUNDANT_PREFIXES``，每项注明原因。
* ``audit_logs`` 是写最频繁的只追加表，索引数必须 ≤7（每多一个索引，每次插入就
  多维护一棵 B 树）。
* 同一张表上不允许两个索引的列集合完全相同。
* ``datasets`` 的 ``uq_datasets_project_name_type`` 必须在模型里声明，且迁移
  ``20261031_01`` 里确实创建它。
"""

from __future__ import annotations

from pathlib import Path

from app.database.base import Base
import app.models  # noqa: F401  确保所有模型注册进 Base.metadata


REQUIRED_COMPOSITE_INDEXES: dict[str, tuple[str, list[str]]] = {
    "ix_tasks_project_status_created": ("tasks", ["project_id", "status", "created_at"]),
    "ix_tasks_user_status_created": ("tasks", ["user_id", "status", "created_at"]),
    "ix_tasks_project_status_finished": (
        "tasks",
        ["project_id", "status", "finished_at", "created_at"],
    ),
    "ix_tasks_queued_updated": ("tasks", ["updated_at"]),
    "ix_tasks_status_finished": ("tasks", ["status", "finished_at"]),
    "ix_task_logs_task_timestamp": ("task_logs", ["task_id", "timestamp"]),
    "ix_artifacts_project_type_updated": (
        "artifacts",
        ["project_id", "artifact_type", "updated_at"],
    ),
    "ix_artifact_versions_artifact_sha_status": (
        "artifact_versions",
        ["artifact_id", "sha256", "status"],
    ),
    "ix_candidates_project_created": ("candidates", ["project_id", "created_at"]),
    "ix_candidate_sets_project_created": ("candidate_sets", ["project_id", "created_at"]),
    "ix_files_owner_created": ("files", ["owner_id", "created_at"]),
    "ix_workflow_runs_active_created": ("workflow_runs", ["created_at"]),
    "ix_tools_status_created": ("tools", ["status", "created_at"]),
}

#: 历史遗留的「单列被真前缀覆盖」索引。它们要么来自更早的迁移，要么由唯一约束
#: 顺带覆盖，不在本轮改动范围；登记在此以免守护测试误报，同时保留可见性。
ALLOWED_REDUNDANT_PREFIXES: dict[str, str] = {
    # 唯一约束 (input_version_id, output_version_id) 覆盖 input_version_id 单列。
    "ix_artifact_lineage_input_version_id": "被 uq_artifact_lineage_input_output 前缀覆盖（历史）",
    # 唯一约束 (project_id, name, dataset_type) 覆盖 project_id 单列。
    "ix_datasets_project_id": "被 uq_datasets_project_name_type 前缀覆盖（历史）",
    # 唯一约束 (repository, tag) 覆盖 repository 单列。
    "ix_image_assets_repository": "被 uq_image_assets_repository_tag 前缀覆盖（历史）",
    # 唯一约束 (task_id, input_role, ordinal) 覆盖 (task_id, input_role)。
    "ix_task_input_snapshots_task_role": "被 uq_task_input_snapshots_task_role_ordinal 前缀覆盖（历史）",
    # 唯一约束 (package_id, version) 覆盖 package_id 单列。
    "ix_tool_package_versions_package_id": "被 uq_tool_package_versions_package_version 前缀覆盖（历史）",
    # 唯一约束 (tool_id, group_id) 覆盖 tool_id 单列。
    "ix_tool_workbench_group_mappings_tool_id": "被 uq_tool_workbench_group_mapping_tool_group 前缀覆盖（历史）",
    # 唯一约束 (project_id, idempotency_key) 覆盖 project_id 单列。
    "ix_upload_sessions_project_id": "被 uq_upload_sessions_project_idem 前缀覆盖（历史）",
    # 复合索引 (email, purpose) 覆盖 email 单列。
    "ix_verification_codes_email": "被 ix_verification_email_purpose 前缀覆盖（历史）",
    # 唯一索引 (email, date) 覆盖 email 单列。
    "ix_verification_daily_counts_email": "被 ix_daily_count_email_date 前缀覆盖（历史）",
}


def _all_indexes():
    """逐条产出 (表名, 索引名, 列名元组, 是否唯一, 是否 partial, 约束名或 None)。"""
    for table in Base.metadata.tables.values():
        for index in table.indexes:
            pg_where = index.dialect_options.get("postgresql", {}).get("where")
            sqlite_where = index.dialect_options.get("sqlite", {}).get("where")
            yield (
                table.name,
                index.name,
                tuple(column.name for column in index.columns),
                bool(index.unique),
                pg_where is not None or sqlite_where is not None,
                None,
            )
        for constraint in table.constraints:
            if constraint.__class__.__name__ == "UniqueConstraint":
                yield (
                    table.name,
                    constraint.name or "<unnamed>",
                    tuple(column.name for column in constraint.columns),
                    True,
                    False,
                    constraint.name or "<unnamed>",
                )


def test_required_composite_indexes_exist():
    missing: list[str] = []
    wrong_order: list[str] = []
    for index_name, (table_name, expected_columns) in REQUIRED_COMPOSITE_INDEXES.items():
        table = Base.metadata.tables.get(table_name)
        assert table is not None, f"表 {table_name} 不存在"
        index = next((ix for ix in table.indexes if ix.name == index_name), None)
        if index is None:
            missing.append(f"{table_name}.{index_name}")
            continue
        actual = [column.name for column in index.columns]
        if actual != expected_columns:
            wrong_order.append(f"{index_name}: 期望 {expected_columns}, 实际 {actual}")
    assert not missing, f"缺少必需复合索引: {missing}"
    assert not wrong_order, f"复合索引列顺序不符: {wrong_order}"


def test_no_redundant_prefix_indexes():
    all_indexes = list(_all_indexes())
    redundant: list[str] = []
    for table_name, index_name, columns, unique, partial, _constraint in all_indexes:
        if unique or partial or index_name == "<unnamed>":
            continue
        for other_table, other_name, other_columns, _u, other_partial, _c in all_indexes:
            if other_table != table_name or other_name == index_name or other_partial:
                continue
            if len(other_columns) > len(columns) and other_columns[: len(columns)] == columns:
                if index_name not in ALLOWED_REDUNDANT_PREFIXES:
                    redundant.append(f"{table_name}.{index_name} 被 {other_name} 真前缀覆盖")
                break
    assert not redundant, "发现新增冗余前缀索引:\n" + "\n".join(redundant)


def test_audit_logs_index_budget(capsys):
    """``audit_logs`` 是写最频繁的只追加表：索引越多，每次 INSERT 维护成本越高。

    原先 10 个索引 → 每次插入维护 10 棵 B 树；收敛到 ≤7 后写入路径显著变轻。
    """
    table = Base.metadata.tables["audit_logs"]
    names = sorted(index.name for index in table.indexes)
    print("audit_logs 当前索引:", names)
    assert len(names) <= 7, f"audit_logs 索引数为 {len(names)}，超过 7: {names}"


def test_no_duplicate_index_on_same_columns():
    duplicates: list[str] = []
    for table in Base.metadata.tables.values():
        seen: dict[tuple[str, ...], list[str]] = {}
        for index in table.indexes:
            key = tuple(column.name for column in index.columns)
            seen.setdefault(key, []).append(index.name)
        for columns, names in seen.items():
            if len(names) > 1:
                duplicates.append(f"{table.name}{columns}: {names}")
    assert not duplicates, "同表存在列集合相同的索引:\n" + "\n".join(duplicates)


def test_datasets_unique_constraint_declared():
    table = Base.metadata.tables["datasets"]
    names = {
        constraint.name
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert "uq_datasets_project_name_type" in names, f"datasets 缺少唯一约束，现有: {names}"

    migration = (
        Path(__file__).resolve().parents[1]
        / "backend"
        / "alembic"
        / "versions"
        / "20261031_01_index_hardening.py"
    )
    assert migration.is_file(), f"迁移文件不存在: {migration}"
    source = migration.read_text(encoding="utf-8")
    assert "uq_datasets_project_name_type" in source, "迁移未创建 uq_datasets_project_name_type"
