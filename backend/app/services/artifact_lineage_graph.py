"""Build typed Artifact lineage graph response data."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def artifact_lineage_graph_data(
    *,
    project_id: str,
    artifacts: list[Any],
    lineages: list[Any],
    tasks_by_id: dict[str, Any],
) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[tuple[str, str, str], dict[str, Any]] = {}
    version_ids: set[str] = set()

    for artifact in artifacts:
        _add_artifact_nodes_and_edges(
            nodes=nodes,
            edges=edges,
            version_ids=version_ids,
            artifact=artifact,
        )

    for task_id, task in tasks_by_id.items():
        _add_task_nodes_and_edges(
            nodes=nodes,
            edges=edges,
            task_id=task_id,
            task=task,
        )

    for lineage in lineages:
        _add_lineage_edge(
            edges=edges,
            version_ids=version_ids,
            lineage=lineage,
        )

    return {
        "project_id": project_id,
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
        "summary": {
            "artifacts": len(artifacts),
            "versions": len(version_ids),
            "tasks": len(tasks_by_id),
            "workflow_nodes": sum(
                1 for node in nodes.values() if node["kind"] == "workflow_node"
            ),
            "lineage_edges": len(lineages),
        },
    }


def _add_artifact_nodes_and_edges(
    *,
    nodes: dict[str, dict[str, Any]],
    edges: dict[tuple[str, str, str], dict[str, Any]],
    version_ids: set[str],
    artifact: Any,
) -> None:
    artifact_node_id = f"artifact:{artifact.id}"
    _add_graph_node(
        nodes,
        {
            "id": artifact_node_id,
            "kind": "artifact",
            "artifact_id": artifact.id,
            "project_id": artifact.project_id,
            "label": artifact.name,
            "name": artifact.name,
            "artifact_type": artifact.artifact_type,
            "semantic_type": artifact.semantic_type,
            "standard_type": artifact.standard_type,
            "standard_version": artifact.standard_version,
            "source_task_id": artifact.source_task_id,
            "latest_version_id": artifact.latest_version_id,
            "created_at": artifact.created_at,
            "updated_at": artifact.updated_at,
        },
    )
    for version in artifact.versions:
        _add_artifact_version_node_and_edges(
            nodes=nodes,
            edges=edges,
            version_ids=version_ids,
            artifact_node_id=artifact_node_id,
            artifact=artifact,
            version=version,
        )


def _add_artifact_version_node_and_edges(
    *,
    nodes: dict[str, dict[str, Any]],
    edges: dict[tuple[str, str, str], dict[str, Any]],
    version_ids: set[str],
    artifact_node_id: str,
    artifact: Any,
    version: Any,
) -> None:
    version_ids.add(str(version.id))
    version_node_id = f"version:{version.id}"
    # 版本自身的来源字段（可空）：即便某个历史版本回退到 artifact 级 produced_by，
    # 也把版本级真值原样带出，供前端/追溯包区分「该版本到底有没有版本级来源」。
    version_source_task_id = getattr(version, "source_task_id", None)
    version_source_attempt_id = getattr(version, "source_attempt_id", None)
    _add_graph_node(
        nodes,
        {
            "id": version_node_id,
            "kind": "version",
            "artifact_id": artifact.id,
            "version_id": version.id,
            "label": f"{artifact.name} v{version.version}",
            "version": version.version,
            "filename": version.filename,
            "content_type": version.content_type,
            "size_bytes": version.size_bytes,
            "sha256": version.sha256,
            "status": version.status,
            "validation_status": version.validation_status,
            "source_task_id": version_source_task_id,
            "source_attempt_id": version_source_attempt_id,
            "created_at": version.created_at,
        },
    )
    _add_graph_edge(
        edges,
        {
            "id": f"{artifact_node_id}->{version_node_id}:has_version",
            "kind": "has_version",
            "source": artifact_node_id,
            "target": version_node_id,
        },
    )
    # produced_by 必须落到**版本次**：同一 artifact 由多个任务产出多个版本时，
    # artifact.source_task_id 只记**首建者**，直接用它会把同一来源任务贴给所有版本，
    # 「哪次执行产出了这一版」就无法回答（PRD M7「一键还原到那次执行」）。
    # 因此优先取版本级 source_task_id；迁移前的历史行该列为空时，回退到 artifact
    # 级字段——这是 best-effort 的旧口径，只能退化到实体级、不能区分多任务。
    producer_task_id = version_source_task_id or artifact.source_task_id
    if version_source_task_id is None and artifact.source_task_id is not None:
        # 可观测性：回退到 artifact 级说明该版本没有版本级来源（历史数据 / 未回填），
        # 线上可据此统计「还有多少版本在吃回退」、验证回填是否生效。
        logger.debug(
            "artifact lineage produced_by falls back to artifact-level source: "
            "artifact_id=%s version_id=%s",
            artifact.id,
            version.id,
        )
    if producer_task_id:
        task_node_id = f"task:{producer_task_id}"
        _add_graph_edge(
            edges,
            {
                "id": f"{task_node_id}->{version_node_id}:produced_by",
                "kind": "produced_by",
                "source": task_node_id,
                "target": version_node_id,
            },
        )


def _add_task_nodes_and_edges(
    *,
    nodes: dict[str, dict[str, Any]],
    edges: dict[tuple[str, str, str], dict[str, Any]],
    task_id: str,
    task: Any,
) -> None:
    tool = task.tool
    task_node_id = f"task:{task_id}"
    _add_graph_node(
        nodes,
        {
            "id": task_node_id,
            "kind": "task",
            "task_id": task_id,
            "label": task.name or (tool.name if tool else task_id),
            "name": task.name,
            "status": task.status,
            "tool_id": task.tool_id,
            "tool_name": tool.name if tool else None,
            "tool_slug": tool.slug if tool else None,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        },
    )
    params = _task_workflow_params(task)
    run_id = params.get("workflow_run_id")
    node_id = params.get("workflow_node_id")
    if not run_id or not node_id:
        return
    workflow_node_id = f"workflow-node:{run_id}:{node_id}"
    _add_graph_node(
        nodes,
        {
            "id": workflow_node_id,
            "kind": "workflow_node",
            "workflow_run_id": str(run_id),
            "workflow_definition_id": (
                str(params["workflow_definition_id"])
                if params.get("workflow_definition_id")
                else None
            ),
            "workflow_node_id": str(node_id),
            "workflow_node_type": str(
                params.get("workflow_node_type") or "tool"
            ),
            "label": str(node_id),
            "task_id": task_id,
        },
    )
    _add_graph_edge(
        edges,
        {
            "id": f"{workflow_node_id}->{task_node_id}:runs_task",
            "kind": "runs_task",
            "source": workflow_node_id,
            "target": task_node_id,
        },
    )


def _add_lineage_edge(
    *,
    edges: dict[tuple[str, str, str], dict[str, Any]],
    version_ids: set[str],
    lineage: Any,
) -> None:
    source = f"version:{lineage.input_version_id}"
    target = f"version:{lineage.output_version_id}"
    if (
        str(lineage.input_version_id) not in version_ids
        or str(lineage.output_version_id) not in version_ids
    ):
        return
    relation_type = lineage.relation_type or "derived_from"
    _add_graph_edge(
        edges,
        {
            "id": f"{source}->{target}:{relation_type}",
            "kind": relation_type,
            "source": source,
            "target": target,
            "lineage_id": lineage.id,
            "project_id": lineage.project_id,
            "relation_type": relation_type,
            "created_at": lineage.created_at,
        },
    )


def _add_graph_node(
    nodes: dict[str, dict[str, Any]],
    node: dict[str, Any],
) -> None:
    nodes[str(node["id"])] = node


def _add_graph_edge(
    edges: dict[tuple[str, str, str], dict[str, Any]],
    edge: dict[str, Any],
) -> None:
    key = (str(edge["source"]), str(edge["target"]), str(edge["kind"]))
    edges[key] = edge


def _task_workflow_params(task: Any) -> dict[str, Any]:
    params = task.inputs.params if task.inputs else {}
    return params if isinstance(params, dict) else {}
