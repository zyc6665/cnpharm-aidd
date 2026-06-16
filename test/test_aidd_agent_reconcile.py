"""AIDD agent task reconciliation tests."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.aidd.service import reconcile_waiting_agent_steps, start_ready_steps  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.models import agent as _agent_models  # noqa: F401,E402
from app.models import files as _files_models  # noqa: F401,E402
from app.models import statistics as _statistics_models  # noqa: F401,E402
from app.models import tasks as _task_models  # noqa: F401,E402
from app.models import tools as _tools_models  # noqa: F401,E402
from app.models import users as _users_models  # noqa: F401,E402
from app.models.agent import AgentRun, AgentRunStep  # noqa: E402
from app.models.files import File as FileModel, FileSourceType  # noqa: E402
from app.models.tasks import Task, TaskOutput, TaskStatus  # noqa: E402
from app.models.tools import Tool, ToolStatus, ToolVersion  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
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


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    user_record = User(
        email="owner@example.com",
        password_hash="hashed-password",
        display_name="Owner",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(user_record)
    await db_session.commit()
    await db_session.refresh(user_record)
    return user_record


async def create_tool(db_session: AsyncSession, owner: User, *, slug: str, name: str) -> Tool:
    tool = Tool(
        owner_id=owner.id,
        name=name,
        slug=slug,
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    db_session.add(tool)
    await db_session.flush()
    version = ToolVersion(
        tool_id=tool.id,
        version="1.0.0",
        config={"type": "ssh_job"},
        is_active=True,
    )
    db_session.add(version)
    await db_session.flush()
    tool.current_version_id = version.id
    await db_session.commit()
    await db_session.refresh(tool)
    return tool


def file_record(
    *,
    owner: User,
    filename: str,
    content: bytes,
    storage_path: str,
    content_type: str = "chemical/x-pdb",
    source_type: str = FileSourceType.UPLOAD.value,
) -> FileModel:
    return FileModel(
        owner_id=owner.id,
        filename=filename,
        content_type=content_type,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        source_type=source_type,
        storage_path=storage_path,
    )


@pytest.mark.asyncio
async def test_successful_step_extracts_output_and_schedules_downstream(
    db_session: AsyncSession,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lvpocket = await create_tool(
        db_session,
        user,
        slug="lvpocket-pocket-prediction",
        name="LVpocket",
    )
    await create_tool(
        db_session,
        user,
        slug="gcdm-pocket-generation",
        name="STD-Diff",
    )

    input_file = FileModel(
        owner_id=user.id,
        filename="protein.pdb",
        content_type="chemical/x-pdb",
        size_bytes=128,
        sha256=hashlib.sha256(b"protein").hexdigest(),
        source_type=FileSourceType.UPLOAD.value,
        storage_path="/tmp/protein.pdb",
    )
    output_file = FileModel(
        owner_id=user.id,
        filename="best_pocket.pdb",
        content_type="chemical/x-pdb",
        size_bytes=128,
        sha256=hashlib.sha256(b"pocket").hexdigest(),
        source_type=FileSourceType.TOOL_OUTPUT.value,
        storage_path="/tmp/best_pocket.pdb",
    )
    db_session.add_all([input_file, output_file])
    await db_session.flush()

    task = Task(
        user_id=user.id,
        tool_id=lvpocket.id,
        tool_version_id=lvpocket.current_version_id,
        status=TaskStatus.SUCCESS.value,
        progress=1.0,
    )
    db_session.add(task)
    await db_session.flush()
    db_session.add(
        TaskOutput(
            task_id=task.id,
            result={"ok": True},
            file_ids=[output_file.id],
            output_type="file",
        )
    )

    run = AgentRun(
        user_id=user.id,
        message="生成分子",
        intent="generate_molecules_from_protein",
        status="waiting_task",
        input_type="protein_pdb",
        input_file_id=input_file.id,
        requested_outputs=["generated_ligand"],
        plan={},
    )
    db_session.add(run)
    await db_session.flush()
    first_step = AgentRunStep(
        agent_run_id=run.id,
        step_key="pocket_prediction",
        tool_slug="lvpocket-pocket-prediction",
        tool_id=lvpocket.id,
        task_id=task.id,
        status="waiting_task",
        sort_order=0,
        semantic_inputs={"protein_pdb": "agent_input"},
        params={},
    )
    second_step = AgentRunStep(
        agent_run_id=run.id,
        step_key="molecule_generation",
        tool_slug="gcdm-pocket-generation",
        status="pending",
        sort_order=1,
        depends_on_step_ids=["pocket_prediction"],
        semantic_inputs={"pocket_pdb": "step:pocket_prediction:pocket_pdb"},
        params={"params.n_samples": 8},
    )
    db_session.add_all([first_step, second_step])
    await db_session.commit()

    async def fake_create_task(*, db, current_user, task_data, direct_runner=None):
        return SimpleNamespace(id="task-generation", tool_id=task_data.tool_id)

    monkeypatch.setattr(
        "app.agents.aidd.service.create_and_schedule_tool_task",
        fake_create_task,
    )

    count = await reconcile_waiting_agent_steps(db_session, run_id=run.id)

    assert count == 1
    refreshed_first = await db_session.get(AgentRunStep, first_step.id)
    refreshed_second = await db_session.get(AgentRunStep, second_step.id)
    assert refreshed_first.status == "success"
    assert refreshed_first.semantic_outputs["pocket_pdb"]["file_id"] == output_file.id
    assert refreshed_second.status == "waiting_task"
    assert refreshed_second.task_id == "task-generation"


@pytest.mark.asyncio
async def test_failed_task_marks_agent_run_failure(
    db_session: AsyncSession,
    user: User,
) -> None:
    lvpocket = await create_tool(
        db_session,
        user,
        slug="lvpocket-pocket-prediction",
        name="LVpocket",
    )
    task = Task(
        user_id=user.id,
        tool_id=lvpocket.id,
        tool_version_id=lvpocket.current_version_id,
        status=TaskStatus.FAILURE.value,
        progress=0.5,
        error_message="boom",
    )
    db_session.add(task)
    await db_session.flush()
    run = AgentRun(
        user_id=user.id,
        message="生成分子",
        intent="generate_molecules_from_protein",
        status="waiting_task",
        input_type="protein_pdb",
        requested_outputs=["generated_ligand"],
        plan={},
    )
    db_session.add(run)
    await db_session.flush()
    step = AgentRunStep(
        agent_run_id=run.id,
        step_key="pocket_prediction",
        tool_slug="lvpocket-pocket-prediction",
        tool_id=lvpocket.id,
        task_id=task.id,
        status="waiting_task",
        sort_order=0,
    )
    db_session.add(step)
    await db_session.commit()

    count = await reconcile_waiting_agent_steps(db_session, run_id=run.id)

    assert count == 1
    refreshed_run = await db_session.get(AgentRun, run.id)
    refreshed_step = await db_session.get(AgentRunStep, step.id)
    assert refreshed_run.status == "failure"
    assert refreshed_step.status == "failure"
    assert refreshed_step.error_message == "boom"


@pytest.mark.asyncio
async def test_legacy_agent_input_source_with_semantic_suffix_is_still_supported(
    db_session: AsyncSession,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await create_tool(
        db_session,
        user,
        slug="gcdm-pocket-generation",
        name="STD-Diff",
    )

    input_file = FileModel(
        owner_id=user.id,
        filename="protein.pdb",
        content_type="chemical/x-pdb",
        size_bytes=128,
        sha256=hashlib.sha256(b"protein-legacy").hexdigest(),
        source_type=FileSourceType.UPLOAD.value,
        storage_path="/tmp/protein-legacy.pdb",
    )
    db_session.add(input_file)
    await db_session.flush()

    run = AgentRun(
        user_id=user.id,
        message="继续执行旧智能体任务",
        intent="generate_molecules_from_pocket",
        status="pending",
        input_type="protein_pdb",
        input_file_id=input_file.id,
        requested_outputs=["generated_ligand"],
        plan={},
    )
    db_session.add(run)
    await db_session.flush()

    step = AgentRunStep(
        agent_run_id=run.id,
        step_key="molecule_generation",
        tool_slug="gcdm-pocket-generation",
        status="pending",
        sort_order=0,
        semantic_inputs={"pocket_pdb": "agent_input:protein_pdb"},
        params={"params.n_samples": 8},
    )
    db_session.add(step)
    await db_session.commit()

    async def fake_create_task(*, db, current_user, task_data, direct_runner=None):
        return SimpleNamespace(id="task-generation-legacy", tool_id=task_data.tool_id)

    monkeypatch.setattr(
        "app.agents.aidd.service.create_and_schedule_tool_task",
        fake_create_task,
    )

    count = await start_ready_steps(db_session, current_user=user, run_id=run.id)

    assert count == 1
    refreshed_step = await db_session.get(AgentRunStep, step.id)
    assert refreshed_step.status == "waiting_task"
    assert refreshed_step.task_id == "task-generation-legacy"


@pytest.mark.asyncio
async def test_virtual_sdf_to_smiles_conversion_creates_csv_and_schedules_property_step(
    db_session: AsyncSession,
    user: User,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gcdm = await create_tool(
        db_session,
        user,
        slug="gcdm-pocket-generation",
        name="STD-Diff",
    )
    await create_tool(
        db_session,
        user,
        slug="molp-pc-property-prediction",
        name="MolP-PC",
    )

    sdf_path = tmp_path / "generated.sdf"
    sdf_content = b"""
