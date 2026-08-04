import sys
from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.base import Base
from app.models import workflows as _workflows  # noqa: F401
from app.schemas.workflows import WorkflowDefinitionCreate, WorkflowDefinitionUpdate


@pytest.mark.asyncio
async def test_workflow_definitions_table_is_registered():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        table_names = await conn.run_sync(
            lambda sync_conn: set(inspect(sync_conn).get_table_names())
        )
        workflow_columns = await conn.run_sync(
            lambda sync_conn: {
                column["name"]
                for column in inspect(sync_conn).get_columns("workflow_definitions")
            }
        )

    await engine.dispose()

    assert "workflow_definitions" in table_names
    assert "canvas_preset_id" in workflow_columns
    assert "template_id" not in workflow_columns


def test_workflow_definition_create_schema_accepts_graph_payload():
    payload = WorkflowDefinitionCreate(
        name="AIDD draft",
        canvas_preset_id="aidd-template",
        nodes=[{"id": "input-protein", "type": "input", "position": {"x": 1, "y": 2}}],
        edges=[{"id": "edge-1", "source": "input-protein", "target": "tool-pocket"}],
        selected_tool_by_node={"tool-pocket": "pocket-explorer"},
        artifact_bindings_by_node={"tool-pocket": {"protein": "file-1"}},
    )

    assert payload.name == "AIDD draft"
    assert payload.status == "draft"
    assert payload.nodes[0]["id"] == "input-protein"


def test_workflow_definition_update_schema_allows_partial_patch():
    payload = WorkflowDefinitionUpdate(name="Updated")

    assert payload.name == "Updated"
    assert payload.nodes is None
