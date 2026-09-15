from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.artifact_lineage_graph import (  # noqa: E402
    artifact_lineage_graph_data,
)


def test_artifact_lineage_graph_includes_task_and_workflow_node() -> None:
    source_version = SimpleNamespace(
        id="version-source",
        version=1,
        filename="protein.pdb",
        content_type="chemical/x-pdb",
        size_bytes=12,
        sha256="a" * 64,
        status="available",
        validation_status="passed",
        created_at=None,
    )
    output_version = SimpleNamespace(
        id="version-output",
        version=1,
        filename="pocket.pdb",
        content_type="chemical/x-pdb",
        size_bytes=16,
        sha256="b" * 64,
        status="available",
        validation_status="passed",
        created_at=None,
    )
    source = SimpleNamespace(
        id="artifact-source",
        project_id="project-1",
        name="protein.pdb",
        artifact_type="protein_structure",
        semantic_type="protein_structure@1",
        standard_type="protein_structure",
        standard_version=1,
        source_task_id=None,
        latest_version_id=source_version.id,
        created_at=None,
        updated_at=None,
        versions=[source_version],
    )
    output = SimpleNamespace(
        id="artifact-output",
        project_id="project-1",
        name="pocket.pdb",
        artifact_type="binding_pocket",
        semantic_type="binding_pocket@1",
        standard_type="binding_pocket",
        standard_version=1,
        source_task_id="task-1",
        latest_version_id=output_version.id,
        created_at=None,
        updated_at=None,
        versions=[output_version],
    )
    task = SimpleNamespace(
        id="task-1",
        name="Workflow Pocket Node",
        status="success",
        tool_id="tool-1",
        tool=SimpleNamespace(name="LVpocket", slug="lvpocket"),
        created_at=None,
        updated_at=None,
        inputs=SimpleNamespace(
            params={
                "workflow_run_id": "run-1",
                "workflow_definition_id": "workflow-1",
                "workflow_node_id": "pocket_prediction",
                "workflow_node_type": "tool",
            }
        ),
    )
    lineage = SimpleNamespace(
        id="lineage-1",
        project_id="project-1",
        input_version_id=source_version.id,
        output_version_id=output_version.id,
        relation_type="derived_from",
        created_at=None,
    )

    graph = artifact_lineage_graph_data(
        project_id="project-1",
        artifacts=[source, output],
        lineages=[lineage],
        tasks_by_id={"task-1": task},
    )

    nodes_by_id = {node["id"]: node for node in graph["nodes"]}
    edge_keys = {
        (edge["source"], edge["target"], edge["kind"])
        for edge in graph["edges"]
    }

    assert (
        nodes_by_id["artifact:artifact-output"]["standard_type"]
        == "binding_pocket"
    )
    assert nodes_by_id["version:version-output"]["filename"] == "pocket.pdb"
    assert nodes_by_id["task:task-1"]["tool_slug"] == "lvpocket"
    assert (
        nodes_by_id["workflow-node:run-1:pocket_prediction"]["task_id"]
        == "task-1"
    )
    assert (
        "version:version-source",
        "version:version-output",
        "derived_from",
    ) in edge_keys
    assert (
        "task:task-1",
        "version:version-output",
        "produced_by",
    ) in edge_keys
    assert (
        "workflow-node:run-1:pocket_prediction",
        "task:task-1",
        "runs_task",
    ) in edge_keys
    assert graph["summary"] == {
        "artifacts": 2,
        "versions": 2,
        "tasks": 1,
        "workflow_nodes": 1,
        "lineage_edges": 1,
    }
