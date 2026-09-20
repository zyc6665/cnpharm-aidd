"""Run preparation module regression tests."""

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

from app.database.base import Base  # noqa: E402
from app.models import (  # noqa: E402,F401
    Artifact,
    ArtifactVersion,
    ArtifactVersionFile,
    File,
    Organization,
    Project,
    Tool,
    ToolVersion,
    User,
)
from app.models.artifacts import Artifact as ArtifactModel  # noqa: E402
from app.models.artifacts import ArtifactVersion as ArtifactVersionModel  # noqa: E402
from app.models.artifacts import ArtifactVersionFile as ArtifactVersionFileModel  # noqa: E402
from app.models.files import File as FileModel  # noqa: E402
from app.models.files import FileSourceType  # noqa: E402
from app.models.tools import Tool as ToolModel  # noqa: E402
from app.models.tools import ToolProviderType, ToolStatus  # noqa: E402
from app.models.tools import ToolVersion as ToolVersionModel  # noqa: E402
from app.models.users import User as UserModel  # noqa: E402
from app.models.users import UserRole, UserStatus  # noqa: E402
from app.services.run_preparation import (  # noqa: E402
    RunContext,
    RunPreparationInput,
    prepare_workflow_node_run,
    prepare_run,
)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    await engine.dispose()


