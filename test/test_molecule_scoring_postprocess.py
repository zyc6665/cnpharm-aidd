"""分子生成任务评分后处理测试。"""

from __future__ import annotations

import hashlib
import builtins
import logging
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.base import Base
from app.models import files as _files_models  # noqa: F401
from app.models import statistics as _statistics_models  # noqa: F401
from app.models import tasks as _task_models  # noqa: F401
from app.models import tools as _tools_models  # noqa: F401
from app.models import users as _user_models  # noqa: F401
from app.models.files import File as FileModel, FileSourceType
from app.models.tasks import Task, TaskInput
from app.models.tools import Tool, ToolStatus, ToolVersion


SDF_RECORDS = [
    "mol_0\n  test\n\n  0  0  0  0  0  0            999 V2000\nM  END\n$$$$\n",
    "mol_1\n  test\n\n  0  0  0  0  0  0            999 V2000\nM  END\n$$$$\n",
    "mol_2\n  test\n\n  0  0  0  0  0  0            999 V2000\nM  END\n$$$$\n",
]


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """创建隔离数据库会话。"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    await engine.dispose()


def write_file(path: Path, content: bytes) -> tuple[int, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return len(content), hashlib.sha256(content).hexdigest()


async def create_tool_and_task(
    db: AsyncSession,
    *,
    config: dict,
) -> tuple[Task, ToolVersion]:
    tool = Tool(
        owner_id="user-1",
        name="Generation Tool",
        slug="generation-tool",
        description="test",
        category="generation",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    db.add(tool)
    await db.flush()

    version = ToolVersion(
        tool_id=tool.id,
        version="1.0.0",
        config=config,
        is_active=True,
    )
    db.add(version)
    await db.flush()

    task = Task(
        user_id="user-1",
        tool_id=tool.id,
        tool_version_id=version.id,
        status="RUNNING",
        priority="normal",
    )
    db.add(task)
    await db.flush()
    db.add(TaskInput(task_id=task.id, params={}, file_ids=[]))
    await db.commit()
    await db.refresh(task)
    await db.refresh(version)
    return task, version


async def create_output_file(
    db: AsyncSession,
    tmp_path: Path,
    *,
    filename: str,
    relative_path: str,
    content: bytes,
) -> FileModel:
    storage_path = tmp_path / filename
    size, sha256 = write_file(storage_path, content)
    file_record = FileModel(
        filename=filename,
        content_type="chemical/x-mdl-sdfile",
        size_bytes=size,
        sha256=sha256,
        storage_path=str(storage_path),
        source_type=FileSourceType.TOOL_OUTPUT.value,
        owner_id="user-1",
        file_meta={"relative_path": relative_path},
    )
    db.add(file_record)
    await db.commit()
    await db.refresh(file_record)
    return file_record


@pytest.mark.asyncio
async def test_molecule_generation_appends_scoring_artifacts(
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """分子生成任务应追加评分 CSV 和 Top10 SDF。"""
    from app.tasks import molecule_scoring

    task, version = await create_tool_and_task(
        db_session,
        config={
            "type": "ssh_job",
            "agent_capability": {
                "enabled": True,
                "capability": "molecule_generation",
            },
        },
    )
    sdf_file = await create_output_file(
        db_session,
        tmp_path,
        filename="artifacts__generated_molecules.sdf",
        relative_path="artifacts/generated_molecules.sdf",
        content="".join(SDF_RECORDS).encode("utf-8"),
    )

    def fake_descriptors(candidate: molecule_scoring.MoleculeCandidate) -> molecule_scoring.DescriptorScores:
        return molecule_scoring.DescriptorScores(
            smiles=f"C{candidate.record_index}",
            qed={0: 0.2, 1: 0.9, 2: 0.7}[candidate.record_index],
            sa={0: 4.0, 1: 2.0, 2: 3.0}[candidate.record_index],
        )

    monkeypatch.setattr(molecule_scoring, "score_molecule_descriptors", fake_descriptors)
    monkeypatch.setattr(molecule_scoring, "score_molecule_vina", lambda *_args, **_kwargs: None)

    output_result = {
        "success": True,
        "result": {"output_file_ids": [sdf_file.id]},
        "output_file_ids": [sdf_file.id],
    }

    updated = await molecule_scoring.append_molecule_scoring_artifacts(
        db_session,
        task,
        version,
        output_result,
    )
    await db_session.commit()

    appended_ids = updated["output_file_ids"]
    assert appended_ids[0] == sdf_file.id
    assert len(appended_ids) == 3
    assert updated["result"]["output_file_ids"] == appended_ids
    assert updated["result"]["molecule_scoring"]["candidate_count"] == 3
    assert updated["result"]["molecule_scoring"]["top_count"] == 3

    result = await db_session.execute(select(FileModel).where(FileModel.id.in_(appended_ids[1:])))
    artifacts = {file.filename: Path(file.storage_path).read_text() for file in result.scalars().all()}

    assert "molecule_scores.csv" in artifacts
    assert "top10_molecules.sdf" in artifacts
    assert artifacts["molecule_scores.csv"].splitlines()[0] == (
        "rank,index,smiles,sdf_file,qed,sa,vina_score,composite_score,error"
    )
    assert artifacts["molecule_scores.csv"].splitlines()[1].startswith("1,1,C1,")
    assert artifacts["top10_molecules.sdf"].startswith(SDF_RECORDS[1])


@pytest.mark.asyncio
async def test_molecule_generation_scoring_keeps_standard_result_v2_schema_clean(
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """标准 result.v2 不应被平台评分后处理写入内部字段。"""
    from app.tasks import molecule_scoring

    task, version = await create_tool_and_task(
        db_session,
        config={
            "type": "ssh_job",
            "agent_capability": {
                "enabled": True,
                "capability": "molecule_generation",
            },
        },
    )
    sdf_file = await create_output_file(
        db_session,
        tmp_path,
        filename="artifacts__generated_molecules.sdf",
        relative_path="artifacts/generated_molecules.sdf",
        content=SDF_RECORDS[0].encode("utf-8"),
    )

    monkeypatch.setattr(
        molecule_scoring,
        "score_molecule_descriptors",
        lambda candidate: molecule_scoring.DescriptorScores(smiles="CCO", qed=0.8, sa=2.5),
    )
    monkeypatch.setattr(molecule_scoring, "score_molecule_vina", lambda *_args, **_kwargs: None)

    output_result = {
        "success": True,
        "result": {
            "result_version": "aidd.sciminer/result",
            "artifacts": {},
            "relations": [],
        },
        "output_file_ids": [sdf_file.id],
    }

    updated = await molecule_scoring.append_molecule_scoring_artifacts(
        db_session,
        task,
        version,
        output_result,
    )

    assert len(updated["output_file_ids"]) == 3
    assert "molecule_scoring" in updated
    assert "output_file_ids" not in updated["result"]
    assert "molecule_scoring" not in updated["result"]


@pytest.mark.asyncio
async def test_non_molecule_generation_skips_scoring(
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    """非分子生成任务不应追加评分产物。"""
    from app.tasks.molecule_scoring import append_molecule_scoring_artifacts

    task, version = await create_tool_and_task(
        db_session,
        config={"type": "ssh_job"},
    )
    sdf_file = await create_output_file(
        db_session,
        tmp_path,
        filename="artifacts__generated_molecules.sdf",
        relative_path="artifacts/generated_molecules.sdf",
        content=SDF_RECORDS[0].encode("utf-8"),
    )
    output_result = {"success": True, "output_file_ids": [sdf_file.id]}

    updated = await append_molecule_scoring_artifacts(db_session, task, version, output_result)

    assert updated["output_file_ids"] == [sdf_file.id]


def test_molecule_generation_capability_failure_is_observable(caplog, monkeypatch):
    """能力表异常时应保留兜底行为，同时记录可排查上下文。"""
    from app.tasks import molecule_scoring

    def fail_import(name, *args, **kwargs):
        if name == "app.tools.capabilities":
            raise RuntimeError("capability unavailable")
        return original_import(name, *args, **kwargs)

    original_import = __import__
    monkeypatch.setattr("builtins.__import__", fail_import)
    tool_version = SimpleNamespace(config={})
    tool = SimpleNamespace(slug="generation-tool")

    with caplog.at_level(logging.DEBUG, logger="app.tasks.molecule_scoring"):
        assert molecule_scoring._is_molecule_generation_tool(tool_version, tool) is False

    assert "Failed to resolve AIDD capability for tool generation-tool" in caplog.text


def test_rdkit_sa_scorer_import_failure_is_observable(caplog, monkeypatch):
    """SA scorer 缺失时应保留降级行为并记录原因。"""
    from app.tasks import molecule_scoring

    original_import = builtins.__import__

    def fail_import(name, *args, **kwargs):
        if name == "rdkit.Contrib.SA_Score":
            raise RuntimeError("sa scorer unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_import)

    with caplog.at_level(logging.DEBUG, logger="app.tasks.molecule_scoring"):
        assert molecule_scoring._rdkit_sa_score(object()) is None

    assert "RDKit SA scorer unavailable: sa scorer unavailable" in caplog.text


def test_rdkit_sa_score_failure_is_observable(caplog, monkeypatch):
    """SA scorer 计算失败时应保留降级行为并记录原因。"""
    from app.tasks import molecule_scoring

    module = types.ModuleType("rdkit.Contrib.SA_Score")
    module.sascorer = SimpleNamespace(
        calculateScore=lambda _mol: (_ for _ in ()).throw(RuntimeError("score failed"))
    )
    monkeypatch.setitem(sys.modules, "rdkit.Contrib.SA_Score", module)

    with caplog.at_level(logging.DEBUG, logger="app.tasks.molecule_scoring"):
        assert molecule_scoring._rdkit_sa_score(object()) is None

    assert "RDKit SA scoring failed: score failed" in caplog.text
