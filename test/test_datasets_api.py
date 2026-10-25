"""数据集登记与查询 API tests (docs/05 §4.1, docs/04 §8).

数据集是「已完成的导入结果」的登记簿：只存 ``file_urn`` + ``summary``，**不重新解析
文件**。本文件守住这几条契约：分页、类型筛选、跨项目不可见（404）、viewer 只读
（403）、删除后不再出现在列表、``summary`` 原样回读、``row_count`` 非负、
``file_urn`` 必须带 ``file:`` 前缀。
"""

from __future__ import annotations

import sys
from pathlib import Path

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

from app.auth.dependencies import get_current_user  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.projects import Organization, Project, ProjectMember  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402

OWNER = "owner"
VIEWER = "viewer"
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
        VIEWER: await _create_user(db_session, "viewer@example.com"),
        OUTSIDER: await _create_user(db_session, "outsider@example.com"),
    }


async def _build_project(db: AsyncSession, *, name: str, slug: str, owner: User) -> Project:
    organization = Organization(name=f"{name} org", slug=slug)
    db.add(organization)
    await db.flush()
    project = Project(
        organization_id=organization.id,
        created_by=owner.id,
        name=name,
        status="active",
    )
    db.add(project)
    await db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=owner.id, role="owner"))
    return project


@pytest_asyncio.fixture
async def project(db_session: AsyncSession, users: dict[str, User]) -> Project:
    record = await _build_project(
        db_session, name="Dataset program", slug="dataset-lab", owner=users[OWNER]
    )
    db_session.add(
        ProjectMember(project_id=record.id, user_id=users[VIEWER].id, role="viewer")
    )
    await db_session.commit()
    await db_session.refresh(record)
    return record


@pytest_asyncio.fixture
async def other_project(db_session: AsyncSession, users: dict[str, User]) -> Project:
    """另一个项目（调用者不是成员），用于跨项目 404 用例。"""
    record = await _build_project(
        db_session, name="Other program", slug="other-lab", owner=users[OWNER]
    )
    await db_session.commit()
    await db_session.refresh(record)
    return record


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


