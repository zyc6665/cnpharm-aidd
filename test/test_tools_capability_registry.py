"""AIDD dynamic tool capability registry tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.tools.capability_registry import load_available_tool_summaries, load_tool_capability  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.models import tools as _tools_models  # noqa: F401,E402
from app.models import users as _users_models  # noqa: F401,E402
from app.models.tools import Tool, ToolStatus, ToolVersion  # noqa: E402
from app.models.users import User, UserRole, UserStatus  # noqa: E402


def minimal_runtime_manifest(slug: str) -> dict:
    return {
        "python": "3.10",
        "executor_support": ["ssh_docker_exec"],
        "selection_policy": "test runtime fixture",
        "artifacts": {
            "primary": {
                "kind": "container",
                "image": f"registry.example/sciminer/{slug}:1.0.0",
                "image_digest": "sha256:test",
            },
            "fallback": {
                "kind": "conda_pack",
                "uri": f"artifacts://model-envs/{slug}/1.0.0/conda-env.tar.gz",
                "sha256": "test",
            },
        },
        "weights": {
            "manifest_uri": f"artifacts://model-weights/{slug}/1.0.0/weights.json",
            "manifest_sha256": "test",
        },
        "cache_policy": {
            "key_fields": ["metadata.slug", "metadata.version"],
            "mutable_host_paths_forbidden": True,
        },
    }


def _v2_manifest(*, agent_exposure: bool = True) -> dict:
    slug = "standard-pocket-tool"
    return {
        "api_version": "aidd.sciminer/tool-package.v2",
        "kind": "ToolPackage",
        "metadata": {
            "slug": slug,
            "name": "Standard Pocket Tool",
            "version": "1.0.0",
        },
        "artifacts": {
            "inputs": [{"name": "protein", "type": "protein_structure@1", "required": True}],
            "outputs": [
                {
                    "name": "pocket",
                    "type": "binding_pocket@1",
                    "cardinality": "one",
                    "required": True,
                }
            ],
        },
        "parameters_schema": {"type": "object"},
        "exposure": {"agent": agent_exposure, "workflow": True, "direct_run": True},
        "runtime": minimal_runtime_manifest(slug),
        "variants": [
            {
                "name": "cpu",
                "accelerator": "cpu",
                "executor_types": ["cli"],
                "entrypoint": ["/app/runner/entrypoint.sh"],
            }
        ],
    }


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
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(user_record)
    await db_session.commit()
    await db_session.refresh(user_record)
    return user_record


async def create_tool_with_agent_config(
    db_session: AsyncSession,
    owner: User,
    *,
    slug: str,
    status: str = ToolStatus.PUBLISHED.value,
    is_public: bool = True,
    version_active: bool = True,
    deprecated: bool = False,
    agent_enabled: bool = True,
) -> Tool:
    tool = Tool(
        owner_id=owner.id,
        name=slug,
        slug=slug,
        status=status,
        is_public=is_public,
    )
    db_session.add(tool)
    await db_session.flush()

    version = ToolVersion(
        tool_id=tool.id,
        version="1.0.0",
        config={
            "type": "ssh_job",
            "agent_capability": {
                "enabled": agent_enabled,
                "capability": "property_prediction",
                "stage": "property_prediction",
                "inputs": [
                    {
                        "semantic_type": "smiles_csv",
                        "field": "smiles_csv",
                        "accepted_extensions": [".csv"],
                    }
                ],
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
        is_active=version_active,
        deprecated=deprecated,
    )
    db_session.add(version)
    await db_session.flush()
    tool.current_version_id = version.id
    await db_session.commit()
    await db_session.refresh(tool)
    return tool


async def create_tool_with_v2_package_config(
    db_session: AsyncSession,
    owner: User,
    *,
    slug: str,
    agent_exposure: bool = True,
) -> Tool:
    tool = Tool(
        owner_id=owner.id,
        name=slug,
        slug=slug,
        status=ToolStatus.PUBLISHED.value,
        is_public=True,
    )
    db_session.add(tool)
    await db_session.flush()

    manifest = _v2_manifest(agent_exposure=agent_exposure)
    manifest["metadata"]["slug"] = slug
    manifest["runtime"] = minimal_runtime_manifest(slug)
    version = ToolVersion(
        tool_id=tool.id,
        version="1.0.0",
        config={"type": "python_script", "tool_package_manifest": manifest},
        is_active=True,
        deprecated=False,
    )
    db_session.add(version)
    await db_session.flush()
    tool.current_version_id = version.id
    await db_session.commit()
    await db_session.refresh(tool)
    return tool


@pytest.mark.asyncio
async def test_dynamic_agent_capability_is_discovered_from_tool_config(
    db_session: AsyncSession,
    user: User,
) -> None:
    await create_tool_with_agent_config(db_session, user, slug="dynamic-admet")

    summaries = await load_available_tool_summaries(db_session)
    dynamic = next(item for item in summaries if item["tool_slug"] == "dynamic-admet")

    assert dynamic["capability"] == "property_prediction"
    assert dynamic["inputs"] == ["molecule_table@1"]
    assert dynamic["outputs"] == ["run_report@1"]
    assert dynamic["defaults"] == {"device": "cpu"}
    assert dynamic["virtual"] is False


@pytest.mark.asyncio
async def test_v2_tool_package_contract_is_discovered_without_agent_capability(
    db_session: AsyncSession,
    user: User,
) -> None:
    await create_tool_with_v2_package_config(db_session, user, slug="standard-pocket-tool")

    summaries = await load_available_tool_summaries(db_session)
    summary = next(item for item in summaries if item["tool_slug"] == "standard-pocket-tool")

    assert summary["capability"] == "standard-pocket-tool"
    assert summary["inputs"] == ["protein_structure@1"]
    assert summary["outputs"] == ["binding_pocket@1"]
    assert summary["artifact_inputs"] == [
        {"name": "protein", "type": "protein_structure@1", "required": True}
    ]
    assert summary["artifact_outputs"][0]["name"] == "pocket"
    assert summary["exposure"]["agent"] is True


@pytest.mark.asyncio
async def test_v2_tool_package_capability_preserves_artifact_output_name(
    db_session: AsyncSession,
    user: User,
) -> None:
    await create_tool_with_v2_package_config(db_session, user, slug="standard-pocket-tool")

    capability = await load_tool_capability(db_session, "standard-pocket-tool")

    assert capability.outputs[0].source == "artifact"
    assert capability.outputs[0].semantic_type == "binding_pocket@1"
    assert capability.outputs[0].path == "pocket"


@pytest.mark.asyncio
async def test_v2_tool_package_can_hide_from_agent_while_remaining_direct_runnable(
    db_session: AsyncSession,
    user: User,
) -> None:
    await create_tool_with_v2_package_config(
        db_session,
        user,
        slug="direct-only-standard-tool",
        agent_exposure=False,
    )

    summaries = await load_available_tool_summaries(db_session)
    tool_slugs = {item["tool_slug"] for item in summaries}

    assert "direct-only-standard-tool" not in tool_slugs


@pytest.mark.asyncio
async def test_dynamic_agent_capability_syncs_tool_availability(
    db_session: AsyncSession,
    user: User,
) -> None:
    await create_tool_with_agent_config(db_session, user, slug="available-agent-tool")
    await create_tool_with_agent_config(
        db_session,
        user,
        slug="draft-agent-tool",
        status=ToolStatus.DRAFT.value,
    )
    await create_tool_with_agent_config(
        db_session,
        user,
        slug="private-agent-tool",
        is_public=False,
    )
    await create_tool_with_agent_config(
        db_session,
        user,
        slug="inactive-version-tool",
        version_active=False,
    )
    await create_tool_with_agent_config(
        db_session,
        user,
        slug="deprecated-version-tool",
        deprecated=True,
    )
    await create_tool_with_agent_config(
        db_session,
        user,
        slug="disabled-agent-config-tool",
        agent_enabled=False,
    )

    tool_slugs = {item["tool_slug"] for item in await load_available_tool_summaries(db_session)}

    assert "available-agent-tool" in tool_slugs
    assert "draft-agent-tool" not in tool_slugs
    assert "private-agent-tool" not in tool_slugs
    assert "inactive-version-tool" not in tool_slugs
    assert "deprecated-version-tool" not in tool_slugs
    assert "disabled-agent-config-tool" not in tool_slugs