Mol A
  generated

> <SMILES>
CCO

$$$$
"""
    sdf_path.write_bytes(sdf_content)
    generated_file = file_record(
        owner=user,
        filename="generated.sdf",
        content=sdf_content,
        storage_path=str(sdf_path),
        content_type="chemical/x-mdl-sdfile",
        source_type=FileSourceType.TOOL_OUTPUT.value,
    )
    db_session.add(generated_file)
    await db_session.flush()

    task = Task(
        user_id=user.id,
        tool_id=gcdm.id,
        tool_version_id=gcdm.current_version_id,
        status=TaskStatus.SUCCESS.value,
    )
    db_session.add(task)
    await db_session.flush()
    db_session.add(TaskOutput(task_id=task.id, result={}, file_ids=[generated_file.id], output_type="file"))

    run = AgentRun(
        user_id=user.id,
        message="生成分子并预测性质",
        intent="generate_molecules_from_protein",
        status="waiting_task",
        input_type="protein_pdb",
        requested_outputs=["generated_ligand", "property_report"],
        plan={},
    )
    db_session.add(run)
    await db_session.flush()

    db_session.add_all(
        [
            AgentRunStep(
                agent_run_id=run.id,
                step_key="molecule_generation",
                tool_slug="gcdm-pocket-generation",
                tool_id=gcdm.id,
                task_id=task.id,
                status="waiting_task",
                sort_order=0,
            ),
            AgentRunStep(
                agent_run_id=run.id,
                step_key="sdf_to_smiles",
                tool_slug="builtin-sdf-to-smiles-csv",
                status="pending",
                sort_order=1,
                depends_on_step_ids=["molecule_generation"],
                semantic_inputs={"generated_ligand": "step:molecule_generation:generated_ligand"},
            ),
            AgentRunStep(
                agent_run_id=run.id,
                step_key="property_prediction",
                tool_slug="molp-pc-property-prediction",
                status="pending",
                sort_order=2,
                depends_on_step_ids=["sdf_to_smiles"],
                semantic_inputs={"smiles_csv": "step:sdf_to_smiles:smiles_csv"},
            ),
        ]
    )
    await db_session.commit()

    scheduled_payloads = []

    async def fake_create_task(*, db, current_user, task_data, direct_runner=None):
        scheduled_payloads.append(task_data)
        return SimpleNamespace(id="task-property", tool_id=task_data.tool_id)

    monkeypatch.setattr(
        "app.agents.aidd.service.create_and_schedule_tool_task",
        fake_create_task,
    )

    count = await reconcile_waiting_agent_steps(db_session, run_id=run.id)

    assert count == 1
    result = await db_session.get(AgentRun, run.id)
    conversion_step = next(step for step in result.steps if step.step_key == "sdf_to_smiles")
    property_step = next(step for step in result.steps if step.step_key == "property_prediction")
    csv_file = await db_session.get(FileModel, conversion_step.semantic_outputs["smiles_csv"]["file_id"])
    assert conversion_step.status == "success"
    assert csv_file.filename.endswith("_smiles.csv")
    assert Path(csv_file.storage_path).read_text(encoding="utf-8").strip() == "SMILES,id\nCCO,mol_1"
    assert property_step.status == "waiting_task"
    assert scheduled_payloads[0].file_ids == [csv_file.id]


@pytest.mark.asyncio
async def test_virtual_sdf_to_smiles_uses_converter_tool_when_sdf_has_no_smiles(
    db_session: AsyncSession,
    user: User,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gcdm = await create_tool(
        db_session,
        user,
        slug="gcdm-pocket-generation",
        name="STD-Diff",
    )

    sdf_path = tmp_path / "generated_without_smiles.sdf"
    sdf_content = b"""
