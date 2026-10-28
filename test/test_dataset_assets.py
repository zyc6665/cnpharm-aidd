"""数据资产（DataFile 写入路径 + G-13 文档/文献/实验数据）专项 tests。

本文件守两件事：

1. **``DataFile`` 写入路径**：登记数据集时，``file:<file_id>`` 形态的 urn 会被解析成
   ``data_files`` 行，字段（文件名/类型/大小/sha256）取自 ``files`` 行；非 ``file:``
   urn 保持「只登记不落 DataFile」的旧行为。
2. **G-13 非结构资产类型**：``DOCUMENT`` / ``LITERATURE`` / ``EXPERIMENT`` 三种类型都能
   登记（不解析，只登记文件 + 结构化属性）；结构化属性通过 ``attributes`` 传入并并入
   ``Dataset.summary``（``summary`` 显式键优先）。

契约边界（哪些拒绝、哪些放行）：
- ``file:`` urn 指向的文件不存在 → 422（不能落一条指向空洞的 DataFile）；
- 文件存在但属于别的项目 → 422（跨项目引用被拒）；
- 非 ``file:`` urn（如 ``oss://``）→ 仍可登记，``files == []``（旧行为兼容）；
- ``datasetType`` 非法值 → 422（``Literal`` 在请求入口拦下）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import Header, HTTPException
from sqlalchemy import func, select, text
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
from app.models.files import File  # noqa: E402
from app.models.projects import Organization, Project, ProjectMember  # noqa: E402
from app.models.uploads import DataFile, Dataset  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402

OWNER = "owner"
VIEWER = "viewer"


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
    await db_session.commit()
    await db_session.refresh(record)
    return record


@pytest_asyncio.fixture
async def other_project(db_session: AsyncSession, users: dict[str, User]) -> Project:
    record = await _build_project(
        db_session, name="Other asset program", slug="other-asset-lab", owner=users[OWNER]
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


async def _seed_file(
    db: AsyncSession,
    *,
    file_id: str,
    project_id: str,
    filename: str = "asset.sdf",
    content_type: str | None = "chemical/x-sdf",
    size_bytes: int = 1024,
    sha256: str = "0" * 64,
) -> File:
    """直接落一条 ``files`` 行（登记数据集会按 urn 反查它）。"""
    record = File(
        id=file_id,
        project_id=project_id,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        sha256=sha256,
        storage_backend="local",
        storage_path=f"/tmp/{file_id}",
    )
    db.add(record)
    await db.commit()
    return record


async def _post_dataset(
    client: httpx.AsyncClient,
    project_id: str,
    *,
    name: str = "资产数据集",
    dataset_type: str = "COMPOUND",
    file_urn: str = "file:asset-1",
    row_count: int = 10,
    summary: dict | None = None,
    attributes: dict | None = None,
    user: str = OWNER,
) -> httpx.Response:
    body: dict = {
        "name": name,
        "datasetType": dataset_type,
        "fileUrn": file_urn,
        "rowCount": row_count,
        "summary": summary if summary is not None else {},
    }
    if attributes is not None:
        body["attributes"] = attributes
    return await client.post(
        f"/api/v1/projects/{project_id}/datasets",
        headers=_headers(user),
        json=body,
    )


# ---------------------------------------------------------------------------
# 1) file: urn → 落 DataFile，字段来自 File 行
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_file_urn_materializes_data_file_from_file_row(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project
) -> None:
    """file: urn 解析成 data_files 行，文件名/类型/大小/sha256 全部取自 files 行。"""

    await _seed_file(
        db_session,
        file_id="asset-1",
        project_id=project.id,
        filename="library.sdf",
        content_type="chemical/x-sdf",
        size_bytes=2048,
        sha256="a" * 64,
    )

    response = await _post_dataset(
        api_client, project.id, file_urn="file:asset-1", summary={"total": 10}
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]

    assert len(data["files"]) == 1
    materialized = data["files"][0]
    assert materialized["urn"] == "file:asset-1"
    assert materialized["fileName"] == "library.sdf"
    assert materialized["fileType"] == "chemical/x-sdf"
    assert materialized["sizeBytes"] == 2048
    assert materialized["sha256"] == "a" * 64
    assert materialized["storageTier"] == "STANDARD"

    # 真的落进 data_files 表，而不只是序列化里拼出来的。
    rows = (
        await db_session.execute(
            select(DataFile).where(DataFile.dataset_id == data["id"])
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].file_name == "library.sdf"
    assert rows[0].urn == "file:asset-1"


# ---------------------------------------------------------------------------
# 2) 跨项目文件被拒
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_project_file_is_rejected(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    project: Project,
    other_project: Project,
) -> None:
    """urn 指向别的项目的文件 → 422，且不落 dataset / data_files。"""

    project_id = str(project.id)
    await _seed_file(db_session, file_id="foreign-1", project_id=other_project.id)

    response = await _post_dataset(
        api_client, project_id, name="跨项目资产", file_urn="file:foreign-1"
    )
    assert response.status_code == 422, response.text
    payload = response.json()
    message = payload.get("message") or payload.get("detail")
    assert "不属于当前项目" in message

    # 登记整体回滚：不落 dataset，也不落半条 DataFile。
    # 服务层是先 flush 出 dataset.id 再校验文件归属，校验失败时那一行只是「已 flush、
    # 未 commit」；生产 ``get_db`` 会在异常时 rollback 掉它，这里手动 rollout 等价语义
    # （测试 override 用共享会话、不自动回滚，故显式模拟，避免误判为持久化成功）。
    await db_session.rollback()
    dataset_count = await db_session.scalar(select(func.count()).select_from(Dataset))
    assert dataset_count == 0
    datafiles = (
        await db_session.execute(select(DataFile).where(DataFile.urn == "file:foreign-1"))
    ).scalars().all()
    assert datafiles == []


# ---------------------------------------------------------------------------
# 3) file_id 不存在被拒
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_file_is_rejected(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    """file: urn 指向不存在的文件 → 422，消息点明 urn 无效。"""

    response = await _post_dataset(
        api_client, project.id, name="幽灵文件", file_urn="file:does-not-exist"
    )
    assert response.status_code == 422, response.text
    payload = response.json()
    message = payload.get("message") or payload.get("detail")
    assert "不存在文件" in message
    assert "does-not-exist" in message


# ---------------------------------------------------------------------------
# 4) 非 file: urn 保持旧行为
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_file_urn_registers_without_datafiles(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project
) -> None:
    """``oss://`` 形态 urn 仍可登记，不报错，files 恒为 []，且不落 data_files。"""

    response = await _post_dataset(
        api_client,
        project.id,
        name="外部 urn",
        file_urn="oss://bucket/path/to/asset.sdf",
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["fileUrn"] == "oss://bucket/path/to/asset.sdf"
    assert data["files"] == []

    rows = (
        await db_session.execute(
            select(DataFile).where(DataFile.dataset_id == data["id"])
        )
    ).scalars().all()
    assert rows == []


# ---------------------------------------------------------------------------
# 5) DOCUMENT / LITERATURE / EXPERIMENT 三种类型都能登记
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("dataset_type", ["DOCUMENT", "LITERATURE", "EXPERIMENT"])
async def test_non_structured_asset_types_register(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    project: Project,
    dataset_type: str,
) -> None:
    """三种非结构类型都能登记，且 file: urn 同样落 DataFile（不解析内容）。"""

    file_id = f"{dataset_type.lower()}-1"
    await _seed_file(db_session, file_id=file_id, project_id=project.id)

    response = await _post_dataset(
        api_client,
        project.id,
        name=f"{dataset_type} 资产",
        dataset_type=dataset_type,
        file_urn=f"file:{file_id}",
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["datasetType"] == dataset_type
    assert len(data["files"]) == 1


# ---------------------------------------------------------------------------
# 6) dataset_type 非法值被拒
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_dataset_type_is_rejected(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    """datasetType 不在 DATASET_TYPES 里 → 422（Literal 在入口拦下）。"""

    response = await _post_dataset(
        api_client, project.id, name="坏类型", dataset_type="UNICORN"
    )
    assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# 7) 列表按 dataset_type 筛选
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_filters_by_dataset_type(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    """?dataset_type=DOCUMENT 只返回 DOCUMENT 类型的数据集。"""

    await _post_dataset(
        api_client,
        project.id,
        name="化合物",
        dataset_type="COMPOUND",
        file_urn="oss://bucket/compound.sdf",
    )
    await _post_dataset(
        api_client,
        project.id,
        name="文档",
        dataset_type="DOCUMENT",
        file_urn="oss://bucket/doc.pdf",
    )

    response = await api_client.get(
        f"/api/v1/projects/{project.id}/datasets?dataset_type=DOCUMENT",
        headers=_headers(),
    )
    assert response.status_code == 200, response.text
    items = response.json()["data"]["items"]
    assert [item["datasetType"] for item in items] == ["DOCUMENT"]


# ---------------------------------------------------------------------------
# 8) serialize_dataset 的 files 有内容（走详情读取路径）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_serialize_dataset_files_populated_on_detail(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project
) -> None:
    """详情接口经 selectinload 回读并 serialize，files 必须是真实内容而非空数组。"""

    await _seed_file(
        db_session,
        file_id="detail-1",
        project_id=project.id,
        filename="report.pdf",
        content_type="application/pdf",
        size_bytes=4096,
        sha256="b" * 64,
    )
    created = await _post_dataset(
        api_client,
        project.id,
        name="详情文档",
        dataset_type="DOCUMENT",
        file_urn="file:detail-1",
    )
    assert created.status_code == 200, created.text
    dataset_id = created.json()["data"]["id"]

    detail = await api_client.get(
        f"/api/v1/datasets/{dataset_id}", headers=_headers()
    )
    assert detail.status_code == 200, detail.text
    files = detail.json()["data"]["files"]
    assert len(files) == 1
    assert files[0]["fileName"] == "report.pdf"
    assert files[0]["fileType"] == "application/pdf"
    assert files[0]["sizeBytes"] == 4096


# ---------------------------------------------------------------------------
# 9) attributes 并入 summary，且 summary 显式键优先
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attributes_merge_into_summary_summary_wins(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    """attributes 补进 summary；冲突键以 summary 显式值为准（summary 不被打回）。"""

    summary = {"doi": "10.1000/explicit", "total": 5}
    attributes = {
        "doi": "10.1000/from-attributes",
        "authors": ["张三", "李四"],
        "journal": "J. Test",
    }

    response = await _post_dataset(
        api_client,
        project.id,
        name="文献资产",
        dataset_type="LITERATURE",
        file_urn="oss://bucket/paper.pdf",
        summary=summary,
        attributes=attributes,
    )
    assert response.status_code == 200, response.text
    merged = response.json()["data"]["summary"]

    # 冲突键：summary 赢（用户显式给的 doi 不被 attributes 覆盖）。
    assert merged["doi"] == "10.1000/explicit"
    # 非冲突键：attributes 的键值被补进来。
    assert merged["authors"] == ["张三", "李四"]
    assert merged["journal"] == "J. Test"
    # summary 自有的键保持不动。
    assert merged["total"] == 5
