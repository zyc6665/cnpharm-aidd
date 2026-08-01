import hashlib
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

from app.agents.aidd.graph import build_plan_with_langgraph
from app.database.base import Base
from app.models import agent as _agent_models  # noqa: F401
from app.models import files as _files_models  # noqa: F401
from app.models import system_settings as _system_settings  # noqa: F401
from app.models import tools as _tools_models  # noqa: F401
from app.models import users as _users_models  # noqa: F401
from app.models.files import File as FileModel, FileSourceType
from app.models.system_settings import ModelService
from app.models.tools import Tool, ToolStatus, ToolVersion
from app.models.users import User, UserRole, UserStatus


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield factory
    await engine.dispose()


async def seed_graph_context(session: AsyncSession):
    user = User(
        email="owner@example.com",
        password_hash="hashed-password",
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
    )
    session.add(user)
    await session.flush()

    service = ModelService(
        name="Default",
        provider_type="openai_compatible",
        base_url="https://api.example.com/v1",
        api_key_encrypted=None,
        model_name="planner",
        is_default=True,
        is_enabled=True,
    )
    session.add(service)

    input_file = FileModel(
        owner_id=user.id,
        filename="protein.pdb",
        content_type="chemical/x-pdb",
        size_bytes=128,
        sha256=hashlib.sha256(b"protein").hexdigest(),
        source_type=FileSourceType.UPLOAD.value,
        storage_path="/tmp/protein.pdb",
    )
    session.add(input_file)

    for slug, name in [
        ("lvpocket-pocket-prediction", "LVpocket"),
        ("gcdm-pocket-generation", "STD-Diff"),
    ]:
        tool = Tool(
            owner_id=user.id,
            name=name,
            slug=slug,
            status=ToolStatus.PUBLISHED.value,
            is_public=True,
        )
        session.add(tool)
        await session.flush()
        version = ToolVersion(
            tool_id=tool.id,
            version="1.0.0",
            config={"type": "ssh_job"},
            is_active=True,
        )
        session.add(version)
        await session.flush()
        tool.current_version_id = version.id

    await session.commit()
    return user, input_file


@pytest.mark.asyncio
async def test_build_plan_with_langgraph_uses_model_plan(session_factory, monkeypatch):
    async with session_factory() as session:
        _user, input_file = await seed_graph_context(session)

        async def fake_request_structured_plan(service, prompt):
            return """
            {
              "intent": "generate_molecules_from_protein",
              "steps": [
                {
                  "step_key": "pocket_prediction",
                  "capability": "pocket_prediction",
                  "tool_slug": "lvpocket-pocket-prediction",
                  "inputs": {"protein_pdb": "agent_input"},
                  "params": {}
                },
                {
                  "step_key": "molecule_generation",
                  "capability": "molecule_generation",
                  "tool_slug": "gcdm-pocket-generation",
                  "inputs": {"pocket_pdb": "step:pocket_prediction:pocket_pdb"},
                  "params": {}
                }
              ]
            }
            """

        monkeypatch.setattr(
            "app.agents.aidd.llm_client.request_structured_plan",
            fake_request_structured_plan,
        )

        plan, input_type = await build_plan_with_langgraph(
            session,
            message="上传蛋白后探索口袋并生成分子",
            input_file=input_file,
            requested_outputs=["generated_ligand"],
            params={},
        )

    assert input_type == "protein_pdb"
    assert plan.intent == "generate_molecules_from_protein"
    assert [step.tool_slug for step in plan.steps] == [
        "lvpocket-pocket-prediction",
        "gcdm-pocket-generation",
    ]


@pytest.mark.asyncio
async def test_build_plan_with_langgraph_normalizes_agent_input_with_semantic_suffix(
    session_factory, monkeypatch
):
    async with session_factory() as session:
        _user, input_file = await seed_graph_context(session)

        async def fake_request_structured_plan(service, prompt):
            return """
            {
              "intent": "generate_molecules_from_protein",
              "steps": [
                {
                  "step_key": "pocket_prediction",
                  "capability": "pocket_prediction",
                  "tool_slug": "lvpocket-pocket-prediction",
                  "inputs": {"protein_pdb": "agent_input:protein_pdb"},
                  "params": {}
                }
              ]
            }
            """

        monkeypatch.setattr(
            "app.agents.aidd.llm_client.request_structured_plan",
            fake_request_structured_plan,
        )

        plan, input_type = await build_plan_with_langgraph(
            session,
            message="上传蛋白后探索口袋",
            input_file=input_file,
            requested_outputs=["pocket_pdb"],
            params={},
    )

    assert input_type == "protein_pdb"
    assert plan.steps[0].inputs["protein_structure@1"] == "agent_input"


@pytest.mark.asyncio
async def test_build_plan_with_langgraph_accepts_dynamic_agent_capability(
    session_factory, monkeypatch
):
    async with session_factory() as session:
        user, input_file = await seed_graph_context(session)
        tool = Tool(
            owner_id=user.id,
            name="Dynamic ADMET",
            slug="dynamic-admet",
            status=ToolStatus.PUBLISHED.value,
            is_public=True,
        )
        session.add(tool)
        await session.flush()
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
        session.add(version)
        await session.flush()
        tool.current_version_id = version.id
        await session.commit()

        async def fake_request_structured_plan(service, prompt):
            assert "dynamic-admet" in prompt
            return """
            {
              "intent": "predict_dynamic_admet",
              "steps": [
                {
                  "step_key": "property_prediction",
                  "capability": "property_prediction",
                  "tool_slug": "dynamic-admet",
                  "inputs": {"smiles_csv": "agent_input:smiles_csv"},
                  "params": {}
                }
              ]
            }
            """

        monkeypatch.setattr(
            "app.agents.aidd.llm_client.request_structured_plan",
            fake_request_structured_plan,
        )

        plan, _input_type = await build_plan_with_langgraph(
            session,
            message="用上传的 smiles 预测 ADMET",
            input_file=input_file,
            input_files={"smiles_csv": input_file},
            input_type="smiles_csv",
            requested_outputs=["property_report"],
            params={},
        )

    assert [step.tool_slug for step in plan.steps] == ["dynamic-admet"]