Mol A
  generated

  0  0  0  0  0  0            999 V2000
M  END
$$$$
"""
    sdf_path.write_bytes(sdf_content)
    generated_file = file_record(
        owner=user,
        filename="generated_without_smiles.sdf",
        content=sdf_content,
        storage_path=str(sdf_path),
        content_type="chemical/x-mdl-sdfile",
        source_type=FileSourceType.TOOL_OUTPUT.value,
    )
    db_session.add(generated_file)
    await db_session.flush()

    task = Task(
        user_id=user.id,
        tool_id=gcdm.id,
        tool_version_id=gcdm.current_version_id,
        status=TaskStatus.SUCCESS.value,
    )
    db_session.add(task)
    await db_session.flush()
    db_session.add(TaskOutput(task_id=task.id, result={}, file_ids=[generated_file.id], output_type="file"))

    run = AgentRun(
        user_id=user.id,
        message="生成分子并转换 SMILES",
        intent="generate_molecules_from_protein",
        status="waiting_task",
        input_type="protein_pdb",
        requested_outputs=["generated_ligand", "property_report"],
        plan={},
    )
    db_session.add(run)
    await db_session.flush()
    db_session.add_all(
        [
            AgentRunStep(
                agent_run_id=run.id,
                step_key="molecule_generation",
                tool_slug="gcdm-pocket-generation",
                tool_id=gcdm.id,
                task_id=task.id,
                status="waiting_task",
                sort_order=0,
            ),
            AgentRunStep(
                agent_run_id=run.id,
                step_key="sdf_to_smiles",
                tool_slug="builtin-sdf-to-smiles-csv",
                status="pending",
                sort_order=1,
                depends_on_step_ids=["molecule_generation"],
                semantic_inputs={"generated_ligand": "step:molecule_generation:generated_ligand"},
            ),
        ]
    )
    await db_session.commit()

    converter_inputs: list[Path] = []

    def fake_converter_tool(path: Path) -> list[str]:
        converter_inputs.append(path)
        return ["NCCO"]

    monkeypatch.setattr(
        "app.agents.aidd.builtin_tools.convert_sdf_to_smiles_with_tool",
        fake_converter_tool,
    )

    count = await reconcile_waiting_agent_steps(db_session, run_id=run.id)

    assert count == 1
    refreshed_run = await db_session.get(AgentRun, run.id)
    conversion_step = next(step for step in refreshed_run.steps if step.step_key == "sdf_to_smiles")
    csv_file = await db_session.get(FileModel, conversion_step.semantic_outputs["smiles_csv"]["file_id"])
    assert converter_inputs == [sdf_path]
    assert Path(csv_file.storage_path).read_text(encoding="utf-8").strip() == "SMILES,id\nNCCO,mol_1"


@pytest.mark.asyncio
async def test_virtual_sdf_to_pdb_conversion_creates_ligand_pdb_and_schedules_affinity_step(
    db_session: AsyncSession,
    user: User,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gcdm = await create_tool(
        db_session,
        user,
        slug="gcdm-pocket-generation",
        name="STD-Diff",
    )
    await create_tool(
        db_session,
        user,
        slug="msign-affinity-prediction",
        name="MSIGN",
    )

    protein_file = file_record(
        owner=user,
        filename="protein.pdb",
        content=b"ATOM      1  N   ALA A   1\n",
        storage_path=str(tmp_path / "protein.pdb"),
    )
    Path(protein_file.storage_path).write_bytes(b"ATOM      1  N   ALA A   1\n")

    sdf_path = tmp_path / "generated.sdf"
    sdf_content = b"""
