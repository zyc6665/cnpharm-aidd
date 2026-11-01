#!/usr/bin/env python3
"""压测造数脚本（幂等、参数化、直连数据库批量写入）。

默认造出 **20 个项目 × 5000 个任务 = 100000 个任务**、**20 个项目 × 10000 个产物
= 200000 个产物**，供「阶段 4：压测准备」的读/写场景使用。数据通过
``DATABASE_URL`` 直连（默认 PostgreSQL）用 SQLAlchemy Core ``insert`` 批量写入，
复用 ``app.models`` 的 ORM 表定义，不手写容易漂移的 DDL。

设计要点
--------
* 幂等：所有数据以 ``--prefix``（默认 ``perf_``）标记；重复执行会先按前缀清理
  再重建，不会删除非本脚本创建的数据（用户默认保留，``--clean-users`` 可一并清理）。
* 终态 / 运行中混合：任务按 SUCCESS / FAILURE / CANCELED / TIMEOUT / RUNNING /
  QUEUED / PENDING 分布，结果中心（只看终态）与任务列表（看全部）都有数据。
* keyset 校验：第 1 个项目的头 ``--collision-rows`` 个任务共享同一 ``finished_at``
  （默认 12，要求 ≥5），用于验证游标分页「不重不漏」；造完会自动跑一次游标遍历
  自检（``--no-verify`` 可跳过）。
* 深页：单项目数据量足够大，列表可翻到很深的分页。

用法示例
--------
    python scripts/perf_seed.py --help
    python scripts/perf_seed.py --dry-run
    python scripts/perf_seed.py --quick                 # 2×100 任务，快速自检
    python scripts/perf_seed.py                         # 默认 10 万任务 / 20 万产物
    python scripts/perf_seed.py --projects 5 --tasks-per-project 2000 --artifacts-per-project 3000
    python scripts/perf_seed.py --clean                 # 仅按 prefix 清理
    python scripts/perf_seed.py --users 3               # 造 3 个压测用户，任务按用户轮转归属
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import random
import sys
import uuid
from datetime import timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"

TERMINAL_STATUSES = ("success", "failure", "canceled", "timeout")
ARTIFACT_TYPES = (
    "compound_set",
    "protein_structure",
    "binding_pocket",
    "ligand_structure",
    "molecule_table",
    "md_trajectory",
    "run_report",
    "dataset",
)


# --------------------------------------------------------------------------- #
# 参数解析
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="压测造数（幂等、参数化）。默认 20 项目 × 5000 任务 = 10 万任务、20 万产物。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--projects", type=int, default=20, help="项目数量")
    p.add_argument("--tasks-per-project", type=int, default=5000, help="每个项目的任务数")
    p.add_argument("--artifacts-per-project", type=int, default=10000, help="每个项目的产物数")
    p.add_argument("--users", type=int, default=1, help="压测用户数量（任务按用户轮转归属）")
    p.add_argument("--prefix", default="perf_", help="数据标记前缀，用于幂等清理")
    p.add_argument("--username", default="perf_user", help="主压测用户名（其余用户为 <prefix>userN）")
    p.add_argument("--email", default="perf_user@perf.local", help="主压测用户邮箱")
    p.add_argument("--password", default="Perf_Passw0rd!", help="压测用户登录密码")
    p.add_argument("--collision-rows", type=int, default=12, help="同 finished_at 的碰撞行数（≥5，用于 keyset 校验）")
    p.add_argument("--detail-samples", type=int, default=50, help="每项目写入 TaskInput/TaskOutput 的样本数")
    p.add_argument("--batch-size", type=int, default=5000, help="单次 executemany 的行数")
    p.add_argument("--seed", type=int, default=42, help="随机数种子（保证可重复）")
    p.add_argument("--database-url", default=None, help="覆盖 settings.DATABASE_URL（默认取 .env / 环境变量）")
    p.add_argument("--quick", action="store_true", help="等价于 --projects 2 --tasks-per-project 100 --artifacts-per-project 120 的初步自检")
    p.add_argument("--clean", action="store_true", help="仅按 prefix 清理既有数据后退出")
    p.add_argument("--clean-users", action="store_true", help="连同 prefix 前缀的用户一起清理")
    p.add_argument("--dry-run", action="store_true", help="只打印计划，不连接数据库")
    p.add_argument("--no-verify", action="store_true", help="造数后不跑游标 keyset 自检")
    return p


def _apply_quick(args: argparse.Namespace) -> None:
    if args.quick:
        args.projects = 2
        args.tasks_per_project = 100
        args.artifacts_per_project = 120


def _planned_totals(args: argparse.Namespace) -> dict:
    return {
        "projects": args.projects,
        "tasks": args.projects * args.tasks_per_project,
        "artifacts": args.projects * args.artifacts_per_project,
        "artifact_versions": args.projects * args.artifacts_per_project,
        "users": args.users,
    }


# --------------------------------------------------------------------------- #
# 造数主逻辑（延迟导入，--help / --dry-run 不需要数据库）
# --------------------------------------------------------------------------- #
async def run_seed(args: argparse.Namespace) -> int:
    # 让 ``app.*`` 可导入，并让 pydantic-settings 读到 backend/.env
    sys.path.insert(0, str(BACKEND_DIR))
    os.chdir(BACKEND_DIR)

    from sqlalchemy import delete, insert, select
    from sqlalchemy import tuple_

    from app.auth.password import hash_password
    from app.database.base import utcnow
    from app.database.session import async_session_factory, engine
    from app.models.artifacts import Artifact, ArtifactVersion
    from app.models.projects import Organization, Project, ProjectMember
    from app.models.tasks import Task, TaskInput, TaskOutput
    from app.models.tools import Tool, ToolVersion
    from app.models.users import User

    if args.database_url:
        url = args.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        # 覆盖 engine：新建一个会话工厂（脚本内局部使用，不影响后端进程）
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        engine = create_async_engine(url, pool_pre_ping=True)
        session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    else:
        session_factory = async_session_factory

    rng = random.Random(args.seed)
    now = utcnow()
    like_prefix = _escape_like(args.prefix) + "%"

    async def clean(session) -> None:
        project_ids = select(Project.id).where(Project.name.like(like_prefix, escape="\\"))
        task_ids = select(Task.id).where(Task.project_id.in_(project_ids))
        artifact_ids = select(Artifact.id).where(Artifact.project_id.in_(project_ids))
        tool_ids = select(Tool.id).where(Tool.slug.like(like_prefix, escape="\\"))

        await session.execute(delete(ArtifactVersion).where(ArtifactVersion.artifact_id.in_(artifact_ids)))
        await session.execute(delete(Artifact).where(Artifact.id.in_(artifact_ids)))
        await session.execute(delete(TaskOutput).where(TaskOutput.task_id.in_(task_ids)))
        await session.execute(delete(TaskInput).where(TaskInput.task_id.in_(task_ids)))
        from app.models.tasks import TaskLog

        await session.execute(delete(TaskLog).where(TaskLog.task_id.in_(task_ids)))
        await session.execute(delete(Task).where(Task.id.in_(task_ids)))
        await session.execute(delete(ProjectMember).where(ProjectMember.project_id.in_(project_ids)))
        await session.execute(delete(Project).where(Project.id.in_(project_ids)))
        await session.execute(delete(ToolVersion).where(ToolVersion.tool_id.in_(tool_ids)))
        await session.execute(delete(Tool).where(Tool.id.in_(tool_ids)))
        if args.clean_users:
            await session.execute(delete(User).where(User.username.like(like_prefix, escape="\\")))

    class Bulk:
        """攒一批行，达到 batch_size 时 executemany 落库。"""

        def __init__(self, session, table, batch_size: int):
            self.session = session
            self.table = table
            self.batch_size = max(1, batch_size)
            self.buf: list[dict] = []
            self.total = 0

        async def add(self, row: dict) -> None:
            self.buf.append(row)
            if len(self.buf) >= self.batch_size:
                await self.flush()

        async def flush(self) -> None:
            if self.buf:
                await self.session.execute(insert(self.table), self.buf)
                self.total += len(self.buf)
                self.buf.clear()

    async with session_factory() as session:
        # 1) 幂等清理
        await clean(session)
        await session.commit()
        if args.clean:
            print("[clean] 已按 prefix='%s' 清理完成。" % args.prefix)
            await engine.dispose()
            return 0

        # 2) 组织
        org = (await session.execute(select(Organization).where(Organization.slug == "default"))).scalar_one_or_none()
        if org is None:
            org_id = str(uuid.uuid4())
            t = now
            await session.execute(
                insert(Organization),
                [{"id": org_id, "name": "Default Organization", "slug": "default", "created_at": t, "updated_at": t}],
            )
        else:
            org_id = org.id
        await session.commit()

        # 3) 用户（幂等复用）
        pwd_hash = hash_password(args.password)
        user_ids: list[str] = []
        usernames: list[str] = []
        for i in range(max(1, args.users)):
            uname = args.username if i == 0 else f"{args.prefix}user{i + 1}"
            email = args.email if i == 0 else f"{args.prefix}user{i + 1}@perf.local"
            u = (await session.execute(select(User).where(User.username == uname))).scalar_one_or_none()
            if u is None:
                u = User(
                    username=uname,
                    email=email,
                    password_hash=pwd_hash,
                    display_name=uname,
                    role="user",
                    status="active",
                    auth_source="local",
                    daily_task_limit=1_000_000,
                )
                session.add(u)
                await session.flush()
            else:
                u.daily_task_limit = 1_000_000
            user_ids.append(u.id)
            usernames.append(uname)
        await session.commit()
        primary_user = user_ids[0]

        # 4) 工具 + 版本（写场景提交任务用；发布态让非 admin 也能看到）
        tool_slug = f"{args.prefix}tool"
        tool = (await session.execute(select(Tool).where(Tool.slug == tool_slug))).scalar_one_or_none()
        if tool is None:
            tool = Tool(
                owner_id=primary_user,
                name="Perf Noop Tool",
                slug=tool_slug,
                description="压测用 no-op 工具（provider=noop，不实际执行）",
                category="perf",
                status="published",
                is_public=True,
                provider_type="platform",
                review_status="not_required",
                gpu_required=False,
                timeout_sec=60,
            )
            session.add(tool)
            await session.flush()
        tv = (await session.execute(select(ToolVersion).where(ToolVersion.tool_id == tool.id))).scalar_one_or_none()
        if tv is None:
            tv = ToolVersion(tool_id=tool.id, version="1.0.0", config={"provider": "noop"}, is_active=True)
            session.add(tv)
            await session.flush()
        if tool.current_version_id != tv.id:
            tool.current_version_id = tv.id
        await session.commit()
        tool_id, tool_version_id = tool.id, tv.id

        # 5) 项目 + 成员
        project_ids: list[str] = []
        project_rows = []
        for pi in range(args.projects):
            pid = str(uuid.uuid4())
            project_ids.append(pid)
            created = now - timedelta(days=args.projects - pi)
            project_rows.append(
                {
                    "id": pid,
                    "organization_id": org_id,
                    "created_by": primary_user,
                    "name": f"{args.prefix}project-{pi:04d}",
                    "goal": f"压测项目 {pi}",
                    "status": "active",
                    "model_policy": {},
                    "data_policy": {},
                    "version": 1,
                    "created_at": created,
                    "updated_at": created,
                }
            )
        await session.execute(insert(Project), project_rows)
        await session.commit()

        member_rows = []
        for pid in project_ids:
            for uid in user_ids:
                member_rows.append(
                    {"project_id": pid, "user_id": uid, "role": "owner", "created_at": now, "updated_at": now}
                )
        if member_rows:
            await session.execute(insert(ProjectMember), member_rows)
            await session.commit()

        # 6) 任务（分批流式写入）
        task_bulk = Bulk(session, Task, args.batch_size)
        collision_ts = now - timedelta(hours=1)  # 第 1 项目碰撞组的统一 finished_at
        project_task_ids: dict[str, list[str]] = {pid: [] for pid in project_ids}
        terminal_counts: dict[str, int] = {pid: 0 for pid in project_ids}
        status_hits = {s: 0 for s in ("success", "failure", "canceled", "timeout", "running", "queued", "pending")}

        for pi, pid in enumerate(project_ids):
            n = args.tasks_per_project
            for ti in range(n):
                tid = str(uuid.uuid4())
                project_task_ids[pid].append(tid)
                created = now - timedelta(seconds=ti * 7 + pi * 3 + rng.randint(0, 3))

                # 第 1 项目前 collision_rows 个任务：同一 finished_at，用于 keyset 不重不漏校验
                if pi == 0 and ti < args.collision_rows:
                    status = "success"
                    finished = collision_ts
                    started = collision_ts - timedelta(seconds=30)
                    # collision_ts 是固定时刻，而 created 是按 now 倒推的，两者会错开一小时。
                    # 时间线必须满足 created <= started <= finished，否则页面上会出现
                    # 「开始时间早于创建时间」这种不可能的顺序。
                    created = finished - timedelta(seconds=90)
                    progress = 100.0
                else:
                    roll = rng.random()
                    if roll < 0.70:
                        status = "success"
                    elif roll < 0.80:
                        status = "failure"
                    elif roll < 0.85:
                        status = "canceled"
                    elif roll < 0.88:
                        status = "timeout"
                    elif roll < 0.92:
                        status = "running"
                    elif roll < 0.97:
                        status = "queued"
                    else:
                        status = "pending"
                    if status in TERMINAL_STATUSES:
                        finished = min(now, created + timedelta(seconds=rng.randint(5, 900)))
                        started = created + timedelta(seconds=rng.randint(0, 4))
                        progress = 100.0
                    elif status == "running":
                        finished = None
                        started = created + timedelta(seconds=rng.randint(0, 4))
                        progress = float(rng.randint(10, 90))
                    else:
                        finished = None
                        started = None
                        progress = 0.0

                status_hits[status] += 1
                if status in TERMINAL_STATUSES:
                    terminal_counts[pid] += 1

                extra = {"project_id": pid}
                if status == "queued":
                    extra.update(
                        {
                            "resource_wait_category": "worker_capacity",
                            "resource_wait_code": "no_worker",
                            "resource_wait_scope": "project",
                        }
                    )
                error_message = None
                if status == "failure":
                    error_message = "perf seed: simulated failure"

                await task_bulk.add(
                    {
                        "id": tid,
                        "user_id": user_ids[ti % len(user_ids)],
                        "project_id": pid,
                        "tool_id": tool_id,
                        "tool_version_id": tool_version_id,
                        "name": f"{args.prefix}task-p{pi:04d}-{ti:06d}",
                        "status": status,
                        "priority": "normal",
                        "started_at": started,
                        "finished_at": finished,
                        "execution_time_sec": (int((finished - started).total_seconds()) if finished and started else None),
                        "progress": progress,
                        "progress_message": None,
                        "error_message": error_message,
                        "retry_count": 0,
                        "max_retries": 0,
                        "extra_data": extra,
                        "created_at": created,
                        "updated_at": finished or started or created,
                    }
                )
        await task_bulk.flush()
        await session.commit()
        print(f"[tasks] 写入 {task_bulk.total} 个任务。状态分布：{status_hits}")

        # 7) 任务详情样本（TaskInput / TaskOutput）
        input_bulk = Bulk(session, TaskInput, args.batch_size)
        output_bulk = Bulk(session, TaskOutput, args.batch_size)
        samples = max(0, args.detail_samples)
        for pid in project_ids:
            for tid in project_task_ids[pid][:samples]:
                await input_bulk.add({"task_id": tid, "params": {"sample": True}, "file_ids": []})
                await output_bulk.add(
                    {"task_id": tid, "result": {"ok": True}, "file_ids": [], "output_type": "json"}
                )
        await input_bulk.flush()
        await output_bulk.flush()
        await session.commit()
        print(f"[details] TaskInput={input_bulk.total} TaskOutput={output_bulk.total}")

        # 8) 产物 + 版本（每个产物一个 available 版本，列表才可见）
        artifact_bulk = Bulk(session, Artifact, args.batch_size)
        version_bulk = Bulk(session, ArtifactVersion, args.batch_size)
        for pi, pid in enumerate(project_ids):
            n = args.artifacts_per_project
            for ai in range(n):
                aid = str(uuid.uuid4())
                vid = str(uuid.uuid4())
                atype = ARTIFACT_TYPES[(ai + pi) % len(ARTIFACT_TYPES)]
                created = now - timedelta(seconds=ai * 2 + pi * 5)
                src_task = project_task_ids[pid][ai % len(project_task_ids[pid])] if project_task_ids[pid] else None
                await artifact_bulk.add(
                    {
                        "id": aid,
                        "project_id": pid,
                        "created_by": user_ids[ai % len(user_ids)],
                        "artifact_type": atype,
                        "semantic_type": atype,
                        "standard_type": atype,
                        "standard_version": 1,
                        "name": f"{args.prefix}artifact-p{pi:04d}-{ai:06d}",
                        "description": None,
                        "latest_version_id": vid,
                        "source_task_id": src_task,
                        "created_at": created,
                        "updated_at": created,
                    }
                )
                await version_bulk.add(
                    {
                        "id": vid,
                        "artifact_id": aid,
                        "created_by": user_ids[ai % len(user_ids)],
                        "version": 1,
                        "filename": f"artifact-{ai:06d}.json",
                        "content_type": "application/json",
                        "size_bytes": 1024 + (ai % 4096),
                        "sha256": hashlib.sha256(f"{pid}-{ai}".encode()).hexdigest(),
                        "storage_key": f"perf/{pid}/{aid}/v1.json",
                        "status": "available",
                        "validation_status": "pending",
                        "manifest_json": {},
                        "summary_json": {},
                        "metrics_json": {},
                        "expires_at": None,
                        "source_task_id": src_task,
                        "storage_tier": "standard",
                        "created_at": created,
                        "updated_at": created,
                    }
                )
        await artifact_bulk.flush()
        await version_bulk.flush()
        await session.commit()
        print(f"[artifacts] Artifact={artifact_bulk.total} ArtifactVersion={version_bulk.total}")

        # 9) keyset 不重不漏自检（仅第 1 个项目）
        if not args.no_verify and project_ids:
            ok = await verify_keyset(session, Task, tuple_, select, project_ids[0], page_size=100)
            if ok:
                print("[verify] keyset 游标遍历：无重复、无遗漏 [OK]")
            else:
                print("[verify] keyset 游标遍历失败 [FAIL]（请检查碰撞组 / 排序）")
                await engine.dispose()
                return 2

        # 10) 总结
        total_terminal = sum(terminal_counts.values())
        print("\n===== perf_seed 完成 =====")
        print(f"prefix      : {args.prefix}")
        print(f"projects    : {len(project_ids)}（首个 id={project_ids[0]}）")
        print(f"tasks       : {args.projects * args.tasks_per_project}（终态 {total_terminal}）")
        print(f"artifacts   : {args.projects * args.artifacts_per_project}")
        print(f"tool_id     : {tool_id}")
        print(f"tool_version: {tool_version_id}")
        print(f"users       : {', '.join(usernames)}")
        print(f"login       : username={args.username} password={args.password}")
        print(f"collision   : project0 前 {args.collision_rows} 个任务共享 finished_at={collision_ts.isoformat()}")
        print("\n给压测脚本用的环境变量：")
        print(f"  export PERF_BASE_URL=http://127.0.0.1:8000/api/v1")
        print(f"  export PERF_USERNAME={args.username}")
        print(f"  export PERF_PASSWORD={args.password}")
        print(f"  export PERF_PROJECT_ID={project_ids[0]}")
        print(f"  export PERF_TOOL_ID={tool_id}")
        print(f"  export PERF_TOOL_VERSION_ID={tool_version_id}")

    await engine.dispose()
    return 0


async def verify_keyset(session, Task, tuple_, select, project_id: str, page_size: int = 100) -> bool:
    """按后端 apply_desc_keyset 语义（(finished_at, id) 元组降序）游标遍历，
    校验无重复、无遗漏。"""
    from sqlalchemy import func

    expected = (
        await session.execute(
            select(func.count()).select_from(Task).where(
                Task.project_id == project_id,
                Task.status.in_(TERMINAL_STATUSES),
                Task.finished_at.is_not(None),
            )
        )
    ).scalar()

    seen: list[str] = []
    cursor_ts = None
    cursor_id = None
    while True:
        stmt = select(Task.id, Task.finished_at).where(
            Task.project_id == project_id,
            Task.status.in_(TERMINAL_STATUSES),
            Task.finished_at.is_not(None),
        )
        if cursor_ts is not None:
            stmt = stmt.where(tuple_(Task.finished_at, Task.id) < (cursor_ts, cursor_id))
        stmt = stmt.order_by(Task.finished_at.desc(), Task.id.desc()).limit(page_size)
        rows = (await session.execute(stmt)).all()
        if not rows:
            break
        for rid, fin in rows:
            seen.append(rid)
        if len(rows) < page_size:
            break
        cursor_ts, cursor_id = rows[-1][1], rows[-1][0]

    if len(seen) != len(set(seen)):
        print(f"  [verify] 出现重复：{len(seen)} 行 / {len(set(seen))} 唯一")
        return False
    if len(seen) != expected:
        print(f"  [verify] 数量不符：遍历 {len(seen)} vs 期望 {expected}")
        return False
    return True


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _apply_quick(args)

    if args.projects <= 0 or args.tasks_per_project < 0 or args.artifacts_per_project < 0:
        parser.error("--projects 必须 > 0，--tasks-per-project / --artifacts-per-project 必须 >= 0")
    if 0 < args.collision_rows < 5:
        parser.error("--collision-rows 必须 >= 5（用于 keyset 不重不漏校验）或为 0")

    if args.dry_run:
        totals = _planned_totals(args)
        print("===== perf_seed 计划（--dry-run，不连库） =====")
        for k, v in totals.items():
            print(f"  {k:18s}: {v}")
        print(f"  collision_rows    : {args.collision_rows}（project0 共享同一 finished_at）")
        print(f"  detail_samples    : {args.detail_samples}/项目")
        print(f"  prefix            : {args.prefix}")
        return 0

    return asyncio.run(run_seed(args))


if __name__ == "__main__":
    raise SystemExit(main())
