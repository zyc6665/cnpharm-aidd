from __future__ import annotations

from datetime import datetime

import httpx
import pytest
import pytest_asyncio
from fastapi import Header, HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import get_current_user
from app.config import settings
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models.tasks import Task, TaskStatus
from app.models.tools import Tool, ToolStatus, ToolVersion
from app.models.users import User, UserRole, UserStatus


@pytest_asyncio.fixture
async def smoke_context():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with factory() as db:
        admin = User(
            email="smoke-admin@example.com",
            password_hash="hashed",
            role=UserRole.ADMIN.value,
            status=UserStatus.ACTIVE.value,
        )
        regular_user = User(
            email="smoke-user@example.com",
            password_hash="hashed",
            role=UserRole.USER.value,
            status=UserStatus.ACTIVE.value,
        )
        db.add_all([admin, regular_user])
        await db.flush()

        tool = Tool(
            owner_id=admin.id,
            name="Smoke Test Tool",
            slug="smoke-test-tool",
            status=ToolStatus.PUBLISHED.value,
        )
        db.add(tool)
        await db.flush()

        ssh_version = ToolVersion(
            tool_id=tool.id,
            version="1.0.0-ssh",
            config={"type": "ssh_job"},
            is_active=True,
        )
        candidate = ToolVersion(
            tool_id=tool.id,
            version="2.0.0-k8s-candidate",
            config={
                "type": "k8s_job",
                "variant": "cpu",
                "runtime": {
                    "image": f"registry.example/model@sha256:{'a' * 64}",
                    "entrypoint": ["/app/platform_run.sh"],
                },
                "resource_profile": "cpu-medium",
            },
            is_active=False,
        )
        db.add_all([ssh_version, candidate])
        await db.flush()
        tool.current_version_id = ssh_version.id
        await db.commit()

        async def override_get_db():
            yield db

        async def override_get_current_user(
            authorization: str | None = Header(default=None),
        ) -> User:
            token = (authorization or "").removeprefix("Bearer ")
            if token == "admin":
                return admin
            if token == "user":
                return regular_user
            raise HTTPException(status_code=401, detail="未提供认证凭证")

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield {
                "admin": admin,
                "candidate": candidate,
                "client": client,
                "db": db,
                "ssh_version": ssh_version,
                "tool": tool,
            }
        app.dependency_overrides.clear()

    await engine.dispose()


def _smoke_url(context, version: ToolVersion | None = None) -> str:
    target = version or context["candidate"]
    return f"/api/v1/tools/{context['tool'].id}/versions/{target.id}/smoke"


def _promotion_url(context, version: ToolVersion | None = None) -> str:
    target = version or context["candidate"]
    return f"/api/v1/tools/{context['tool'].id}/versions/{target.id}/promote"


async def _add_smoke_task(
    context,
    *,
    task_tool_id: str | None = None,
    status: str = TaskStatus.SUCCESS.value,
    run_kind: str | None = "tool_version_smoke",
) -> Task:
    task = Task(
        user_id=context["admin"].id,
        tool_id=task_tool_id or context["tool"].id,
        tool_version_id=context["candidate"].id,
        status=status,
        extra_data={"run_kind": run_kind} if run_kind else {},
    )
    context["db"].add(task)
    await context["db"].commit()
    return task


@pytest.mark.asyncio
async def test_admin_smoke_runs_inactive_candidate_and_marks_task_server_side(
    smoke_context,
    monkeypatch: pytest.MonkeyPatch,
):
    context = smoke_context
    from app.api.v1 import tool_versions

    class RecordingRunner:
        scheduled: list[tuple[str, str]] = []

        def schedule_task(self, task_id: str, tool_version_id: str) -> None:
            self.scheduled.append((task_id, tool_version_id))

    runner = RecordingRunner()
    monkeypatch.setattr(tool_versions, "direct_task_runner", runner)
    monkeypatch.setattr(settings, "TASK_EXECUTION_BACKEND", "direct", raising=False)

    response = await context["client"].post(
        _smoke_url(context),
        headers={"Authorization": "Bearer admin"},
        json={"params": {"seed": 42}},
    )

    assert response.status_code == 200, response.json()
    task_id = response.json()["data"]["task_id"]
    task = await context["db"].get(Task, task_id)
    assert task is not None
    assert task.tool_version_id == context["candidate"].id
    assert task.project_id
    assert task.extra_data["project_id"] == task.project_id
    assert task.extra_data["run_kind"] == "tool_version_smoke"
    assert runner.scheduled == [(task_id, context["candidate"].id)]


