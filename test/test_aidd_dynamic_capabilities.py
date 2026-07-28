"""AIDD dynamic capability registry tests — DB-first resolution."""

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

from app.agents.aidd.capabilities import AIDD_TOOL_CAPABILITIES, ToolCapability  # noqa: E402
from app.agents.aidd.registry import (  # noqa: E402
    _db_row_to_capability,
    load_available_tool_capabilities,
    load_tool_capability,
    load_available_tool_summaries,
    upsert_capability_from_config,
)
from app.database.base import Base  # noqa: E402
from app.models import tool_capabilities as _tc_models  # noqa: F401, E402
from app.models import tools as _tools_models  # noqa: F401, E402
from app.models import users as _users_models  # noqa: F401, E402
from app.models.tool_capabilities import ToolCapability as ToolCapabilityModel  # noqa: E402
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


async def _create_tool(
    db_session: AsyncSession,
    owner: User,
    *,
    slug: str,
    name: str,
    config: dict | None = None,
) -> Tool:
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
        config=config or {"type": "ssh_job"},
        is_active=True,
    )
    db_session.add(version)
    await db_session.flush()
    tool.current_version_id = version.id
    await db_session.commit()
    await db_session.refresh(tool)
    return tool


# ---------------------------------------------------------------------------
# _db_row_to_capability conversion
# ---------------------------------------------------------------------------

class TestDbRowToCapability:
    def test_converts_basic_fields(self):
        row = ToolCapabilityModel(
            capability="pocket_prediction",
            stage="pocket_exploration",
            inputs=[
                {
                    "semantic_type": "protein_pdb",
                    "field": "protein_pdb",
                    "required": True,
                    "accepted_extensions": [".pdb"],
                }
            ],
            outputs=[
                {
                    "semantic_type": "pocket_pdb",
                    "source": "output_files",
                    "match": {"extension": ".pdb", "filename_contains_any": ["pocket"]},
                    "required": True,
                }
            ],
            defaults={"model_choice": "auto"},
            is_builtin=False,
        )

        cap = _db_row_to_capability(row)

        assert cap.capability == "pocket_prediction"
        assert cap.stage == "pocket_exploration"
        assert not cap.virtual
        assert cap.defaults == {"model_choice": "auto"}
        assert len(cap.inputs) == 1
        assert cap.inputs[0].semantic_type == "protein_pdb"
        assert cap.inputs[0].required is True
        assert cap.inputs[0].accepted_extensions == (".pdb",)
        assert len(cap.outputs) == 1
        assert cap.outputs[0].semantic_type == "pocket_pdb"
        assert cap.outputs[0].source == "output_files"
        assert cap.outputs[0].match is not None
        assert cap.outputs[0].match.extension == ".pdb"

    def test_converts_empty_defaults_and_lists(self):
        row = ToolCapabilityModel(
            capability="general_tool",
            stage="general",
            inputs=[
                {"semantic_type": "smiles_csv", "required": False}
            ],
            outputs=[
                {"semantic_type": "property_report", "source": "output_files"}
            ],
            defaults=None,
            is_builtin=False,
        )

        cap = _db_row_to_capability(row)

        assert cap.defaults == {}
        assert len(cap.inputs) == 1
        assert cap.inputs[0].accepted_extensions == ()
        assert cap.outputs[0].match is None
        assert cap.outputs[0].path is None


# ---------------------------------------------------------------------------
# upsert_capability_from_config
# ---------------------------------------------------------------------------

