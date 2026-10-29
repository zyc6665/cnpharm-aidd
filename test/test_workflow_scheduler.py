"""Workflow scheduler tool availability tests."""

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

from app.common.exceptions import ValidationException  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.models import artifacts as _artifact_models  # noqa: F401,E402
from app.models import files as _files_models  # noqa: F401,E402
from app.models import statistics as _statistics_models  # noqa: F401,E402
from app.models import tasks as _task_models  # noqa: F401,E402
from app.models import tools as _tools_models  # noqa: F401,E402
from app.models import users as _users_models  # noqa: F401,E402
from app.models.files import File as FileModel, FileSourceType  # noqa: E402
from app.models.artifacts import Artifact as ArtifactModel  # noqa: E402
from app.models.artifacts import ArtifactVersion as ArtifactVersionModel  # noqa: E402
from app.models.artifacts import ArtifactVersionFile as ArtifactVersionFileModel  # noqa: E402
from app.models.tools import Tool, ToolProviderType, ToolStatus, ToolVersion  # noqa: E402
from app.services.workflow_loop_scheduler import schedule_loop_node  # noqa: E402
from app.services.workflow_map_scheduler import schedule_map_node  # noqa: E402
from app.services.workflow_tool_scheduler import schedule_workflow_node  # noqa: E402
from app.services.workflow_tool_lookup import load_available_workflow_tool  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def owner(db_session: AsyncSession) -> User:
    user = User(
        email="workflow-owner@example.com",
        password_hash="hashed-password",
        display_name="workflow-owner",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def _create_tool(
    db_session: AsyncSession,
    owner: User,
    *,
    slug: str,
    provider_type: str,
    executor_type: str,
    config: dict | None = None,
    is_public: bool = False,
    is_active: bool = True,
    deprecated: bool = False,
) -> Tool:
    tool = Tool(
        owner_id=owner.id,
        name=slug,
        slug=slug,
        status=ToolStatus.PUBLISHED.value,
        is_public=is_public,
        provider_type=provider_type,
    )
    db_session.add(tool)
    await db_session.flush()
    version = ToolVersion(
        tool_id=tool.id,
        version="1.0.0",
        config=config or {"type": executor_type},
        is_active=is_active,
        deprecated=deprecated,
    )
    db_session.add(version)
    await db_session.flush()
    tool.current_version_id = version.id
    await db_session.commit()
    return tool


async def _create_protein_artifact_version(
    db_session: AsyncSession,
    owner: User,
    *,
    name: str,
    roles: dict[str, FileModel],
    preparation_status: str,
) -> ArtifactVersionModel:
    artifact = ArtifactModel(
        project_id="project-1",
        created_by=owner.id,
        artifact_type="protein_structure",
        semantic_type="protein_structure",
        standard_type="protein_structure",
        standard_version=1,
        name=name,
    )
    db_session.add(artifact)
    await db_session.flush()
    version = ArtifactVersionModel(
        artifact_id=artifact.id,
        created_by=owner.id,
        version=1,
        filename=f"{name}.manifest.json",
        content_type="application/json",
        size_bytes=2,
        sha256=hashlib.sha256(name.encode()).hexdigest(),
        storage_key=f"legacy/{name}.manifest.json",
        validation_status="passed",
        validation_errors=[],
        manifest_json={
            "type": "protein_structure@1",
            "metadata": {"preparation_status": preparation_status},
        },
        summary_json={},
        metrics_json={},
    )
    db_session.add(version)
    await db_session.flush()
    for index, (role, file_record) in enumerate(roles.items()):
        db_session.add(
            ArtifactVersionFileModel(
                artifact_version_id=version.id,
                role=role,
                file_id=file_record.id,
                is_primary=index == 0,
                sort_order=index,
            )
        )
    artifact.latest_version_id = version.id
    await db_session.commit()
    return version


async def _create_artifact_version(
    db_session: AsyncSession,
    owner: User,
    *,
    name: str,
    type_ref: str,
    roles: dict[str, FileModel],
) -> ArtifactVersionModel:
    standard_type, version_text = type_ref.split("@", 1)
    artifact = ArtifactModel(
        project_id="project-1",
        created_by=owner.id,
        artifact_type=standard_type,
        semantic_type=standard_type,
        standard_type=standard_type,
        standard_version=int(version_text),
        name=name,
    )
    db_session.add(artifact)
    await db_session.flush()
    version = ArtifactVersionModel(
        artifact_id=artifact.id,
        created_by=owner.id,
        version=1,
        filename=f"{name}.manifest.json",
        content_type="application/json",
        size_bytes=2,
        sha256=hashlib.sha256(name.encode()).hexdigest(),
        storage_key=f"legacy/{name}.manifest.json",
        validation_status="passed",
        validation_errors=[],
        manifest_json={"type": type_ref, "metadata": {}},
        summary_json={},
        metrics_json={},
    )
    db_session.add(version)
    await db_session.flush()
    for index, (role, file_record) in enumerate(roles.items()):
        db_session.add(
            ArtifactVersionFileModel(
                artifact_version_id=version.id,
                role=role,
                file_id=file_record.id,
                is_primary=index == 0,
                sort_order=index,
            )
        )
    artifact.latest_version_id = version.id
    await db_session.commit()
    return version


async def _create_workflow_file(
    db_session: AsyncSession,
    owner: User,
    *,
    filename: str,
    content: bytes,
    content_type: str = "chemical/x-pdb",
) -> FileModel:
    file_record = FileModel(
        owner_id=owner.id,
        project_id="project-1",
        filename=filename,
        content_type=content_type,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        source_type=FileSourceType.TOOL_OUTPUT.value,
        storage_path=f"/tmp/{filename}",
        is_public=False,
    )
    db_session.add(file_record)
    await db_session.flush()
    return file_record


@pytest.mark.asyncio
async def test_private_platform_builtin_is_available_to_workflow(
    db_session: AsyncSession,
    owner: User,
) -> None:
    tool = await _create_tool(
        db_session,
        owner,
        slug="builtin-sdf-to-pdb",
        provider_type=ToolProviderType.PLATFORM.value,
        executor_type="builtin",
    )

    loaded = await load_available_workflow_tool(db_session, node={"tool_id": tool.id})

    assert loaded.id == tool.id


@pytest.mark.asyncio
async def test_private_user_tool_remains_unavailable_to_workflow(
    db_session: AsyncSession,
    owner: User,
) -> None:
    tool = await _create_tool(
        db_session,
        owner,
        slug="private-user-tool",
        provider_type=ToolProviderType.USER.value,
        executor_type="builtin",
    )

    with pytest.raises(ValidationException, match="Workflow tool is unavailable"):
        await load_available_workflow_tool(db_session, node={"tool_id": tool.id})


@pytest.mark.asyncio
async def test_deprecated_platform_builtin_is_unavailable_to_workflow(
    db_session: AsyncSession,
    owner: User,
) -> None:
    tool = await _create_tool(
        db_session,
        owner,
        slug="builtin-deprecated",
        provider_type=ToolProviderType.PLATFORM.value,
        executor_type="builtin",
        is_public=True,
        deprecated=True,
    )

    with pytest.raises(ValidationException, match="Workflow tool has no active version"):
        await load_available_workflow_tool(db_session, node={"tool_id": tool.id})


@pytest.mark.asyncio
async def test_builtin_workflow_node_receives_standard_artifact_inputs(
    db_session: AsyncSession,
    owner: User,
) -> None:
    protein_file = FileModel(
        owner_id=owner.id,
        filename="protein.pdb",
        content_type="chemical/x-pdb",
        size_bytes=7,
        sha256=hashlib.sha256(b"protein").hexdigest(),
        source_type=FileSourceType.UPLOAD.value,
        storage_path="/tmp/protein.pdb",
        is_public=False,
    )
    db_session.add(protein_file)
    await db_session.flush()
    tool = await _create_tool(
        db_session,
        owner,
        slug="builtin-protein-preparation",
        provider_type=ToolProviderType.PLATFORM.value,
        executor_type="builtin",
        config={
            "type": "builtin",
            "builtin_slug": "builtin-protein-preparation",
            "artifacts": {
                "inputs": [
                    {"name": "protein", "type": "protein_structure@1", "required": True}
                ],
                "outputs": [
                    {"name": "prepared_protein", "type": "protein_structure@1", "required": True}
                ],
            },
        },
    )
    run = SimpleNamespace(
        id="run-1",
        name="Protein Preparation Run",
        workflow_definition_id="workflow-1",
        project_id=None,
        input_files={"protein_structure@1": protein_file.id},
    )
    node = {
        "id": "protein_preparation",
        "kind": "tool",
        "tool_id": tool.id,
        "tool_slug": tool.slug,
        "artifact_input_slots": [
            {"name": "protein", "type": "protein_structure@1", "required": True}
        ],
        "artifact_inputs": {"protein": "workflow_input:protein_structure@1"},
        "params": {"options": {"ph": 7.4}},
    }
    scheduled: list[dict] = []

    async def fake_schedule_task(**kwargs):
        task_data = kwargs["task_data"]
        scheduled.append({"params": task_data.params, "file_ids": task_data.file_ids})
        return SimpleNamespace(id="task-1")

    node_states = {"protein_preparation": {"status": "pending"}}

    created = await schedule_workflow_node(
        db_session,
        current_user=owner,
        run=run,
        node_id="protein_preparation",
        node=node,
        node_states=node_states,
        schedule_task_fn=fake_schedule_task,
    )

    assert created is True
    assert scheduled[0]["file_ids"] == [protein_file.id]
    assert scheduled[0]["params"]["builtin_inputs"] == {
        "protein_structure@1": protein_file.id
    }
    assert node_states["protein_preparation"]["params"]["builtin_inputs"] == {
        "protein_structure@1": protein_file.id
    }


@pytest.mark.asyncio
async def test_builtin_workflow_node_receives_upstream_standard_artifact_input(
    db_session: AsyncSession,
    owner: User,
) -> None:
    prepared_file = FileModel(
        owner_id=owner.id,
        filename="prepared.pdb",
        content_type="chemical/x-pdb",
        size_bytes=8,
        sha256=hashlib.sha256(b"prepared").hexdigest(),
        source_type=FileSourceType.TOOL_OUTPUT.value,
        storage_path="/tmp/prepared.pdb",
        is_public=False,
    )
    db_session.add(prepared_file)
    await db_session.flush()
    tool = await _create_tool(
        db_session,
        owner,
        slug="builtin-vina-docking",
        provider_type=ToolProviderType.PLATFORM.value,
        executor_type="builtin",
        config={
            "type": "builtin",
            "builtin_slug": "builtin-vina-docking",
            "artifacts": {
                "inputs": [
                    {"name": "protein", "type": "protein_structure@1", "required": True}
                ],
                "outputs": [],
            },
        },
    )
    run = SimpleNamespace(
        id="run-1",
        name="Docking Run",
        workflow_definition_id="workflow-1",
        project_id=None,
        input_files={},
    )
    node = {
        "id": "docking",
        "kind": "tool",
        "tool_id": tool.id,
        "tool_slug": tool.slug,
        "artifact_input_slots": [
            {"name": "protein", "type": "protein_structure@1", "required": True}
        ],
        "artifact_inputs": {"protein": "node:protein_preparation:prepared_protein"},
    }
    node_states = {
        "docking": {"status": "pending"},
        "protein_preparation": {
            "status": "success",
            "standard_artifacts": {
                "file_ids_by_artifact_ref": {
                    "prepared_protein": [prepared_file.id],
                }
            },
        },
    }
    scheduled: list[dict] = []

    async def fake_schedule_task(**kwargs):
        task_data = kwargs["task_data"]
        scheduled.append({"params": task_data.params, "file_ids": task_data.file_ids})
        return SimpleNamespace(id="task-docking")

    created = await schedule_workflow_node(
        db_session,
        current_user=owner,
        run=run,
        node_id="docking",
        node=node,
        node_states=node_states,
        schedule_task_fn=fake_schedule_task,
    )

    assert created is True
    assert scheduled[0]["file_ids"] == [prepared_file.id]
    assert scheduled[0]["params"]["builtin_inputs"] == {
        "protein_structure@1": prepared_file.id
    }


@pytest.mark.asyncio
async def test_workflow_node_receives_upstream_standard_artifact_binding(
    db_session: AsyncSession,
    owner: User,
) -> None:
    pocket_file = FileModel(
        owner_id=owner.id,
        filename="pocket.json",
        content_type="application/json",
        size_bytes=2,
        sha256=hashlib.sha256(b"{}").hexdigest(),
        source_type=FileSourceType.TOOL_OUTPUT.value,
        storage_path="/tmp/pocket.json",
        is_public=False,
    )
    db_session.add(pocket_file)
    await db_session.flush()
    pocket_version = await _create_artifact_version(
        db_session,
        owner,
        name="pocket",
        type_ref="binding_pocket@1",
        roles={"pocket_metadata_json": pocket_file},
    )
    tool = await _create_tool(
        db_session,
        owner,
        slug="tool-package-pocket-generation",
        provider_type=ToolProviderType.USER.value,
        executor_type="ssh_job",
        is_public=True,
        config={
            "type": "ssh_job",
            "tool_package_manifest": {"api_version": "aidd.sciminer/tool-package"},
        },
    )
    run = SimpleNamespace(
        id="run-1",
        name="Generation Run",
        workflow_definition_id="workflow-1",
        project_id="project-1",
        input_files={},
    )
    node = {
        "id": "molecule_generation",
        "kind": "tool",
        "tool_id": tool.id,
        "tool_slug": tool.slug,
        "artifact_input_slots": [
            {"name": "pocket", "type": "binding_pocket@1", "required": True}
        ],
        "artifact_inputs": {"pocket": "node:pocket_prediction:pocket"},
    }
    node_states = {
        "molecule_generation": {"status": "pending"},
        "pocket_prediction": {
            "status": "success",
            "standard_artifacts": {
                "artifact_version_ids_by_ref": {"pocket": pocket_version.id},
                "file_ids_by_artifact_ref": {"pocket": [pocket_file.id]},
            },
        },
    }
    scheduled: list[dict] = []

    async def fake_schedule_task(**kwargs):
        task_data = kwargs["task_data"]
        scheduled.append(
            {
                "file_ids": task_data.file_ids,
                "input_bindings": task_data.input_bindings,
            }
        )
        return SimpleNamespace(id="task-generation")

    created = await schedule_workflow_node(
        db_session,
        current_user=owner,
        run=run,
        node_id="molecule_generation",
        node=node,
        node_states=node_states,
        schedule_task_fn=fake_schedule_task,
    )

    assert created is True
    assert scheduled[0]["file_ids"] == [pocket_file.id]
    assert scheduled[0]["input_bindings"] == {"pocket": pocket_version.id}
    assert node_states["molecule_generation"]["input_bindings"] == {
        "pocket": pocket_version.id
    }


@pytest.mark.asyncio
async def test_at003_molp_pc_node_receives_rdkit_properties_artifact_binding(
    db_session: AsyncSession,
    owner: User,
) -> None:
    table_file = await _create_workflow_file(
        db_session,
        owner,
        filename="rdkit_properties.csv",
        content=b"SMILES,MW\nCCO,46\n",
        content_type="text/csv",
    )
    metadata_file = await _create_workflow_file(
        db_session,
        owner,
        filename="rdkit_properties_metadata.json",
        content=b"{}",
        content_type="application/json",
    )
    properties_version = await _create_artifact_version(
        db_session,
        owner,
        name="rdkit-properties",
        type_ref="molecule_table@1",
        roles={"table_file": table_file, "metadata_json": metadata_file},
    )
    tool = await _create_tool(
        db_session,
        owner,
        slug="molp-pc-property-prediction",
        provider_type=ToolProviderType.USER.value,
        executor_type="ssh_job",
        is_public=True,
        config={
            "type": "ssh_job",
            "tool_package_manifest": {
                "api_version": "aidd.sciminer/tool-package",
                "metadata": {"slug": "molp-pc-property-prediction"},
            },
        },
    )
    run = SimpleNamespace(
        id="run-at003",
        name="AT-003 ADMET Run",
        workflow_definition_id="workflow-at003",
        project_id="project-1",
        input_files={},
    )
    node = {
        "id": "molp_pc_admet",
        "kind": "tool",
        "tool_id": tool.id,
        "tool_slug": tool.slug,
        "artifact_input_slots": [
            {"name": "molecules", "type": "molecule_table@1", "required": True}
        ],
        "artifact_inputs": {"molecules": "node:rdkit_properties:properties"},
    }
    node_states = {
        "molp_pc_admet": {"status": "pending"},
        "rdkit_properties": {
            "status": "success",
            "standard_artifacts": {
                "artifact_version_ids_by_ref": {"properties": properties_version.id},
                "file_ids_by_artifact_ref": {
                    "properties": [table_file.id, metadata_file.id],
                },
            },
        },
    }
    scheduled: list[dict] = []

    async def fake_schedule_task(**kwargs):
        task_data = kwargs["task_data"]
        scheduled.append(
            {
                "file_ids": task_data.file_ids,
                "input_bindings": task_data.input_bindings,
                "params": task_data.params,
            }
        )
        return SimpleNamespace(id="task-molp-pc")

    created = await schedule_workflow_node(
        db_session,
        current_user=owner,
        run=run,
        node_id="molp_pc_admet",
        node=node,
        node_states=node_states,
        schedule_task_fn=fake_schedule_task,
    )

    assert created is True
    assert scheduled[0]["file_ids"] == [table_file.id, metadata_file.id]
    assert scheduled[0]["input_bindings"] == {"molecules": properties_version.id}
    assert scheduled[0]["params"]["workflow_node_type"] == "tool"
    assert node_states["molp_pc_admet"]["input_bindings"] == {
        "molecules": properties_version.id
    }


@pytest.mark.asyncio
async def test_workflow_node_binds_first_cardinality_many_standard_artifact(
    db_session: AsyncSession,
    owner: User,
) -> None:
    ligand_file = FileModel(
        owner_id=owner.id,
        filename="generated.sdf",
        content_type="chemical/x-mdl-sdfile",
        size_bytes=8,
        sha256=hashlib.sha256(b"ligand").hexdigest(),
        source_type=FileSourceType.TOOL_OUTPUT.value,
        storage_path="/tmp/generated.sdf",
        is_public=False,
    )
    db_session.add(ligand_file)
    await db_session.flush()
    ligand_version = await _create_artifact_version(
        db_session,
        owner,
        name="generated-ligand",
        type_ref="ligand_structure@1",
        roles={"structure_file": ligand_file},
    )
    tool = await _create_tool(
        db_session,
        owner,
        slug="tool-package-affinity",
        provider_type=ToolProviderType.USER.value,
        executor_type="ssh_job",
        is_public=True,
        config={
            "type": "ssh_job",
            "tool_package_manifest": {"api_version": "aidd.sciminer/tool-package"},
        },
    )
    run = SimpleNamespace(
        id="run-affinity",
        name="Affinity Run",
        workflow_definition_id="workflow-1",
        project_id="project-1",
        input_files={},
    )
    node = {
        "id": "affinity_prediction",
        "kind": "tool",
        "tool_id": tool.id,
        "tool_slug": tool.slug,
        "artifact_input_slots": [
            {"name": "ligand", "type": "ligand_structure@1", "required": True}
        ],
        "artifact_inputs": {"ligand": "node:molecule_generation:ligands"},
    }
    node_states = {
        "affinity_prediction": {"status": "pending"},
        "molecule_generation": {
            "status": "success",
            "standard_artifacts": {
                "artifact_version_ids_by_ref": {"ligands[0]": ligand_version.id},
                "file_ids_by_artifact_ref": {"ligands[0]": [ligand_file.id]},
            },
        },
    }
    scheduled: list[dict] = []

    async def fake_schedule_task(**kwargs):
        task_data = kwargs["task_data"]
        scheduled.append(
            {
                "file_ids": task_data.file_ids,
                "input_bindings": task_data.input_bindings,
            }
        )
        return SimpleNamespace(id="task-affinity")

    created = await schedule_workflow_node(
        db_session,
        current_user=owner,
        run=run,
        node_id="affinity_prediction",
        node=node,
        node_states=node_states,
        schedule_task_fn=fake_schedule_task,
    )

    assert created is True
    assert scheduled[0]["file_ids"] == [ligand_file.id]
    assert scheduled[0]["input_bindings"] == {"ligand": ligand_version.id}
    assert node_states["affinity_prediction"]["input_bindings"] == {
        "ligand": ligand_version.id
    }


@pytest.mark.asyncio
async def test_map_node_passes_standard_artifact_bindings_to_each_subtask(
    db_session: AsyncSession,
    owner: User,
) -> None:
    pocket_file = await _create_workflow_file(
        db_session,
        owner,
        filename="pocket.json",
        content=b"{}",
        content_type="application/json",
    )
    pocket_version = await _create_artifact_version(
        db_session,
        owner,
        name="binding-pocket",
        type_ref="binding_pocket@1",
        roles={"pocket_metadata_json": pocket_file},
    )
    tool = await _create_tool(
        db_session,
        owner,
        slug="tool-package-map-scoring",
        provider_type=ToolProviderType.USER.value,
        executor_type="ssh_job",
        is_public=True,
        config={
            "type": "ssh_job",
            "tool_package_manifest": {"api_version": "aidd.sciminer/tool-package"},
        },
    )
    run = SimpleNamespace(
        id="run-map",
        name="Map Run",
        workflow_definition_id="workflow-1",
        project_id="project-1",
        input_files={"items": ["ligand-a", "ligand-b"]},
    )
    node = {
        "id": "map_score",
        "kind": "map",
        "over": "workflow_input:items",
        "max_parallelism": 5,
        "tool_id": tool.id,
        "tool_slug": tool.slug,
        "artifact_input_slots": [
            {"name": "pocket", "type": "binding_pocket@1", "required": True}
        ],
        "artifact_inputs": {"pocket": "node:pocket_detection:pocket"},
    }
    node_states = {
        "map_score": {"status": "pending"},
        "pocket_detection": {
            "status": "success",
            "standard_artifacts": {
                "artifact_version_ids_by_ref": {"pocket": pocket_version.id},
                "file_ids_by_artifact_ref": {"pocket": [pocket_file.id]},
            },
        },
    }
    scheduled: list[dict] = []

    async def fake_schedule_task(**kwargs):
        task_data = kwargs["task_data"]
        scheduled.append(
            {
                "file_ids": task_data.file_ids,
                "input_bindings": task_data.input_bindings,
                "params": task_data.params,
            }
        )
        return SimpleNamespace(id=f"task-{len(scheduled)}")

    created = await schedule_map_node(
        db_session,
        current_user=owner,
        run=run,
        node_id="map_score",
        node=node,
        node_states=node_states,
        schedule_task_fn=fake_schedule_task,
    )

    assert created is True
    assert len(scheduled) == 2
    assert scheduled[0]["file_ids"] == [pocket_file.id]
    assert scheduled[0]["input_bindings"] == {"pocket": pocket_version.id}
    assert scheduled[1]["input_bindings"] == {"pocket": pocket_version.id}
    assert scheduled[0]["params"]["workflow_node_id"] == "map_score[0]"
    assert scheduled[1]["params"]["workflow_node_id"] == "map_score[1]"


@pytest.mark.asyncio
async def test_loop_node_passes_standard_artifact_bindings_to_body_tasks(
    db_session: AsyncSession,
    owner: User,
) -> None:
    pocket_file = await _create_workflow_file(
        db_session,
        owner,
        filename="loop-pocket.json",
        content=b"{}",
        content_type="application/json",
    )
    pocket_version = await _create_artifact_version(
        db_session,
        owner,
        name="loop-binding-pocket",
        type_ref="binding_pocket@1",
        roles={"pocket_metadata_json": pocket_file},
    )
    tool = await _create_tool(
        db_session,
        owner,
        slug="tool-package-loop-scoring",
        provider_type=ToolProviderType.USER.value,
        executor_type="ssh_job",
        is_public=True,
        config={
            "type": "ssh_job",
            "tool_package_manifest": {"api_version": "aidd.sciminer/tool-package"},
        },
    )
    run = SimpleNamespace(
        id="run-loop",
        name="Loop Run",
        workflow_definition_id="workflow-1",
        project_id="project-1",
        input_files={},
    )
    node = {
        "id": "loop_score",
        "kind": "loop",
        "max_iterations": 3,
        "artifact_input_slots": [
            {"name": "pocket", "type": "binding_pocket@1", "required": True}
        ],
        "artifact_inputs": {"pocket": "node:pocket_detection:pocket"},
        "body": [
            {
                "id": "score",
                "kind": "tool",
                "tool_id": tool.id,
                "tool_slug": tool.slug,
            }
        ],
    }
    node_states = {
        "loop_score": {"status": "pending"},
        "pocket_detection": {
            "status": "success",
            "standard_artifacts": {
                "artifact_version_ids_by_ref": {"pocket": pocket_version.id},
                "file_ids_by_artifact_ref": {"pocket": [pocket_file.id]},
            },
        },
    }
    scheduled: list[dict] = []

    async def fake_schedule_task(**kwargs):
        task_data = kwargs["task_data"]
        scheduled.append(
            {
                "file_ids": task_data.file_ids,
                "input_bindings": task_data.input_bindings,
                "params": task_data.params,
            }
        )
        return SimpleNamespace(id="task-loop-score")

    created = await schedule_loop_node(
        db_session,
        current_user=owner,
        run=run,
        node_id="loop_score",
        node=node,
        node_states=node_states,
        schedule_task_fn=fake_schedule_task,
    )

    assert created is True
    assert scheduled[0]["file_ids"] == [pocket_file.id]
    assert scheduled[0]["input_bindings"] == {"pocket": pocket_version.id}
    assert scheduled[0]["params"]["workflow_node_id"] == "loop_score/score[1]"
    assert node_states["loop_score"]["input_bindings"] == {"pocket": pocket_version.id}


@pytest.mark.asyncio
async def test_role_aware_artifact_input_blocks_raw_protein_when_prepared_required(
    db_session: AsyncSession,
    owner: User,
) -> None:
    raw_file = await _create_workflow_file(
        db_session,
        owner,
        filename="raw.pdb",
        content=b"ATOM raw\n",
    )
    raw_version = await _create_protein_artifact_version(
        db_session,
        owner,
        name="raw-protein",
        roles={"structure_file": raw_file},
        preparation_status="raw",
    )
    tool = await _create_tool(
        db_session,
        owner,
        slug="prepared-only-tool",
        provider_type=ToolProviderType.USER.value,
        executor_type="ssh_job",
        is_public=True,
        config={
            "type": "ssh_job",
            "artifacts": {
                "inputs": [
                    {
                        "name": "protein",
                        "type": "protein_structure@1",
                        "required": True,
                        "readiness_policy": "require_prepared",
                    }
                ],
                "outputs": [],
            },
        },
    )
    run = SimpleNamespace(
        id="run-raw",
        name="Raw Binding Run",
        workflow_definition_id="workflow-1",
        project_id="project-1",
        input_files={},
    )
    node = {
        "id": "prepared_required",
        "kind": "tool",
        "tool_id": tool.id,
        "tool_slug": tool.slug,
        "artifact_input_slots": [
            {
                "name": "protein",
                "type": "protein_structure@1",
                "required": True,
                "readiness_policy": "require_prepared",
            }
        ],
        "artifact_inputs": {"protein": "node:fetch_pdb:protein"},
    }
    node_states = {
        "prepared_required": {"status": "pending"},
        "fetch_pdb": {
            "status": "success",
            "standard_artifacts": {
                "artifact_version_ids_by_ref": {"protein": raw_version.id},
                "file_ids_by_artifact_ref": {"protein": [raw_file.id]},
            },
        },
    }
    scheduled: list[dict] = []

    async def fake_schedule_task(**kwargs):
        scheduled.append(kwargs)
        return SimpleNamespace(id="task-should-not-create")

    created = await schedule_workflow_node(
        db_session,
        current_user=owner,
        run=run,
        node_id="prepared_required",
        node=node,
        node_states=node_states,
        schedule_task_fn=fake_schedule_task,
    )

    assert created is False
    assert scheduled == []
    assert node_states["prepared_required"]["status"] == "blocked"
    assert node_states["prepared_required"]["binding_decisions"]["protein"]["status"] == (
        "needs_preparation"
    )
    assert node_states["prepared_required"]["binding_decisions"]["protein"][
        "suggested_tool_slug"
    ] == "builtin-protein-preparation"


@pytest.mark.asyncio
async def test_role_aware_artifact_input_schedules_selected_prepared_role_only(
    db_session: AsyncSession,
    owner: User,
) -> None:
    raw_file = await _create_workflow_file(
        db_session,
        owner,
        filename="raw.pdb",
        content=b"ATOM raw\n",
    )
    prepared_file = await _create_workflow_file(
        db_session,
        owner,
        filename="prepared.pdb",
        content=b"ATOM prepared\n",
    )
    prepared_version = await _create_protein_artifact_version(
        db_session,
        owner,
        name="prepared-protein",
        roles={"structure_file": raw_file, "prepared_pdb": prepared_file},
        preparation_status="prepared",
    )
    tool = await _create_tool(
        db_session,
        owner,
        slug="prepared-role-tool",
        provider_type=ToolProviderType.USER.value,
        executor_type="ssh_job",
        is_public=True,
        config={
            "type": "ssh_job",
            "input_schema": {
                "type": "object",
                "properties": {
                    "protein_pdb": {"type": "string", "format": "file"},
                    "device": {"type": "string"},
                },
            },
        },
    )
    run = SimpleNamespace(
        id="run-prepared",
        name="Prepared Binding Run",
        workflow_definition_id="workflow-1",
        project_id="project-1",
        input_files={},
    )
    node = {
        "id": "prepared_required",
        "kind": "tool",
        "tool_id": tool.id,
        "tool_slug": tool.slug,
        "artifact_input_slots": [
            {
                "name": "protein",
                "type": "protein_structure@1",
                "required": True,
                "readiness_policy": "require_prepared",
            }
        ],
        "artifact_inputs": {"protein": "node:protein_preparation:prepared_protein"},
    }
    node_states = {
        "prepared_required": {"status": "pending"},
        "protein_preparation": {
            "status": "success",
            "standard_artifacts": {
                "artifact_version_ids_by_ref": {"prepared_protein": prepared_version.id},
                "file_ids_by_artifact_ref": {
                    "prepared_protein": [raw_file.id, prepared_file.id],
                },
            },
        },
    }
    scheduled: list[dict] = []

    async def fake_schedule_task(**kwargs):
        task_data = kwargs["task_data"]
        scheduled.append(
            {
                "file_ids": task_data.file_ids,
                "params": task_data.params,
                "input_bindings": task_data.input_bindings,
            }
        )
        return SimpleNamespace(id="task-prepared")

    created = await schedule_workflow_node(
        db_session,
        current_user=owner,
        run=run,
        node_id="prepared_required",
        node=node,
        node_states=node_states,
        schedule_task_fn=fake_schedule_task,
    )

    assert created is True
    assert scheduled[0]["file_ids"] == [prepared_file.id]
    assert scheduled[0]["input_bindings"] == {}
    assert scheduled[0]["params"]["input_files"] == {
        "protein_pdb": "input/prepared.pdb"
    }
    assert node_states["prepared_required"]["input_file_ids"] == [prepared_file.id]
    assert node_states["prepared_required"]["input_bindings"] == {}
    assert node_states["prepared_required"]["binding_decisions"]["protein"]["status"] == "ready"
    assert node_states["prepared_required"]["binding_decisions"]["protein"]["selected_role"] == (
        "prepared_pdb"
    )
