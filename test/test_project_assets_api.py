"""``GET /projects/{id}/assets?type=`` 统一资产检索 tests（Task 5 §7.3）。

覆盖：
- ``?type=`` 过滤（只回该类型，且 artifact 来源）；
- 分页边界（page_size 上限 100、page>=1、第二页、total 为过滤后真实总数）；
- 非项目成员 404 / 项目成员放行；
- 非法 ``type`` → 422；
- ``type=dataset`` 合并 ``datasets`` 领域表与 ``artifact_type='dataset'`` 的 Artifact（两源）；
- 不传 ``type`` 时 artifact + dataset 合并混排；
- 不可用（非 available / 已过期）的 artifact 不进列表。
"""

from __future__ import annotations

import sys
from datetime import datetime
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
from app.models.artifacts import Artifact, ArtifactVersion  # noqa: E402
from app.models.projects import Organization, Project, ProjectMember  # noqa: E402
from app.models.uploads import Dataset  # noqa: E402
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
        db_session, name="Asset program", slug="asset-lab", owner=users[OWNER]
    )
    # 额外挂一个 viewer，用来测「成员放行」。
    db_session.add(
        ProjectMember(project_id=record.id, user_id=users[VIEWER].id, role="viewer")
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


def _headers(user: str = OWNER) -> dict[str, str]:
    return {"Authorization": f"Bearer {user}"}


async def _seed_artifact(
    db: AsyncSession,
    *,
    project_id: str,
    owner: User,
    artifact_type: str,
    name: str,
    semantic_type: str | None = None,
    status: str = "available",
    updated_at: datetime | None = None,
) -> Artifact:
    artifact = Artifact(
        project_id=project_id,
        created_by=owner.id,
        artifact_type=artifact_type,
        semantic_type=semantic_type or artifact_type,
        name=name,
    )
    if updated_at is not None:
        artifact.created_at = updated_at
    db.add(artifact)
    await db.flush()
    version = ArtifactVersion(
        artifact_id=artifact.id,
        created_by=owner.id,
        version=1,
        filename=f"{name}.dat",
        content_type="application/octet-stream",
        size_bytes=16,
        sha256="0" * 64,
        storage_key=f"artifacts/{artifact.id}/v1",
        status=status,
    )
    db.add(version)
    await db.flush()
    artifact.latest_version_id = version.id
    if updated_at is not None:
        # 必须在设置 latest_version_id 之后赋值：这次 UPDATE 会触发 TimestampMixin 的
        # onupdate=utcnow，只有把 updated_at 显式放进 SET 才能保住夹具指定时间。
        artifact.updated_at = updated_at
    await db.commit()
    await db.refresh(artifact)
    return artifact


async def _post_dataset(
    client: httpx.AsyncClient,
    project_id: str,
    *,
    name: str = "资产数据集",
    dataset_type: str = "COMPOUND",
    file_urn: str = "oss://bucket/asset.sdf",
) -> httpx.Response:
    return await client.post(
        f"/api/v1/projects/{project_id}/datasets",
        headers=_headers(),
        json={
            "name": name,
            "datasetType": dataset_type,
            "fileUrn": file_urn,
            "rowCount": 10,
            "summary": {},
        },
    )


def _items(response: httpx.Response) -> list[dict]:
    return response.json()["data"]["items"]


async def _seed_dataset_row(
    db: AsyncSession,
    *,
    project_id: str,
    owner: User,
    name: str,
    created_at: datetime,
    dataset_type: str = "COMPOUND",
) -> Dataset:
    """直接落一条 datasets 领域表记录，便于精确控制 created_at 做混排断言。"""
    dataset = Dataset(
        project_id=project_id,
        created_by=owner.id,
        name=name,
        dataset_type=dataset_type,
        file_urn=f"oss://bucket/{name}.sdf",
        row_count=10,
        summary={},
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(dataset)
    await db.commit()
    await db.refresh(dataset)
    return dataset



# ---------------------------------------------------------------------------
# 1) ?type= 过滤
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filter_by_type_returns_only_that_type(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project, users
) -> None:
    await _seed_artifact(
        db_session,
        project_id=project.id,
        owner=users[OWNER],
        artifact_type="protein_structure",
        name="EGFR 结构",
    )
    await _seed_artifact(
        db_session,
        project_id=project.id,
        owner=users[OWNER],
        artifact_type="binding_pocket",
        name="ATP 口袋",
    )

    response = await api_client.get(
        f"/api/v1/projects/{project.id}/assets?type=protein_structure",
        headers=_headers(),
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total"] == 1
    assert data["page"] == 1
    assert data["page_size"] == 20
    items = data["items"]
    assert [item["asset_type"] for item in items] == ["protein_structure"]
    assert items[0]["name"] == "EGFR 结构"
    assert items[0]["source"] == "artifact"


# ---------------------------------------------------------------------------
# 2) 分页边界
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pagination_boundaries(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project, users
) -> None:
    for index in range(3):
        await _seed_artifact(
            db_session,
            project_id=project.id,
            owner=users[OWNER],
            artifact_type="run_report",
            name=f"报告{index}",
        )

    first = await api_client.get(
        f"/api/v1/projects/{project.id}/assets?type=run_report&page=1&page_size=2",
        headers=_headers(),
    )
    assert first.status_code == 200, first.text
    assert first.json()["data"]["total"] == 3
    assert len(_items(first)) == 2

    second = await api_client.get(
        f"/api/v1/projects/{project.id}/assets?type=run_report&page=2&page_size=2",
        headers=_headers(),
    )
    assert second.status_code == 200, second.text
    assert len(_items(second)) == 1

    too_large = await api_client.get(
        f"/api/v1/projects/{project.id}/assets?page_size=101", headers=_headers()
    )
    assert too_large.status_code == 422, too_large.text

    bad_page = await api_client.get(
        f"/api/v1/projects/{project.id}/assets?page=0", headers=_headers()
    )
    assert bad_page.status_code == 422, bad_page.text


# ---------------------------------------------------------------------------
# 3) 权限
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_member_gets_404(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    response = await api_client.get(
        f"/api/v1/projects/{project.id}/assets", headers=_headers(OUTSIDER)
    )
    assert response.status_code == 404, response.text


@pytest.mark.asyncio
async def test_member_is_allowed(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    response = await api_client.get(
        f"/api/v1/projects/{project.id}/assets", headers=_headers(VIEWER)
    )
    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# 4) 非法 type
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_type_is_rejected(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    response = await api_client.get(
        f"/api/v1/projects/{project.id}/assets?type=bogus", headers=_headers()
    )
    assert response.status_code == 422, response.text
    payload = response.json()
    message = payload.get("message") or payload.get("detail")
    assert "不支持的资产类型" in message


# ---------------------------------------------------------------------------
# 5) type=dataset 回落领域表
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dataset_type_reads_domain_table(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    created = await _post_dataset(
        api_client, project.id, name="化合物库", dataset_type="COMPOUND"
    )
    assert created.status_code == 200, created.text

    response = await api_client.get(
        f"/api/v1/projects/{project.id}/assets?type=dataset", headers=_headers()
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total"] == 1
    item = data["items"][0]
    assert item["asset_type"] == "dataset"
    assert item["source"] == "dataset"
    assert item["name"] == "化合物库"
    assert item["metadata"]["datasetType"] == "COMPOUND"


# ---------------------------------------------------------------------------
# 6) 不传 type：artifact + dataset 合并
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_assets_merges_artifacts_and_datasets(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project, users
) -> None:
    await _seed_artifact(
        db_session,
        project_id=project.id,
        owner=users[OWNER],
        artifact_type="molecule_table",
        name="分子表",
    )
    created = await _post_dataset(api_client, project.id, name="化合物库")
    assert created.status_code == 200, created.text

    response = await api_client.get(
        f"/api/v1/projects/{project.id}/assets", headers=_headers()
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total"] == 2
    assert {item["source"] for item in data["items"]} == {"artifact", "dataset"}


# ---------------------------------------------------------------------------
# 7) 不可用 artifact 不进列表
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unavailable_artifact_is_excluded(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project, users
) -> None:
    await _seed_artifact(
        db_session,
        project_id=project.id,
        owner=users[OWNER],
        artifact_type="ligand_structure",
        name="待校验配体",
        status="pending",
    )
    response = await api_client.get(
        f"/api/v1/projects/{project.id}/assets?type=ligand_structure",
        headers=_headers(),
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["total"] == 0


# ---------------------------------------------------------------------------
# 8) type=dataset 必须是「领域表 + artifact_type='dataset' 的 Artifact」两源合并
#    （通用输入上传兜底会写入 artifact_type='dataset'，见 useWorkflowPersistence.ts）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dataset_type_includes_uploaded_artifact_rows(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project, users
) -> None:
    await _seed_artifact(
        db_session,
        project_id=project.id,
        owner=users[OWNER],
        artifact_type="dataset",
        name="用户刚上传的通用文件",
    )

    response = await api_client.get(
        f"/api/v1/projects/{project.id}/assets?type=dataset", headers=_headers()
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total"] == 1
    item = data["items"][0]
    assert item["name"] == "用户刚上传的通用文件"
    assert item["source"] == "artifact"
    assert item["metadata"]["filename"] == "用户刚上传的通用文件.dat"


@pytest.mark.asyncio
async def test_dataset_type_merges_domain_table_and_artifacts(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project, users
) -> None:
    created = await _post_dataset(api_client, project.id, name="登记数据集")
    assert created.status_code == 200, created.text
    await _seed_artifact(
        db_session,
        project_id=project.id,
        owner=users[OWNER],
        artifact_type="dataset",
        name="上传出的数据集产物",
    )

    response = await api_client.get(
        f"/api/v1/projects/{project.id}/assets?type=dataset", headers=_headers()
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total"] == 2
    assert {item["source"] for item in data["items"]} == {"artifact", "dataset"}


@pytest.mark.asyncio
async def test_dataset_type_pagination_interleaves_by_updated_at(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project, users
) -> None:
    # 5 条记录，按更新时间交错：art3 > art2 > dsB > art1 > dsA
    base = datetime(2026, 1, 1, 0, 0, 0)
    art1 = await _seed_artifact(
        db_session,
        project_id=project.id,
        owner=users[OWNER],
        artifact_type="dataset",
        name="art1",
        updated_at=base.replace(hour=2),
    )
    art2 = await _seed_artifact(
        db_session,
        project_id=project.id,
        owner=users[OWNER],
        artifact_type="dataset",
        name="art2",
        updated_at=base.replace(hour=4),
    )
    art3 = await _seed_artifact(
        db_session,
        project_id=project.id,
        owner=users[OWNER],
        artifact_type="dataset",
        name="art3",
        updated_at=base.replace(hour=5),
    )
    ds_a = await _seed_dataset_row(
        db_session,
        project_id=project.id,
        owner=users[OWNER],
        name="dsA",
        created_at=base.replace(hour=1),
    )
    ds_b = await _seed_dataset_row(
        db_session,
        project_id=project.id,
        owner=users[OWNER],
        name="dsB",
        created_at=base.replace(hour=3),
    )

    expected_order = ["art3", "art2", "dsB", "art1", "dsA"]

    seen: list[str] = []
    for page in (1, 2, 3):
        response = await api_client.get(
            f"/api/v1/projects/{project.id}/assets?type=dataset"
            f"&page={page}&page_size=2",
            headers=_headers(),
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["total"] == 5, f"page {page} total 应为两源之和 5"
        seen.extend(item["id"] for item in data["items"])

    id_to_name = {
        str(art3.id): "art3",
        str(art2.id): "art2",
        str(ds_b.id): "dsB",
        str(art1.id): "art1",
        str(ds_a.id): "dsA",
    }
    seen_names = [id_to_name.get(item_id, item_id) for item_id in seen]
    assert seen_names == expected_order, f"翻页顺序/去重不正确：{seen_names}"
    assert len(set(seen)) == len(seen) == 5, "翻页出现重复或遗漏"

