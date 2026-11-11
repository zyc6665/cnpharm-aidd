"""任务结果回写领域表的测试（docs/26 H-16）。

覆盖四件事：
1. ``protein_structure@1`` → ``protein_structures``（含 pLDDT 归一化与重放幂等）
2. ``protein_structure@1``（结构准备）→ ``prepared_urn`` / ``pdbqt_urn``
3. ``binding_pocket@1`` → ``pockets`` + ``pocket_residues``（残基名从 PDB 读、rank 接续、
   重放不重复）
4. 没有领域上下文 / 没有标准产物时什么都不写，且不改任务状态
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.base import Base  # noqa: E402
from app.execution.result_parser import (  # noqa: E402
    ParsedStandardArtifact,
    ParsedStandardFile,
)
from app.files.writer import store_file_bytes  # noqa: E402
from app.models.files import FileSourceType  # noqa: E402
from app.models.projects import Organization, Project, ProjectMember  # noqa: E402
from app.models.targets import (  # noqa: E402
    Pocket,
    PocketResidue,
    Protein,
    ProteinStructure,
    Target,
)
from app.models.users import User, UserRole, UserStatus  # noqa: E402
from app.services.domain_results import (  # noqa: E402
    DOMAIN_WRITEBACK_KEY,
    parse_pdb_residues,
    write_back_domain_results,
)
from app.services.domain_targets import structure_input_file_record  # noqa: E402
from app.services.standard_artifacts import (  # noqa: E402
    StandardArtifactPersistenceResult,
)

STRUCTURE_TYPE = "protein_structure@1"
POCKET_TYPE = "binding_pocket@1"
REPORT_TYPE = "run_report@1"


# ---------------------------------------------------------------------------
# fixtures
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


@pytest_asyncio.fixture
async def owner(db_session: AsyncSession) -> User:
    user = User(
        email="owner@example.com",
        password_hash="hashed-password",
        display_name="owner",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def project(db_session: AsyncSession, owner: User) -> Project:
    organization = Organization(name="Domain Lab", slug="domain-lab")
    db_session.add(organization)
    await db_session.flush()
    project = Project(
        organization_id=organization.id,
        created_by=owner.id,
        name="EGFR program",
        status="active",
    )
    db_session.add(project)
    await db_session.flush()
    db_session.add(ProjectMember(project_id=project.id, user_id=owner.id, role="owner"))
    await db_session.commit()
    await db_session.refresh(project)
    return project


@pytest_asyncio.fixture
async def protein(db_session: AsyncSession, project: Project, owner: User) -> Protein:
    target = Target(project_id=project.id, created_by=owner.id, name="EGFR")
    db_session.add(target)
    await db_session.flush()
    record = Protein(
        target_id=target.id,
        name="EGFR L858R",
        sequence="MEEPSDVRKC",
        seq_length=10,
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)
    return record


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _atom_line(*, serial: int, res_name: str, chain: str, res_seq: int) -> str:
    """按 PDB 固定列位生成一行 ATOM 记录（残基名 17-20、链 21、序号 22-26）。"""
    chars = list(" " * 80)
    chars[0:4] = "ATOM"
    chars[6:11] = f"{serial:>5d}"
    chars[12:16] = f" {res_name:<3s}"[:4]
    chars[17:20] = f"{res_name:<3s}"
    chars[21] = chain
    chars[22:26] = f"{res_seq:>4d}"
    chars[30:38] = f"{10.0:>8.3f}"
    return "".join(chars)


def _pdb(*residues: tuple[int, str, str, int]) -> bytes:
    lines = [
        _atom_line(serial=index + 1, res_name=name, chain=chain, res_seq=seq)
        for index, (chain, seq, name, _) in enumerate(residues)
    ]
    return ("\n".join(lines) + "\nEND\n").encode("utf-8")


def _pdb_with_coordinates(points: list[tuple[float, float, float]]) -> bytes:
    """生成带真实 x/y/z 的 ATOM 行（x=31-38、y=39-46、z=47-54）。"""
    lines = []
    for index, (x, y, z) in enumerate(points):
        chars = list(_atom_line(serial=index + 1, res_name="MET", chain="A", res_seq=index + 1))
        for start, value in zip((30, 38, 46), (x, y, z)):
            chars[start : start + 8] = f"{value:>8.3f}"
        lines.append("".join(chars))
    return ("\n".join(lines) + "\nEND\n").encode("utf-8")


async def _store(
    db: AsyncSession, *, project: Project, owner: User, filename: str, content: bytes
):
    record = await store_file_bytes(
        db,
        content=content,
        filename=filename,
        content_type="chemical/x-pdb",
        source_type=FileSourceType.TOOL_OUTPUT,
        owner_id=owner.id,
        project_id=project.id,
    )
    await db.commit()
    return record


def _persistence(
    entries: list[dict],
) -> StandardArtifactPersistenceResult:
    """按「ref → 类型 / 角色-文件 / metadata / metrics」构造持久化结果。"""
    parsed: dict[str, ParsedStandardArtifact] = {}
    file_ids_by_ref: dict[str, list[str]] = {}
    roles_by_ref: dict[str, dict[str, str]] = {}
    artifact_ids: dict[str, str] = {}
    version_ids: dict[str, str] = {}
    for entry in entries:
        ref = entry["ref"]
        roles: dict[str, str] = dict(entry.get("roles") or {})
        parsed[ref] = ParsedStandardArtifact(
            output_name=ref.split("[")[0],
            type=entry["type"],
            name=entry.get("name"),
            files={
                role: ParsedStandardFile(
                    role=role,
                    path=Path("/tmp") / role,
                    relative_path=role,
                    sha256=entry.get("sha256") or "",
                )
                for role in roles
            },
            index=entry.get("index"),
            metadata=entry.get("metadata") or {},
            summary={},
            metrics=entry.get("metrics") or {},
        )
        roles_by_ref[ref] = roles
        file_ids_by_ref[ref] = list(roles.values())
        artifact_ids[ref] = f"artifact-{ref}"
        version_ids[ref] = f"version-{ref}"
    return StandardArtifactPersistenceResult(
        artifact_ids_by_ref=artifact_ids,
        artifact_version_ids_by_ref=version_ids,
        file_ids_by_artifact_ref=file_ids_by_ref,
        file_ids_by_artifact_role=roles_by_ref,
        parsed_artifacts_by_ref=parsed,
    )


def _task(domain: dict | None, *, task_id: str = "task-1") -> SimpleNamespace:
    extra_data = {"domain": domain} if domain is not None else {}
    return SimpleNamespace(id=task_id, extra_data=extra_data)


# ---------------------------------------------------------------------------
# 结构预测
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_structure_prediction_writes_predicted_structure(
    db_session: AsyncSession, project: Project, owner: User, protein: Protein
):
    pdb = await _store(
        db_session, project=project, owner=owner, filename="structure.pdb", content=b"ATOM\n"
    )
    persistence = _persistence(
        [
            {
                "ref": "predicted_structure",
                "type": STRUCTURE_TYPE,
                "roles": {"structure_file": pdb.id},
                # boltz2 的 complex_plddt 是 0~1 概率，落库统一成 0~100
                "metrics": {"complex_plddt": 0.8734},
                "sha256": "a" * 64,
            }
        ]
    )
    task = _task({"kind": "structure_prediction", "protein_id": protein.id})

    marker = await write_back_domain_results(
        db_session, task=task, persistence_result=persistence
    )
    await db_session.commit()

    assert marker is not None
    assert marker["status"] == "written"
    structures = (
        (await db_session.execute(select(ProteinStructure))).scalars().all()
    )
    assert len(structures) == 1
    structure = structures[0]
    assert structure.protein_id == protein.id
    assert structure.source_type == "PREDICTED"
    assert structure.structure_urn == f"file:{pdb.id}"
    assert structure.sha256 == pdb.sha256 or structure.sha256 == "a" * 64
    assert float(structure.plddt_mean) == 87.34
    assert structure.task_id == "task-1"
    assert task.extra_data[DOMAIN_WRITEBACK_KEY]["status"] == "written"


@pytest.mark.asyncio
async def test_structure_prediction_reads_plddt_from_run_report(
    db_session: AsyncSession, project: Project, owner: User, protein: Protein
):
    """Boltz-2 的置信度在 report.json 里，不在结构产物上——必须答得出来。

    真实任务是这个形状：``protein_structure@1`` 的 ``metrics`` 是空字典，
    ``report.json`` 顶层才有 ``confidence.complex_plddt``。只读结构产物 `metrics`
    的话，页面上「pLDDT 均值」对每个真实任务都是空。
    """
    pdb = await _store(
        db_session, project=project, owner=owner, filename="structure.pdb", content=b"ATOM\n"
    )
    report = await _store(
        db_session,
        project=project,
        owner=owner,
        filename="report.json",
        content=json.dumps(
            {"status": "succeeded", "confidence": {"complex_plddt": 0.8304, "ptm": 0.87}}
        ).encode("utf-8"),
    )
    persistence = _persistence(
        [
            {
                "ref": "predicted_structure",
                "type": STRUCTURE_TYPE,
                "roles": {"structure_file": pdb.id},
                "metrics": {},
                "sha256": "a" * 64,
            },
            {
                "ref": "report",
                "type": REPORT_TYPE,
                "roles": {"report_json": report.id},
            },
        ]
    )
    task = _task({"kind": "structure_prediction", "protein_id": protein.id})

    marker = await write_back_domain_results(
        db_session, task=task, persistence_result=persistence
    )
    await db_session.commit()

    assert marker is not None and marker["status"] == "written"
    structures = ((await db_session.execute(select(ProteinStructure))).scalars().all())
    assert len(structures) == 1
    assert float(structures[0].plddt_mean) == 83.04


@pytest.mark.asyncio
async def test_structure_prediction_without_confidence_leaves_plddt_empty(
    db_session: AsyncSession, project: Project, owner: User, protein: Protein
):
    """报告里也没有置信度时留空，不能编一个 0 出来（0 会被当成「极低可信」）。"""
    pdb = await _store(
        db_session, project=project, owner=owner, filename="structure.pdb", content=b"ATOM\n"
    )
    persistence = _persistence(
        [
            {
                "ref": "predicted_structure",
                "type": STRUCTURE_TYPE,
                "roles": {"structure_file": pdb.id},
                "metrics": {},
            }
        ]
    )
    task = _task({"kind": "structure_prediction", "protein_id": protein.id})

    await write_back_domain_results(db_session, task=task, persistence_result=persistence)
    await db_session.commit()

    structures = ((await db_session.execute(select(ProteinStructure))).scalars().all())
    assert len(structures) == 1
    assert structures[0].plddt_mean is None


@pytest.mark.asyncio
async def test_structure_prediction_replay_updates_the_same_row(
    db_session: AsyncSession, project: Project, owner: User, protein: Protein
):
    pdb = await _store(
        db_session, project=project, owner=owner, filename="structure.pdb", content=b"ATOM\n"
    )
    scope = {"kind": "structure_prediction", "protein_id": protein.id}
    first = _persistence(
        [{"ref": "predicted_structure", "type": STRUCTURE_TYPE,
          "roles": {"structure_file": pdb.id}, "metrics": {"complex_plddt": 0.5}}]
    )
    second = _persistence(
        [{"ref": "predicted_structure", "type": STRUCTURE_TYPE,
          "roles": {"structure_file": pdb.id}, "metrics": {"complex_plddt": 0.91}}]
    )

    await write_back_domain_results(
        db_session, task=_task(scope), persistence_result=first
    )
    await write_back_domain_results(
        db_session, task=_task(scope), persistence_result=second
    )
    await db_session.commit()

    structures = (
        (await db_session.execute(select(ProteinStructure))).scalars().all()
    )
    assert len(structures) == 1, "同一任务重放不应新增结构行"
    assert float(structures[0].plddt_mean) == 91.0


# ---------------------------------------------------------------------------
# 结构准备
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_structure_preparation_fills_prepared_and_pdbqt_urns(
    db_session: AsyncSession, project: Project, owner: User, protein: Protein
):
    raw = await _store(
        db_session, project=project, owner=owner, filename="raw.pdb", content=b"ATOM\n"
    )
    prepared = await _store(
        db_session, project=project, owner=owner, filename="prepared.pdb", content=b"ATOM\n"
    )
    pdbqt = await _store(
        db_session, project=project, owner=owner, filename="receptor.pdbqt", content=b"ATOM\n"
    )
    structure = ProteinStructure(
        protein_id=protein.id, source_type="IMPORTED", structure_urn=f"file:{raw.id}"
    )
    db_session.add(structure)
    await db_session.commit()
    await db_session.refresh(structure)

    persistence = _persistence(
        [
            {
                "ref": "prepared_protein",
                "type": STRUCTURE_TYPE,
                "roles": {
                    "structure_file": prepared.id,
                    "prepared_pdb": prepared.id,
                    "receptor_pdbqt": pdbqt.id,
                },
            }
        ]
    )
    marker = await write_back_domain_results(
        db_session,
        task=_task({"kind": "structure_preparation", "structure_id": structure.id}),
        persistence_result=persistence,
    )
    await db_session.commit()
    await db_session.refresh(structure)

    assert marker["status"] == "written"
    assert structure.prepared_urn == f"file:{prepared.id}"
    assert structure.pdbqt_urn == f"file:{pdbqt.id}"
    assert structure.structure_urn == f"file:{raw.id}", "原始结构不能被准备产物覆盖"


@pytest.mark.asyncio
async def test_downstream_input_prefers_prepared_structure(
    db_session: AsyncSession, project: Project, owner: User, protein: Protein
):
    raw = await _store(
        db_session, project=project, owner=owner, filename="raw.pdb", content=b"ATOM\n"
    )
    prepared = await _store(
        db_session, project=project, owner=owner, filename="prepared.pdb", content=b"ATOM\n"
    )
    structure = ProteinStructure(
        protein_id=protein.id, source_type="IMPORTED", structure_urn=f"file:{raw.id}"
    )
    db_session.add(structure)
    await db_session.commit()
    await db_session.refresh(structure)

    assert (await structure_input_file_record(
        db_session, structure=structure, user=owner
    )).id == raw.id

    structure.prepared_urn = f"file:{prepared.id}"
    await db_session.commit()
    await db_session.refresh(structure)

    assert (await structure_input_file_record(
        db_session, structure=structure, user=owner
    )).id == prepared.id


# ---------------------------------------------------------------------------
# 口袋预测
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pocket_prediction_creates_pocket_with_residues(
    db_session: AsyncSession, project: Project, owner: User, protein: Protein
):
    structure = ProteinStructure(
        protein_id=protein.id, source_type="PREDICTED", structure_urn="file:unused"
    )
    db_session.add(structure)
    await db_session.commit()
    await db_session.refresh(structure)

    residue_pdb = await _store(
        db_session,
        project=project,
        owner=owner,
        filename="pocket.pdb",
        content=_pdb(("A", 1, "MET", 0), ("A", 745, "LYS", 0), ("A", 1, "MET", 0)),
    )
    persistence = _persistence(
        [
            {
                "ref": "pocket",
                "type": POCKET_TYPE,
                "roles": {"residue_pocket_pdb": residue_pdb.id},
                "metadata": {
                    "center": [1.0, 2.0, 3.0],
                    "bbox": {"min": [0, 0, 0], "max": [10, 20, 30]},
                    "residue_ids": ["A:1", "A:745"],
                },
            }
        ]
    )
    marker = await write_back_domain_results(
        db_session,
        task=_task({"kind": "pocket_prediction", "structure_id": structure.id}),
        persistence_result=persistence,
    )
    await db_session.commit()

    assert marker["status"] == "written"
    pockets = (await db_session.execute(select(Pocket))).scalars().all()
    assert len(pockets) == 1
    pocket = pockets[0]
    assert pocket.structure_id == structure.id
    assert pocket.rank == 1
    assert float(pocket.center_x) == 1.0
    assert float(pocket.box_size_z) == 30.0
    assert float(pocket.volume) == 6000.0
    assert pocket.residue_count == 2
    assert pocket.selected is False
    assert pocket.task_id == "task-1"

    residues = (
        (await db_session.execute(select(PocketResidue))).scalars().all()
    )
    assert {(item.chain, item.residue_seq, item.residue_name) for item in residues} == {
        ("A", 1, "MET"),
        ("A", 745, "LYS"),
    }
    assert all(item.is_key for item in residues)


@pytest.mark.asyncio
async def test_pocket_geometry_falls_back_to_residue_pdb(
    db_session: AsyncSession, project: Project, owner: User, protein: Protein
):
    """metadata 只给文件引用时，几何从口袋残基 PDB 的原子坐标反算。

    LVpocket 的 ``prediction.json`` 里 ``pockets[]`` 只有 ``pdb`` / ``mol2`` 路径，
    没有 ``center`` / ``bbox``。若只读 metadata，真实任务的口袋在页面上中心、包围盒、
    体积三列全是空——数据其实在文件里，只是没人去算。
    """
    structure = ProteinStructure(
        protein_id=protein.id, source_type="PREDICTED", structure_urn="file:unused"
    )
    db_session.add(structure)
    await db_session.commit()
    await db_session.refresh(structure)

    residue_pdb = await _store(
        db_session,
        project=project,
        owner=owner,
        filename="pocket0.pdb",
        content=_pdb_with_coordinates([(0.0, 0.0, 0.0), (10.0, 20.0, 30.0)]),
    )
    persistence = _persistence(
        [
            {
                "ref": "pocket",
                "type": POCKET_TYPE,
                "roles": {"residue_pocket_pdb": residue_pdb.id},
                "metadata": {"residue_ids": ["A:1", "A:2"]},
            }
        ]
    )

    marker = await write_back_domain_results(
        db_session,
        task=_task({"kind": "pocket_prediction", "structure_id": structure.id}),
        persistence_result=persistence,
    )
    await db_session.commit()

    assert marker["status"] == "written"
    pocket = (await db_session.execute(select(Pocket))).scalars().one()
    assert float(pocket.center_x) == 5.0
    assert float(pocket.center_z) == 15.0
    assert float(pocket.box_size_y) == 20.0
    assert float(pocket.volume) == 6000.0
    # 模型没有给打分，就不能编一个出来
    assert pocket.score is None


@pytest.mark.asyncio
async def test_pocket_geometry_prefers_artifact_metadata(
    db_session: AsyncSession, project: Project, owner: User, protein: Protein
):
    """metadata 里有几何时以 metadata 为准，不被 PDB 反算覆盖。"""
    structure = ProteinStructure(
        protein_id=protein.id, source_type="PREDICTED", structure_urn="file:unused"
    )
    db_session.add(structure)
    await db_session.commit()
    await db_session.refresh(structure)

    residue_pdb = await _store(
        db_session,
        project=project,
        owner=owner,
        filename="pocket0.pdb",
        content=_pdb_with_coordinates([(0.0, 0.0, 0.0), (10.0, 20.0, 30.0)]),
    )
    persistence = _persistence(
        [
            {
                "ref": "pocket",
                "type": POCKET_TYPE,
                "roles": {"residue_pocket_pdb": residue_pdb.id},
                "metadata": {
                    "center": [1.0, 2.0, 3.0],
                    "bbox": {"min": [0, 0, 0], "max": [5, 5, 5]},
                },
            }
        ]
    )

    await write_back_domain_results(
        db_session,
        task=_task({"kind": "pocket_prediction", "structure_id": structure.id}),
        persistence_result=persistence,
    )
    await db_session.commit()

    pocket = (await db_session.execute(select(Pocket))).scalars().one()
    assert float(pocket.center_x) == 1.0
    assert float(pocket.volume) == 125.0


@pytest.mark.asyncio
async def test_pocket_prediction_appends_rank_after_existing_pockets(
    db_session: AsyncSession, project: Project, owner: User, protein: Protein
):
    structure = ProteinStructure(
        protein_id=protein.id, source_type="PREDICTED", structure_urn="file:unused"
    )
    db_session.add(structure)
    await db_session.flush()
    db_session.add(Pocket(structure_id=structure.id, rank=1, tool_name="manual"))
    await db_session.commit()
    await db_session.refresh(structure)

    persistence = _persistence(
        [
            {
                "ref": "pocket",
                "type": POCKET_TYPE,
                "roles": {},
                "metadata": {"center": [0, 0, 0]},
            }
        ]
    )
    await write_back_domain_results(
        db_session,
        task=_task({"kind": "pocket_prediction", "structure_id": structure.id}),
        persistence_result=persistence,
    )
    await db_session.commit()

    ranks = sorted(
        (await db_session.execute(select(Pocket.rank))).scalars().all()
    )
    assert ranks == [1, 2], "新预测必须接在已有 rank 之后，不能重排撞唯一约束"


@pytest.mark.asyncio
async def test_pocket_prediction_replay_replaces_previous_rows(
    db_session: AsyncSession, project: Project, owner: User, protein: Protein
):
    structure = ProteinStructure(
        protein_id=protein.id, source_type="PREDICTED", structure_urn="file:unused"
    )
    db_session.add(structure)
    await db_session.commit()
    await db_session.refresh(structure)

    residue_pdb = await _store(
        db_session,
        project=project,
        owner=owner,
        filename="pocket.pdb",
        content=_pdb(("A", 1, "MET", 0)),
    )
    persistence = _persistence(
        [
            {
                "ref": "pocket",
                "type": POCKET_TYPE,
                "roles": {"residue_pocket_pdb": residue_pdb.id},
                "metadata": {"center": [1, 2, 3]},
            }
        ]
    )
    scope = {"kind": "pocket_prediction", "structure_id": structure.id}

    await write_back_domain_results(
        db_session, task=_task(scope), persistence_result=persistence
    )
    await write_back_domain_results(
        db_session, task=_task(scope), persistence_result=persistence
    )
    await db_session.commit()

    pockets = (await db_session.execute(select(Pocket))).scalars().all()
    residues = (await db_session.execute(select(PocketResidue))).scalars().all()
    assert len(pockets) == 1, "同一任务重放不应堆积口袋行"
    assert len(residues) == 1, "重放要连带清掉旧口袋的残基行"


# ---------------------------------------------------------------------------
# 跳过与容错
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_domain_context_writes_nothing(db_session: AsyncSession):
    task = _task(None)
    marker = await write_back_domain_results(
        db_session, task=task, persistence_result=_persistence([])
    )
    await db_session.commit()

    assert marker is None
    assert DOMAIN_WRITEBACK_KEY not in task.extra_data


@pytest.mark.asyncio
async def test_missing_standard_artifacts_is_skipped_with_reason(
    db_session: AsyncSession, protein: Protein
):
    task = _task({"kind": "structure_prediction", "protein_id": protein.id})
    marker = await write_back_domain_results(
        db_session, task=task, persistence_result=None
    )
    await db_session.commit()

    assert marker is not None
    assert marker["status"] == "skipped"
    assert "标准产物" in marker["reason"]
    structures = (
        (await db_session.execute(select(ProteinStructure))).scalars().all()
    )
    assert structures == []


@pytest.mark.asyncio
async def test_writeback_failure_keeps_session_usable(
    db_session: AsyncSession, protein: Protein
):
    """回写失败只能留标记，不能把调用方事务一起回滚掉。"""
    task = _task({"kind": "structure_prediction", "protein_id": protein.id})
    broken = _persistence(
        [
            {
                "ref": "predicted_structure",
                "type": STRUCTURE_TYPE,
                "roles": {"structure_file": "does-not-exist"},
            }
        ]
    )
    marker = await write_back_domain_results(
        db_session, task=task, persistence_result=broken
    )
    await db_session.commit()

    assert marker["status"] == "skipped"
    # 会话仍然可用：失败被 SAVEPOINT 圈住，没有把外层事务打成不可用状态
    assert (await db_session.execute(select(Protein.id))).scalars().all() == [protein.id]


# ---------------------------------------------------------------------------
# PDB 解析
# ---------------------------------------------------------------------------


def test_parse_pdb_residues_deduplicates_and_ignores_bad_lines():
    content = "\n".join(
        [
            _atom_line(serial=1, res_name="MET", chain="A", res_seq=1),
            _atom_line(serial=2, res_name="MET", chain="A", res_seq=1),
            _atom_line(serial=3, res_name="LYS", chain="B", res_seq=745),
            "REMARK   not an atom record",
            "ATOM short",
            "",
        ]
    ).encode("utf-8")

    residues = parse_pdb_residues(content)

    assert residues == [
        {"chain": "A", "residue_seq": 1, "residue_name": "MET"},
        {"chain": "B", "residue_seq": 745, "residue_name": "LYS"},
    ]