async def _create_owner(db: AsyncSession) -> UserModel:
    owner = UserModel(
        email="run-preparation@example.com",
        password_hash="hashed-password",
        display_name="Run Preparation Owner",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db.add(owner)
    await db.flush()
    return owner


async def _create_tool(
    db: AsyncSession,
    owner: UserModel,
    *,
    slug: str,
    config: dict,
    provider_type: str = ToolProviderType.USER.value,
) -> tuple[ToolModel, ToolVersionModel]:
    tool = ToolModel(
        owner_id=owner.id,
        name=slug,
        slug=slug,
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
        provider_type=provider_type,
    )
    db.add(tool)
    await db.flush()
    version = ToolVersionModel(
        tool_id=tool.id,
        version="1.0.0",
        config=config,
        is_active=True,
        deprecated=False,
    )
    db.add(version)
    await db.flush()
    tool.current_version_id = version.id
    tool.current_version = version
    await db.flush()
    return tool, version


async def _create_file(
    db: AsyncSession,
    owner: UserModel,
    *,
    filename: str,
    content: bytes,
) -> FileModel:
    file_record = FileModel(
        owner_id=owner.id,
        project_id="project-1",
        filename=filename,
        content_type="chemical/x-pdb",
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        storage_path=f"/tmp/{filename}",
        source_type=FileSourceType.TOOL_OUTPUT.value,
    )
    db.add(file_record)
    await db.flush()
    return file_record


async def _create_protein_version(
    db: AsyncSession,
    owner: UserModel,
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
    db.add(artifact)
    await db.flush()

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
    db.add(version)
    await db.flush()

    for index, (role, file_record) in enumerate(roles.items()):
        db.add(
            ArtifactVersionFileModel(
                artifact_version_id=version.id,
                role=role,
                file_id=file_record.id,
                is_primary=index == 0,
                sort_order=index,
            )
        )
    artifact.latest_version_id = version.id
    await db.flush()
    return version


def _prepared_only_ssh_config() -> dict:
    return {
        "type": "ssh_job",
        "input_schema": {
            "type": "object",
            "properties": {
                "protein_pdb": {"type": "string", "format": "file"},
                "device": {"type": "string"},
            },
        },
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
    }


def _two_protein_ssh_config() -> dict:
    return {
        "type": "ssh_job",
        "input_schema": {
            "type": "object",
            "properties": {
                "protein_a_pdb": {"type": "string", "format": "file"},
                "protein_b_pdb": {"type": "string", "format": "file"},
            },
        },
        "artifacts": {
            "inputs": [
                {
                    "name": "protein_a",
                    "type": "protein_structure@1",
                    "required": True,
                    "role_preferences": ["structure_file"],
                },
                {
                    "name": "protein_b",
                    "type": "protein_structure@1",
                    "required": True,
                    "role_preferences": ["structure_file"],
                },
            ],
            "outputs": [],
        },
    }


def _plain_protein_ssh_config() -> dict:
    return {
        "type": "ssh_job",
        "input_schema": {
            "type": "object",
            "properties": {
                "protein_pdb": {"type": "string", "format": "file"},
            },
        },
        "artifacts": {
            "inputs": [
                {
                    "name": "protein",
                    "type": "protein_structure@1",
                    "required": True,
                }
            ],
            "outputs": [],
        },
    }


@pytest.mark.asyncio
async def test_prepare_run_projects_multiple_standard_inputs_to_distinct_legacy_fields(
    db_session: AsyncSession,
) -> None:
    owner = await _create_owner(db_session)
    protein_a_file = await _create_file(
        db_session,
        owner,
        filename="protein-a.pdb",
        content=b"ATOM protein a\n",
    )
    protein_b_file = await _create_file(
        db_session,
        owner,
        filename="protein-b.pdb",
        content=b"ATOM protein b\n",
    )
    protein_a_version = await _create_protein_version(
        db_session,
        owner,
        name="protein-a",
        roles={"structure_file": protein_a_file},
        preparation_status="raw",
    )
    protein_b_version = await _create_protein_version(
        db_session,
        owner,
        name="protein-b",
        roles={"structure_file": protein_b_file},
        preparation_status="raw",
    )
    tool, version = await _create_tool(
        db_session,
        owner,
        slug="two-protein-ssh",
        config=_two_protein_ssh_config(),
    )

    prepared = await prepare_run(
        db_session,
        input=RunPreparationInput(
            tool=tool,
            tool_version=version,
            context=RunContext(
                surface="tool_detail",
                user_id=str(owner.id),
                project_id="project-1",
            ),
            params={},
            file_ids=[],
            input_bindings={
                "protein_a": protein_a_version.id,
                "protein_b": protein_b_version.id,
            },
            standard_input_uploads={},
        ),
    )

    assert prepared.ready is True
    assert prepared.params["input_files"] == {
        "protein_a_pdb": "input/protein-a.pdb",
        "protein_b_pdb": "input/protein-b.pdb",
    }


@pytest.mark.asyncio
async def test_tool_detail_and_workflow_node_prepare_same_legacy_artifact_binding(
    db_session: AsyncSession,
) -> None:
    owner = await _create_owner(db_session)
    protein_file = await _create_file(
        db_session,
        owner,
        filename="shared-protein.pdb",
        content=b"ATOM shared\n",
    )
    protein_version = await _create_protein_version(
        db_session,
        owner,
        name="shared-protein",
        roles={"structure_file": protein_file},
        preparation_status="raw",
    )
    tool, version = await _create_tool(
        db_session,
        owner,
        slug="plain-protein-ssh",
        config=_plain_protein_ssh_config(),
    )
    run = SimpleNamespace(
        id="run-1",
        workflow_definition_id="workflow-1",
        project_id="project-1",
        input_files={},
    )
    node = {
        "id": "plain_protein",
        "kind": "tool",
        "artifact_input_slots": [
            {
                "name": "protein",
                "type": "protein_structure@1",
                "required": True,
            }
        ],
        "artifact_inputs": {"protein": "node:upstream:protein"},
    }

    direct = await prepare_run(
        db_session,
        input=RunPreparationInput(
            tool=tool,
            tool_version=version,
            context=RunContext(
                surface="tool_detail",
                user_id=str(owner.id),
                project_id="project-1",
            ),
            params={},
            file_ids=[],
            input_bindings={"protein": protein_version.id},
            standard_input_uploads={},
        ),
    )
    workflow = await prepare_workflow_node_run(
        db_session,
        run=run,
        node_id="plain_protein",
        node=node,
        node_states={
            "upstream": {
                "status": "success",
                "standard_artifacts": {
                    "artifact_version_ids_by_ref": {"protein": protein_version.id},
                    "file_ids_by_artifact_ref": {"protein": [protein_file.id]},
                },
            }
        },
        tool=tool,
        current_user=owner,
        params={},
    )

    assert workflow is not None
    assert direct == workflow
    assert direct.file_ids == [protein_file.id]
    assert direct.params["input_files"] == {"protein_pdb": "input/shared-protein.pdb"}


@pytest.mark.asyncio
async def test_prepare_run_projects_prepared_artifact_to_legacy_ssh_input(
    db_session: AsyncSession,
) -> None:
    owner = await _create_owner(db_session)
    raw_file = await _create_file(db_session, owner, filename="raw.pdb", content=b"ATOM raw\n")
    prepared_file = await _create_file(
        db_session,
        owner,
        filename="prepared.pdb",
        content=b"ATOM prepared\n",
    )
    protein_version = await _create_protein_version(
        db_session,
        owner,
        name="prepared-protein",
        roles={"structure_file": raw_file, "prepared_pdb": prepared_file},
        preparation_status="prepared",
    )
    tool, version = await _create_tool(
        db_session,
        owner,
        slug="prepared-only-ssh",
        config=_prepared_only_ssh_config(),
    )

    prepared = await prepare_run(
        db_session,
        input=RunPreparationInput(
            tool=tool,
            tool_version=version,
            context=RunContext(
                surface="tool_detail",
                user_id=str(owner.id),
                project_id="project-1",
            ),
            params={"params": {"device": "cpu"}},
            file_ids=[],
            input_bindings={"protein": protein_version.id},
            standard_input_uploads={},
        ),
    )

    assert prepared.ready is True
    assert prepared.input_bindings == {}
    assert prepared.file_ids == [prepared_file.id]
    assert prepared.params["input_files"] == {"protein_pdb": "input/prepared.pdb"}
    assert prepared.binding_decisions["protein"]["status"] == "ready"
    assert prepared.binding_decisions["protein"]["selected_role"] == "prepared_pdb"


@pytest.mark.asyncio
async def test_prepare_run_blocks_raw_artifact_when_prepared_role_required(
    db_session: AsyncSession,
) -> None:
    owner = await _create_owner(db_session)
    raw_file = await _create_file(db_session, owner, filename="raw.pdb", content=b"ATOM raw\n")
    protein_version = await _create_protein_version(
        db_session,
        owner,
        name="raw-protein",
        roles={"structure_file": raw_file},
        preparation_status="raw",
    )
    tool, version = await _create_tool(
        db_session,
        owner,
        slug="prepared-only-ssh-raw",
        config=_prepared_only_ssh_config(),
    )

    prepared = await prepare_run(
        db_session,
        input=RunPreparationInput(
            tool=tool,
            tool_version=version,
            context=RunContext(
                surface="tool_detail",
                user_id=str(owner.id),
                project_id="project-1",
            ),
            params={},
            file_ids=[],
            input_bindings={"protein": protein_version.id},
            standard_input_uploads={},
        ),
    )

    assert prepared.ready is False
    assert prepared.blocked_reason == "Protein input requires a prepared PDB role."
    assert prepared.file_ids == []
    assert prepared.binding_decisions["protein"]["status"] == "needs_preparation"
    assert prepared.binding_decisions["protein"]["suggested_tool_slug"] == "builtin-protein-preparation"


@pytest.mark.asyncio
async def test_prepare_run_projects_standard_upload_to_builtin_inputs(
    db_session: AsyncSession,
) -> None:
    owner = await _create_owner(db_session)
    protein_file = await _create_file(
        db_session,
        owner,
        filename="uploaded-protein.pdb",
        content=b"ATOM upload\n",
    )
    tool, version = await _create_tool(
        db_session,
        owner,
        slug="builtin-protein-preparation",
        provider_type=ToolProviderType.PLATFORM.value,
        config={
            "type": "builtin",
            "builtin_slug": "builtin-protein-preparation",
            "artifacts": {
                "inputs": [
                    {"name": "protein", "type": "protein_structure@1", "required": True}
                ],
                "outputs": [],
            },
        },
    )

    prepared = await prepare_run(
        db_session,
        input=RunPreparationInput(
            tool=tool,
            tool_version=version,
            context=RunContext(
                surface="tool_detail",
                user_id=str(owner.id),
                project_id="project-1",
            ),
            params={},
            file_ids=[],
            input_bindings={},
            standard_input_uploads={"protein": protein_file.id},
        ),
    )

    assert prepared.ready is True
    assert prepared.file_ids == [protein_file.id]
    assert prepared.standard_input_uploads == {"protein": protein_file.id}
    assert prepared.params["builtin_inputs"] == {"protein_structure@1": protein_file.id}


@pytest.mark.asyncio
async def test_prepare_run_keeps_standard_bindings_for_tool_package_v2(
    db_session: AsyncSession,
) -> None:
    owner = await _create_owner(db_session)
    protein_file = await _create_file(
        db_session,
        owner,
        filename="protein.pdb",
        content=b"ATOM protein\n",
    )
    protein_version = await _create_protein_version(
        db_session,
        owner,
        name="standard-protein",
        roles={"structure_file": protein_file},
        preparation_status="raw",
    )
    tool, version = await _create_tool(
        db_session,
        owner,
        slug="tool-package-v2-consumer",
        config={
            "type": "ssh_job",
            "tool_package_manifest": {
                "api_version": "aidd.sciminer/tool-package.v2",
                "kind": "ToolPackage",
                "metadata": {
                    "slug": "tool-package-v2-consumer",
                    "name": "Tool Package V2 Consumer",
                    "version": "1.0.0",
                },
                "artifacts": {
                    "inputs": [
                        {"name": "protein", "type": "protein_structure@1", "required": True}
                    ],
                    "outputs": [],
                },
                "parameters_schema": {"type": "object", "properties": {}},
                "runtime": {},
                "variants": [],
            },
        },
    )

    prepared = await prepare_run(
        db_session,
        input=RunPreparationInput(
            tool=tool,
            tool_version=version,
            context=RunContext(
                surface="tool_detail",
                user_id=str(owner.id),
                project_id="project-1",
            ),
            params={"params": {"threshold": 0.5}},
            file_ids=[],
            input_bindings={"protein": protein_version.id},
            standard_input_uploads={},
        ),
    )

    assert prepared.ready is True
    assert prepared.input_bindings == {"protein": protein_version.id}
    assert prepared.file_ids == []
    assert "input_files" not in prepared.params


@pytest.mark.asyncio
async def test_prepare_workflow_node_run_projects_workflow_input_to_builtin(
    db_session: AsyncSession,
) -> None:
    owner = await _create_owner(db_session)
    protein_file = await _create_file(
        db_session,
        owner,
        filename="workflow-protein.pdb",
        content=b"ATOM workflow\n",
    )
    tool, _version = await _create_tool(
        db_session,
        owner,
        slug="builtin-protein-preparation-workflow",
        provider_type=ToolProviderType.PLATFORM.value,
        config={
            "type": "builtin",
            "builtin_slug": "builtin-protein-preparation",
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
        workflow_definition_id="workflow-1",
        project_id=None,
        input_files={"protein_structure@1": protein_file.id},
    )
    node = {
        "id": "protein_preparation",
        "kind": "tool",
        "artifact_input_slots": [
            {"name": "protein", "type": "protein_structure@1", "required": True}
        ],
        "artifact_inputs": {"protein": "workflow_input:protein_structure@1"},
    }

    prepared = await prepare_workflow_node_run(
        db_session,
        run=run,
        node_id="protein_preparation",
        node=node,
        node_states={},
        tool=tool,
        current_user=owner,
        params={"workflow_node_type": "tool"},
    )

    assert prepared is not None
    assert prepared.ready is True
    assert prepared.file_ids == [protein_file.id]
    assert prepared.params["builtin_inputs"] == {"protein_structure@1": protein_file.id}
    assert prepared.input_bindings == {}


@pytest.mark.asyncio
async def test_prepare_workflow_node_run_projects_upstream_prepared_role_to_legacy_ssh(
    db_session: AsyncSession,
) -> None:
    owner = await _create_owner(db_session)
    raw_file = await _create_file(db_session, owner, filename="raw.pdb", content=b"ATOM raw\n")
    prepared_file = await _create_file(
        db_session,
        owner,
        filename="prepared.pdb",
        content=b"ATOM prepared\n",
    )
    protein_version = await _create_protein_version(
        db_session,
        owner,
        name="prepared-workflow-protein",
        roles={"structure_file": raw_file, "prepared_pdb": prepared_file},
        preparation_status="prepared",
    )
    tool, _version = await _create_tool(
        db_session,
        owner,
        slug="prepared-workflow-ssh",
        config=_prepared_only_ssh_config(),
    )
    run = SimpleNamespace(
        id="run-1",
        workflow_definition_id="workflow-1",
        project_id="project-1",
        input_files={},
    )
    node = {
        "id": "prepared_required",
        "kind": "tool",
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
        "protein_preparation": {
            "status": "success",
            "standard_artifacts": {
                "artifact_version_ids_by_ref": {"prepared_protein": protein_version.id},
                "file_ids_by_artifact_ref": {
                    "prepared_protein": [raw_file.id, prepared_file.id],
                },
            },
        }
    }

    prepared = await prepare_workflow_node_run(
        db_session,
        run=run,
        node_id="prepared_required",
        node=node,
        node_states=node_states,
        tool=tool,
        current_user=owner,
        params={"workflow_node_type": "tool"},
    )

    assert prepared is not None
    assert prepared.ready is True
    assert prepared.input_bindings == {}
    assert prepared.file_ids == [prepared_file.id]
    assert prepared.params["input_files"] == {"protein_pdb": "input/prepared.pdb"}
    assert prepared.binding_decisions["protein"]["selected_role"] == "prepared_pdb"