def _headers(user: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {user}"}


async def _create_dataset(
    client: httpx.AsyncClient,
    project_id: str,
    *,
    name: str = "化合物库 2026Q3",
    dataset_type: str = "COMPOUND",
    file_urn: str = "file:11111111-1111-1111-1111-111111111111",
    row_count: int = 1280,
    summary: dict | None = None,
    user: str = OWNER,
) -> dict:
    response = await client.post(
        f"/api/v1/projects/{project_id}/datasets",
        headers=_headers(user),
        json={
            "name": name,
            "datasetType": dataset_type,
            "fileUrn": file_urn,
            "rowCount": row_count,
            "summary": summary if summary is not None else {"total": row_count},
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


# ---------------------------------------------------------------------------
# 1) 列表分页
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_datasets_paginates(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    """3 条数据、page_size=2 → 首页 2 条且 total=3，第二页 1 条。"""

    for index in range(3):
        await _create_dataset(
            api_client, project.id, name=f"数据集 {index}", file_urn=f"file:u-{index}"
        )

    first = await api_client.get(
        f"/api/v1/projects/{project.id}/datasets?page=1&page_size=2",
        headers=_headers(OWNER),
    )
    assert first.status_code == 200, first.text
    payload = first.json()["data"]
    assert payload["total"] == 3
    assert payload["page"] == 1
    assert payload["page_size"] == 2
    assert len(payload["items"]) == 2

    second = await api_client.get(
        f"/api/v1/projects/{project.id}/datasets?page=2&page_size=2",
        headers=_headers(OWNER),
    )
    assert len(second.json()["data"]["items"]) == 1


# ---------------------------------------------------------------------------
# 2) 类型筛选
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_datasets_filters_by_type(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    """dataset_type=PROTEIN 只返回蛋白数据集。"""

    await _create_dataset(
        api_client, project.id, name="化合物", dataset_type="COMPOUND", file_urn="file:c1"
    )
    await _create_dataset(
        api_client, project.id, name="蛋白", dataset_type="PROTEIN", file_urn="file:p1"
    )

    response = await api_client.get(
        f"/api/v1/projects/{project.id}/datasets?dataset_type=PROTEIN",
        headers=_headers(OWNER),
    )
    assert response.status_code == 200, response.text
    items = response.json()["data"]["items"]
    assert [item["datasetType"] for item in items] == ["PROTEIN"]


# ---------------------------------------------------------------------------
# 3) 跨项目 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_project_dataset_is_404(
    api_client: httpx.AsyncClient, other_project: Project
) -> None:
    """非成员访问其他项目的数据集列表 → 404「研究项目不存在」。"""

    response = await api_client.get(
        f"/api/v1/projects/{other_project.id}/datasets", headers=_headers(VIEWER)
    )
    assert response.status_code == 404, response.text
    assert "研究项目不存在" in response.json()["detail"] or (
        "研究项目不存在" in response.json()["message"]
    )


# ---------------------------------------------------------------------------
# 4) viewer 只读
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_viewer_cannot_create_dataset(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    """viewer 可读不可写：POST → 403。"""

    response = await api_client.post(
        f"/api/v1/projects/{project.id}/datasets",
        headers=_headers(VIEWER),
        json={
            "name": "越权登记",
            "datasetType": "COMPOUND",
            "fileUrn": "file:x",
            "rowCount": 1,
            "summary": {},
        },
    )
    assert response.status_code == 403, response.text


# ---------------------------------------------------------------------------
# 5) 删除后不在列表
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deleted_dataset_disappears_from_list(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    """DELETE 后列表为空，且详情 404。"""

    created = await _create_dataset(api_client, project.id, file_urn="file:doomed")

    deleted = await api_client.delete(
        f"/api/v1/datasets/{created['id']}", headers=_headers(OWNER)
    )
    assert deleted.status_code == 200, deleted.text

    listed = await api_client.get(
        f"/api/v1/projects/{project.id}/datasets", headers=_headers(OWNER)
    )
    assert listed.json()["data"]["items"] == []

    detail = await api_client.get(
        f"/api/v1/datasets/{created['id']}", headers=_headers(OWNER)
    )
    assert detail.status_code == 404


# ---------------------------------------------------------------------------
# 6) summary 原样回读
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summary_round_trips_verbatim(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    """summary 是解析摘要，必须原样回读（含嵌套结构与中文键）。"""

    summary = {
        "total": 1280,
        "invalid": 3,
        "columns": ["smiles", "name"],
        "有效": {"min": 0.1, "max": 9.9},
    }
    created = await _create_dataset(api_client, project.id, summary=summary)

    assert created["summary"] == summary
    detail = await api_client.get(
        f"/api/v1/datasets/{created['id']}", headers=_headers(OWNER)
    )
    assert detail.json()["data"]["summary"] == summary


# ---------------------------------------------------------------------------
# 7) row_count 非负
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_negative_row_count_is_rejected(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    """rowCount=-1 → 422（schema 的 ge=0）。"""

    response = await api_client.post(
        f"/api/v1/projects/{project.id}/datasets",
        headers=_headers(OWNER),
        json={
            "name": "负数行数",
            "datasetType": "COMPOUND",
            "fileUrn": "file:neg",
            "rowCount": -1,
            "summary": {},
        },
    )
    assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# 8) file_urn 前缀校验
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_file_urn_requires_file_scheme(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    """fileUrn 不带 ``file:`` 前缀 → 422（不能反查文件，入口即拒）。"""

    response = await api_client.post(
        f"/api/v1/projects/{project.id}/datasets",
        headers=_headers(OWNER),
        json={
            "name": "裸 urn",
            "datasetType": "COMPOUND",
            "fileUrn": "11111111-1111-1111-1111-111111111111",
            "rowCount": 10,
            "summary": {},
        },
    )
    assert response.status_code == 422, response.text