@pytest.mark.asyncio
async def test_regular_user_cannot_start_candidate_smoke(smoke_context):
    response = await smoke_context["client"].post(
        _smoke_url(smoke_context),
        headers={"Authorization": "Bearer user"},
        json={},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_smoke_rejects_active_or_non_kubernetes_versions(smoke_context):
    context = smoke_context
    ssh_response = await context["client"].post(
        _smoke_url(context, context["ssh_version"]),
        headers={"Authorization": "Bearer admin"},
        json={},
    )
    assert ssh_response.status_code == 422

    context["candidate"].is_active = True
    await context["db"].commit()
    active_response = await context["client"].post(
        _smoke_url(context),
        headers={"Authorization": "Bearer admin"},
        json={},
    )
    assert active_response.status_code == 422


@pytest.mark.asyncio
async def test_promotion_requires_successful_smoke_for_inactive_candidate(smoke_context):
    context = smoke_context

    no_smoke = await context["client"].post(
        _promotion_url(context),
        headers={"Authorization": "Bearer admin"},
    )
    assert no_smoke.status_code == 422
    assert no_smoke.json()["message"] == "候选版本必须先通过成功的 smoke 验证"

    await _add_smoke_task(context, status=TaskStatus.FAILURE.value)
    failed_smoke = await context["client"].post(
        _promotion_url(context),
        headers={"Authorization": "Bearer admin"},
    )

    assert failed_smoke.status_code == 422
    assert context["tool"].current_version_id == context["ssh_version"].id
    assert context["candidate"].is_active is False


@pytest.mark.asyncio
async def test_latest_failed_smoke_blocks_promotion_after_earlier_success(smoke_context):
    context = smoke_context
    context["db"].add_all(
        [
            Task(
                user_id=context["admin"].id,
                tool_id=context["tool"].id,
                tool_version_id=context["candidate"].id,
                status=TaskStatus.SUCCESS.value,
                extra_data={"run_kind": "tool_version_smoke"},
                created_at=datetime(2026, 1, 1),
            ),
            Task(
                user_id=context["admin"].id,
                tool_id=context["tool"].id,
                tool_version_id=context["candidate"].id,
                status=TaskStatus.FAILURE.value,
                extra_data={"run_kind": "tool_version_smoke"},
                created_at=datetime(2026, 1, 2),
            ),
        ]
    )
    await context["db"].commit()

    response = await context["client"].post(
        _promotion_url(context),
        headers={"Authorization": "Bearer admin"},
    )

    assert response.status_code == 422
    assert context["tool"].current_version_id == context["ssh_version"].id
    assert context["candidate"].is_active is False


@pytest.mark.asyncio
async def test_promotion_requires_smoke_for_same_tool_and_version(smoke_context):
    context = smoke_context
    other_tool = Tool(
        owner_id=context["admin"].id,
        name="Other Smoke Tool",
        slug="other-smoke-tool",
        status=ToolStatus.PUBLISHED.value,
    )
    context["db"].add(other_tool)
    await context["db"].flush()
    await _add_smoke_task(context, task_tool_id=other_tool.id)

    response = await context["client"].post(
        _promotion_url(context),
        headers={"Authorization": "Bearer admin"},
    )

    assert response.status_code == 422
    assert context["tool"].current_version_id == context["ssh_version"].id


@pytest.mark.asyncio
async def test_deprecated_version_cannot_be_promoted(smoke_context):
    context = smoke_context
    context["candidate"].deprecated = True
    await _add_smoke_task(context)

    response = await context["client"].post(
        _promotion_url(context),
        headers={"Authorization": "Bearer admin"},
    )

    assert response.status_code == 422
    assert context["tool"].current_version_id == context["ssh_version"].id
    assert context["candidate"].is_active is False


@pytest.mark.asyncio
async def test_admin_promotes_smoked_candidate_and_can_switch_back_to_ssh(
    smoke_context,
):
    context = smoke_context
    await _add_smoke_task(context)

    promoted = await context["client"].post(
        _promotion_url(context),
        headers={"Authorization": "Bearer admin"},
    )

    assert promoted.status_code == 200, promoted.json()
    assert promoted.json()["data"]["current_version_id"] == context["candidate"].id
    assert context["candidate"].is_active is True
    assert context["ssh_version"].is_active is True

    rolled_back = await context["client"].post(
        _promotion_url(context, context["ssh_version"]),
        headers={"Authorization": "Bearer admin"},
    )

    assert rolled_back.status_code == 200, rolled_back.json()
    assert rolled_back.json()["data"]["current_version_id"] == context["ssh_version"].id