Mol A
  generated

  0  0  0  0  0  0            999 V2000
M  END
$$$$
"""
    sdf_path.write_bytes(sdf_content)
    generated_file = file_record(
        owner=user,
        filename="generated.sdf",
        content=sdf_content,
        storage_path=str(sdf_path),
        content_type="chemical/x-mdl-sdfile",
        source_type=FileSourceType.TOOL_OUTPUT.value,
    )
    db_session.add_all([protein_file, generated_file])
    await db_session.flush()

    task = Task(
        user_id=user.id,
        tool_id=gcdm.id,
        tool_version_id=gcdm.current_version_id,
        status=TaskStatus.SUCCESS.value,
    )
    db_session.add(task)
    await db_session.flush()
    db_session.add(TaskOutput(task_id=task.id, result={}, file_ids=[generated_file.id], output_type="file"))

    run = AgentRun(
        user_id=user.id,
        message="生成分子并预测亲和力",
        intent="generate_molecules_from_protein",
        status="waiting_task",
        input_type="protein_pdb",
        input_file_id=protein_file.id,
        requested_outputs=["generated_ligand", "affinity_report"],
        plan={"input_files": {"protein_pdb": protein_file.id}},
    )
    db_session.add(run)
    await db_session.flush()
    db_session.add_all(
        [
            AgentRunStep(
                agent_run_id=run.id,
                step_key="molecule_generation",
                tool_slug="gcdm-pocket-generation",
                tool_id=gcdm.id,
                task_id=task.id,
                status="waiting_task",
                sort_order=0,
            ),
            AgentRunStep(
                agent_run_id=run.id,
                step_key="sdf_to_ligand_pdb",
                tool_slug="builtin-sdf-to-pdb",
                status="pending",
                sort_order=1,
                depends_on_step_ids=["molecule_generation"],
                semantic_inputs={"generated_ligand": "step:molecule_generation:generated_ligand"},
            ),
            AgentRunStep(
                agent_run_id=run.id,
                step_key="affinity_prediction",
                tool_slug="msign-affinity-prediction",
                status="pending",
                sort_order=2,
                depends_on_step_ids=["sdf_to_ligand_pdb"],
                semantic_inputs={
                    "protein_pdb": "agent_input:protein_pdb",
                    "ligand_pdb": "step:sdf_to_ligand_pdb:ligand_pdb",
                },
            ),
        ]
    )
    await db_session.commit()

    converter_inputs: list[Path] = []

    def fake_converter_tool(path: Path) -> bytes:
        converter_inputs.append(path)
        return b"HETATM    1  C1  LIG A   1       0.000   0.000   0.000\nEND\n"

    monkeypatch.setattr(
        "app.agents.aidd.builtin_tools.convert_sdf_to_pdb_with_tool",
        fake_converter_tool,
    )

    scheduled_payloads = []

    async def fake_create_task(*, db, current_user, task_data, direct_runner=None):
        scheduled_payloads.append(task_data)
        return SimpleNamespace(id="task-affinity", tool_id=task_data.tool_id)

    monkeypatch.setattr(
        "app.agents.aidd.service.create_and_schedule_tool_task",
        fake_create_task,
    )

    count = await reconcile_waiting_agent_steps(db_session, run_id=run.id)

    assert count == 1
    refreshed_run = await db_session.get(AgentRun, run.id)
    conversion_step = next(step for step in refreshed_run.steps if step.step_key == "sdf_to_ligand_pdb")
    affinity_step = next(step for step in refreshed_run.steps if step.step_key == "affinity_prediction")
    ligand_file = await db_session.get(FileModel, conversion_step.semantic_outputs["ligand_pdb"]["file_id"])
    assert converter_inputs == [sdf_path]
    assert conversion_step.status == "success"
    assert ligand_file.filename == "generated_ligand.pdb"
    assert Path(ligand_file.storage_path).read_text(encoding="utf-8").startswith("HETATM")
    assert affinity_step.status == "waiting_task"
    assert scheduled_payloads[0].file_ids == [protein_file.id, ligand_file.id]
    assert scheduled_payloads[0].params["input_files"] == {
        "protein_pdb": "input/protein.pdb",
        "ligand_pdb": "input/generated_ligand.pdb",
    }


@pytest.mark.asyncio
async def test_virtual_vina_docking_creates_docking_report(
    db_session: AsyncSession,
    user: User,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    protein_path = tmp_path / "protein.pdb"
    ligand_path = tmp_path / "ligand.pdb"
    protein_content = b"ATOM      1  N   ALA A   1       0.000   0.000   0.000\nEND\n"
    ligand_content = b"HETATM    1  C1  LIG A   1       1.000   2.000   3.000\nEND\n"
    protein_path.write_bytes(protein_content)
    ligand_path.write_bytes(ligand_content)

    protein_file = file_record(
        owner=user,
        filename="protein.pdb",
        content=protein_content,
        storage_path=str(protein_path),
    )
    ligand_file = file_record(
        owner=user,
        filename="ligand.pdb",
        content=ligand_content,
        storage_path=str(ligand_path),
    )
    db_session.add_all([protein_file, ligand_file])
    await db_session.flush()

    run = AgentRun(
        user_id=user.id,
        message="用 Vina 对接打分",
        intent="rank_generated_ligands",
        status="pending",
        input_type="protein_pdb",
        input_file_id=protein_file.id,
        requested_outputs=["docking_report", "ranking_csv"],
        plan={"input_files": {"protein_pdb": protein_file.id, "ligand_pdb": ligand_file.id}},
    )
    db_session.add(run)
    await db_session.flush()
    db_session.add(
        AgentRunStep(
            agent_run_id=run.id,
            step_key="vina_docking",
            tool_slug="builtin-vina-docking",
            status="pending",
            sort_order=0,
            semantic_inputs={
                "protein_pdb": "agent_input:protein_pdb",
                "ligand_pdb": "agent_input:ligand_pdb",
            },
        )
    )
    await db_session.commit()

    docking_inputs: list[tuple[Path, Path]] = []

    def fake_vina(protein: Path, ligand: Path) -> dict[str, object]:
        docking_inputs.append((protein, ligand))
        return {
            "vina_score": -7.4,
            "center": {"x": 1.0, "y": 2.0, "z": 3.0},
            "size": {"x": 22.5, "y": 22.5, "z": 22.5},
            "stdout": "mode | affinity\n1 -7.4",
        }

    monkeypatch.setattr(
        "app.agents.aidd.builtin_tools.run_vina_docking_with_tool",
        fake_vina,
    )

    count = await start_ready_steps(db_session, current_user=user, run_id=run.id)

    assert count == 1
    refreshed_run = await db_session.get(AgentRun, run.id)
    docking_step = next(step for step in refreshed_run.steps if step.step_key == "vina_docking")
    report_file = await db_session.get(FileModel, docking_step.semantic_outputs["docking_report"]["file_id"])
    ranking_file = await db_session.get(FileModel, docking_step.semantic_outputs["ranking_csv"]["file_id"])
    report_text = Path(report_file.storage_path).read_text(encoding="utf-8")
    ranking_text = Path(ranking_file.storage_path).read_text(encoding="utf-8")
    assert docking_inputs == [(protein_path, ligand_path)]
    assert docking_step.status == "success"
    assert report_file.filename == "ligand_vina_report.json"
    assert ranking_file.filename == "ligand_vina_ranking.csv"
    assert '"vina_score": -7.4' in report_text
    assert "rank,ligand_id,ligand_filename,protein_filename,vina_score" in ranking_text
    assert "1,ligand,ligand.pdb,protein.pdb,-7.4" in ranking_text


@pytest.mark.asyncio
async def test_dynamic_agent_capability_schedules_platform_tool(
    db_session: AsyncSession,
    user: User,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = Tool(
        owner_id=user.id,
        name="Dynamic ADMET",
        slug="dynamic-admet",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    db_session.add(tool)
    await db_session.flush()
    version = ToolVersion(
        tool_id=tool.id,
        version="1.0.0",
        config={
            "type": "ssh_job",
            "agent_capability": {
                "enabled": True,
                "capability": "property_prediction",
                "stage": "property_prediction",
                "inputs": [{"semantic_type": "smiles_csv", "field": "smiles_csv"}],
                "outputs": [
                    {
                        "semantic_type": "property_report",
                        "source": "output_files",
                        "match": {"extension": ".csv", "filename_contains_any": ["admet"]},
                    }
                ],
                "defaults": {"device": "cpu"},
            },
        },
        is_active=True,
    )
    db_session.add(version)
    await db_session.flush()
    tool.current_version_id = version.id

    smiles_path = tmp_path / "molecules.csv"
    smiles_content = b"smiles,id\nCCO,mol_1\n"
    smiles_path.write_bytes(smiles_content)
    smiles_file = file_record(
        owner=user,
        filename="molecules.csv",
        content=smiles_content,
        storage_path=str(smiles_path),
        content_type="text/csv",
    )
    db_session.add(smiles_file)
    await db_session.flush()

    run = AgentRun(
        user_id=user.id,
        message="预测 ADMET",
        intent="predict_dynamic_admet",
        status="pending",
        input_type="smiles_csv",
        input_file_id=smiles_file.id,
        requested_outputs=["property_report"],
        plan={"input_files": {"smiles_csv": smiles_file.id}},
    )
    db_session.add(run)
    await db_session.flush()
    db_session.add(
        AgentRunStep(
            agent_run_id=run.id,
            step_key="property_prediction",
            tool_slug="dynamic-admet",
            status="pending",
            sort_order=0,
            semantic_inputs={"smiles_csv": "agent_input:smiles_csv"},
            params={},
        )
    )
    await db_session.commit()

    scheduled_payloads = []

    async def fake_create_task(*, db, current_user, task_data, direct_runner=None):
        scheduled_payloads.append(task_data)
        return SimpleNamespace(id="task-dynamic-admet", tool_id=task_data.tool_id)

    monkeypatch.setattr(
        "app.agents.aidd.service.create_and_schedule_tool_task",
        fake_create_task,
    )

    count = await start_ready_steps(db_session, current_user=user, run_id=run.id)

    refreshed_run = await db_session.get(AgentRun, run.id)
    dynamic_step = next(step for step in refreshed_run.steps if step.step_key == "property_prediction")
    assert count == 1
    assert dynamic_step.status == "waiting_task"
    assert dynamic_step.task_id == "task-dynamic-admet"
    assert scheduled_payloads[0].file_ids == [smiles_file.id]
    assert scheduled_payloads[0].params == {
        "device": "cpu",
        "input_files": {"smiles_csv": "input/molecules.csv"},
    }


@pytest.mark.asyncio
async def test_dynamic_agent_capability_extracts_semantic_outputs(
    db_session: AsyncSession,
    user: User,
    tmp_path: Path,
) -> None:
    tool = Tool(
        owner_id=user.id,
        name="Dynamic ADMET",
        slug="dynamic-admet",
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    db_session.add(tool)
    await db_session.flush()
    version = ToolVersion(
        tool_id=tool.id,
        version="1.0.0",
        config={
            "type": "ssh_job",
            "agent_capability": {
                "enabled": True,
                "capability": "property_prediction",
                "stage": "property_prediction",
                "inputs": [{"semantic_type": "smiles_csv", "field": "smiles_csv"}],
                "outputs": [
                    {
                        "semantic_type": "property_report",
                        "source": "output_files",
                        "match": {"extension": ".csv", "filename_contains_any": ["admet"]},
                    }
                ],
            },
        },
        is_active=True,
    )
    db_session.add(version)
    await db_session.flush()
    tool.current_version_id = version.id

    output_path = tmp_path / "admet_results.csv"
    output_content = b"smiles,qed\nCCO,0.7\n"
    output_path.write_bytes(output_content)
    output_file = file_record(
        owner=user,
        filename="admet_results.csv",
        content=output_content,
        storage_path=str(output_path),
        content_type="text/csv",
        source_type=FileSourceType.TOOL_OUTPUT.value,
    )
    db_session.add(output_file)
    await db_session.flush()

    task = Task(
        user_id=user.id,
        tool_id=tool.id,
        tool_version_id=version.id,
        status=TaskStatus.SUCCESS.value,
    )
    db_session.add(task)
    await db_session.flush()
    db_session.add(TaskOutput(task_id=task.id, result={}, file_ids=[output_file.id], output_type="file"))

    run = AgentRun(
        user_id=user.id,
        message="预测 ADMET",
        intent="predict_dynamic_admet",
        status="waiting_task",
        input_type="smiles_csv",
        requested_outputs=["property_report"],
        plan={},
    )
    db_session.add(run)
    await db_session.flush()
    db_session.add(
        AgentRunStep(
            agent_run_id=run.id,
            step_key="property_prediction",
            tool_slug="dynamic-admet",
            tool_id=tool.id,
            task_id=task.id,
            status="waiting_task",
            sort_order=0,
        )
    )
    await db_session.commit()

    count = await reconcile_waiting_agent_steps(db_session, run_id=run.id)

    refreshed_run = await db_session.get(AgentRun, run.id)
    dynamic_step = next(step for step in refreshed_run.steps if step.step_key == "property_prediction")
    assert count == 1
    assert dynamic_step.status == "success"
    assert dynamic_step.semantic_outputs["property_report"]["file_id"] == output_file.id


@pytest.mark.asyncio
async def test_failed_step_replans_downstream_to_uploaded_fallback_input(
    db_session: AsyncSession,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lvpocket = await create_tool(
        db_session,
        user,
        slug="lvpocket-pocket-prediction",
        name="LVpocket",
    )
    await create_tool(
        db_session,
        user,
        slug="gcdm-pocket-generation",
        name="STD-Diff",
    )

    protein_file = file_record(
        owner=user,
        filename="protein.pdb",
        content=b"protein",
        storage_path="/tmp/protein.pdb",
    )
    pocket_file = file_record(
        owner=user,
        filename="backup_pocket.pdb",
        content=b"pocket",
        storage_path="/tmp/backup_pocket.pdb",
    )
    db_session.add_all([protein_file, pocket_file])
    await db_session.flush()

    failed_task = Task(
        user_id=user.id,
        tool_id=lvpocket.id,
        tool_version_id=lvpocket.current_version_id,
        status=TaskStatus.FAILURE.value,
        error_message="pocket model failed",
    )
    db_session.add(failed_task)
    await db_session.flush()

    run = AgentRun(
        user_id=user.id,
        message="优先预测口袋，失败时用上传口袋继续生成",
        intent="generate_molecules_from_protein",
        status="waiting_task",
        input_type="protein_pdb",
        input_file_id=protein_file.id,
        requested_outputs=["generated_ligand"],
        plan={
            "input_files": {
                "protein_pdb": protein_file.id,
                "pocket_pdb": pocket_file.id,
            }
        },
    )
    db_session.add(run)
    await db_session.flush()
    db_session.add_all(
        [
            AgentRunStep(
                agent_run_id=run.id,
                step_key="pocket_prediction",
                tool_slug="lvpocket-pocket-prediction",
                tool_id=lvpocket.id,
                task_id=failed_task.id,
                status="waiting_task",
                sort_order=0,
            ),
            AgentRunStep(
                agent_run_id=run.id,
                step_key="molecule_generation",
                tool_slug="gcdm-pocket-generation",
                status="pending",
                sort_order=1,
                depends_on_step_ids=["pocket_prediction"],
                semantic_inputs={"pocket_pdb": "step:pocket_prediction:pocket_pdb"},
            ),
        ]
    )
    await db_session.commit()

    scheduled_payloads = []

    async def fake_create_task(*, db, current_user, task_data, direct_runner=None):
        scheduled_payloads.append(task_data)
        return SimpleNamespace(id="task-generation-fallback", tool_id=task_data.tool_id)

    monkeypatch.setattr(
        "app.agents.aidd.service.create_and_schedule_tool_task",
        fake_create_task,
    )

    count = await reconcile_waiting_agent_steps(db_session, run_id=run.id)

    assert count == 1
    refreshed_run = await db_session.get(AgentRun, run.id)
    failed_step = next(step for step in refreshed_run.steps if step.step_key == "pocket_prediction")
    generation_step = next(step for step in refreshed_run.steps if step.step_key == "molecule_generation")
    assert refreshed_run.status == "waiting_task"
    assert failed_step.status == "skipped"
    assert "pocket model failed" in failed_step.error_message
    assert generation_step.depends_on_step_ids == []
    assert generation_step.semantic_inputs == {"pocket_pdb": "agent_input:pocket_pdb"}
    assert generation_step.status == "waiting_task"
    assert generation_step.task_id == "task-generation-fallback"
    assert scheduled_payloads[0].file_ids == [pocket_file.id]
