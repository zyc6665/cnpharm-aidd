"""分析报告 PDF 端点测试（docs/12 TC-M7-04 / TC-M7-08）。

覆盖：
* ``GET /results/{taskId}/report.pdf`` 返回合法 PDF（魔数、大小、content-type）；
* PDF 文本里能取到中文任务名（STSong-Light + pypdf CMap）与模板版本；
* 失败/取消任务也能导出报告（复盘场景）；
* 旧 JSON 端点 ``GET /results/{taskId}/report`` 行为不变（前端兼容）；
* ``POST /results/{taskId}/report:export`` 落库 + 900 秒预签名 URL。
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pypdf
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

from app.auth.dependencies import get_current_user, get_current_user_optional  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.logging.audit import AuditAction, ResourceType, get_audit_logger  # noqa: E402
from app.main import app as main_app  # noqa: E402
from app.models.artifacts import Artifact, ArtifactVersion  # noqa: E402
from app.models.projects import Organization, Project, ProjectMember  # noqa: E402
from app.models.tasks import Task, TaskInput, TaskOutput  # noqa: E402
from app.models.tools import Tool, ToolProviderType, ToolStatus, ToolVersion  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402
from app.services.report_pdf import (  # noqa: E402
    CJK_FONT_NAME,
    REPORT_TEMPLATE_VERSION,
    build_result_report_pdf,
    extract_conclusions,
)

OWNER = "owner"
VIEWER = "viewer"
OUTSIDER = "outsider"
ADMIN = "admin"

CN_TASK_NAME = "分子对接测试任务：EGFR 靶点筛选"

#: 哨兵：区分「没传 result（用默认 metrics）」与「显式传 None（真的没有输出）」。
_UNSET = object()


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
        ADMIN: await _create_user(db_session, "admin@example.com", role=UserRole.ADMIN.value),
    }


@pytest_asyncio.fixture
async def project(db_session: AsyncSession, users: dict[str, User]) -> Project:
    organization = Organization(name="Report Lab", slug="report-lab")
    db_session.add(organization)
    await db_session.flush()
    project = Project(
        organization_id=organization.id,
        created_by=users[OWNER].id,
        name="EGFR program",
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

    # 下载入口用 optional 依赖；浏览器下载令牌兑换时要求能比对当前请求者。
    main_app.dependency_overrides[get_current_user_optional] = override_get_current_user

    # 必须复用真实 app，否则 AppException 处理器不生效（404/422 会变成裸异常）。
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
        tool_id=tool.id,
        version="2.0.1",
        config={"type": "ssh_job", "image": "registry.internal/cnpharm/boltz-2:2.0.1"},
        is_active=True,
        deprecated=False,
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
    project: Project,
    tool: Tool,
    task_id: str,
    name: str = CN_TASK_NAME,
    status: str = "SUCCESS",
    params: dict | None = None,
    result: dict | None = _UNSET,
    error_message: str | None = None,
) -> Task:
    task = Task(
        id=task_id,
        user_id=owner.id,
        tool_id=tool.id,
        tool_version_id=tool.current_version_id,
        name=name,
        status=status,
        priority="normal",
        progress=1.0,
        execution_time_sec=750.5,
        retry_count=1,
        error_message=error_message,
        extra_data={
            "project_id": str(project.id),
            "domain": {"kind": "docking", "model_ref": {"name": "vina", "version": "1.2.0"}},
            "resource_snapshot": {"cpu": 8, "gpu": 1},
        },
    )
    db.add(task)
    await db.flush()
    db.add(
        TaskInput(
            task_id=task.id,
            params=params
            if params is not None
            else {
                "box": {"center_x": 1.5, "center_y": -2.5, "center_z": 30.0, "size": [20, 20, 20]},
                "exhaustiveness": 32,
                "seed": 42,
                "备注": "中文参数值",
            },
            file_ids=[],
        )
    )
    db.add(
        TaskOutput(
            task_id=task.id,
            result=(
                {"metrics": {"best_affinity": -9.2, "num_poses": 9}}
                if result is _UNSET
                else result
            ),
            file_ids=[],
            output_type="json",
        )
    )
    await db.commit()
    await db.refresh(task)
    return task


async def _create_artifact_with_metrics(
    db: AsyncSession, *, owner: User, project: Project, task: Task
) -> Artifact:
    artifact = Artifact(
        project_id=project.id,
        created_by=owner.id,
        # 资产类型收敛为受控枚举：此夹具历史上用 file（旧渲染别名），现归一为
        # run_report；semantic_type 仍是 docking_result@1，PDF 渲染样例不受影响。
        artifact_type="run_report",
        semantic_type="docking_result@1",
        name="对接结果",
        source_task_id=str(task.id),
    )
    db.add(artifact)
    await db.flush()
    version = ArtifactVersion(
        artifact_id=artifact.id,
        created_by=owner.id,
        version=1,
        filename="结果.sdf",
        size_bytes=204800,
        sha256="b" * 64,
        storage_key="artifacts/result.sdf",
        metrics_json={"artifact_metric": 12.5},
        summary_json={"artifact_summary": "9 个构象，最佳 -9.2 kcal/mol"},
    )
    db.add(version)
    await db.flush()
    artifact.latest_version_id = version.id
    await db.commit()
    await db.refresh(artifact)
    return artifact


# ---------------------------------------------------------------------------
# PDF 生成（纯函数层）
# ---------------------------------------------------------------------------


def _sample_package(**overrides):
    package = {
        "taskId": "11111111-2222-3333-4444-555555555555",
        "taskName": CN_TASK_NAME,
        "taskType": "docking",
        "status": "SUCCESS",
        "submittedBy": {"userId": "u-1", "displayName": "张伟", "email": "zhang@example.com"},
        "projectId": "proj-1",
        "timeline": {
            "created": "2026-10-25T13:00:00Z",
            "started": "2026-10-25T13:00:05Z",
            "finished": "2026-10-25T13:12:35Z",
            "executionSeconds": 750.5,
            "retryCount": 1,
        },
        "inputs": [
            {
                "inputRole": "RECEPTOR",
                "ordinal": 0,
                "urn": "file:abc",
                "sha256": "a" * 64,
                "dataVersion": 3,
            }
        ],
        "environment": {
            "image": "registry.internal/cnpharm/boltz-2:2.0.1",
            "executorType": "ssh_job",
            "tool": {"id": "t-1", "name": "分子对接", "slug": "dock", "version": "2.0.1"},
            "model": {"name": "vina", "version": "1.2.0"},
            "resourceSnapshot": {"cpu": 8},
            "contractVersion": "v2",
        },
        "params": {"requested": {"box": {"center_x": 1.5}, "exhaustiveness": 32}, "inputBindings": {}},
        "process": {"exitMessage": None, "progressMessage": "done", "logAvailable": True},
        "outputs": [
            {
                "kind": "artifact",
                "artifactType": "file",
                "semanticType": "docking_result@1",
                "urn": "artifact:1",
                "sha256": "b" * 64,
                "sizeBytes": 204800,
                "filename": "结果.sdf",
            }
        ],
        "bizRef": {"projectId": "proj-1", "domain": {"kind": "docking"}},
        "exportedAt": "2026-10-25T13:20:00Z",
        "packageVersion": "traceability.v1",
    }
    package.update(overrides)
    return package


def test_renderer_emits_valid_pdf_with_chinese_text():
    pdf = build_result_report_pdf(
        _sample_package(),
        conclusions=extract_conclusions({"metrics": {"best_affinity": -9.2}}),
        package_sha256="c" * 64,
    )
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 3000

    text = "\n".join(page.extract_text() for page in pypdf.PdfReader(_bytes(pdf)).pages)
    # 中文可提取：STSong-Light 是 CID 字体，pypdf 通过 CMap 还原 Unicode。
    assert CN_TASK_NAME in text
    assert "中国医药 AIDD 平台" in text
    assert REPORT_TEMPLATE_VERSION in text
    assert "best_affinity" in text
    # 追溯包指纹写在页脚。
    assert ("c" * 64) in text


def _bytes(pdf: bytes):
    import io

    return io.BytesIO(pdf)


def test_renderer_marks_truncated_params_explicitly():
    huge = {"blob": "长" * 40000}
    pdf = build_result_report_pdf(
        _sample_package(params={"requested": huge, "inputBindings": {}}),
        conclusions=[],
        package_sha256="d" * 64,
    )
    text = "\n".join(page.extract_text() for page in pypdf.PdfReader(_bytes(pdf)).pages)
    assert "已截断" in text
    # 不能静默丢掉：要指向完整内容的出口。
    assert ":export" in text


def test_renderer_says_no_metrics_instead_of_inventing_them():
    pdf = build_result_report_pdf(_sample_package(), conclusions=[], package_sha256="e" * 64)
    text = "\n".join(page.extract_text() for page in pypdf.PdfReader(_bytes(pdf)).pages)
    assert "本任务未产出结构化指标" in text


def test_renderer_renders_empty_fields_as_dash():
    pdf = build_result_report_pdf(
        _sample_package(taskName=None, submittedBy={}, params={"requested": None}),
        conclusions=[],
        package_sha256="f" * 64,
    )
    text = "\n".join(page.extract_text() for page in pypdf.PdfReader(_bytes(pdf)).pages)
    assert "None" not in text
    assert "-" in text


def test_renderer_uses_stsong_cid_font():
    """字体断言兜底：即便某个环境解不出 CID 文本，也证明用的是内置 CJK 字体。"""
    from reportlab.pdfbase import pdfmetrics

    build_result_report_pdf(_sample_package(), conclusions=[], package_sha256="1" * 64)
    assert CJK_FONT_NAME == "STSong-Light"
    assert pdfmetrics.getFont(CJK_FONT_NAME) is not None


def test_extract_conclusions_ignores_non_metric_noise():
    assert extract_conclusions({"pdb_header": "ATOM ...", "chains": 4}) == []
    assert extract_conclusions(None) == []
    rows = extract_conclusions({"metrics": {"a": 1, "nested": {"b": True}}})
    assert [(row["path"], row["value"]) for row in rows] == [("a", "1"), ("nested.b", "是")]


# ---------------------------------------------------------------------------
# HTTP 层
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_report_pdf_endpoint_returns_pdf(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User], project: Project
):
    tool = await _create_tool(db_session, users[OWNER])
    task = await _create_task(
        db_session, owner=users[OWNER], project=project, tool=tool, task_id="task-pdf-1"
    )

    response = await api_client.get(f"/api/v1/results/{task.id}/report.pdf", headers=_headers(OWNER))
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    body = response.content
    assert body[:5] == b"%PDF-"
    assert len(body) > 3000
    assert response.headers["x-report-template-version"] == REPORT_TEMPLATE_VERSION
    assert len(response.headers["x-traceability-sha256"]) == 64
    assert response.headers["content-disposition"].endswith('.pdf"')

    text = "\n".join(page.extract_text() for page in pypdf.PdfReader(_bytes(body)).pages)
    assert CN_TASK_NAME in text
    assert "exhaustiveness" in text
    assert "best_affinity" in text


@pytest.mark.asyncio
async def test_report_pdf_includes_artifact_metrics_as_conclusions(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User], project: Project
):
    tool = await _create_tool(db_session, users[OWNER])
    task = await _create_task(
        db_session, owner=users[OWNER], project=project, tool=tool, task_id="task-pdf-artifact",
        result={"pdb_header": "ATOM"},
    )
    await _create_artifact_with_metrics(
        db_session, owner=users[OWNER], project=project, task=task
    )

    response = await api_client.get(f"/api/v1/results/{task.id}/report.pdf", headers=_headers(OWNER))
    assert response.status_code == 200
    text = "\n".join(page.extract_text() for page in pypdf.PdfReader(_bytes(response.content)).pages)
    assert "artifact_metric" in text
    assert "artifact_summary" in text


@pytest.mark.asyncio
async def test_report_pdf_for_failed_task(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User], project: Project
):
    """失败任务也要能出报告：复盘正是最需要报告的时候。"""
    tool = await _create_tool(db_session, users[OWNER])
    task = await _create_task(
        db_session,
        owner=users[OWNER],
        project=project,
        tool=tool,
        task_id="task-pdf-failed",
        status="FAILURE",
        error_message="对接引擎崩溃 /engine exited with code 137",
        result=None,
    )

    response = await api_client.get(f"/api/v1/results/{task.id}/report.pdf", headers=_headers(OWNER))
    assert response.status_code == 200
    assert response.content[:5] == b"%PDF-"
    text = "\n".join(
        page.extract_text() for page in pypdf.PdfReader(_bytes(response.content)).pages
    )
    assert "任务失败" in text
    assert "exited with code 137" in text
    assert "本任务未产出结构化指标" in text


@pytest.mark.asyncio
async def test_report_pdf_rejects_outsider(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User], project: Project
):
    tool = await _create_tool(db_session, users[OWNER])
    task = await _create_task(
        db_session, owner=users[OWNER], project=project, tool=tool, task_id="task-pdf-deny"
    )

    response = await api_client.get(
        f"/api/v1/results/{task.id}/report.pdf", headers=_headers(OUTSIDER)
    )
    assert response.status_code in (403, 404)


@pytest.mark.asyncio
async def test_report_pdf_unknown_task_is_404(api_client: httpx.AsyncClient):
    response = await api_client.get(
        "/api/v1/results/no-such-task/report.pdf", headers=_headers(OWNER)
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_legacy_json_report_endpoint_is_unchanged(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User], project: Project
):
    """前端在用的 JSON 结构必须保持：不能为了 PDF 而改这个端点的形状。"""
    tool = await _create_tool(db_session, users[OWNER])
    task = await _create_task(
        db_session, owner=users[OWNER], project=project, tool=tool, task_id="task-report-json"
    )

    response = await api_client.get(f"/api/v1/results/{task.id}/report", headers=_headers(OWNER))
    assert response.status_code == 200
    data = response.json()["data"]
    assert set(data) == {"task_id", "name", "status", "summary", "artifacts", "lineage_hint"}
    assert data["task_id"] == task.id
    assert data["summary"]["metrics"]["best_affinity"] == -9.2
    assert data["lineage_hint"]["project_id"] == str(project.id)


@pytest.mark.asyncio
async def test_report_export_persists_pdf_with_15min_url(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User], project: Project
):
    tool = await _create_tool(db_session, users[OWNER])
    task = await _create_task(
        db_session, owner=users[OWNER], project=project, tool=tool, task_id="task-report-export"
    )

    response = await api_client.post(
        f"/api/v1/results/{task.id}/report:export", headers=_headers(OWNER)
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["filename"].startswith("report-")
    assert data["filename"].endswith(".pdf")
    assert data["content_type"] == "application/pdf"
    assert data["size_bytes"] > 3000
    assert len(data["sha256"]) == 64
    assert data["template_version"] == REPORT_TEMPLATE_VERSION
    assert data["expires_in_seconds"] == 900
    assert data["download_url"].startswith("/api/v1/files/")
    assert "token=" in data["download_url"]


@pytest.mark.asyncio
async def test_report_export_writes_audit_event(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    users: dict[str, User],
    project: Project,
    monkeypatch,
):
    """导出 PDF 报告必须留痕（V3.0 §6.2 / docs/26 H-9）。"""
    tool = await _create_tool(db_session, users[OWNER])
    task = await _create_task(
        db_session, owner=users[OWNER], project=project, tool=tool, task_id="task-report-audit"
    )

    events: list = []
    audit_logger = get_audit_logger()
    monkeypatch.setattr(audit_logger, "enable_file_logging", False)
    monkeypatch.setattr(audit_logger, "enable_db_logging", True)
    monkeypatch.setattr(audit_logger, "_db_writer", events.append)

    response = await api_client.post(
        f"/api/v1/results/{task.id}/report:export", headers=_headers(OWNER)
    )
    assert response.status_code == 200

    export_events = [event for event in events if event.action is AuditAction.EXPORT]
    assert len(export_events) == 1
    event = export_events[0]
    assert event.resource_type is ResourceType.TASK
    assert event.resource_id == task.id
    assert event.extra["kind"] == "result_report_pdf"
    assert event.extra["format"] == "pdf"
    assert event.extra["sha256"] == response.json()["data"]["sha256"]


@pytest.mark.asyncio
async def test_report_export_is_downloadable(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User], project: Project
):
    """导出的 PDF 能用返回的预签名 URL 真的下回来。"""
    tool = await _create_tool(db_session, users[OWNER])
    task = await _create_task(
        db_session, owner=users[OWNER], project=project, tool=tool, task_id="task-report-dl"
    )

    exported = await api_client.post(
        f"/api/v1/results/{task.id}/report:export", headers=_headers(OWNER)
    )
    download_url = exported.json()["data"]["download_url"]

    response = await api_client.get(download_url, headers=_headers(OWNER))
    assert response.status_code == 200
    assert response.content[:5] == b"%PDF-"


@pytest.mark.asyncio
async def test_report_pdf_is_stable_across_calls(
    api_client: httpx.AsyncClient, db_session: AsyncSession, users: dict[str, User], project: Project
):
    """同一条历史记录两次渲染得到相同模板版本与相同追溯包指纹。"""
    tool = await _create_tool(db_session, users[OWNER])
    task = await _create_task(
        db_session, owner=users[OWNER], project=project, tool=tool, task_id="task-report-stable"
    )

    first = await api_client.get(f"/api/v1/results/{task.id}/report.pdf", headers=_headers(OWNER))
    second = await api_client.get(f"/api/v1/results/{task.id}/report.pdf", headers=_headers(OWNER))
    assert first.status_code == second.status_code == 200
    # exportedAt 是渲染时刻，会变；追溯包内容指纹必须一致。
    assert first.headers["x-traceability-sha256"] == second.headers["x-traceability-sha256"]
