"""Result center and traceability APIs (docs/05 §10, docs/01 M7).

M7「结果管理与追溯」在一期只交付两件必须可验的事：**结果可检索**、**结果可还原**。
本模块提供：

- 项目/候选物维度的结果列表（``GET /projects/{id}/results``）；
- 单个结果的详情与追溯包（``GET /results/{taskId}``、``/results/{taskId}/traceability``）；
- 追溯包导出为 JSON 文件（``POST /results/{taskId}:export``）；
- 分析报告：JSON 快照（``GET /results/{taskId}/report``，历史行为不变）、
  PDF 直出（``GET /results/{taskId}/report.pdf``）、PDF 落库导出
  （``POST /results/{taskId}/report:export``）——docs/12 TC-M7-04 / TC-M7-08；
- 运行参数差异矩阵（``POST /results:compare``）——docs/12 TC-M7-07。

所有端点复用 ``app.services.traceability`` 的装配逻辑，HTTP 层只做权限与包装。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.common.exceptions import ForbiddenException, NotFoundException, ValidationException
from app.common.responses import paginated_response, success_response
from app.common.task_context import task_project_id
from app.common.task_status import task_status_to_api
from app.common.time import utcnow
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
from app.services.param_diff import (
    MAX_TASKS,
    MIN_TASKS,
    build_param_diff,
    load_task_params,
    load_tasks_by_ids,
)
from app.services.project_access import require_project_role
from app.services.report_pdf import (
    REPORT_TEMPLATE_VERSION,
    build_result_report_pdf,
    extract_conclusions,
)
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
#:
#: REJECTED 刻意**不在**这里：它是终态，但一个从未执行的任务没有「结果」可言，
#: 出现在结果中心只会让用户点进去看到空产物。它属于任务中心（P-31）的
#: 「历史」页签——那里才是「我那次提交发生了什么」的归宿。
RESULT_STATUSES = (
    TaskStatus.SUCCESS.value,
    TaskStatus.FAILURE.value,
    TaskStatus.CANCELED.value,
    TaskStatus.TIMEOUT.value,
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
    domain = (task.extra_data or {}).get("domain") or {}
    return {
        "task_id": str(task.id),
        "name": task.name,
        "status": task_status_to_api(task.status),
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
        # 列表页按字符串渲染；domain 是结构化 dict，直接下发会显示 [object Object]。
        "domain": domain.get("kind") if isinstance(domain, dict) else None,
        "mock": bool((task.extra_data or {}).get("mock")),
    }


@project_router.get("/{project_id}/results", summary="项目结果列表")
async def list_project_results(
    project_id: str,
    status: str | None = Query(
        default=None, description="按终态过滤（小写）：success/failure/canceled/timeout"
    ),
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
        # 前端按小写契约传参（success/failure/canceled/timeout），库里是枚举大写值。
        normalized = status.strip().upper()
        if normalized not in RESULT_STATUSES:
            raise ValidationException(f"不支持的结果状态: {status}")
        query = query.where(Task.status == normalized)
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
            "status": task_status_to_api(task.status),
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


async def _report_payload(
    db: AsyncSession, *, task: Task
) -> tuple[dict[str, Any], str, list[dict[str, str]]]:
    """装配 PDF 报告所需的全部数据：``(追溯包, 追溯包内容 sha256, 结论行)``。

    报告与追溯包共用同一个数据源，避免「纸面报告与导出文件对不上」。
    ``ArtifactVersion.summary_json`` / ``metrics_json`` 只用来补「结论」段，
    取不到就空着，绝不臆造指标。

    指纹取的是**内容**指纹（排除 ``exportedAt``）：那是本次构建时刻，同一份
    历史任务两次渲染必然不同，拿它当页脚指纹就没法用来复核「报告没被改过」。
    """
    package = await build_traceability_package(
        db,
        task=task,
        tool=task.tool,
        tool_version=task.tool_version,
        submitter=await db.get(User, str(task.user_id)) if task.user_id else None,
    )

    summaries: list[tuple[str, dict[str, Any]]] = []
    artifacts = (
        await db.execute(
            select(Artifact)
            .where(Artifact.source_task_id == str(task.id))
            .order_by(Artifact.created_at)
        )
    ).scalars().all()
    for artifact in artifacts:
        if not artifact.latest_version_id:
            continue
        version = await db.get(ArtifactVersion, artifact.latest_version_id)
        if version is None:
            continue
        merged: dict[str, Any] = {}
        for source in (getattr(version, "metrics_json", None), getattr(version, "summary_json", None)):
            if isinstance(source, dict):
                merged.update(source)
        if merged:
            summaries.append((artifact.name or artifact.semantic_type, merged))

    conclusions = extract_conclusions(
        task.outputs.result if task.outputs else None,
        artifact_summaries=summaries,
    )
    return package, _package_content_sha256(package), conclusions


def _package_content_sha256(package: dict[str, Any]) -> str:
    """追溯包**内容**指纹：去掉每次构建都会变的 ``exportedAt`` 后再哈希。

    ``exportedAt`` 是「这次装配发生在何时」，不属于任务事实；把它算进指纹
    会让同一历史任务每次渲染得到不同页脚，既无法复核也无法测试。
    """
    content = {key: value for key, value in package.items() if key != "exportedAt"}
    return package_sha256(content)


def _render_report_pdf(
    package: dict[str, Any],
    *,
    digest: str,
    conclusions: list[dict[str, str]],
    generated_at: datetime,
) -> bytes:
    return build_result_report_pdf(
        package,
        conclusions=conclusions,
        package_sha256=digest,
        generated_at=generated_at,
    )


@router.get(
    "/results/{task_id}/report.pdf",
    summary="结果分析报告（PDF）",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def get_result_report_pdf(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Render the 分析报告 as a real PDF (docs/12 TC-M7-08).

    直出流而非落库：报告是追溯包的**纯函数投影**（同包 → 同内容），没有
    需要在服务端留存的新信息；直接返回字节省掉一次存储写入与一次下载往返，
    也让「打开即见」的交互不受文件生命周期策略影响。需要归档文件或分享链接
    时用 ``POST /results/{taskId}/report:export``（900 秒预签名 URL）。
    """
    task = await _load_task(db, task_id)
    await ensure_task_read_access(db, task=task, current_user=current_user)

    package, digest, conclusions = await _report_payload(db, task=task)
    pdf_bytes = _render_report_pdf(
        package, digest=digest, conclusions=conclusions, generated_at=utcnow()
    )

    filename = f"report-{str(task.id)[:8]}-{digest[:12]}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # 模板版本与追溯包指纹放进响应头，便于 CDN/网关日志里也能核对。
            "X-Report-Template-Version": REPORT_TEMPLATE_VERSION,
            "X-Traceability-Sha256": digest,
        },
    )