class TestUpsertCapabilityFromConfig:

    @pytest.mark.asyncio
    async def test_inserts_new_row_when_config_has_agent_capability(
        self, db_session: AsyncSession, user: User
    ) -> None:
        tool = await _create_tool(
            db_session,
            user,
            slug="custom-docking-tool",
            name="Custom Docking",
            config={
                "type": "docker_image",
                "image": "docking:v1",
                "agent_capability": {
                    "enabled": True,
                    "capability": "docking_scoring",
                    "stage": "docking_scoring",
                    "inputs": [
                        {"semantic_type": "protein_pdb", "required": True},
                        {"semantic_type": "ligand_pdb", "required": True},
                    ],
                    "outputs": [
                        {
                            "semantic_type": "docking_report",
                            "source": "output_files",
                            "match": {"extension": ".json"},
                        }
                    ],
                    "defaults": {"exhaustiveness": 8},
                },
            },
        )

        row = await upsert_capability_from_config(db_session, tool)

        assert row is not None
        assert row.tool_id == tool.id
        assert row.capability == "docking_scoring"
        assert row.stage == "docking_scoring"
        assert len(row.inputs) == 2
        assert len(row.outputs) == 1
        assert row.defaults == {"exhaustiveness": 8}
        assert row.is_builtin is False
        assert row.is_enabled is True

    @pytest.mark.asyncio
    async def test_updates_existing_row_on_reimport(
        self, db_session: AsyncSession, user: User
    ) -> None:
        tool = await _create_tool(
            db_session,
            user,
            slug="evolving-tool",
            name="Evolving Tool",
            config={
                "type": "docker_image",
                "agent_capability": {
                    "enabled": True,
                    "capability": "old_capability",
                    "stage": "old_stage",
                    "inputs": [{"semantic_type": "protein_pdb"}],
                    "outputs": [{"semantic_type": "pocket_pdb"}],
                },
            },
        )

        first = await upsert_capability_from_config(db_session, tool)
        assert first is not None
        first_id = first.id
        assert first.capability == "old_capability"

        # Simulate config update
        tool.current_version.config["agent_capability"]["capability"] = "new_capability"
        tool.current_version.config["agent_capability"]["stage"] = "new_stage"
        await db_session.flush()

        second = await upsert_capability_from_config(db_session, tool)
        assert second is not None
        assert second.id == first_id  # same row, updated
        assert second.capability == "new_capability"
        assert second.stage == "new_stage"

    @pytest.mark.asyncio
    async def test_returns_none_when_agent_capability_disabled(
        self, db_session: AsyncSession, user: User
    ) -> None:
        tool = await _create_tool(
            db_session,
            user,
            slug="no-capability-tool",
            name="No Capability",
            config={
                "type": "docker_image",
                "agent_capability": {"enabled": False},
            },
        )

        row = await upsert_capability_from_config(db_session, tool)
        assert row is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_agent_capability_config(
        self, db_session: AsyncSession, user: User
    ) -> None:
        tool = await _create_tool(
            db_session,
            user,
            slug="plain-tool",
            name="Plain Tool",
            config={"type": "docker_image"},
        )

        row = await upsert_capability_from_config(db_session, tool)
        assert row is None


# ---------------------------------------------------------------------------
# load_available_tool_capabilities — DB-first path
# ---------------------------------------------------------------------------

class TestLoadAvailableToolCapabilities:

    @pytest.mark.asyncio
    async def test_db_capability_does_not_hide_config_capability(
        self, db_session: AsyncSession, user: User
    ) -> None:
        db_tool = await _create_tool(
            db_session,
            user,
            slug="db-tool",
            name="DB Tool",
            config={
                "type": "docker_image",
                "agent_capability": {
                    "enabled": True,
                    "capability": "docking_scoring",
                    "stage": "docking",
                    "inputs": [{"semantic_type": "protein_pdb"}],
                    "outputs": [{"semantic_type": "docking_report", "source": "output_files"}],
                },
            },
        )
        await upsert_capability_from_config(db_session, db_tool)
        await _create_tool(
            db_session,
            user,
            slug="config-tool",
            name="Config Tool",
            config={
                "type": "docker_image",
                "agent_capability": {
                    "enabled": True,
                    "capability": "property_prediction",
                    "stage": "property",
                    "inputs": [{"semantic_type": "smiles_csv"}],
                    "outputs": [{"semantic_type": "property_report", "source": "output_files"}],
                },
            },
        )

        slugs = {cap.tool_slug for cap in await load_available_tool_capabilities(db_session)}

        assert {"db-tool", "config-tool"} <= slugs

    @pytest.mark.asyncio
    async def test_db_first_returns_capability_from_table(
        self, db_session: AsyncSession, user: User
    ) -> None:
        """When DB has capability rows, they take priority over static registry."""
        tool = await _create_tool(
            db_session,
            user,
            slug="my-docking-tool",
            name="My Docking Tool",
            config={
                "type": "docker_image",
                "agent_capability": {
                    "enabled": True,
                    "capability": "docking_scoring",
                    "stage": "docking_scoring",
                    "inputs": [
                        {"semantic_type": "protein_pdb"},
                        {"semantic_type": "ligand_pdb"},
                    ],
                    "outputs": [
                        {"semantic_type": "docking_report", "source": "output_files"}
                    ],
                },
            },
        )
        await upsert_capability_from_config(db_session, tool)

        caps = await load_available_tool_capabilities(db_session)

        # Should include our DB-registered tool
        my_caps = [c for c in caps if c.tool_slug == "my-docking-tool"]
        assert len(my_caps) == 1
        assert my_caps[0].capability == "docking_scoring"
        assert my_caps[0].stage == "docking_scoring"
        assert not my_caps[0].virtual

        # Virtual tools should always be included
        virtual_slugs = {c.tool_slug for c in caps if c.virtual}
        assert "builtin-vina-docking" in virtual_slugs
        assert "builtin-admet-prediction" not in virtual_slugs

    @pytest.mark.asyncio
    async def test_db_registered_tool_excluded_when_tool_becomes_unavailable(
        self, db_session: AsyncSession, user: User
    ) -> None:
        """When a tool changes status away from published, its capability is filtered."""
        tool = await _create_tool(
            db_session,
            user,
            slug="soon-disabled-tool",
            name="Soon Disabled",
            config={
                "type": "docker_image",
                "agent_capability": {
                    "enabled": True,
                    "capability": "general_tool",
                    "stage": "general",
                    "inputs": [{"semantic_type": "protein_pdb"}],
                    "outputs": [{"semantic_type": "pocket_pdb"}],
                },
            },
        )
        await upsert_capability_from_config(db_session, tool)

        # Verify it shows up initially
        caps_before = await load_available_tool_capabilities(db_session)
        assert any(c.tool_slug == "soon-disabled-tool" for c in caps_before)

        # Disable the tool
        tool.status = ToolStatus.DISABLED.value
        await db_session.commit()
        await db_session.refresh(tool)

        # Should no longer appear
        caps_after = await load_available_tool_capabilities(db_session)
        assert not any(c.tool_slug == "soon-disabled-tool" for c in caps_after)

    @pytest.mark.asyncio
    async def test_fallback_to_static_when_db_empty(
        self, db_session: AsyncSession, user: User
    ) -> None:
        """When the DB capability table is empty, fall back to static registry for real tools."""
        # Create a tool whose slug matches a static entry (lvpocket-pocket-prediction)
        await _create_tool(
            db_session,
            user,
            slug="lvpocket-pocket-prediction",
            name="LVpocket",
            config={"type": "ssh_job"},
        )

        caps = await load_available_tool_capabilities(db_session)

        # Should find the static capability for lvpocket
        pocket_caps = [c for c in caps if c.tool_slug == "lvpocket-pocket-prediction"]
        assert len(pocket_caps) == 1
        assert pocket_caps[0].capability == "pocket_prediction"

        # Virtual tools always present
        assert any(c.tool_slug == "builtin-vina-docking" for c in caps)


