#!/usr/bin/env python3
"""清理压测数据（perf_ 前缀），让演示环境恢复干净。

背景
----
``scripts/perf_seed.py`` 会在本地库里造出一批带 ``perf_`` 前缀的项目 / 任务 /
产物 / 工具（默认 ``perf_project-*``、``perf_task-*``、``perf_tool``），这些数据
会污染任务中心、我的待办等界面的计数。本脚本把这类压测数据**安全、可复现**地
删掉，且默认是 dry-run（只打印将删多少行，不落库）。

安全护栏（硬约束，任何一条不满足都会直接退出，不做任何删除）
------------------------------------------------------------
1. 前缀护栏：只按 ``--prefix``（默认 ``perf_``）选中项目 / 任务；选中集合里只要
   出现一个名字不是以该前缀开头的项目或任务，立即中止（``_guard_names``）。
2. 显式 id 护栏：所有 DELETE 语句的 WHERE 都是「显式 id 集合」或 ``name LIKE
   'perf\\_%'``，绝不做全表删除（``_build_plan`` 里每条 ``where``）。
3. 外键依赖预检：删除前扫描 ``pg_constraint``，任何「未被列入删除计划、却仍引用
   了 perf 父记录」的外键子表只要行数 > 0 就中止（``_preflight_fk``），避免外键
   报错或误删。
4. 顺序护栏：严格按外键依赖从属表→父表删除（见 ``_build_plan`` 的 ORDER 注释）。

用法
----
    # 1) 只看会删什么（默认 dry-run，不连写）
    python scripts/dev_cleanup_perf_data.py

    # 2) 确认无误后真删
    python scripts/dev_cleanup_perf_data.py --yes

    # 3) 换库 / 换前缀
    python scripts/dev_cleanup_perf_data.py --database-url postgresql+asyncpg://.../scitool --yes
    python scripts/dev_cleanup_perf_data.py --prefix perf_ --yes

恢复演示数据
------------
压测数据本身是可再生的。要恢复到「有演示数据」的状态，重跑造数脚本即可：

    python scripts/perf_seed.py --quick     # 2 个项目 × 100 任务 / 120 产物
    # 或自定义规模：
    python scripts/perf_seed.py --projects 2 --tasks-per-project 100 --artifacts-per-project 120

注意：脚本**不会**删除 ``*_user``（如 ``perf_user``）等用户，也不会删除演示 /
默认项目里的真实业务数据。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"

_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _escape_like(value: str) -> str:
    """转义 LIKE 通配符，避免前缀里的 ``_`` / ``%`` 变成通配符。"""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _assert_identifier(name: str) -> None:
    """只允许合法 SQL 标识符拼进 DDL 片段（表名 / 列名来自可信 catalog）。"""
    if not _IDENT_RE.fullmatch(name or ""):
        raise RuntimeError(f"拒绝拼接非法 SQL 标识符: {name!r}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="清理 perf_ 前缀压测数据（默认 dry-run，加 --yes 才真删）。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--prefix", default="perf_", help="压测数据标记前缀；只删该前缀的项目/任务/工具")
    p.add_argument("--yes", action="store_true", help="真正执行删除；缺省只做 dry-run 打印")
    p.add_argument("--database-url", default=None, help="覆盖 settings.DATABASE_URL（默认取 backend/.env）")
    return p


def _guard_names(kind: str, rows: list[tuple[str, str]], prefix: str) -> None:
    """护栏 1：选中集合里所有名字都必须以 prefix 开头，否则中止。"""
    bad = [(rid, name) for rid, name in rows if not (name or "").startswith(prefix)]
    if bad:
        detail = "\n  ".join(f"id={rid} name={name!r}" for rid, name in bad[:20])
        raise SystemExit(
            f"[ABORT] 选中的 {kind} 里存在 {len(bad)} 个名字不以 {prefix!r} 开头的记录，"
            f"为防误删已中止：\n  {detail}"
        )


def _build_plan(ids: dict) -> list[dict]:
    """按外键顺序构造删除计划。

    ORDER（从属 → 父）：artifact_version_files / artifact_lineage / artifact_versions /
    artifacts → task_logs / task_outputs / task_inputs / task_input_snapshots /
    gpu_allocations / execution_records → tasks → project_members / project_quotas →
    projects → tool_capabilities / tool_tag_map / tool_statistics / tool_favorites /
    tool_workbench_group_mappings / tool_versions → tools。

    每条 where 都只用显式 id 集合（满足护栏 2）。
    """
    from sqlalchemy import or_

    from app.models.artifacts import Artifact, ArtifactLineage, ArtifactVersion, ArtifactVersionFile
    from app.models.executions import ExecutionRecord
    from app.models.gpu import GPUAllocation
    from app.models.projects import Project, ProjectMember
    from app.models.quotas import ProjectQuota
    from app.models.statistics import ToolStatistics
    from app.models.tasks import Task, TaskInput, TaskLog, TaskOutput
    from app.models.tool_capabilities import ToolCapability
    from app.models.tools import Tool, ToolFavorite, ToolVersion, ToolWorkbenchGroupMapping, tool_tag_association
    from app.models.traceability import TaskInputSnapshot

    project_ids = ids["project_ids"]
    task_ids = ids["task_ids"]
    artifact_ids = ids["artifact_ids"]
    version_ids = ids["version_ids"]
    tool_ids = ids["tool_ids"]

    exec_cond = or_(
        ExecutionRecord.task_id.in_(task_ids),
        ExecutionRecord.project_id.in_(project_ids),
    )
    lineage_cond = or_(
        ArtifactLineage.project_id.in_(project_ids),
        ArtifactLineage.input_version_id.in_(version_ids),
        ArtifactLineage.output_version_id.in_(version_ids),
    )

    return [
        # --- 产物从属 ---
        {"table": "artifact_version_files", "model": ArtifactVersionFile,
         "where": ArtifactVersionFile.artifact_version_id.in_(version_ids),
         "desc": "产物版本文件（引用 perf 版本）"},
        {"table": "artifact_lineage", "model": ArtifactLineage, "where": lineage_cond,
         "desc": "产物血缘（引用 perf 项目/版本）"},
        {"table": "artifact_versions", "model": ArtifactVersion,
         "where": ArtifactVersion.artifact_id.in_(artifact_ids),
         "desc": "产物版本（引用 perf 产物）"},
        {"table": "artifacts", "model": Artifact, "where": Artifact.id.in_(artifact_ids),
         "desc": "产物（perf 项目/前缀）"},
        # --- 任务从属 ---
        {"table": "task_logs", "model": TaskLog, "where": TaskLog.task_id.in_(task_ids),
         "desc": "任务日志"},
        {"table": "task_outputs", "model": TaskOutput, "where": TaskOutput.task_id.in_(task_ids),
         "desc": "任务输出"},
        {"table": "task_inputs", "model": TaskInput, "where": TaskInput.task_id.in_(task_ids),
         "desc": "任务输入"},
        {"table": "task_input_snapshots", "model": TaskInputSnapshot,
         "where": TaskInputSnapshot.task_id.in_(task_ids),
         "desc": "任务输入快照（只追加表，走 Core delete 绕过 ORM 守卫）"},
        {"table": "gpu_allocations", "model": GPUAllocation,
         "where": GPUAllocation.task_id.in_(task_ids),
         "desc": "GPU 分配"},
        {"table": "execution_records", "model": ExecutionRecord, "where": exec_cond,
         "desc": "执行记录（引用 perf 任务/项目）"},
        # --- 任务 ---
        {"table": "tasks", "model": Task, "where": Task.id.in_(task_ids),
         "desc": "任务"},
        # --- 项目成员 / 配额 / 项目 ---
        {"table": "project_members", "model": ProjectMember,
         "where": ProjectMember.project_id.in_(project_ids),
         "desc": "项目成员"},
        {"table": "project_quotas", "model": ProjectQuota,
         "where": ProjectQuota.project_id.in_(project_ids),
         "desc": "项目配额"},
        {"table": "projects", "model": Project, "where": Project.id.in_(project_ids),
         "desc": "项目"},
        # --- 工具从属 ---
        {"table": "tool_capabilities", "model": ToolCapability,
         "where": ToolCapability.tool_id.in_(tool_ids),
         "desc": "工具能力"},
        {"table": "tool_tag_map", "model": tool_tag_association,
         "where": tool_tag_association.c.tool_id.in_(tool_ids),
         "desc": "工具标签关联"},
        {"table": "tool_statistics", "model": ToolStatistics,
         "where": ToolStatistics.tool_id.in_(tool_ids),
         "desc": "工具统计"},
        {"table": "tool_favorites", "model": ToolFavorite,
         "where": ToolFavorite.tool_id.in_(tool_ids),
         "desc": "工具收藏"},
        {"table": "tool_workbench_group_mappings", "model": ToolWorkbenchGroupMapping,
         "where": ToolWorkbenchGroupMapping.tool_id.in_(tool_ids),
         "desc": "工具工作台分组"},
        {"table": "tool_versions", "model": ToolVersion,
         "where": ToolVersion.tool_id.in_(tool_ids),
         "desc": "工具版本"},
        {"table": "tools", "model": Tool, "where": Tool.id.in_(tool_ids),
         "desc": "工具"},
    ]


async def _preflight_fk(session, ids: dict, deleted_tables: set[str]) -> None:
    """护栏 3：未列入删除计划、却仍引用 perf 父记录的外键子表必须为 0 行。"""
    from sqlalchemy import bindparam, text

    parent_ids = {
        "projects": ids["project_ids"],
        "tasks": ids["task_ids"],
        "artifacts": ids["artifact_ids"],
        "artifact_versions": ids["version_ids"],
        "tool_versions": ids["tool_version_ids"],
        "tools": ids["tool_ids"],
    }
    fk_rows = (
        await session.execute(
            text(
                """
                SELECT c.conrelid::regclass::text AS child_table,
                       a.attname AS child_col,
                       c.confrelid::regclass::text AS parent_table
                FROM pg_constraint c
                JOIN pg_attribute a
                  ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
                WHERE c.contype = 'f'
                """
            )
        )
    ).all()

    problems: list[str] = []
    for child_table, child_col, parent_table in fk_rows:
        child = (child_table or "").split(".")[-1].strip('"')
        parent = (parent_table or "").split(".")[-1].strip('"')
        if parent not in parent_ids or not parent_ids[parent]:
            continue
        if child in deleted_tables:
            continue
        _assert_identifier(child)
        _assert_identifier(child_col)
        stmt = text(
            f"SELECT count(*) FROM {child} WHERE {child_col} IN :ids"
        ).bindparams(bindparam("ids", expanding=True))
        cnt = (await session.execute(stmt, {"ids": parent_ids[parent]})).scalar_one()
        if cnt:
            problems.append(f"{child}.{child_col} -> {parent}: {cnt} 行")
    if problems:
        detail = "\n  ".join(problems)
        raise SystemExit(
            "[ABORT] 存在未列入删除计划、却仍引用 perf 父记录的外键子表，"
            f"为防外键报错/误删已中止（请人工确认）：\n  {detail}"
        )


async def run_cleanup(args: argparse.Namespace) -> int:
    # 让 ``app.*`` 可导入，并让 pydantic-settings 读到 backend/.env
    sys.path.insert(0, str(BACKEND_DIR))
    os.chdir(BACKEND_DIR)

    from sqlalchemy import delete, func, or_, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.database.session import async_session_factory, engine
    from app.models.artifacts import Artifact, ArtifactVersion
    from app.models.projects import Project
    from app.models.tasks import Task
    from app.models.tools import Tool, ToolStatus, ToolVersion

    if not args.prefix:
        raise SystemExit("[ABORT] --prefix 不能为空。")

    if args.database_url:
        url = args.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        engine = create_async_engine(url, pool_pre_ping=True)
        session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    else:
        session_factory = async_session_factory

    prefix = args.prefix
    like_prefix = _escape_like(prefix) + "%"

    async with session_factory() as session:
        # ---- 选中 perf 项目 / 任务 / 产物 / 工具（只读） ----
        proj_rows = (
            await session.execute(
                select(Project.id, Project.name).where(Project.name.like(like_prefix, escape="\\"))
            )
        ).all()
        _guard_names("项目", proj_rows, prefix)
        project_ids = [r[0] for r in proj_rows]

        task_conditions = [Task.name.like(like_prefix, escape="\\")]
        if project_ids:
            task_conditions.append(Task.project_id.in_(project_ids))
        task_rows = (
            await session.execute(
                select(Task.id, Task.name, Task.project_id).where(or_(*task_conditions))
            )
        ).all()
        _guard_names("任务", [(r[0], r[1]) for r in task_rows], prefix)
        task_ids = [r[0] for r in task_rows]

        artifact_conditions = [Artifact.name.like(like_prefix, escape="\\")]
        if project_ids:
            artifact_conditions.append(Artifact.project_id.in_(project_ids))
        if task_ids:
            artifact_conditions.append(Artifact.source_task_id.in_(task_ids))
        artifact_rows = (
            await session.execute(
                select(Artifact.id, Artifact.project_id, Artifact.source_task_id).where(or_(*artifact_conditions))
            )
        ).all()
        artifact_ids = [r[0] for r in artifact_rows]

        tool_rows = (
            await session.execute(select(Tool.id, Tool.slug).where(Tool.slug.like(like_prefix, escape="\\")))
        ).all()
        tool_ids = [r[0] for r in tool_rows]

        version_ids = [
            r[0]
            for r in (
                await session.execute(
                    select(ArtifactVersion.id).where(ArtifactVersion.artifact_id.in_(artifact_ids))
                )
            ).all()
        ] if artifact_ids else []
        tool_version_ids = [
            r[0]
            for r in (
                await session.execute(
                    select(ToolVersion.id).where(ToolVersion.tool_id.in_(tool_ids))
                )
            ).all()
        ] if tool_ids else []

        ids = {
            "project_ids": project_ids,
            "task_ids": task_ids,
            "artifact_ids": artifact_ids,
            "version_ids": version_ids,
            "tool_ids": tool_ids,
            "tool_version_ids": tool_version_ids,
        }

        plan = _build_plan(ids)
        deleted_tables = {p["table"] for p in plan}

        # ---- 护栏 3：外键依赖预检 ----
        await _preflight_fk(session, ids, deleted_tables)

        # ---- 统计计划删除行数 ----
        planned: list[tuple[str, int, str]] = []
        for p in plan:
            cnt = (
                await session.execute(select(func.count()).select_from(p["model"]).where(p["where"]))
            ).scalar_one()
            planned.append((p["table"], cnt, p["desc"]))
        total = sum(c for _, c, _ in planned)

        mode = "实际删除" if args.yes else "DRY-RUN（未落库，加 --yes 才真删）"
        print("=" * 72)
        print(f"perf 数据清理 · {mode}")
        print(f"数据库  : {engine.url.render_as_string(hide_password=True) if hasattr(engine, 'url') else 'settings.DATABASE_URL'}")
        print(f"前缀    : {prefix!r}   选中项目={len(project_ids)} 任务={len(task_ids)} 产物={len(artifact_ids)} 工具={len(tool_ids)}")
        print("-" * 72)
        print(f"{'表':32s} {'行数':>8s}  说明")
        for table, cnt, desc in planned:
            print(f"{table:32s} {cnt:>8d}  {desc}")
        print("-" * 72)
        print(f"{'合计':32s} {total:>8d}")
        print("=" * 72)

        if not args.yes:
            print("[dry-run] 未执行任何删除。确认无误后请加 --yes。")
            return 0

        # ---- 护栏 4：按外键顺序真删 ----
        print("[delete] 开始按外键顺序删除……")
        deleted_total = 0
        for p in plan:
            res = await session.execute(delete(p["model"]).where(p["where"]))
            n = res.rowcount or 0
            deleted_total += n
            print(f"  deleted {p['table']:32s} {n:>8d}")
        await session.commit()
        print(f"[delete] 已提交，实际删除 {deleted_total} 行。")

        # ---- 清理后现状 ----
        remain_tasks = (await session.execute(select(func.count()).select_from(Task))).scalar_one()
        remain_projects = (
            await session.execute(select(Project.id, Project.name).order_by(Project.name))
        ).all()
        remain_tools = (
            await session.execute(
                select(Tool.slug)
                .where(Tool.is_public.is_(True), Tool.status == ToolStatus.PUBLISHED.value)
                .order_by(Tool.slug)
            )
        ).all()
        print("-" * 72)
        print(f"[verify] tasks 总数            : {remain_tasks}")
        print(f"[verify] 剩余项目              : {[r[1] for r in remain_projects]}")
        print(f"[verify] 公开已发布工具数       : {len(remain_tools)}  {[r[0] for r in remain_tools]}")
        print("=" * 72)

    try:
        await engine.dispose()
    except Exception:  # noqa: BLE001 - 释放失败不影响结果
        pass
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return asyncio.run(run_cleanup(args))


if __name__ == "__main__":
    raise SystemExit(main())
