"""数据版本表 tests (docs/04 §8.3, docs/18 G-11).

D-11 要守住的是「历史与当前态分开」这条分工，而不是「能写进一张表」：

* 版本号从 1 起、按实体单调递增，**同一实体的第二次写入必须是 2 而不是 1**；
* 幂等：同一份内容重复导入不该追加版本（否则「第几版」很快不再表示任何语义）；
* 并发：``next_version`` 先查后插在并发下必然漏判，唯一约束才是真值来源，
  冲突后要能自动重排一次而不是把 500 抛给用户；
* 只追加：服务层没有 update / delete，历史只能靠新增版本订正；
* 鉴权沿用各实体既有口径，跨项目不可见一律 404（不把存在性当 403 泄露）。

本文件同时覆盖服务层（版本号、哈希、重试、序列化）与三个写入路径的接线
（``upsert_compound`` / ``create_protein`` / ``register_dataset``）。
"""

from __future__ import annotations

import hashlib
import sys
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
from app.common.exceptions import ValidationException  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.projects import Organization, Project, ProjectMember  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402
from app.models.versions import (  # noqa: E402
    ENTITY_TYPE_COMPOUND,
    ENTITY_TYPE_DATASET,
    ENTITY_TYPE_PROTEIN,
    SOURCE_TYPE_IMPORT,
    SOURCE_TYPE_MANUAL,
    DataVersion,
)
from app.services import data_versions  # noqa: E402

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
        db_session, name="Version program", slug="version-lab", owner=users[OWNER]
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
        db_session, name="Other program", slug="other-version-lab", owner=users[OWNER]
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


# ---------------------------------------------------------------------------
# 三个写入路径的辅助：让每个实体都真的经过 HTTP，避免测试直接构造版本行
# 「绕过被测接线」
# ---------------------------------------------------------------------------


