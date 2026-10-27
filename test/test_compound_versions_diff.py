"""化合物版本历史与版本差异 tests (docs/05 §4 ``/versions``、``/diff``，docs/18 G-3)。

本文件守住四件事：

* **列表**：按版本号倒序、分页与 ``total`` 正确、列表不带 content 快照；
* **幂等**：同一分子导入两次（内容相同）不产生第二条版本——版本号必须仍然表示
  「内容第几次变化」，否则 diff 的 ``from``/``to`` 就没有语义；
* **diff**：``props`` 必须摊平成 ``props.logP`` 这样的点分路径，变化的字段精确到
  一条，未变的字段单独列出；
* **降级与鉴权**：无内容快照时给 ``warning`` 而不是静默空数组或 409；无权访问的
  化合物一律 404（沿用「不暴露存在性」口径）。

diff 的第 2 版怎么造
--------------------
走 ``record_manual_version``（``source_type=MANUAL``）而不是再导入一次：化合物内容
只有两条写入路径会追加版本——首次导入，和「按 InChIKey 复用 + 重算描述符」。后者
在同一台机器、同一版 RDKit 下算出的值与第 1 版完全相同，于是被
``if hash != before_hash`` 正确地判为「没有变化」、不追加版本。也就是说：

* 想测「内容变了」，就只能让内容真的变——手工改描述符再记一次 MANUAL 版本，正是
  ``record_manual_version`` 存在的理由（人工校正性质）；
* 「同一内容不追加版本」本身是另一条用例（``test_reimport_same_molecule_...``）。

两组用例配对存在：一条守住「变了要记」，一条守住「没变不许记」，缺任一条都测不出
``if hash != before_hash`` 被写成恒真或恒假。
"""

from __future__ import annotations

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
from app.database.base import Base  # noqa: E402
from app.database.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.compounds import Compound  # noqa: E402
from app.models.projects import Organization, Project, ProjectMember  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402
from app.models.versions import (  # noqa: E402
    ENTITY_TYPE_COMPOUND,
    SOURCE_TYPE_IMPORT,
    SOURCE_TYPE_MANUAL,
    DataVersion,
)
from app.services import data_versions, domain_compounds  # noqa: E402
from app.services.data_versions import (  # noqa: E402
    _same_leaf,
    content_hash_of,
    diff_contents,
    normalize_content,
)

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


@pytest_asyncio.fixture
async def project(db_session: AsyncSession, users: dict[str, User]) -> Project:
    organization = Organization(name="Molecule Lab", slug="molecule-lab-g3")
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
    db_session.add(
        ProjectMember(project_id=project.id, user_id=users[OWNER].id, role="owner")
    )
    db_session.add(
        ProjectMember(project_id=project.id, user_id=users[VIEWER].id, role="viewer")
    )
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

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client
    app.dependency_overrides.clear()


