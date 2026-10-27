"""运行参数 diff 端点测试（docs/12 TC-M7-07）。

覆盖：
* 参数完全相同 → ``changes`` 为空、所有字段落在 ``unchanged``；
* 参数不同 → 差异精确定位到点分路径（``params.box.center_x`` 级别，不是整块）；
* 任务数越界（1 个 / 7 个）→ 422；
* 无权限 → 404（不暴露任务是否存在）；
* 历史参数不可变：连续两次 diff 结果一致（含参数指纹）。
"""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import Header, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.auth.dependencies import get_current_user  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.main import app as main_app  # noqa: E402
from app.models.projects import Organization, Project, ProjectMember  # noqa: E402
from app.models.tasks import Task, TaskInput  # noqa: E402
from app.models.tools import Tool, ToolProviderType, ToolStatus, ToolVersion  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402
from app.services.param_diff import (  # noqa: E402
    MAX_TASKS,
    MIN_TASKS,
    flatten_params,
    param_fingerprint,
)

OWNER = "owner"
VIEWER = "viewer"
OUTSIDER = "outsider"

BASE_PARAMS = {
    "box": {
        "center_x": 1.5,
        "center_y": -2.5,
        "center_z": 30.0,
        "size": [20, 20, 20],
    },
    "exhaustiveness": 32,
    "seed": 42,
    "备注": "中文参数值",
}


# ---------------------------------------------------------------------------
# fixtures（形态照抄 test/test_traceability_api.py）
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        await session.execute(text("PRAGMA foreign_keys=ON"))
        yield session
    await engine.dispose()


async def _create_user(db: AsyncSession, email: str, *, role: str = UserRole.USER.value) -> User:
    user = User(
        email=email,
        password_hash="hashed-password",
        display_name=email.split("@")[0],
        role=role,
        status=UserStatus.ACTIVE.value,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def users(db_session: AsyncSession) -> dict[str, User]:
    return {
        OWNER: await _create_user(db_session, "owner@example.com"),
        VIEWER: await _create_user(db_session, "viewer@example.com"),
        OUTSIDER: await _create_user(db_session, "outsider@example.com"),
    }


@pytest_asyncio.fixture
async def project(db_session: AsyncSession, users: dict[str, User]) -> Project:
    organization = Organization(name="Diff Lab", slug="diff-lab")
    db_session.add(organization)
    await db_session.flush()
    project = Project(
        organization_id=organization.id,
        created_by=users[OWNER].id,
        name="Diff program",
        status="active",
    )
    db_session.add(project)
    await db_session.flush()
    db_session.add(ProjectMember(project_id=project.id, user_id=users[OWNER].id, role="owner"))
    db_session.add(ProjectMember(project_id=project.id, user_id=users[VIEWER].id, role="viewer"))
    await db_session.commit()
    await db_session.refresh(project)
    return project


@pytest_asyncio.fixture
async def api_client(db_session: AsyncSession, users: dict[str, User]):
    async def override_get_db():
        yield db_session

    async def override_get_current_user(
        authorization: str | None = Header(default=None),
    ) -> User:
        token = (authorization or "").removeprefix("Bearer ")
        if token in users:
            return users[token]
        raise HTTPException(status_code=401, detail="未提供认证凭证")

    main_app.dependency_overrides[get_db] = override_get_db
    main_app.dependency_overrides[get_current_user] = override_get_current_user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main_app), base_url="http://testserver"
    ) as client:
        yield client
    main_app.dependency_overrides.clear()


