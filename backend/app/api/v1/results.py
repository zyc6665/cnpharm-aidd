"""Result center and traceability APIs (docs/05 §10, docs/01 M7).

M7「结果管理与追溯」在一期只交付两件必须可验的事：**结果可检索**、**结果可还原**。
本模块提供：

- 项目/候选物维度的结果列表（``GET /projects/{id}/results``）；
- 单个结果的详情与追溯包（``GET /results/{taskId}``、``/results/{taskId}/traceability``）；
- 追溯包导出为 JSON 文件（``POST /results/{taskId}:export``）。

所有端点复用 ``app.services.traceability`` 的装配逻辑，HTTP 层只做权限与包装。
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.common.exceptions import NotFoundException, ValidationException
from app.common.responses import paginated_response, success_response
from app.common.task_context import task_project_id
from app.database.session import get_db
from app.feature_flags import require_feature_flag
from app.files.remote_access_tokens import create_browser_file_access_token
from app.files.writer import store_file_bytes
from app.models.artifacts import Artifact, ArtifactVersion
from app.models.compounds import Candidate
from app.models.files import FileSourceType
from app.models.tasks import Task, TaskStatus
from app.models.tools import Tool
from app.models.users import User
from app.services.domain_compounds import require_candidate_read_access
from app.services.project_access import require_project_role
from app.services.task_access import ensure_task_read_access
from app.services.traceability import (
    build_traceability_package,
    load_task_snapshots,
    package_sha256,
    serialize_snapshot,
)

_FEATURE_FLAG = Depends(require_feature_flag("AIDD_PROJECT_WORKSPACE_ENABLED"))

READ_ROLES = ("owner", "editor", "runner", "viewer")

#: A task counts as a "result" once it reached a terminal state. Queued and
#: running tasks are visible through the task center instead (docs/06 P-31).
RESULT_STATUSES = (
    TaskStatus.SUCCESS.value,
    TaskStatus.FAILURE.value,
    TaskStatus.CANCELED.value,
)

router = APIRouter(dependencies=[_FEATURE_FLAG])
# 不加 prefix：注册时由 api_router 统一挂 ``/projects``（与 targets / compounds 一致）。
# 自己带 prefix 会让实际路径变成 ``/projects/projects/{id}/results``。
project_router = APIRouter(dependencies=[_FEATURE_FLAG])

__all__ = ["project_router", "router"]


def _download_url(file_id: str, user: User, *, expires_in: int = 3600) -> str:
    from urllib.parse import quote

    token = create_browser_file_access_token(
        file_id=file_id, user_id=str(user.id), expires_in_seconds=expires_in
    )
    return f"/api/v1/files/{file_id}/download?token={quote(token)}"


def _iso(value: Any) -> str | None:
    return value.isoformat() if value else None


async def _load_task(db: AsyncSession, task_id: str) -> Task:
    result = await db.execute(
        select(Task)
        .options(
            selectinload(Task.tool).selectinload(Tool.current_version),
            selectinload(Task.inputs),
            selectinload(Task.outputs),
        )
        .where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise NotFoundException("结果不存在")
    return task


async def _artifact_outputs(db: AsyncSession, task_id: str) -> list[dict[str, Any]]:
    artifacts = (
        await db.execute(
            select(Artifact)
            .where(Artifact.source_task_id == task_id)
            .order_by(Artifact.created_at)
        )
    ).scalars().all()
    entries: list[dict[str, Any]] = []
    for artifact in artifacts:
        version = (
            await db.get(ArtifactVersion, artifact.latest_version_id)
            if artifact.latest_version_id
            else None
        )
        entries.append(
            {
                "id": str(artifact.id),
                "artifact_type": artifact.artifact_type,
                "semantic_type": artifact.semantic_type,
                "standard_type": artifact.standard_type,
                "standard_version": artifact.standard_version,
                "name": artifact.name,
                "version_id": artifact.latest_version_id,
                "version": getattr(version, "version", None),
                "filename": getattr(version, "filename", None),
                "size_bytes": getattr(version, "size_bytes", None),
                "sha256": getattr(version, "sha256", None),
            }
        )
    return entries


def _serialize_result(task: Task) -> dict[str, Any]:
    return {
        "task_id": str(task.id),
        "name": task.name,
        "status": task.status,
        "priority": task.priority,
        "project_id": task_project_id(task),
        "tool_id": str(task.tool_id) if task.tool_id else None,
        "tool_name": task.tool.name if task.tool else None,
        "tool_slug": task.tool.slug if task.tool else None,
        "submitted_by": str(task.user_id) if task.user_id else None,
        "created_at": _iso(task.created_at),
        "started_at": _iso(task.started_at),
        "finished_at": _iso(task.finished_at),
        "execution_time_sec": task.execution_time_sec,
        "error_message": task.error_message,
        "domain": (task.extra_data or {}).get("domain"),
    }


@project_router.get("/{project_id}/results", summary="项目结果列表")
async def list_project_results(
    project_id: str,
    status: str | None = Query(default=None, description="按终态过滤：success/failure/canceled"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List terminal tasks of a project — the 结果中心 数据源 (docs/06 P-33)."""
    await require_project_role(
        db, project_id=project_id, user=current_user, allowed_roles=READ_ROLES
    )

    query = select(Task).where(Task.project_id_expression() == project_id)
    if status:
        if status not in RESULT_STATUSES:
            raise ValidationException(f"不支持的结果状态: {status}")
        query = query.where(Task.status == status)
    else:
        query = query.where(Task.status.in_(RESULT_STATUSES))

    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar_one()
    rows = (
        await db.execute(
            query.options(selectinload(Task.tool))
            .order_by(Task.finished_at.desc().nullslast(), Task.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    return paginated_response(
        items=[_serialize_result(task) for task in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/results/{task_id}", summary="结果详情")
async def get_result(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Result detail: task context + frozen inputs + produced artifacts."""
    task = await _load_task(db, task_id)
    await ensure_task_read_access(db, task=task, current_user=current_user)

    snapshots = await load_task_snapshots(db, task_id=str(task.id))
    return success_response(
        data={
            **_serialize_result(task),
            "inputs": [serialize_snapshot(row) for row in snapshots],
            "outputs": await _artifact_outputs(db, str(task.id)),
            "output_data": task.outputs.result if task.outputs else None,
        }
    )


@router.get("/results/{task_id}/traceability", summary="追溯包")
async def get_result_traceability(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the 追溯包 JSON (docs/05 §10.1, docs/01 §11.2 G-3)."""
    task = await _load_task(db, task_id)
    await ensure_task_read_access(db, task=task, current_user=current_user)

    package = await build_traceability_package(
        db,
        task=task,
        tool=task.tool,
        tool_version=task.tool_version,
        submitter=await db.get(User, str(task.user_id)) if task.user_id else None,
    )
    return success_response(data=package)


@router.post("/results/{task_id}:export", summary="导出追溯包")
async def export_result_traceability(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Persist the 追溯包 as a downloadable JSON file and return its URL.

    A file rather than an inline blob because docs/01 §11.2 的验收动作是「一键导出
    追溯包」——用户拿到的是可以归档、可以发给审计的文件。
    """
    task = await _load_task(db, task_id)
    await ensure_task_read_access(db, task=task, current_user=current_user)

    package = await build_traceability_package(
        db,
        task=task,
        tool=task.tool,
        tool_version=task.tool_version,
        submitter=await db.get(User, str(task.user_id)) if task.user_id else None,
    )
    digest = package_sha256(package)
    content = json.dumps(package, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    filename = f"traceability-{task_id[:8]}-{digest[:12]}.json"

    record = await store_file_bytes(
        db,
        content=content,
        filename=filename,
        content_type="application/json",
        source_type=FileSourceType.SYSTEM,
        owner_id=str(current_user.id),
        project_id=task_project_id(task),
        file_meta={"kind": "traceability_package", "task_id": str(task.id)},
        is_permanent=True,
    )
    await db.commit()
    await db.refresh(record)

    return success_response(
        data={
            "task_id": str(task.id),
            "file_id": str(record.id),
            "filename": filename,
            "sha256": digest,
            "size_bytes": record.size_bytes,
            "download_url": _download_url(str(record.id), current_user),
        }
    )


@router.get("/results/{task_id}/report", summary="结果报告（JSON 快照）")
async def get_result_report(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Human-readable summary of a result, reused by the detail page header."""
    task = await _load_task(db, task_id)
    await ensure_task_read_access(db, task=task, current_user=current_user)

    outputs = await _artifact_outputs(db, str(task.id))
    return success_response(
        data={
            "task_id": str(task.id),
            "name": task.name,
            "status": task.status,
            "summary": (task.outputs.result if task.outputs else None),
            "artifacts": outputs,
            "lineage_hint": {
                "project_id": task_project_id(task),
                "lineage_endpoint": f"/api/v1/projects/{task_project_id(task)}/artifact-lineage"
                if task_project_id(task)
                else None,
            },
        }
    )


@router.get("/candidates/{candidate_id}/results", summary="候选物结果列表")
async def list_candidate_results(
    candidate_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Results whose domain context points at this candidate (docs/05 §5)."""
    candidate = await db.get(Candidate, candidate_id)
    if candidate is None:
        raise NotFoundException("候选物不存在")
    await require_candidate_read_access(db, candidate=candidate, user=current_user)

    query = select(Task).where(Task.status.in_(RESULT_STATUSES))
    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar_one()
    rows = (
        await db.execute(
            query.options(selectinload(Task.tool))
            .order_by(Task.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    matched = [
        task
        for task in rows
        if str(((task.extra_data or {}).get("domain") or {}).get("candidate_id") or "")
        == str(candidate.id)
    ]
    return paginated_response(
        items=[_serialize_result(task) for task in matched],
        total=len(matched),
        page=page,
        page_size=page_size,
    )
