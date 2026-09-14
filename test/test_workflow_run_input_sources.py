"""Workflow run input source resolution tests."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.models.files import File as FileModel  # noqa: E402
from app.services.workflow_run_input_sources import (  # noqa: E402
    resolve_workflow_input_sources,
)


class FakeDb:
    def __init__(self, files: dict[str, object]) -> None:
        self.files = files
        self.calls: list[tuple[type[FileModel], str]] = []

    async def get(self, model: type[FileModel], file_id: str) -> object | None:
        self.calls.append((model, file_id))
        return self.files.get(file_id)


@pytest.mark.asyncio
async def test_wraps_workflow_input_upload() -> None:
    db = FakeDb({"file-1": SimpleNamespace(id="file-1")})
    run = SimpleNamespace(input_files={"protein_structure@1": "file-1"})
    node = {
        "artifact_input_slots": [
            {
                "name": "protein",
                "type": "protein_structure@1",
                "required": True,
            }
        ],
        "artifact_inputs": {"protein": "workflow_input:protein_structure@1"},
    }

    sources = await resolve_workflow_input_sources(
        db,  # type: ignore[arg-type]
        run=run,
        node=node,
        node_states={},
    )

    assert sources is not None
    assert sources.file_ids == ["file-1"]
    assert sources.standard_input_uploads == {"protein": "file-1"}
    assert sources.legacy_file_bindings == {"protein": "file-1"}


@pytest.mark.asyncio
async def test_resolve_workflow_input_sources_waits_for_pending_node() -> None:
    db = FakeDb({})
    run = SimpleNamespace(input_files={})
    node = {"artifact_inputs": {"protein": "node:upstream:protein"}}

    sources = await resolve_workflow_input_sources(
        db,  # type: ignore[arg-type]
        run=run,
        node=node,
        node_states={"upstream": {"status": "running"}},
    )

    assert sources is None


@pytest.mark.asyncio
async def test_records_missing_standard_artifact_version() -> None:
    db = FakeDb({})
    run = SimpleNamespace(input_files={})
    node = {
        "artifact_input_slots": [
            {
                "name": "protein",
                "type": "protein_structure@1",
                "readiness_policy": "require_prepared",
            }
        ],
        "artifact_inputs": {"protein": "node:upstream:prepared_protein"},
    }

    sources = await resolve_workflow_input_sources(
        db,  # type: ignore[arg-type]
        run=run,
        node=node,
        node_states={
            "upstream": {"status": "success", "standard_artifacts": {}},
        },
    )

    assert sources is not None
    assert sources.binding_decisions["protein"] == {
        "status": "invalid",
        "input_name": "protein",
        "standard_type": "protein_structure@1",
        "selected_role": None,
        "selected_file_id": None,
        "artifact_version_id": None,
        "reason": "Standard artifact version is missing for prepared_protein.",
        "suggested_tool_slug": None,
    }


@pytest.mark.asyncio
async def test_resolve_workflow_input_sources_collects_node_file_ids() -> None:
    db = FakeDb(
        {
            "raw-file": SimpleNamespace(id="raw-file"),
            "prepared-file": SimpleNamespace(id="prepared-file"),
        }
    )
    run = SimpleNamespace(input_files={})
    node = {
        "artifact_input_slots": [
            {
                "name": "protein",
                "type": "protein_structure@1",
                "required": True,
            }
        ],
        "artifact_inputs": {"protein": "node:upstream:protein"},
    }

    sources = await resolve_workflow_input_sources(
        db,  # type: ignore[arg-type]
        run=run,
        node=node,
        node_states={
            "upstream": {
                "status": "success",
                "standard_artifacts": {
                    "file_ids_by_artifact_ref": {
                        "protein": ["raw-file", "prepared-file"]
                    },
                },
            }
        },
    )

    assert sources is not None
    assert sources.file_ids == ["raw-file", "prepared-file"]
    assert sources.legacy_file_bindings == {"protein": "raw-file"}