def _headers(user: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {user}"}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _create_tool(db: AsyncSession, owner: User) -> Tool:
    tool = Tool(
        owner_id=owner.id,
        name="Boltz-2",
        slug="boltz-2",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
        provider_type=ToolProviderType.PLATFORM.value,
    )
    db.add(tool)
    await db.flush()
    version = ToolVersion(
        tool_id=tool.id, version="2.0.1", config={"type": "ssh_job"}, is_active=True, deprecated=False
    )
    db.add(version)
    await db.flush()
    tool.current_version_id = version.id
    await db.commit()
    await db.refresh(tool)
    return tool


async def _create_task(
    db: AsyncSession,
    *,
    owner: User,
    tool: Tool,
    task_id: str,
    name: str,
    params: dict | None = None,
    project: Project | None = None,
) -> Task:
    task = Task(
        id=task_id,
        user_id=owner.id,
        tool_id=tool.id,
        tool_version_id=tool.current_version_id,
        name=name,
        status="SUCCESS",
        priority="normal",
        extra_data={"project_id": str(project.id)} if project is not None else {},
    )
    db.add(task)
    await db.flush()
    db.add(TaskInput(task_id=task.id, params=params, file_ids=[]))
    await db.commit()
    await db.refresh(task)
    return task


async def _compare(client: httpx.AsyncClient, task_ids: list[str], *, user: str = OWNER):
    return await client.post(
        "/api/v1/results:compare", json={"taskIds": task_ids}, headers=_headers(user)
    )


# ---------------------------------------------------------------------------
# 纯函数层：摊平与指纹
# ---------------------------------------------------------------------------


def test_flatten_params_reaches_leaves():
    flat = flatten_params(BASE_PARAMS)
    assert flat["box.center_x"] == 1.5
    assert flat["box.size[2]"] == 20
    assert flat["exhaustiveness"] == 32
    assert flat["备注"] == "中文参数值"
    # 容器本身不再是叶子，差异才能定位到叶子。
    assert "box" not in flat


def test_flatten_params_keeps_empty_containers():
    flat = flatten_params({"a": {}, "b": [], "c": None})
    assert flat == {"a": {}, "b": [], "c": None}


def test_param_fingerprint_is_key_order_insensitive():
    assert param_fingerprint({"a": 1, "b": 2}) == param_fingerprint({"b": 2, "a": 1})
    assert param_fingerprint(None) == param_fingerprint({})
    assert param_fingerprint({"a": 1}) != param_fingerprint({"a": 2})


# ---------------------------------------------------------------------------
# HTTP 层
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compare_identical_params_has_no_changes(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User]
):
    tool = await _create_tool(db_session, users[OWNER])
    first = await _create_task(
        db_session, owner=users[OWNER], tool=tool, task_id="task-same-1",
        name="同参数 A", params=deepcopy(BASE_PARAMS),
    )
    second = await _create_task(
        db_session, owner=users[OWNER], tool=tool, task_id="task-same-2",
        name="同参数 B", params=deepcopy(BASE_PARAMS),
    )

    response = await _compare(api_client, [first.id, second.id])
    assert response.status_code == 200
    data = response.json()["data"]

    assert data["identical"] is True
    assert data["changes"] == []
    assert data["summary"]["changedCount"] == 0
    assert "box.center_x" in data["unchanged"]
    assert "exhaustiveness" in data["unchanged"]
    assert data["summary"]["unchangedCount"] == data["summary"]["fieldCount"]
    assert {row["path"] for row in data["rows"]} == set(data["unchanged"])
    assert all(row["changed"] is False for row in data["rows"])
    # 两个任务的参数指纹必须相同。
    fingerprints = {column["paramFingerprint"] for column in data["columns"]}
    assert len(fingerprints) == 1


@pytest.mark.asyncio
async def test_compare_pinpoints_nested_difference(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User]
):
    tool = await _create_tool(db_session, users[OWNER])
    changed = deepcopy(BASE_PARAMS)
    changed["box"]["center_x"] = 9.75
    changed["seed"] = 7

    first = await _create_task(
        db_session, owner=users[OWNER], tool=tool, task_id="task-diff-1",
        name="参数一", params=deepcopy(BASE_PARAMS),
    )
    second = await _create_task(
        db_session, owner=users[OWNER], tool=tool, task_id="task-diff-2",
        name="参数二", params=changed,
    )

    response = await _compare(api_client, [first.id, second.id])
    assert response.status_code == 200
    data = response.json()["data"]

    assert data["identical"] is False
    assert set(data["changes"]) == {"box.center_x", "seed"}
    # 差异只落在改动的叶子上，兄弟字段不受牵连。
    assert "box.center_y" in data["unchanged"]
    assert "box.size[0]" in data["unchanged"]

    rows = {row["path"]: row for row in data["rows"]}
    assert rows["box.center_x"]["changed"] is True
    assert rows["box.center_x"]["values"][first.id] == "1.5"
    assert rows["box.center_x"]["values"][second.id] == "9.75"
    assert rows["box.center_y"]["changed"] is False
    assert data["summary"]["changedCount"] == 2


@pytest.mark.asyncio
async def test_compare_reports_missing_field_per_task(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User]
):
    """一个任务有某字段、另一个没有 → 必须算差异，并点名谁缺。"""
    tool = await _create_tool(db_session, users[OWNER])
    partial = {"exhaustiveness": 32}

    first = await _create_task(
        db_session, owner=users[OWNER], tool=tool, task_id="task-miss-1",
        name="全参数", params=deepcopy(BASE_PARAMS),
    )
    second = await _create_task(
        db_session, owner=users[OWNER], tool=tool, task_id="task-miss-2",
        name="缺参数", params=partial,
    )

    response = await _compare(api_client, [first.id, second.id])
    assert response.status_code == 200
    data = response.json()["data"]

    assert "box.center_x" in data["changes"]
    rows = {row["path"]: row for row in data["rows"]}
    assert rows["box.center_x"]["missing"] == [second.id]
    assert rows["box.center_x"]["values"][second.id] == "-"
    # 共有且相同的字段仍算 unchanged。
    assert "exhaustiveness" in data["unchanged"]


