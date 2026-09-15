"""Reusable artifact file listing helpers."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from app.services.artifact_file_list import (  # noqa: E402
    artifact_file_item_data,
    artifact_sources_by_file_id,
)


def test_artifact_sources_by_file_id_keeps_first_task_source() -> None:
    tool = SimpleNamespace(id="tool-1", name="Pocket", slug="pocket")
    first_task = SimpleNamespace(
        id="task-1",
        tool=tool,
        outputs=SimpleNamespace(file_ids=["file-1", "file-2"]),
    )
    duplicate_task = SimpleNamespace(
        id="task-2",
        tool=tool,
        outputs=SimpleNamespace(file_ids=["file-1"]),
    )
    no_tool_task = SimpleNamespace(
        id="task-3",
        tool=None,
        outputs=SimpleNamespace(file_ids=["file-3"]),
    )

    sources = artifact_sources_by_file_id(
        [first_task, duplicate_task, no_tool_task]
    )

    assert sorted(sources) == ["file-1", "file-2"]
    assert sources["file-1"].task.id == "task-1"
    assert sources["file-1"].tool.slug == "pocket"


def test_artifact_file_item_data_projects_standard_metadata() -> None:
    created_at = datetime(2026, 1, 1)
    file_record = SimpleNamespace(
        id="file-1",
        filename="prepared.pdb",
        content_type="chemical/x-pdb",
        size_bytes=128,
        source_type="tool_output",
        created_at=created_at,
        updated_at=created_at,
    )
    tool = SimpleNamespace(
        id="tool-1",
        name="Protein Prep",
        slug="protein-prep",
    )
    task = SimpleNamespace(id="task-1", name="prep run", tool=tool)
    source = artifact_sources_by_file_id(
        [
            SimpleNamespace(
                **task.__dict__,
                outputs=SimpleNamespace(file_ids=["file-1"]),
            )
        ]
    )["file-1"]

    item = artifact_file_item_data(
        file_record,
        source,
        {
            "artifact_id": "artifact-1",
            "artifact_version_id": "version-1",
            "standard_artifact_role": "prepared_pdb",
            "standard_artifact_output": "protein",
            "semantic_type": "protein_structure@1",
        },
    )

    assert item["id"] == "file-1"
    assert item["download_url"] == "/api/v1/files/file-1/download"
    assert item["task_name"] == "prep run"
    assert item["tool_slug"] == "protein-prep"
    assert item["artifact_version_id"] == "version-1"
    assert item["standard_artifact_role"] == "prepared_pdb"
    assert item["semantic_type"] == "protein_structure@1"