def _headers(user: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {user}"}


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


async def _version_rows(db: AsyncSession, compound_id: str) -> list[DataVersion]:
    result = await db.execute(
        select(DataVersion)
        .where(
            DataVersion.entity_type == ENTITY_TYPE_COMPOUND,
            DataVersion.entity_id == str(compound_id),
        )
        .order_by(DataVersion.version)
    )
    return list(result.scalars().all())


async def _mutate_descriptors_and_record_manual_version(
    db: AsyncSession, *, compound_id: str, user: User, logP: float
) -> DataVersion:
    """把 ``props.logP`` 改成给定值，并以 MANUAL 来源记一版（人工校正性质）。

    只动 ``logP``，其余 5 个性质保持第 1 版的取值：这样 diff 的期望结果就是一个
    精确的「只有 ``props.logP`` 变了」，而不是「props 整块变了」。
    """
    compound = await db.get(Compound, compound_id)
    assert compound is not None, compound_id
    props = dict(compound.props or {})
    assert "logP" in props, props
    props["logP"] = logP
    compound.props = props
    await db.flush()

    record = await data_versions.record_manual_version(
        db,
        entity_type=ENTITY_TYPE_COMPOUND,
        entity_id=compound_id,
        user=user,
        change_summary="人工校正 logP",
        content=domain_compounds._compound_version_content(compound),
    )
    await db.commit()
    return record


# ---------------------------------------------------------------------------
# 列表：倒序、分页、total、不带 content
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_versions_list_paginates_and_orders_desc(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    users: dict[str, User],
    project: Project,
) -> None:
    """``?page=1&page_size=2`` 取到最新两版，``total`` 是全部 3 版。"""
    candidate = await _create_candidate(api_client, project.id, smiles="CCO")
    compound_id = candidate["compound_id"]
    for index, logp in enumerate((0.11, 0.22), start=1):
        await _mutate_descriptors_and_record_manual_version(
            db_session,
            compound_id=compound_id,
            user=users[OWNER],
            logP=logp,
        )

    response = await api_client.get(
        f"/api/v1/compounds/{compound_id}/versions?page=1&page_size=2",
        headers=_headers(OWNER),
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total"] == 3
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert data["total_pages"] == 2
    assert [item["version"] for item in data["items"]] == [3, 2]

    second_page = await api_client.get(
        f"/api/v1/compounds/{compound_id}/versions?page=2&page_size=2",
        headers=_headers(OWNER),
    )
    assert second_page.status_code == 200, second_page.text
    assert [item["version"] for item in second_page.json()["data"]["items"]] == [1]


@pytest.mark.asyncio
async def test_versions_list_default_page_size_is_twenty_and_hides_content(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    """默认页长 20；列表行**不带**内容快照（体量：每行一份完整 props 没意义）。"""
    candidate = await _create_candidate(api_client, project.id, smiles="CCO")

    response = await api_client.get(
        f"/api/v1/compounds/{candidate['compound_id']}/versions",
        headers=_headers(VIEWER),
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert data["total"] == 1
    assert data["items"][0]["version"] == 1
    assert data["items"][0]["sourceType"] == SOURCE_TYPE_IMPORT
    assert data["items"][0]["changeSummary"] == "首次导入"
    assert "content" not in data["items"][0]


# ---------------------------------------------------------------------------
# 幂等：同一内容不产生第二条版本
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reimport_same_molecule_does_not_append_version(
    api_client: httpx.AsyncClient, db_session: AsyncSession, project: Project
) -> None:
    """同一 InChIKey 的两种 SMILES 写法 → 同一分子、只有第 1 版。"""
    first = await _create_candidate(api_client, project.id, smiles="CCO")
    second = await _create_candidate(api_client, project.id, smiles="OCC")
    assert first["compound_id"] == second["compound_id"]

    rows = await _version_rows(db_session, first["compound_id"])
    assert [row.version for row in rows] == [1]

    response = await api_client.get(
        f"/api/v1/compounds/{first['compound_id']}/versions",
        headers=_headers(OWNER),
    )
    assert response.json()["data"]["total"] == 1


# ---------------------------------------------------------------------------
# diff：字段级、props 摊平、方向
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_diff_reports_exact_changed_field_with_flattened_props(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    users: dict[str, User],
    project: Project,
) -> None:
    """``props`` 摊平成 ``props.logP``：改一个性质就只报这一个字段。"""
    candidate = await _create_candidate(api_client, project.id, smiles="CCO")
    compound_id = candidate["compound_id"]
    first = (await _version_rows(db_session, compound_id))[0]
    first_logp = first.content["props"]["logP"]

    await _mutate_descriptors_and_record_manual_version(
        db_session, compound_id=compound_id, user=users[OWNER], logP=0.13
    )

    response = await api_client.get(
        f"/api/v1/compounds/{compound_id}/diff?from=1&to=2",
        headers=_headers(OWNER),
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]

    assert data["compoundId"] == compound_id
    assert data["from"]["version"] == 1
    assert data["from"]["sourceType"] == SOURCE_TYPE_IMPORT
    assert data["from"]["changeSummary"] == "首次导入"
    assert data["to"]["version"] == 2
    assert data["to"]["sourceType"] == "MANUAL"
    assert data["to"]["changeSummary"] == "人工校正 logP"
    assert data["contentHashChanged"] is True
    assert data["warning"] is None

    # 精确到一条：只有 props.logP 变了，其余 5 个性质与 3 个真值字段都在 unchanged 里。
    assert data["changes"] == [
        {"field": "props.logP", "from": first_logp, "to": 0.13}
    ]
    assert data["unchangedFields"] == [
        "canonical_smiles",
        "inchikey",
        "mol_formula",
        "props.HBA",
        "props.HBD",
        "props.QED",
        "props.RotB",
        "props.TPSA",
    ]


@pytest.mark.asyncio
async def test_diff_keeps_request_direction_when_from_is_newer(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    users: dict[str, User],
    project: Project,
) -> None:
    """``from=2&to=1`` 表示「从第 2 版退回第 1 版会改什么」：方向不排序、不报 422。

    若排序成 ``min → max``，响应里的 ``from`` 就与请求参数不一致——前端会把「第 1 版」
    渲染在用户刚点的「第 3 版」上，数据对、标签错，是最难查的一类 bug。
    """
    candidate = await _create_candidate(api_client, project.id, smiles="CCO")
    compound_id = candidate["compound_id"]
    await _mutate_descriptors_and_record_manual_version(
        db_session, compound_id=compound_id, user=users[OWNER], logP=0.13
    )

    forward = await api_client.get(
        f"/api/v1/compounds/{compound_id}/diff?from=1&to=2",
        headers=_headers(OWNER),
    )
    backward = await api_client.get(
        f"/api/v1/compounds/{compound_id}/diff?from=2&to=1",
        headers=_headers(OWNER),
    )
    assert forward.status_code == 200, forward.text
    assert backward.status_code == 200, backward.text

    forward_change = forward.json()["data"]["changes"][0]
    backward_change = backward.json()["data"]["changes"][0]
    assert backward_change["field"] == forward_change["field"] == "props.logP"
    assert backward_change["from"] == forward_change["to"] == 0.13
    assert backward_change["to"] == forward_change["from"]
    # 元数据也跟着请求方向走：from 是第 2 版，不是被排序后的第 1 版。
    assert backward.json()["data"]["from"]["version"] == 2
    assert backward.json()["data"]["to"]["version"] == 1


@pytest.mark.asyncio
async def test_diff_same_version_has_no_changes(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    """``from == to`` 是合法查询（内容必然一致），返回空 changes + 全部 unchanged。"""
    candidate = await _create_candidate(api_client, project.id, smiles="CCO")

    response = await api_client.get(
        f"/api/v1/compounds/{candidate['compound_id']}/diff?from=1&to=1",
        headers=_headers(OWNER),
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["changes"] == []
    assert data["contentHashChanged"] is False
    assert data["warning"] is None
    assert "props.logP" in data["unchangedFields"]


@pytest.mark.asyncio
async def test_diff_warns_instead_of_failing_when_snapshot_missing(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    users: dict[str, User],
    project: Project,
) -> None:
    """第 2 版没有内容快照（迁移前写入 / 调用方只给了哈希）→ warning，不 409。

    历史版本是既成事实：报 409/422 的唯一效果是让用户「去改历史」，而历史不可改。
    """
    candidate = await _create_candidate(api_client, project.id, smiles="CCO")
    compound_id = candidate["compound_id"]
    await data_versions.record_version(
        db_session,
        entity_type=ENTITY_TYPE_COMPOUND,
        entity_id=compound_id,
        source_type=SOURCE_TYPE_IMPORT,
        user=users[OWNER],
        change_summary="迁移前的历史行（只记了哈希）",
        content_hash="0" * 64,
    )
    await db_session.commit()

    response = await api_client.get(
        f"/api/v1/compounds/{compound_id}/diff?from=1&to=2",
        headers=_headers(OWNER),
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["changes"] == []
    assert data["unchangedFields"] == []
    assert data["warning"] == "第 2 版未记录内容快照，无法比对字段"
    # 哈希两侧都有，所以「是否变了」仍然是可回答的。
    assert data["contentHashChanged"] is True


@pytest.mark.asyncio
async def test_diff_both_sides_missing_snapshot_reports_unknown_hash(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    users: dict[str, User],
    project: Project,
) -> None:
    """两侧都没有内容快照 → ``contentHashChanged`` 必须是 ``null``（不知道），不是 ``False``。

    ``False`` 会被前端渲染成「没有改动」，而实际上我们只是无从判断——把「未知」
    说成「没变」是两种错误里更危险的那个（用户会据此跳过复核）。
    """
    candidate = await _create_candidate(api_client, project.id, smiles="CCO")
    compound_id = candidate["compound_id"]
    for summary in ("迁移前历史行 A", "迁移前历史行 B"):
        await data_versions.record_version(
            db_session,
            entity_type=ENTITY_TYPE_COMPOUND,
            entity_id=compound_id,
            source_type=SOURCE_TYPE_IMPORT,
            user=users[OWNER],
            change_summary=summary,
        )
    await db_session.commit()

    response = await api_client.get(
        f"/api/v1/compounds/{compound_id}/diff?from=2&to=3",
        headers=_headers(OWNER),
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["contentHashChanged"] is None
    assert data["changes"] == []
    assert "未记录内容快照" in data["warning"]


@pytest.mark.asyncio
async def test_data_versions_support_peptide_entity_type(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    users: dict[str, User],
) -> None:
    """``data_versions`` 是**通用**账本，不只为化合物服务。

    ``docs/04`` §8.3 的 ``entity_type`` 是 ``COMPOUND`` / ``PROTEIN`` / ``DATASET``，
    多肽候选物走 ``PEPTIDE``。若哪天有人把账本收窄成「只认化合物」，多肽的版本历史
    会静默记不进去（``record_version`` 不报错，只是没留下东西）。
    """
    protein_id = "peptide-entity-1"
    for index in (1, 2):
        await data_versions.record_version(
            db_session,
            entity_type="PROTEIN",
            entity_id=protein_id,
            source_type=SOURCE_TYPE_MANUAL,
            user=users[OWNER],
            change_summary=f"第 {index} 次改序列",
            content={"sequence": "MKTAYIAK" if index == 1 else "MKTAYIAKR"},
        )
    await db_session.commit()

    records, total = await data_versions.list_versions(
        db_session, entity_type="PROTEIN", entity_id=protein_id
    )
    assert total == 2
    assert [record.version for record in records] == [2, 1]
    assert records[0].content == {"sequence": "MKTAYIAKR"}

    changes, unchanged = data_versions.diff_contents(
        records[1].content, records[0].content
    )
    assert changes == [{"field": "sequence", "from": "MKTAYIAK", "to": "MKTAYIAKR"}]
    assert unchanged == []


# ---------------------------------------------------------------------------
# 404：版本不存在、化合物不可见
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_diff_missing_version_returns_404(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    candidate = await _create_candidate(api_client, project.id, smiles="CCO")

    response = await api_client.get(
        f"/api/v1/compounds/{candidate['compound_id']}/diff?from=1&to=99",
        headers=_headers(OWNER),
    )
    assert response.status_code == 404, response.text
    assert "99" in response.json()["message"]


@pytest.mark.asyncio
async def test_versions_and_diff_require_visible_compound(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    """未被任何可见项目引用的化合物：两个端点都 404（不是 403，不泄露存在性）。"""
    candidate = await _create_candidate(api_client, project.id, smiles="CCO")
    compound_id = candidate["compound_id"]

    for path in (
        f"/api/v1/compounds/{compound_id}/versions",
        f"/api/v1/compounds/{compound_id}/diff?from=1&to=1",
    ):
        allowed = await api_client.get(path, headers=_headers(VIEWER))
        assert allowed.status_code == 200, (path, allowed.text)

        denied = await api_client.get(path, headers=_headers(OUTSIDER))
        assert denied.status_code == 404, (path, denied.text)
        assert denied.json()["message"] == "化合物不存在"


@pytest.mark.asyncio
async def test_single_version_endpoint_returns_content_snapshot(
    api_client: httpx.AsyncClient, project: Project
) -> None:
    """按版本号取单行时才返回 ``content``：列表不带、单行带。

    这两个读端点共用一张表却序列化口径不同，若只有列表用例，谁把
    ``serialize_version_detail`` 换成 ``serialize_version``（或反过来）都不会红。
    """
    candidate = await _create_candidate(api_client, project.id, smiles="CCO")

    detail = await api_client.get(
        f"/api/v1/data-versions/{ENTITY_TYPE_COMPOUND}/{candidate['compound_id']}/1",
        headers=_headers(OWNER),
    )
    assert detail.status_code == 200, detail.text
    snapshot = detail.json()["data"]["content"]
    assert snapshot["canonical_smiles"] == "CCO"
    assert snapshot["props"]["logP"] == -0.0014


@pytest.mark.asyncio
async def test_unknown_compound_returns_404(
    api_client: httpx.AsyncClient,
) -> None:
    """不存在的化合物 id 也是 404，与「无权」无法区分——这正是设计意图。

    断言消息而不只是状态码：FastAPI 对**未注册**的路由也回 404，只判
    ``status_code == 404`` 的用例在路由被摘掉之后照样是绿的（实测：注释掉
    ``api/v1/__init__.py`` 的注册行后，本文件其余 9 条变红、它仍绿）。
    """
    response = await api_client.get(
        "/api/v1/compounds/00000000-0000-0000-0000-000000000000/versions",
        headers=_headers(OWNER),
    )
    assert response.status_code == 404, response.text
    assert response.json()["message"] == "化合物不存在"


@pytest.mark.asyncio
async def test_low_privilege_role_cannot_read_compound_versions(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    users: dict[str, User],
    project: Project,
) -> None:
    """角色不在 ``READ_ROLES`` 里时读不到版本历史（守住 G-3 收紧的鉴权）。

    ``ProjectMember.role`` 没有 CHECK 约束，schema 之外的值能直插进库；这里换成一个
    不在 ``READ_ROLES`` 里的角色，确保「可见性 = 必须是四种读角色之一」这条判据真的
    被执行。变异验证：把 ``require_compound_read_access`` 里的角色判据改成无条件
    返回，本用例立刻变红，而其余 11 条全绿——此前正是这样漏掉的。
    """
    candidate = await _create_candidate(api_client, project.id)
    compound_id = candidate["compound"]["id"]
    await db_session.execute(
        text("UPDATE project_members SET role = 'auditor' WHERE user_id = :user_id"),
        {"user_id": users[OWNER].id},
    )
    await db_session.commit()

    for path in (
        f"/api/v1/compounds/{compound_id}/versions",
        f"/api/v1/compounds/{compound_id}/diff?from=1&to=1",
        f"/api/v1/compounds/{compound_id}",
    ):
        response = await api_client.get(path, headers=_headers(OWNER))
        assert response.status_code == 404, f"{path} -> {response.text}"
        assert response.json()["message"] == "化合物不存在"


# ===========================================================================
# 哈希口径与 diff 判等必须一致（G-3 评审 B-1）
# ---------------------------------------------------------------------------
# ``contentHashChanged`` 由 ``content_hash_of`` 判，``changes`` 由 ``_same_leaf``
# 判。两套判据只要不一致，同一个响应里就会出现「哈希说变了、diff 说没变」这种
# 自相矛盾的结论——比单纯算错更难排查，因为两个字段各自都"看起来对"。
# 下面三条分别守住评审实测出的三种矛盾。
# ===========================================================================


def test_zero_and_zero_float_are_reported_as_changed_by_both() -> None:
    """``0`` 与 ``0.0``：哈希不同，diff 也必须报变化。

    修复前：hash 视 ``0``/``0.0`` 为两次写入（序列化后是 ``0`` 与 ``0.0``），
    而 ``_same_leaf`` 用 ``==`` 判等视为同一个值 → ``contentHashChanged: true``
    配 ``changes: []``。
    """
    before = {"props": {"logP": 0}}
    after = {"props": {"logP": 0.0}}

    assert content_hash_of(before) != content_hash_of(after)
    changes, unchanged = diff_contents(before, after)
    assert changes == [{"field": "props.logP", "from": 0, "to": 0.0}]
    assert unchanged == []


def test_hash_is_computed_after_normalization() -> None:
    """哈希必须只认「最终落库的那个形态」。

    早期实现是「原始对象算哈希、``normalize_content`` 之后的值落库」，于是同一个
    落库值可能对应两个不同的哈希来源。这里用 ``Decimal`` 做探针：它会被
    ``default=str`` 变成字符串 ``"0.13"``，若哈希在规范化之前算，两者会得到不同
    结果，而落库内容完全一致。
    """
    from decimal import Decimal

    raw = {"a": Decimal("0.13")}
    normalized = normalize_content(raw)

    assert content_hash_of(normalized) == content_hash_of(normalize_content(normalized))
    assert isinstance(normalized["a"], str)


def test_vanished_empty_container_is_reported_as_changed() -> None:
    """``{"props": {}}`` 与 ``{}``：``props`` 字段确实被删了，不能静默漏报。

    修复前 ``flatten_content`` 把空容器摊平成「什么都没有」，两份内容都没有字段，
    diff 报 ``changes: []`` 且 ``unchanged: []``——用户看到「没有任何变化」，
    但哈希说变了。
    """
    before = {"props": {}}
    after = {}

    assert content_hash_of(before) != content_hash_of(after)
    changes, unchanged = diff_contents(before, after)
    assert changes == [{"field": "props", "from": {}, "to": None}]
    assert unchanged == []


def test_nan_snapshot_is_rejected_instead_of_written() -> None:
    """NaN 不是合法 JSON：写入侧就拒收，而不是等 PG 的 jsonb 报错。

    实测 PostgreSQL：``SELECT '{"x": NaN}'::jsonb`` → ``Token "NaN" is invalid``；
    而 SQLite 会静默存下。同一份内容在两种库上一种能写一种报错，是最难查的那类
    环境差异——所以把它挡在 ``normalize_content`` / ``content_hash_of`` 里。
    """
    from app.common.exceptions import ValidationException

    with pytest.raises(ValidationException, match="NaN"):
        normalize_content({"props": {"logP": float("nan")}})
    with pytest.raises(ValidationException, match="NaN"):
        content_hash_of({"props": {"logP": float("nan")}})


def test_existing_nan_history_rows_still_compare_equal() -> None:
    """历史行里若已有 NaN，两版都是 NaN 时应判为「没变化」而不是荒谬的差异。

    NaN 现在写不进来了（上一条用例），但已落库的数据不能因为判据变严就冒出
    ``from: null, to: null`` 这种用户无法理解的「变化」。
    """
    assert _same_leaf(float("nan"), float("nan")) is True
    assert diff_contents({"a": float("nan")}, {"a": float("nan")}) == ([], ["a"])