@pytest.mark.asyncio
async def test_compare_supports_six_tasks(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User]
):
    tool = await _create_tool(db_session, users[OWNER])
    tasks = []
    for index in range(MAX_TASKS):
        params = deepcopy(BASE_PARAMS)
        params["seed"] = 42 + index
        tasks.append(
            await _create_task(
                db_session, owner=users[OWNER], tool=tool, task_id=f"task-six-{index}",
                name=f"批量 {index}", params=params,
            )
        )

    response = await _compare(api_client, [task.id for task in tasks])
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["taskIds"] == [task.id for task in tasks]
    assert len(data["columns"]) == MAX_TASKS
    assert data["changes"] == ["seed"]
    assert len({column["paramFingerprint"] for column in data["columns"]}) == MAX_TASKS


@pytest.mark.asyncio
async def test_compare_rejects_single_task(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User]
):
    tool = await _create_tool(db_session, users[OWNER])
    task = await _create_task(
        db_session, owner=users[OWNER], tool=tool, task_id="task-one", name="单任务",
        params=deepcopy(BASE_PARAMS),
    )

    response = await _compare(api_client, [task.id])
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_compare_rejects_seven_tasks(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User]
):
    tool = await _create_tool(db_session, users[OWNER])
    tasks = []
    for index in range(MAX_TASKS + 1):
        tasks.append(
            await _create_task(
                db_session, owner=users[OWNER], tool=tool, task_id=f"task-many-{index}",
                name=f"超量 {index}", params=deepcopy(BASE_PARAMS),
            )
        )

    response = await _compare(api_client, [task.id for task in tasks])
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_compare_deduplicates_identical_ids(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User]
):
    """同一个 ID 传两次不算「2 个任务」，去重后不足下限 → 422。"""
    tool = await _create_tool(db_session, users[OWNER])
    task = await _create_task(
        db_session, owner=users[OWNER], tool=tool, task_id="task-dup", name="重复",
        params=deepcopy(BASE_PARAMS),
    )

    response = await _compare(api_client, [task.id, task.id])
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_compare_hides_unreadable_task_as_404(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User],
    project: Project,
):
    """任一任务不可读 → 整体 404，不暴露存在性。"""
    tool = await _create_tool(db_session, users[OWNER])
    mine = await _create_task(
        db_session, owner=users[OWNER], tool=tool, task_id="task-mine", name="我的任务",
        params=deepcopy(BASE_PARAMS), project=project,
    )
    others = await _create_task(
        db_session, owner=users[OUTSIDER], tool=tool, task_id="task-others", name="别人的任务",
        params=deepcopy(BASE_PARAMS),
    )

    response = await _compare(api_client, [mine.id, others.id], user=OWNER)
    assert response.status_code == 404

    # 与「任务根本不存在」的响应完全一致 —— 单看状态码无法区分。
    missing = await _compare(api_client, [mine.id, "no-such-task"], user=OWNER)
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_compare_allows_project_viewer(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User],
    project: Project,
):
    tool = await _create_tool(db_session, users[OWNER])
    first = await _create_task(
        db_session, owner=users[OWNER], tool=tool, task_id="task-view-1", name="视图 1",
        params=deepcopy(BASE_PARAMS), project=project,
    )
    second = await _create_task(
        db_session, owner=users[OWNER], tool=tool, task_id="task-view-2", name="视图 2",
        params=deepcopy(BASE_PARAMS), project=project,
    )

    response = await _compare(api_client, [first.id, second.id], user=VIEWER)
    assert response.status_code == 200
    assert response.json()["data"]["identical"] is True


@pytest.mark.asyncio
async def test_compare_is_repeatable_and_params_immutable(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User]
):
    """TC-M7-07「历史任务参数不可被修改」：连续两次 diff 结果必须一致。"""
    tool = await _create_tool(db_session, users[OWNER])
    changed = deepcopy(BASE_PARAMS)
    changed["box"]["center_z"] = 99.0

    first = await _create_task(
        db_session, owner=users[OWNER], tool=tool, task_id="task-stable-1", name="稳定 1",
        params=deepcopy(BASE_PARAMS),
    )
    second = await _create_task(
        db_session, owner=users[OWNER], tool=tool, task_id="task-stable-2", name="稳定 2",
        params=changed,
    )

    first_response = await _compare(api_client, [first.id, second.id])
    second_response = await _compare(api_client, [first.id, second.id])
    assert first_response.status_code == second_response.status_code == 200

    first_data = first_response.json()["data"]
    second_data = second_response.json()["data"]
    assert first_data == second_data
    assert first_data["changes"] == ["box.center_z"]

    # 落库的参数本身没被 diff 读操作改写。
    stored = (
        await db_session.execute(select(TaskInput).where(TaskInput.task_id == first.id))
    ).scalar_one()
    await db_session.refresh(stored)
    assert stored.params == BASE_PARAMS
    assert param_fingerprint(stored.params) == param_fingerprint(BASE_PARAMS)


@pytest.mark.asyncio
async def test_compare_requires_auth(api_client: httpx.AsyncClient):
    response = await api_client.post(
        "/api/v1/results:compare",
        json={"taskIds": ["a", "b"]},
        headers={"Authorization": "Bearer nobody"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_compare_min_tasks_constant_matches_contract():
    assert MIN_TASKS == 2
    assert MAX_TASKS == 6
