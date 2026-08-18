"""Protein preparation actions for research boards."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.research_boards import _load_board, _require_board_write_access
from app.auth.dependencies import get_current_user
from app.common.responses import success_response
from app.common.time import utcnow
from app.config import settings
from app.database.session import get_db
from app.models.artifacts import Artifact, ArtifactVersion
from app.models.tasks import Task, TaskOutput, TaskStatus
from app.models.users import User
from app.schemas.protein_preparation import ProteinPreparationRequest
from app.schemas.tasks import TaskCreate
from app.services.aidd_builtin_tools import ensure_aidd_builtin_tool
from app.services.research_board_content import normalize_board_content
from app.tasks.service import create_and_schedule_tool_task


router = APIRouter()


@router.post("/research-boards/{board_id}/protein-preparations", response_model=dict)
async def start_protein_preparation(
    board_id: str,
    data: ProteinPreparationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    board = await _load_board(board_id, current_user, db)
    await _require_board_write_access(board, current_user, db)
    artifact = await _load_source_protein_artifact(db, artifact_id=data.artifact_id)
    if board.project_id and artifact.project_id != board.project_id:
        raise HTTPException(status_code=400, detail="蛋白 Artifact 不属于当前白板项目")
    if not board.project_id and artifact.created_by != current_user.id:
        raise HTTPException(status_code=404, detail="蛋白 Artifact 不存在")

    source_version = _artifact_version(artifact, data.artifact_version_id)
    primary_file_id = _primary_file_id(source_version)
    if not primary_file_id:
        raise HTTPException(status_code=400, detail="蛋白 Artifact 缺少可用结构文件")

    system_user_id = settings.AIDD_SYSTEM_USER_ID
    if not system_user_id:
        raise HTTPException(status_code=500, detail="AIDD_SYSTEM_USER_ID 未配置")
    builtin_tool = await ensure_aidd_builtin_tool(
        db,
        owner_id=system_user_id,
        tool_slug="builtin-protein-preparation",
    )
    if not builtin_tool.current_version_id:
        raise HTTPException(status_code=500, detail="蛋白制备内置工具缺少可用版本")

    task = await create_and_schedule_tool_task(
        db=db,
        current_user=current_user,
        task_data=TaskCreate(
            name=f"Prepare protein {artifact.name}",
            project_id=board.project_id or artifact.project_id,
            tool_id=builtin_tool.id,
            tool_version_id=builtin_tool.current_version_id,
            params={
                "options": data.options.model_dump(),
                "advanced_options": data.advanced_options,
                "preparation_profile": data.preparation_profile,
                "builtin_inputs": {"protein_structure@1": primary_file_id},
            },
            file_ids=[primary_file_id],
            input_bindings={"protein": source_version.id},
        ),
    )

    content = normalize_board_content(board.content)
    preparation_node = _preparation_node(
        content,
        tool_id=builtin_tool.id,
        task_id=str(task.id),
        source_node_id=data.source_node_id,
        position=data.position.model_dump() if data.position else None,
    )
    edge = _preparation_edge(data.source_node_id, preparation_node["id"])
    content["nodes"] = [node for node in content["nodes"] if node.get("id") != preparation_node["id"]]
    content["nodes"].append(preparation_node)
    if edge:
        content["edges"] = [item for item in content["edges"] if item.get("id") != edge["id"]]
        content["edges"].append(edge)
    board.content = content
    board.version += 1
    board.updated_at = utcnow()
    await db.commit()

    return success_response(
        data={
            "task_id": str(task.id),
            "preparation_node": preparation_node,
            "edge": edge,
        },
        message="蛋白制备任务已创建",
    )


@router.post("/research-boards/{board_id}/protein-preparations/{task_id}/sync", response_model=dict)
async def sync_protein_preparation(
    board_id: str,
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    board = await _load_board(board_id, current_user, db)
    await _require_board_write_access(board, current_user, db)
    task = await db.get(Task, task_id)
    if not task or task.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="蛋白制备任务不存在")

    content = normalize_board_content(board.content)
    preparation_node = next(
        (node for node in content["nodes"] if node.get("task_id") == task_id),
        None,
    )
    if preparation_node is None:
        raise HTTPException(status_code=404, detail="白板中不存在对应蛋白制备节点")

    preparation_node["status"] = _task_node_status(task.status)
    artifact_node = None
    edge = None
    output_artifact_id = await _prepared_artifact_id(db, task_id=task_id)
    if output_artifact_id:
        preparation_node["output_artifact_id"] = output_artifact_id
        artifact_node = _prepared_artifact_node(content, output_artifact_id=output_artifact_id)
        edge = _prepared_artifact_edge(preparation_node["id"], artifact_node["id"])
        content["nodes"] = [node for node in content["nodes"] if node.get("id") != artifact_node["id"]]
        content["nodes"].append(artifact_node)
        content["edges"] = [item for item in content["edges"] if item.get("id") != edge["id"]]
        content["edges"].append(edge)

    board.content = content
    board.version += 1
    board.updated_at = utcnow()
    await db.commit()
    return success_response(
        data={
            "preparation_node": preparation_node,
            "artifact_node": artifact_node,
            "edge": edge,
        },
        message="蛋白制备节点已同步",
    )


async def _load_source_protein_artifact(db: AsyncSession, *, artifact_id: str) -> Artifact:
    result = await db.execute(
        select(Artifact)
        .options(selectinload(Artifact.latest_version).selectinload(ArtifactVersion.files))
        .where(Artifact.id == artifact_id)
    )
    artifact = result.scalar_one_or_none()
    if artifact is None or artifact.standard_type != "protein_structure":
        raise HTTPException(status_code=404, detail="蛋白 Artifact 不存在")
    return artifact


def _artifact_version(artifact: Artifact, version_id: str | None) -> ArtifactVersion:
    latest_version = artifact.latest_version
    if latest_version is None or latest_version.status != "available":
        raise HTTPException(status_code=400, detail="蛋白 Artifact 没有可用版本")
    if version_id and latest_version.id != version_id:
        raise HTTPException(status_code=400, detail="暂不支持制备非 latest 的 ArtifactVersion")
    return latest_version


def _primary_file_id(version: ArtifactVersion) -> str | None:
    version_files = list(version.files or [])
    if not version_files:
        return None
    primary = next((item for item in version_files if item.is_primary), None)
    return str((primary or version_files[0]).file_id)


def _preparation_node(
    content: dict[str, Any],
    *,
    tool_id: str,
    task_id: str,
    source_node_id: str | None,
    position: dict[str, float] | None,
) -> dict[str, Any]:
    node_id = f"protein-preparation:{task_id}"
    return {
        "id": node_id,
        "type": "tool",
        "position": position or _offset_position(content, source_node_id=source_node_id),
        "tool_id": tool_id,
        "task_id": task_id,
        "status": "pending",
        "content": "Protein Preparation",
    }


def _offset_position(content: dict[str, Any], *, source_node_id: str | None) -> dict[str, float]:
    source = next(
        (node for node in content.get("nodes", []) if node.get("id") == source_node_id),
        None,
    )
    source_position = source.get("position") if isinstance(source, dict) else None
    if not isinstance(source_position, dict):
        return {"x": 320.0, "y": 0.0}
    return {
        "x": float(source_position.get("x") or 0) + 320.0,
        "y": float(source_position.get("y") or 0),
    }


def _preparation_edge(source_node_id: str | None, target_node_id: str) -> dict[str, Any] | None:
    if not source_node_id:
        return None
    return {
        "id": f"{source_node_id}->{target_node_id}",
        "source": source_node_id,
        "target": target_node_id,
        "label": "prepare",
    }


def _task_node_status(task_status: str) -> str:
    if task_status == TaskStatus.SUCCESS.value:
        return "success"
    if task_status == TaskStatus.FAILURE.value:
        return "failure"
    if task_status == TaskStatus.RUNNING.value:
        return "running"
    if task_status == TaskStatus.CANCELED.value:
        return "canceled"
    return "pending"


async def _prepared_artifact_id(db: AsyncSession, *, task_id: str) -> str | None:
    result = await db.execute(select(TaskOutput).where(TaskOutput.task_id == task_id))
    output = result.scalar_one_or_none()
    if output is None or not isinstance(output.result, dict):
        return None
    standard_artifacts = output.result.get("standard_artifacts")
    if not isinstance(standard_artifacts, dict):
        return None
    artifact_ids = standard_artifacts.get("artifact_ids_by_ref")
    if not isinstance(artifact_ids, dict):
        return None
    artifact_id = artifact_ids.get("prepared_protein")
    return str(artifact_id) if artifact_id else None


def _prepared_artifact_node(content: dict[str, Any], *, output_artifact_id: str) -> dict[str, Any]:
    return {
        "id": f"artifact:{output_artifact_id}",
        "type": "artifact",
        "position": _next_artifact_position(content),
        "artifact_id": output_artifact_id,
    }


def _next_artifact_position(content: dict[str, Any]) -> dict[str, float]:
    nodes = content.get("nodes") if isinstance(content.get("nodes"), list) else []
    max_x = max(
        (
            float((node.get("position") or {}).get("x") or 0)
            for node in nodes
            if isinstance(node, dict)
        ),
        default=0.0,
    )
    return {"x": max_x + 320.0, "y": 0.0}


def _prepared_artifact_edge(source_node_id: str, target_node_id: str) -> dict[str, Any]:
    return {
        "id": f"{source_node_id}->{target_node_id}",
        "source": source_node_id,
        "target": target_node_id,
        "label": "prepared protein",
    }