@router.post("/results/{task_id}/report:export", summary="导出分析报告（PDF 文件）")
async def export_result_report_pdf(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Persist the PDF report and return a short-lived download URL.

    URL 有效期 900 秒（15 分钟），对齐 docs/12 TC-M7-08「预签名 URL 有效期
    ≤ 15min」。报告本身 ``is_permanent=True``：过期的是**链接**，不是报告。
    """
    task = await _load_task(db, task_id)
    await ensure_task_read_access(db, task=task, current_user=current_user)

    package, digest, conclusions = await _report_payload(db, task=task)
    pdf_bytes = _render_report_pdf(
        package, digest=digest, conclusions=conclusions, generated_at=utcnow()
    )

    filename = f"report-{str(task.id)[:8]}-{digest[:12]}.pdf"
    record = await store_file_bytes(
        db,
        content=pdf_bytes,
        filename=filename,
        content_type="application/pdf",
        source_type=FileSourceType.SYSTEM,
        owner_id=str(current_user.id),
        project_id=task_project_id(task),
        file_meta={
            "kind": "result_report_pdf",
            "task_id": str(task.id),
            "template_version": REPORT_TEMPLATE_VERSION,
            "traceability_sha256": digest,
        },
        is_permanent=True,
    )
    await db.commit()
    await db.refresh(record)

    return success_response(
        data={
            "task_id": str(task.id),
            "file_id": str(record.id),
            "filename": filename,
            "content_type": "application/pdf",
            "sha256": digest,
            "size_bytes": record.size_bytes,
            "template_version": REPORT_TEMPLATE_VERSION,
            "expires_in_seconds": 900,
            "download_url": _download_url(str(record.id), current_user, expires_in=900),
        }
    )


class ResultCompareRequest(BaseModel):
    """``POST /results:compare`` 的请求体（docs/05）。"""

    task_ids: list[str] = Field(
        ...,
        alias="taskIds",
        min_length=MIN_TASKS,
        max_length=MAX_TASKS,
        description=f"待比较的任务 ID，{MIN_TASKS}~{MAX_TASKS} 个",
    )

    model_config = {"populate_by_name": True}


@router.post("/results:compare", summary="运行参数差异（多任务）")
async def compare_result_params(
    payload: ResultCompareRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """参数差异矩阵：字段为行、任务为列（docs/12 TC-M7-07）。

    POST 而非 GET：任务 ID 是**资源选择**而不是检索条件的修饰符，6 个 UUID
    塞进 query string 会逼近部分网关的 URL 长度限制，且这里返回的是「一次
    比较」的结果对象而非集合——docs/05 也把它定义为 ``POST ...:compare``。
    """
    task_ids = list(dict.fromkeys(payload.task_ids))
    if len(task_ids) < MIN_TASKS:
        raise ValidationException(f"至少需要 {MIN_TASKS} 个不同的任务")
    if len(task_ids) > MAX_TASKS:
        raise ValidationException(f"最多支持 {MAX_TASKS} 个任务")

    tasks = await load_tasks_by_ids(db, task_ids=task_ids)
    if len(tasks) != len(task_ids):
        # 与「不存在」同一响应：不暴露某个 ID 是否存在。
        raise NotFoundException("结果不存在")

    for task in tasks:
        try:
            await ensure_task_read_access(db, task=task, current_user=current_user)
        except ForbiddenException as exc:
            # 任一任务不可读 → 整体 404，避免用 403 反推出任务存在。
            raise NotFoundException("结果不存在") from exc

    params_by_task = await load_task_params(db, task_ids=task_ids)
    diff = build_param_diff(tasks, params_by_task)
    diff["templateVersion"] = REPORT_TEMPLATE_VERSION
    return success_response(data=diff)


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

    query = select(Task).where(
        Task.status.in_(RESULT_STATUSES),
        Task.extra_data["domain"]["candidate_id"].as_string() == candidate_id,
    )
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

    return paginated_response(
        items=[_serialize_result(task) for task in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