async def _create_candidate(
    client: httpx.AsyncClient, project_id: str, *, smiles: str = "CCO", **overrides
) -> dict:
    payload = {"smiles": smiles, "name": "ethanol"}
    payload.update(overrides)
    response = await client.post(
        f"/api/v1/projects/{project_id}/candidates",
        headers=_headers(OWNER),
        json=payload,
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


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


async def _create_target(client: httpx.AsyncClient, project_id: str) -> dict:
    response = await client.post(
        f"/api/v1/projects/{project_id}/targets",
        headers=_headers(OWNER),
        json={
            "name": "EGFR kinase domain",
            "uniprot_id": "P00533",
            "gene_name": "EGFR",
            "description": "L858R mutant construct",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _create_protein(
    client: httpx.AsyncClient, target_id: str, *, source: str = "MANUAL", **overrides
) -> dict:
    payload = {"name": "EGFR L858R", "sequence": "MEEP QSDV RKC", "source": source}
    payload.update(overrides)
    response = await client.post(
        f"/api/v1/targets/{target_id}/proteins", headers=_headers(OWNER), json=payload
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _version_rows(db: AsyncSession, entity_type: str, entity_id: str) -> list[DataVersion]:
    result = await db.execute(
        select(DataVersion)
        .where(
            DataVersion.entity_type == entity_type,
            DataVersion.entity_id == str(entity_id),
        )
        .order_by(DataVersion.version)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# 1) 服务层：版本号、哈希、重试、序列化
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_version_numbers_from_one_and_increments(
    db_session: AsyncSession, users: dict[str, User]
) -> None:
    """首个版本是 1（``MAX(version)`` 为 NULL 时不能变成 0），之后 2、3。"""
    versions = []
    for index in range(3):
        record = await data_versions.record_version(
            db_session,
            entity_type=ENTITY_TYPE_COMPOUND,
            entity_id="compound-1",
            source_type=SOURCE_TYPE_IMPORT,
            user=users[OWNER],
            change_summary=f"第 {index} 次写入",
            content={"index": index},
        )
        versions.append(record.version)
    await db_session.commit()

    assert versions == [1, 2, 3]
    rows = await _version_rows(db_session, ENTITY_TYPE_COMPOUND, "compound-1")
    assert [row.version for row in rows] == [1, 2, 3]


@pytest.mark.asyncio
async def test_record_version_rejects_unknown_entity_type(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(ValidationException) as excinfo:
        await data_versions.record_version(
            db_session,
            entity_type="SPACESHIP",
            entity_id="x",
            source_type=SOURCE_TYPE_MANUAL,
        )
    assert "不支持的实体类型" in str(excinfo.value)


@pytest.mark.asyncio
async def test_record_version_rejects_unknown_source_type(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(ValidationException) as excinfo:
        await data_versions.record_version(
            db_session,
            entity_type=ENTITY_TYPE_DATASET,
            entity_id="x",
            source_type="TELEPATHY",
        )
    assert "不支持的版本来源" in str(excinfo.value)


@pytest.mark.asyncio
async def test_record_version_without_content_leaves_hash_empty(
    db_session: AsyncSession,
) -> None:
    """没给内容就不编一个「空内容哈希」，``content_hash`` 留 NULL。"""
    record = await data_versions.record_version(
        db_session,
        entity_type=ENTITY_TYPE_PROTEIN,
        entity_id="protein-1",
        source_type=SOURCE_TYPE_MANUAL,
    )
    await db_session.commit()
    assert record.content_hash is None


@pytest.mark.asyncio
async def test_record_version_snapshots_operator_email(
    db_session: AsyncSession, users: dict[str, User]
) -> None:
    """``operator`` 存 email 快照（users 表没有 username 列），不是外键。"""
    record = await data_versions.record_version(
        db_session,
        entity_type=ENTITY_TYPE_PROTEIN,
        entity_id="protein-2",
        source_type=SOURCE_TYPE_MANUAL,
        user=users[OWNER],
        content={"sequence": "MEEP"},
    )
    await db_session.commit()
    assert record.operator == "owner@example.com"


def test_content_hash_of_is_stable_across_key_order() -> None:
    """键序不同、语义相同的两份内容必须得到同一个哈希。"""
    first = data_versions.content_hash_of({"a": 1, "b": [2, 3]})
    second = data_versions.content_hash_of({"b": [2, 3], "a": 1})
    assert first == second
    assert len(first) == 64


def test_content_hash_of_hashes_strings_as_utf8() -> None:
    """字符串走 utf-8 原始字节，和 ``hashlib.sha256`` 的口径一致。"""
    assert data_versions.content_hash_of("蛋白") == hashlib.sha256(
        "蛋白".encode("utf-8")
    ).hexdigest()


@pytest.mark.asyncio
async def test_record_version_retries_once_after_unique_conflict(
    db_session: AsyncSession, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    """并发下两个写入者算出同一个 N：唯一约束拦下第一个，重算后重试成功。

    这里把 ``next_version`` 第一次调用钉死成 1（而 1 号版本已存在），模拟并发
    抢占；第二次调用落回真实实现。断言最终拿到 2，且表里只有两行。
    """
    await data_versions.record_version(
        db_session,
        entity_type=ENTITY_TYPE_COMPOUND,
        entity_id="compound-race",
        source_type=SOURCE_TYPE_IMPORT,
        user=users[OWNER],
        content={"v": 1},
    )
    await db_session.commit()

    original = data_versions.next_version
    calls = {"count": 0}

    async def collide_first(db: AsyncSession, *, entity_type: str, entity_id: str) -> int:
        calls["count"] += 1
        if calls["count"] == 1:
            return 1  # 已被占用
        return await original(db, entity_type=entity_type, entity_id=entity_id)

    monkeypatch.setattr(data_versions, "next_version", collide_first)

    record = await data_versions.record_version(
        db_session,
        entity_type=ENTITY_TYPE_COMPOUND,
        entity_id="compound-race",
        source_type=SOURCE_TYPE_IMPORT,
        user=users[OWNER],
        change_summary="并发抢占后的重试",
        content={"v": 2},
    )
    await db_session.commit()

    assert calls["count"] == 2
    assert record.version == 2
    rows = await _version_rows(db_session, ENTITY_TYPE_COMPOUND, "compound-race")
    assert [row.version for row in rows] == [1, 2]


@pytest.mark.asyncio
async def test_record_manual_version_uses_manual_source(
    db_session: AsyncSession, users: dict[str, User]
) -> None:
    record = await data_versions.record_manual_version(
        db_session,
        entity_type=ENTITY_TYPE_PROTEIN,
        entity_id="protein-3",
        user=users[OWNER],
        change_summary="手工修正第 42 位残基",
        content={"sequence": "MEEP"},
    )
    await db_session.commit()
    assert record.source_type == SOURCE_TYPE_MANUAL


@pytest.mark.asyncio
async def test_list_versions_returns_newest_first_with_total(
    db_session: AsyncSession, users: dict[str, User]
) -> None:
    for index in range(3):
        await data_versions.record_version(
            db_session,
            entity_type=ENTITY_TYPE_DATASET,
            entity_id="dataset-1",
            source_type=SOURCE_TYPE_IMPORT,
            user=users[OWNER],
            content={"n": index},
        )
    await db_session.commit()

    records, total = await data_versions.list_versions(
        db_session, entity_type=ENTITY_TYPE_DATASET, entity_id="dataset-1", page=1, page_size=2
    )
    assert total == 3
    assert [item.version for item in records] == [3, 2]


@pytest.mark.asyncio
async def test_list_versions_rejects_unknown_entity_type(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(ValidationException):
        await data_versions.list_versions(
            db_session, entity_type="NOT_A_TYPE", entity_id="x"
        )


@pytest.mark.asyncio
async def test_serialize_version_uses_camel_case_and_utc_suffix(
    db_session: AsyncSession, users: dict[str, User]
) -> None:
    record = await data_versions.record_version(
        db_session,
        entity_type=ENTITY_TYPE_COMPOUND,
        entity_id="compound-9",
        source_type=SOURCE_TYPE_IMPORT,
        user=users[OWNER],
        source_file_urn="file:abc",
        change_summary="首次导入",
        content={"inchikey": "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"},
    )
    await db_session.commit()

    payload = data_versions.serialize_version(record)
    assert payload["entityType"] == ENTITY_TYPE_COMPOUND
    assert payload["sourceType"] == SOURCE_TYPE_IMPORT
    assert payload["sourceFileUrn"] == "file:abc"
    assert payload["contentHash"] == record.content_hash
    assert payload["operator"] == "owner@example.com"
    # 裸 isoformat 会让东八区前端把 UTC 当成本地时间，必须带 Z。
    assert payload["createdAt"].endswith("Z")


# ---------------------------------------------------------------------------
# 2) 写入路径接线：化合物 / 蛋白 / 数据集各产生第 1 版
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_candidate_creation_records_compound_first_version(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project
) -> None:
    candidate = await _create_candidate(api_client, project.id, smiles="CCO")
    assert candidate["compound_id"], candidate

    rows = await _version_rows(db_session, ENTITY_TYPE_COMPOUND, candidate["compound_id"])
    assert len(rows) == 1
    assert rows[0].version == 1
    assert rows[0].source_type == SOURCE_TYPE_IMPORT
    assert rows[0].operator == "owner@example.com"
    assert rows[0].content_hash, "首次导入必须留下内容指纹"


@pytest.mark.asyncio
async def test_reusing_same_compound_does_not_duplicate_version(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project
) -> None:
    """同一 InChIKey 第二次进来走复用分支，内容没变就不该产生第 2 版。

    没有这条，「导入两次 → 两条一模一样的版本行」会让版本号失去语义。
    """
    first = await _create_candidate(api_client, project.id, smiles="CCO")
    second = await _create_candidate(api_client, project.id, smiles="OCC")
    assert first["compound_id"] == second["compound_id"]

    rows = await _version_rows(db_session, ENTITY_TYPE_COMPOUND, first["compound_id"])
    assert [row.version for row in rows] == [1]


@pytest.mark.asyncio
async def test_refreshing_stale_compound_appends_next_version(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    users: dict[str, User],
    project: Project,
) -> None:
    """复用分支里内容**真的变了**才追加版本：把 props 弄脏后再刷新应得到第 2 版。

    和上一条配对存在：一条守住「内容没变不追加」，一条守住「内容变了要追加」，
    否则 ``if hash != before_hash`` 这个条件写成恒假也测不出来。
    """
    from app.models.compounds import Compound
    from app.services import domain_compounds

    candidate = await _create_candidate(api_client, project.id, smiles="CCO")
    compound = await db_session.get(Compound, candidate["compound_id"])
    compound.props = {"mangled": True}
    await db_session.commit()

    await domain_compounds.upsert_compound(
        db_session, smiles="CCO", name=None, user=users[OWNER], refresh_descriptors=True
    )
    await db_session.commit()

    rows = await _version_rows(db_session, ENTITY_TYPE_COMPOUND, candidate["compound_id"])
    assert [row.version for row in rows] == [1, 2]
    assert rows[1].change_summary == "按 InChIKey 复用并刷新派生性质"


@pytest.mark.asyncio
async def test_dataset_registration_records_first_version(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project
) -> None:
    dataset = await _create_dataset(api_client, project.id, file_urn="file:dataset-1")

    rows = await _version_rows(db_session, ENTITY_TYPE_DATASET, dataset["id"])
    assert len(rows) == 1
    assert rows[0].version == 1
    assert rows[0].source_file_urn == "file:dataset-1"
    assert rows[0].operator == "owner@example.com"


@pytest.mark.asyncio
async def test_protein_creation_records_manual_version(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project
) -> None:
    target = await _create_target(api_client, project.id)
    protein = await _create_protein(api_client, target["id"], source="MANUAL")

    rows = await _version_rows(db_session, ENTITY_TYPE_PROTEIN, protein["id"])
    assert len(rows) == 1
    assert rows[0].version == 1
    assert rows[0].source_type == SOURCE_TYPE_MANUAL
    assert rows[0].change_summary


@pytest.mark.asyncio
async def test_protein_creation_records_import_version(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project
) -> None:
    """``source=IMPORT`` 的蛋白版本行来源也必须是 IMPORT，不能一律写 MANUAL。"""
    target = await _create_target(api_client, project.id)
    protein = await _create_protein(api_client, target["id"], source="IMPORT")

    rows = await _version_rows(db_session, ENTITY_TYPE_PROTEIN, protein["id"])
    assert rows[0].source_type == SOURCE_TYPE_IMPORT


@pytest.mark.asyncio
async def test_protein_sequence_update_appends_version(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project
) -> None:
    """改序列 → ``current_version`` +1 且多一条版本行，摘要带新版本号。

    这是 ``update_protein`` 原本自相矛盾的地方：它已经在递增 ``current_version``，
    却没有对应记录，导致「第 2 版」在历史里根本不存在。
    """
    target = await _create_target(api_client, project.id)
    protein = await _create_protein(api_client, target["id"])

    response = await api_client.put(
        f"/api/v1/proteins/{protein['id']}",
        headers=_headers(OWNER),
        json={"sequence": "MKTAYIAKQR"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["current_version"] == 2

    rows = await _version_rows(db_session, ENTITY_TYPE_PROTEIN, protein["id"])
    assert [row.version for row in rows] == [1, 2]
    assert rows[1].source_type == SOURCE_TYPE_MANUAL
    assert "第 2 版" in rows[1].change_summary
    assert rows[1].content_hash and rows[1].content_hash != rows[0].content_hash


@pytest.mark.asyncio
async def test_protein_rename_does_not_bump_version(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project
) -> None:
    """只改名字不算新版本 —— 防回归的关键用例。

    ``name`` 不参与结构预测的任何输入；若改名也递增，``current_version`` 表示的
    就不再是「序列被改过几次」而是「保存过几次」。
    """
    target = await _create_target(api_client, project.id)
    protein = await _create_protein(api_client, target["id"])

    response = await api_client.put(
        f"/api/v1/proteins/{protein['id']}",
        headers=_headers(OWNER),
        json={"name": "EGFR L858R (renamed)"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["name"] == "EGFR L858R (renamed)"
    assert response.json()["data"]["current_version"] == 1

    rows = await _version_rows(db_session, ENTITY_TYPE_PROTEIN, protein["id"])
    assert [row.version for row in rows] == [1]


@pytest.mark.asyncio
async def test_saving_identical_sequence_does_not_bump_version(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project
) -> None:
    """原样再保存一次不该跳版本号（用户连点两次保存的场景）。"""
    target = await _create_target(api_client, project.id)
    protein = await _create_protein(api_client, target["id"], sequence="MEEPQSDVRKC")

    response = await api_client.put(
        f"/api/v1/proteins/{protein['id']}",
        headers=_headers(OWNER),
        json={"sequence": "MEEPQSDVRKC"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["current_version"] == 1

    rows = await _version_rows(db_session, ENTITY_TYPE_PROTEIN, protein["id"])
    assert [row.version for row in rows] == [1]


@pytest.mark.asyncio
async def test_updating_sequence_and_name_in_one_request(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project
) -> None:
    """同一次请求既改序列又改名：版本号 +1、版本行只有一条、快照只含序列。

    这条覆盖的是「组合路径」，此前只存在于代码注释的推理里：``update_protein``
    先处理 ``sequence``（含递增与记版）、再改 ``name``、最后统一 ``commit``。
    因此版本行的 ``content`` 快照取到的是 ``name`` 赋值**之前**的状态——而
    ``name`` 本来就不进快照，所以结果正确。

    风险点在于「两条写入各自触发一次记版」：若哪天把 ``record_version`` 挪到
    ``name`` 分支或 commit 之后，同一请求会留下两条版本行或让快照带上 name。
    这条用例把「一次请求 = 一个版本」钉住。
    """
    target = await _create_target(api_client, project.id)
    protein = await _create_protein(api_client, target["id"], sequence="MEEPQSDVRKC")

    response = await api_client.put(
        f"/api/v1/proteins/{protein['id']}",
        headers=_headers(OWNER),
        json={"sequence": "MKTAYIAKQR", "name": "EGFR L858R + renamed"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert payload["current_version"] == 2
    assert payload["name"] == "EGFR L858R + renamed"
    assert payload["seq_length"] == 10

    rows = await _version_rows(db_session, ENTITY_TYPE_PROTEIN, protein["id"])
    # 一次请求只产生一个版本，不能因为改了 name 再多记一条。
    assert [row.version for row in rows] == [1, 2]
    # 快照只认结构输入：name 不进快照，seq_length 是派生量也不计入。
    assert rows[1].content_hash == data_versions.content_hash_of(
        {"target_id": target["id"], "sequence": "MKTAYIAKQR"}
    )
    assert "renamed" not in str(rows[1].change_summary)


@pytest.mark.asyncio
async def test_reverting_sequence_still_counts_as_new_version(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project
) -> None:
    """改走再改回：版本按次递增，不因「与更早的版本相同」被拒。

    判据是「与上一版比」而不是「与历史任意版去重」——后者会让撤销操作在历史里
    变成空白，恰好抹掉最需要追溯的那一步。
    """
    target = await _create_target(api_client, project.id)
    protein = await _create_protein(api_client, target["id"], sequence="MEEPQSDVRKC")

    first = await api_client.put(
        f"/api/v1/proteins/{protein['id']}",
        headers=_headers(OWNER),
        json={"sequence": "MKTAYIAKQR"},
    )
    assert first.json()["data"]["current_version"] == 2

    reverted = await api_client.put(
        f"/api/v1/proteins/{protein['id']}",
        headers=_headers(OWNER),
        json={"sequence": "MEEPQSDVRKC"},
    )
    assert reverted.status_code == 200, reverted.text
    assert reverted.json()["data"]["current_version"] == 3

    rows = await _version_rows(db_session, ENTITY_TYPE_PROTEIN, protein["id"])
    assert [row.version for row in rows] == [1, 2, 3]
    # 第 3 版的内容与第 1 版相同，但仍是独立一条 —— 哈希相同、版本号不同。
    assert rows[2].content_hash == rows[0].content_hash


# ---------------------------------------------------------------------------
# 3) 读接口：实体历史 / 最新版 / 单版本 / 项目一览
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_latest_endpoint_returns_highest_version(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    users: dict[str, User],
    project: Project,
) -> None:
    dataset = await _create_dataset(api_client, project.id, file_urn="file:latest")
    await data_versions.record_manual_version(
        db_session,
        entity_type=ENTITY_TYPE_DATASET,
        entity_id=dataset["id"],
        user=users[OWNER],
        change_summary="重新解析",
        content={"row_count": 1281},
    )
    await db_session.commit()

    response = await api_client.get(
        f"/api/v1/data-versions/{ENTITY_TYPE_DATASET}/{dataset['id']}/latest",
        headers=_headers(VIEWER),
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["version"] == 2


@pytest.mark.asyncio
async def test_entity_history_paginates_and_orders_desc(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    users: dict[str, User],
    project: Project,
) -> None:
    dataset = await _create_dataset(api_client, project.id, file_urn="file:history")
    for index in range(2):
        await data_versions.record_manual_version(
            db_session,
            entity_type=ENTITY_TYPE_DATASET,
            entity_id=dataset["id"],
            user=users[OWNER],
            change_summary=f"第 {index} 次调整",
            content={"n": index},
        )
    await db_session.commit()

    response = await api_client.get(
        f"/api/v1/data-versions/{ENTITY_TYPE_DATASET}/{dataset['id']}?page=1&page_size=2",
        headers=_headers(OWNER),
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total"] == 3
    assert [item["version"] for item in data["items"]] == [3, 2]


@pytest.mark.asyncio
async def test_specific_version_endpoint_and_missing_version_404(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    dataset = await _create_dataset(api_client, project.id, file_urn="file:single")

    found = await api_client.get(
        f"/api/v1/data-versions/{ENTITY_TYPE_DATASET}/{dataset['id']}/1",
        headers=_headers(OWNER),
    )
    assert found.status_code == 200, found.text
    assert found.json()["data"]["version"] == 1

    missing = await api_client.get(
        f"/api/v1/data-versions/{ENTITY_TYPE_DATASET}/{dataset['id']}/99",
        headers=_headers(OWNER),
    )
    assert missing.status_code == 404, missing.text


@pytest.mark.asyncio
async def test_project_feed_lists_all_three_entity_types(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    """项目一览跨实体类型聚合：化合物靠候选物、蛋白靠靶点、数据集靠 project_id。"""
    candidate = await _create_candidate(api_client, project.id, smiles="CCO")
    dataset = await _create_dataset(api_client, project.id, file_urn="file:feed")
    target = await _create_target(api_client, project.id)
    protein = await _create_protein(api_client, target["id"])

    response = await api_client.get(
        f"/api/v1/projects/{project.id}/data-versions?page=1&page_size=50",
        headers=_headers(VIEWER),
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    entity_ids = {item["entityId"] for item in data["items"]}
    assert {
        candidate["compound_id"],
        dataset["id"],
        protein["id"],
    } <= entity_ids
    assert data["total"] >= 3


@pytest.mark.asyncio
async def test_project_feed_filters_by_entity_type(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    await _create_candidate(api_client, project.id, smiles="CCO")
    await _create_dataset(api_client, project.id, file_urn="file:filter")

    response = await api_client.get(
        f"/api/v1/projects/{project.id}/data-versions?entity_type={ENTITY_TYPE_DATASET}",
        headers=_headers(OWNER),
    )
    assert response.status_code == 200, response.text
    items = response.json()["data"]["items"]
    assert items, "至少应有刚登记的数据集版本"
    assert {item["entityType"] for item in items} == {ENTITY_TYPE_DATASET}


@pytest.mark.asyncio
async def test_outsider_cannot_read_entity_history(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    """跨项目不可见返回 404，不把「这条历史存在」当 403 泄露。"""
    dataset = await _create_dataset(api_client, project.id, file_urn="file:private")

    response = await api_client.get(
        f"/api/v1/data-versions/{ENTITY_TYPE_DATASET}/{dataset['id']}",
        headers=_headers(OUTSIDER),
    )
    assert response.status_code == 404, response.text


@pytest.mark.asyncio
async def test_outsider_cannot_read_project_feed(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    response = await api_client.get(
        f"/api/v1/projects/{project.id}/data-versions", headers=_headers(OUTSIDER)
    )
    assert response.status_code == 404, response.text


@pytest.mark.asyncio
async def test_reading_other_project_dataset_version_is_404(
    api_client: httpx.AsyncClient, other_project: Project
) -> None:
    dataset = await _create_dataset(api_client, other_project.id, file_urn="file:other")

    response = await api_client.get(
        f"/api/v1/data-versions/{ENTITY_TYPE_DATASET}/{dataset['id']}",
        headers=_headers(VIEWER),
    )
    assert response.status_code == 404, response.text


@pytest.mark.asyncio
async def test_unknown_entity_type_in_path_returns_404(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.get(
        "/api/v1/data-versions/SPACESHIP/whatever", headers=_headers(OWNER)
    )
    assert response.status_code == 404, response.text


@pytest.mark.asyncio
async def test_deleted_dataset_history_is_not_reachable(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project
) -> None:
    """删除数据集后其版本历史仍是 404 —— 现有取��，不是遗漏。

    追加式账本不删历史行（下面断言仍在库里），但读接口走 ``load_dataset`` 会先
    404。放开就得允许「已删除实体的历史可查」，那是产品口径问题（见
    ``backend/app/api/v1/data_versions.py`` 里 ``_require_entity_read_access``
    的注释）。此用例把这个现状钉住：口径一旦改变，这里会红，提醒同步改注释。
    """
    dataset = await _create_dataset(api_client, project.id, file_urn="file:to-delete")

    deleted = await api_client.delete(
        f"/api/v1/datasets/{dataset['id']}", headers=_headers(OWNER)
    )
    assert deleted.status_code == 200, deleted.text

    # 历史行没有被连带删除。
    rows = await _version_rows(db_session, ENTITY_TYPE_DATASET, dataset["id"])
    assert [row.version for row in rows] == [1]

    response = await api_client.get(
        f"/api/v1/data-versions/{ENTITY_TYPE_DATASET}/{dataset['id']}",
        headers=_headers(OWNER),
    )
    assert response.status_code == 404, response.text
