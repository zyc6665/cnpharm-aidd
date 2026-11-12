"""候选物结果链路的写入侧与读取侧（V3.0 §4.8 归属关系、``docs/26`` H-14）。

历史缺陷：``GET /candidates/{id}/results`` 读 ``Task.extra_data["domain"]["candidate_id"]``，
而这个键**全仓没有写入方** —— 接口存在、鉴权正确、永远返回空列表。这里守住三件事：

1. 提交任务时显式声明 ``candidate_id`` 会写进任务领域上下文（写入侧）；
2. 列表包含**产出该候选物的任务**（``Candidate.task_id``）与**为它跑的任务**（读取侧双向）；
3. 跨项目的候选物不能被挂到别的项目的任务上（否则一次提交就能把 A 项目的结果
   挂到 B 项目的候选物下）。
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import Header, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.v1 import tasks as tasks_api  # noqa: E402
from app.auth.dependencies import get_current_user  # noqa: E402
from app.common.exceptions import ValidationException  # noqa: E402
from app.config import settings as config_settings  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.projects import Organization, Project, ProjectMember  # noqa: E402
from app.models.tasks import Task, TaskStatus  # noqa: E402
from app.models.tools import Tool, ToolStatus, ToolVersion  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402
from app.schemas.tasks import TaskCreate  # noqa: E402
from app.services.candidate_results import (  # noqa: E402
    DOMAIN_KIND_CANDIDATE_TASK,
    attach_candidate_domain,
)
from app.tasks.service import create_and_schedule_tool_task  # noqa: E402

OWNER = "owner"
OUTSIDER = "outsider"


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


async def _create_user(db: AsyncSession, email: str) -> User:
    user = User(
        email=email,
        password_hash="hashed-password",
        display_name=email.split("@")[0],
        role=UserRole.USER.value,
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
        OUTSIDER: await _create_user(db_session, "outsider@example.com"),
    }


async def _create_project(db: AsyncSession, owner: User, *, name: str, slug: str) -> Project:
    organization = Organization(name=f"{name} org", slug=f"{slug}-org")
    db.add(organization)
    await db.flush()
    project = Project(
        organization_id=organization.id, created_by=owner.id, name=name, status="active"
    )
    db.add(project)
    await db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=owner.id, role="owner"))
    await db.commit()
    await db.refresh(project)
    return project


@pytest_asyncio.fixture
async def project(db_session: AsyncSession, users: dict[str, User]) -> Project:
    return await _create_project(db_session, users[OWNER], name="EGFR", slug="egfr")


@pytest_asyncio.fixture
async def other_project(db_session: AsyncSession, users: dict[str, User]) -> Project:
    return await _create_project(
        db_session, users[OWNER], name="KRAS", slug="kras"
    )


@pytest_asyncio.fixture
async def tool(db_session: AsyncSession, users: dict[str, User]) -> Tool:
    tool = Tool(
        owner_id=users[OWNER].id,
        name="Candidate Tool",
        slug="candidate-tool",
        category="generation",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
        gpu_required=False,
    )
    db_session.add(tool)
    await db_session.flush()
    version = ToolVersion(
        tool_id=tool.id, version="1.0.0", config={"type": "python_script"}, is_active=True
    )
    db_session.add(version)
    await db_session.flush()
    tool.current_version_id = version.id
    await db_session.commit()
    await db_session.refresh(tool)
    return tool


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

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def direct_runner(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    runner = SimpleNamespace(
        scheduled=[],
        schedule_task=lambda task_id, tool_version_id: runner.scheduled.append(
            (task_id, tool_version_id)
        ),
        cancel_task=lambda task_id: True,
    )
    monkeypatch.setattr(config_settings, "TASK_EXECUTION_BACKEND", "direct", raising=False)
    monkeypatch.setattr(tasks_api, "direct_task_runner", runner, raising=False)
    return runner


def _headers(user: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {user}"}


async def _create_candidate(
    client: httpx.AsyncClient, project_id: str, *, user: str = OWNER, **overrides
) -> dict:
    payload = {"smiles": "CCO", "name": "ethanol"}
    payload.update(overrides)
    response = await client.post(
        f"/api/v1/projects/{project_id}/candidates",
        headers=_headers(user),
        json=payload,
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _make_task(
    db: AsyncSession,
    *,
    owner: User,
    project: Project,
    tool: Tool,
    status: str = TaskStatus.SUCCESS.value,
    extra_data: dict | None = None,
    name: str = "task",
) -> Task:
    task = Task(
        user_id=owner.id,
        project_id=project.id,
        tool_id=tool.id,
        tool_version_id=tool.current_version_id,
        status=status,
        priority="normal",
        progress=0.0,
        name=name,
        extra_data=extra_data or {},
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


# ---------------------------------------------------------------------------
# 写入侧：attach_candidate_domain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attach_candidate_domain_writes_both_keys(
    db_session: AsyncSession,
    api_client: httpx.AsyncClient,
    users: dict[str, User],
    project: Project,
) -> None:
    candidate = await _create_candidate(api_client, project.id)

    merged = await attach_candidate_domain(
        db_session,
        extra_data={"project_id": project.id},
        candidate_id=candidate["id"],
        project_id=project.id,
        user=users[OWNER],
    )

    assert merged["project_id"] == project.id
    assert merged["domain"]["kind"] == DOMAIN_KIND_CANDIDATE_TASK
    assert merged["domain"]["candidate_id"] == candidate["id"]
    # 双写：读取侧读 snake_case，前端习惯 camelCase，两者都要在。
    assert merged["domain"]["candidateId"] == candidate["id"]


@pytest.mark.asyncio
async def test_attach_candidate_domain_is_a_noop_without_candidate(
    db_session: AsyncSession, users: dict[str, User], project: Project
) -> None:
    merged = await attach_candidate_domain(
        db_session,
        extra_data={"project_id": project.id},
        candidate_id=None,
        project_id=project.id,
        user=users[OWNER],
    )
    assert merged == {"project_id": project.id}


@pytest.mark.asyncio
async def test_attach_candidate_domain_requires_a_project(
    db_session: AsyncSession,
    api_client: httpx.AsyncClient,
    users: dict[str, User],
    project: Project,
) -> None:
    candidate = await _create_candidate(api_client, project.id)

    with pytest.raises(ValidationException) as excinfo:
        await attach_candidate_domain(
            db_session,
            extra_data={},
            candidate_id=candidate["id"],
            project_id=None,
            user=users[OWNER],
        )
    assert "项目" in str(excinfo.value)  # 归错项目比报错更难发现


@pytest.mark.asyncio
async def test_attach_candidate_domain_rejects_another_project(
    db_session: AsyncSession,
    api_client: httpx.AsyncClient,
    users: dict[str, User],
    project: Project,
    other_project: Project,
) -> None:
    candidate = await _create_candidate(api_client, project.id)

    with pytest.raises(ValidationException):
        await attach_candidate_domain(
            db_session,
            extra_data={"project_id": other_project.id},
            candidate_id=candidate["id"],
            project_id=other_project.id,
            user=users[OWNER],
        )


# ---------------------------------------------------------------------------
# 写入侧：真实提交路径
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submitting_a_task_for_a_candidate_records_its_identity(
    db_session: AsyncSession,
    api_client: httpx.AsyncClient,
    users: dict[str, User],
    project: Project,
    tool: Tool,
    direct_runner: SimpleNamespace,
) -> None:
    candidate = await _create_candidate(api_client, project.id)

    task = await create_and_schedule_tool_task(
        db=db_session,
        current_user=users[OWNER],
        task_data=TaskCreate(
            name="affinity for candidate",
            project_id=project.id,
            tool_id=tool.id,
            params={},
            candidate_id=candidate["id"],
        ),
        direct_runner=direct_runner,
    )

    assert task.extra_data["domain"]["candidate_id"] == candidate["id"]
    assert task.extra_data["domain"]["kind"] == DOMAIN_KIND_CANDIDATE_TASK
    assert direct_runner.scheduled  # 提交没有被候选物校验拦成中间态


@pytest.mark.asyncio
async def test_submitting_with_a_foreign_candidate_is_rejected(
    db_session: AsyncSession,
    api_client: httpx.AsyncClient,
    users: dict[str, User],
    project: Project,
    other_project: Project,
    tool: Tool,
    direct_runner: SimpleNamespace,
) -> None:
    foreign = await _create_candidate(api_client, other_project.id)

    with pytest.raises(ValidationException):
        await create_and_schedule_tool_task(
            db=db_session,
            current_user=users[OWNER],
            task_data=TaskCreate(
                name="wrong project",
                project_id=project.id,
                tool_id=tool.id,
                params={},
                candidate_id=foreign["id"],
            ),
            direct_runner=direct_runner,
        )
    assert not direct_runner.scheduled


# ---------------------------------------------------------------------------
# 读取侧：/candidates/{id}/results
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_candidate_results_include_the_producing_task(
    db_session: AsyncSession,
    api_client: httpx.AsyncClient,
    users: dict[str, User],
    project: Project,
    tool: Tool,
) -> None:
    """产出该候选物的任务必须出现在它的结果里（``Candidate.task_id``）。"""
    producing = await _make_task(
        db_session,
        owner=users[OWNER],
        project=project,
        tool=tool,
        name="pocket2mol run",
    )
    candidate = await _create_candidate(api_client, project.id, task_id=producing.id)

    response = await api_client.get(
        f"/api/v1/candidates/{candidate['id']}/results", headers=_headers(OWNER)
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert [item["task_id"] for item in data["items"]] == [producing.id]


@pytest.mark.asyncio
async def test_candidate_results_include_tasks_declared_for_the_candidate(
    db_session: AsyncSession,
    api_client: httpx.AsyncClient,
    users: dict[str, User],
    project: Project,
    tool: Tool,
) -> None:
    candidate = await _create_candidate(api_client, project.id)
    declared = await _make_task(
        db_session,
        owner=users[OWNER],
        project=project,
        tool=tool,
        name="affinity run",
        extra_data={"domain": {"kind": DOMAIN_KIND_CANDIDATE_TASK, "candidate_id": candidate["id"]}},
    )
    unrelated = await _make_task(
        db_session,
        owner=users[OWNER],
        project=project,
        tool=tool,
        name="unrelated run",
    )

    response = await api_client.get(
        f"/api/v1/candidates/{candidate['id']}/results", headers=_headers(OWNER)
    )
    assert response.status_code == 200, response.text
    ids = [item["task_id"] for item in response.json()["data"]["items"]]
    assert ids == [declared.id]
    assert unrelated.id not in ids


@pytest.mark.asyncio
async def test_candidate_results_ignore_unfinished_tasks(
    db_session: AsyncSession,
    api_client: httpx.AsyncClient,
    users: dict[str, User],
    project: Project,
    tool: Tool,
) -> None:
    """排队中的任务不是「结果」——它属于任务中心（docs/06 P-31）。"""
    candidate = await _create_candidate(api_client, project.id)
    await _make_task(
        db_session,
        owner=users[OWNER],
        project=project,
        tool=tool,
        status=TaskStatus.QUEUED.value,
        name="still queued",
        extra_data={"domain": {"kind": DOMAIN_KIND_CANDIDATE_TASK, "candidate_id": candidate["id"]}},
    )

    response = await api_client.get(
        f"/api/v1/candidates/{candidate['id']}/results", headers=_headers(OWNER)
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["items"] == []