# ---------------------------------------------------------------------------
# load_tool_capability — single tool resolution
# ---------------------------------------------------------------------------

class TestLoadToolCapability:

    @pytest.mark.asyncio
    async def test_db_first_resolution(
        self, db_session: AsyncSession, user: User
    ) -> None:
        tool = await _create_tool(
            db_session,
            user,
            slug="db-registered-tool",
            name="DB Registered",
            config={
                "type": "docker_image",
                "agent_capability": {
                    "enabled": True,
                    "capability": "custom_capability",
                    "stage": "custom_stage",
                    "inputs": [{"semantic_type": "protein_pdb"}],
                    "outputs": [{"semantic_type": "pocket_pdb"}],
                },
            },
        )
        await upsert_capability_from_config(db_session, tool)

        cap = await load_tool_capability(db_session, "db-registered-tool")

        assert cap.tool_slug == "db-registered-tool"
        assert cap.capability == "custom_capability"
        assert cap.stage == "custom_stage"
        assert not cap.virtual

    @pytest.mark.asyncio
    async def test_virtual_tool_resolved_from_static(
        self, db_session: AsyncSession
    ) -> None:
        cap = await load_tool_capability(db_session, "builtin-vina-docking")

        assert cap.tool_slug == "builtin-vina-docking"
        assert cap.capability == "docking_scoring"
        assert cap.virtual

    @pytest.mark.asyncio
    async def test_fallback_to_static_for_unregistered_tool(
        self, db_session: AsyncSession, user: User
    ) -> None:
        """Tool without DB capability row falls back to static + config."""
        await _create_tool(
            db_session,
            user,
            slug="lvpocket-pocket-prediction",
            name="LVpocket",
            config={"type": "ssh_job"},
        )

        cap = await load_tool_capability(db_session, "lvpocket-pocket-prediction")

        assert cap.capability == "pocket_prediction"
        assert cap.stage == "pocket_exploration"

    @pytest.mark.asyncio
    async def test_raises_for_unknown_tool(
        self, db_session: AsyncSession
    ) -> None:
        from app.common.exceptions import ValidationException

        with pytest.raises(ValidationException, match="未配置"):
            await load_tool_capability(db_session, "non-existent-tool")


# ---------------------------------------------------------------------------
# load_available_tool_summaries
# ---------------------------------------------------------------------------

class TestLoadAvailableToolSummaries:

    @pytest.mark.asyncio
    async def test_returns_summaries_with_virtual_tools(
        self, db_session: AsyncSession, user: User
    ) -> None:
        summaries = await load_available_tool_summaries(db_session)

        assert isinstance(summaries, list)
        # Virtual tools always present in summaries
        virtual_summaries = [
            s for s in summaries
            if s.get("slug", "").startswith("builtin-")
        ]
        assert len(virtual_summaries) > 0
        # Check structure
        for s in summaries:
            assert "slug" in s or "tool_slug" in s
