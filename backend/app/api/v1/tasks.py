# backend/app/api/v1/tasks.py
"""任务管理API"""

import logging
from datetime import datetime
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import Any, AsyncIterator, Optional

from app.database.session import async_session_factory, get_db
from app.models.files import File as FileModel
from app.models.users import User
from app.models.tools import Tool, ToolVersion
from app.models.tasks import Task, TaskLog, TaskStatus
from app.tasks.attempts import (
    get_execution_attempt_id,
    is_task_cancellation_pending,
    mark_task_execution_released,
)
from app.tasks.cancellation import cancel_platform_task
from app.common.task_context import task_project_id
from app.tasks.direct_runner import direct_task_runner
from app.tasks.resource_lease import release_task_resource_reservation
from app.tasks.state_machine import TaskStateMachine
from app.tasks.service import (
    create_and_schedule_tool_task,
    dispatch_tool_task,
    prepare_tool_task_preview,
    record_tool_usage,
)
from app.tasks.naming import (
    resolve_task_display_name as _resolve_task_display_name,
    _dedupe_file_ids,
    _extract_file_ids_from_result,
)
from app.auth.dependencies import get_current_user, get_current_user_optional, get_admin_user
from app.config import settings, use_direct_task_execution
from app.schemas.tasks import (
    TaskCreate, TaskListResponse
)
from app.common.responses import paginated_response, success_response
from app.middleware.idempotency import idempotent_route
from app.common.exceptions import (
    ConflictException,
    NotFoundException,
    UnauthorizedException,
    ValidationException,
)
from app.common.task_status import task_status_to_api
from app.files.file_records import is_file_usable
from app.services.task_access import (
    ensure_task_operation_access as _ensure_task_operation_access,
    ensure_task_read_access as _ensure_task_read_access,
)
from app.services.task_views import (
    TaskQueryInput,
    query_resource_wait_stats,
    query_task_page,
    query_task_view_counts,
)
from app.services.tool_presentation import sanitize_public_tool_config
from app.services.task_access import load_task_for_read_access
from app.services.task_event_stream import (
    load_state as load_task_state,
    stream_task_events as stream_events,
)

logger = logging.getLogger(__name__)
router = APIRouter()
def _normalize_task_status(status: Optional[str]) -> Optional[str]:
    return task_status_to_api(status)


def _extract_primary_output_data(result: Any) -> Any:
    if not isinstance(result, dict):
        return result

    nested_result = result.get("result")
    if isinstance(nested_result, dict):
        return nested_result

    return result


_MAX_FAILURE_STREAM_LENGTH = 4000
_STANDARD_ARTIFACT_ERROR_MARKERS = (
    "required standard artifacts",
    "missing required output artifact",
    "result manifest",
    "standard artifact persistence",
)


def _normalize_diagnostic_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if len(text) <= _MAX_FAILURE_STREAM_LENGTH:
        return text
    return f"{text[:_MAX_FAILURE_STREAM_LENGTH]}..."


def _read_diagnostic_field(source: Any, key: str, *, depth: int = 0) -> str:
    if not isinstance(source, dict) or depth > 2:
        return ""

    direct = _normalize_diagnostic_text(source.get(key))
    if direct:
        return direct

    from_details = _read_diagnostic_field(source.get("details"), key, depth=depth + 1)
    if from_details:
        return from_details

    return _read_diagnostic_field(source.get("result"), key, depth=depth + 1)


def _standard_artifact_failure_message(messages: list[str]) -> str:
    for message in messages:
        lowered = message.lower()
        if any(marker in lowered for marker in _STANDARD_ARTIFACT_ERROR_MARKERS):
            return message
        if "standard artifact" in lowered and ("missing" in lowered or "required" in lowered):
            return message
    return ""


def _task_failure_diagnostics(task: Task) -> dict[str, str] | None:
    if _normalize_task_status(task.status) != "failure":
        return None

    result = task.outputs.result if task.outputs else None
    output_data = _extract_primary_output_data(result)
    error_message = _normalize_diagnostic_text(task.error_message)
    stdout = _read_diagnostic_field(result, "stdout") or _read_diagnostic_field(output_data, "stdout")
    stderr = _read_diagnostic_field(result, "stderr") or _read_diagnostic_field(output_data, "stderr")
    standard_artifact_message = _standard_artifact_failure_message(
        [error_message, stderr, stdout]
    )

    if not any([error_message, stdout, stderr, standard_artifact_message]):
        return None

    return {
        "error_message": error_message,
        "stdout": stdout,
        "stderr": stderr,
        "standard_artifact_message": standard_artifact_message,
    }


def _task_project_id(task: Task) -> Optional[str]:
    return task_project_id(task)


def _task_input_bindings(task: Task) -> dict[str, str]:
    data = task.extra_data if isinstance(task.extra_data, dict) else {}
    bindings = data.get("input_bindings")
    if not isinstance(bindings, dict):
        return {}
    return {
        str(input_name): str(version_id)
        for input_name, version_id in bindings.items()
        if input_name and version_id
    }


def _task_binding_decisions(task: Task) -> dict[str, Any]:
    data = task.extra_data if isinstance(task.extra_data, dict) else {}
    decisions = data.get("binding_decisions")
    return decisions if isinstance(decisions, dict) else {}


def _task_resource_wait(task: Task) -> dict[str, Any] | None:
    """Expose safe resource-wait metadata for pending tasks."""
    data = task.extra_data if isinstance(task.extra_data, dict) else {}
    legacy_reason = data.get("resource_wait_reason")
    reason = data.get("resource_wait_code") or legacy_reason
    if not reason:
        return None

    try:
        retry_count = int(data.get("resource_retry_count") or 0)
    except (TypeError, ValueError):
        retry_count = 0

    next_attempt_at = data.get("resource_retry_next_at")
    result = {
        "reason": str(reason),
        "retry_count": retry_count,
        "next_attempt_at": str(next_attempt_at) if next_attempt_at else None,
    }
    if data.get("resource_wait_code"):
        result.update(
            {
                "category": str(data.get("resource_wait_category") or "resource"),
                "scope": str(data["resource_wait_scope"])
                if data.get("resource_wait_scope")
                else None,
                "dimension": str(data["resource_wait_dimension"])
                if data.get("resource_wait_dimension")
                else None,
                "legacy_reason": str(legacy_reason)
                if legacy_reason and legacy_reason != reason
                else None,
            }
        )
    return result


def _serialize_task_log(log: TaskLog) -> dict[str, Any]:
    return {
        "id": log.id,
        "task_id": log.task_id,
        "timestamp": log.timestamp,
        "level": (log.level or "INFO").lower(),
        "message": log.message,
        "metadata": log.log_data or {},
    }


async def _load_files(db: AsyncSession, file_ids: list[str]) -> list[dict[str, Any]]:
    if not file_ids:
        return []

    result = await db.execute(
        select(FileModel).where(FileModel.id.in_(file_ids))
    )
    files = {file.id: file for file in result.scalars().all()}

    serialized: list[dict[str, Any]] = []
    for file_id in file_ids:
        file = files.get(file_id)
        if not file or not is_file_usable(file):
            logger.warning("Task detail references missing file id %s", file_id)
            continue

        original_name = file.file_meta.get("original_name") if isinstance(file.file_meta, dict) else None
        relative_path = file.file_meta.get("relative_path") if isinstance(file.file_meta, dict) else None
        serialized.append({
            "id": file.id,
            "filename": file.filename,
            "original_name": original_name or file.filename,
            "relative_path": relative_path,
            "size": file.size_bytes,
            "content_type": file.content_type,
            "sha256": file.sha256,
            "url": f"/api/v1/files/{file.id}/download",
        })

    return serialized


def _serialize_task_tool(tool: Optional[Tool]) -> Optional[dict[str, Any]]:
    if not tool:
        return None

    current_version = None
    if tool.current_version:
        current_version = {
            "id": tool.current_version.id,
            "tool_id": tool.current_version.tool_id,
            "version": tool.current_version.version,
            "config": sanitize_public_tool_config(
                tool.current_version.config or {}
            ),
            "is_active": tool.current_version.is_active,
            "deprecated": tool.current_version.deprecated,
        }

    return {
        "id": tool.id,
        "name": tool.name,
        "slug": tool.slug,
        "description": tool.description,
        "icon": tool.icon,
        "status": tool.status,
        "version": tool.current_version.version if tool.current_version else None,
        "run_count": tool.statistics.usage_count if tool.statistics else 0,
        "current_version": current_version,
    }


async def _record_tool_usage(db: AsyncSession, tool_id: str) -> None:
    """确保工具统计存在，并记录一次使用。"""
    await record_tool_usage(db, tool_id)


def _resolve_session_factory(db: AsyncSession) -> async_sessionmaker[AsyncSession]:
    """SSE 生成器要自己开关会话，不能复用请求作用域的 ``db``。

    测试里会覆盖 ``get_db`` 指向内存库，此时必须用同一个 bind 建会话工厂，
    否则流式阶段会去连生产库。
    """
    bind = db.get_bind()
    bound_engine = getattr(bind, "engine", None) or bind
    if bound_engine is async_session_factory.kw["bind"]:
        return async_session_factory
    return async_sessionmaker(bound_engine, expire_on_commit=False, autoflush=False)


async def _guarded_event_source(
    generator: AsyncIterator[str],
    request: Request,
) -> AsyncIterator[str]:
    """浏览器关闭标签页时及时停止生成器，避免泄漏数据库轮询。"""
    try:
        async for chunk in generator:
            if await request.is_disconnected():
                break
            yield chunk
    finally:
        await generator.aclose()


@router.get("", response_model=dict)
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    view: Optional[str] = Query(
        None,
        description="系统任务视图: all/running/history/needs_attention/recent_results",
    ),
    status: Optional[str] = None,
    tool_id: Optional[str] = None,
    keyword: Optional[str] = None,
    project_id: Optional[str] = Query(None, min_length=1, max_length=36),
    created_from: Optional[datetime] = Query(None, description="创建时间起点"),
    created_to: Optional[datetime] = Query(None, description="创建时间终点"),
    workflow_run_id: Optional[str] = Query(None, description="工作流运行 ID"),
    workflow_definition_id: Optional[str] = Query(None, description="工作流定义 ID"),
    workflow_node_id: Optional[str] = Query(None, description="工作流节点 ID"),
    resource_wait_category: Optional[str] = Query(
        None, description="按资源等待分类筛选: quota/worker_capacity/gpu/scheduler/resource"
    ),
    resource_wait_scope: Optional[str] = Query(
        None, description="按资源等待 scope 筛选: user/project"
    ),
    cursor: Optional[str] = Query(
        None,
        description=(
            "游标分页（深分页用）。传入上一页响应里的 nextCursor 即可，"
            "此时不再返回 total，只用 nextCursor/hasMore 翻页"
        ),
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取任务列表"""
    page_result = await query_task_page(
        db,
        TaskQueryInput(
            current_user=current_user,
            page=page,
            page_size=page_size,
            view=view,
            status=status,
            tool_id=tool_id,
            keyword=keyword,
            project_id=project_id,
            created_from=created_from,
            created_to=created_to,
            workflow_run_id=workflow_run_id,
            workflow_definition_id=workflow_definition_id,
            workflow_node_id=workflow_node_id,
            resource_wait_category=resource_wait_category,
            resource_wait_scope=resource_wait_scope,
        ),
        cursor=cursor,
    )

    # 构建响应
    task_list = []
    for task in page_result.tasks:
        task_dict = TaskListResponse.model_validate(task).model_dump()
        task_dict["status"] = _normalize_task_status(task.status)
        if task.tool:
            task_dict["tool_name"] = task.tool.name
            task_dict["tool_slug"] = task.tool.slug
        task_dict["name"] = _resolve_task_display_name(
            name=task.name,
            tool_name=task.tool.name if task.tool else None,
            created_at=task.created_at,
            task_id=task.id,
        )
        task_dict["project_id"] = _task_project_id(task)
        task_dict["input_bindings"] = _task_input_bindings(task)
        task_dict["binding_decisions"] = _task_binding_decisions(task)
        task_dict["resource_wait"] = _task_resource_wait(task)
        task_dict["user_id"] = task.user_id
        if task.user:
            task_dict["user_name"] = task.user.display_name or task.user.email.split("@")[0]
            task_dict["user_email"] = task.user.email
        task_list.append(task_dict)

    response = paginated_response(
        items=task_list,
        total=page_result.total or 0,
        page=page,
        page_size=page_size,
    )
    # 游标模式不承诺 total：算总数与深分页同代价，会把这轮优化的收益抵掉。
    data = response["data"]
    data["nextCursor"] = page_result.next_cursor
    data["hasMore"] = page_result.has_more
    data["totalKnown"] = page_result.total is not None
    if page_result.total is None:
        data["total"] = None
        data["total_pages"] = None
    return response


@router.get("/counts", response_model=dict)
async def get_task_counts(
    tool_id: Optional[str] = None,
    keyword: Optional[str] = None,
    project_id: Optional[str] = Query(None, min_length=1, max_length=36),
    created_from: Optional[datetime] = Query(None, description="创建时间起点"),
    created_to: Optional[datetime] = Query(None, description="创建时间终点"),
    workflow_run_id: Optional[str] = Query(None, description="工作流运行 ID"),
    workflow_definition_id: Optional[str] = Query(None, description="工作流定义 ID"),
    workflow_node_id: Optional[str] = Query(None, description="工作流节点 ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取任务系统视图计数。"""
    counts = await query_task_view_counts(
        db,
        TaskQueryInput(
            current_user=current_user,
            tool_id=tool_id,
            keyword=keyword,
            project_id=project_id,
            created_from=created_from,
            created_to=created_to,
            workflow_run_id=workflow_run_id,
            workflow_definition_id=workflow_definition_id,
            workflow_node_id=workflow_node_id,
        ),
    )

    return success_response(counts.__dict__)


@router.get("/resource-wait-stats", response_model=dict)
async def get_resource_wait_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户可见 pending 任务的资源等待统计。"""
    stats = await query_resource_wait_stats(
        db,
        TaskQueryInput(current_user=current_user),
    )
    return success_response(stats.__dict__)


@router.post("/prepare-preview", response_model=dict)
async def prepare_task_preview(    task_data: TaskCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """预览任务输入准备和标准 Artifact readiness，不创建任务。"""
    preview = await prepare_tool_task_preview(
        db=db,
        current_user=current_user,
        task_data=task_data,
    )
    return success_response(data=preview)


@router.get("/{task_id}/events")
async def stream_task_events(
    task_id: str,
    request: Request,
    include_logs: bool = Query(True, description="是否把新日志作为 log 事件一并推送"),
    max_seconds: Optional[int] = Query(None, ge=5, le=7200, description="单条连接最长存活秒数"),
    current_user: User = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """SSE 订阅任务状态与进度（docs/05 §1.5、§9；docs/10 API-08）。

    认证仅接受 `Authorization: Bearer` 或 HttpOnly Cookie（P1-7 起前端 EventSource
    已用 `withCredentials` Cookie 认证）。不再接受 `?token=` 查询参数——URL 会进
    访问日志/Referer，泄漏长寿命凭证（P2 已移除）。

    事件序列：`snapshot` → （`status` / `progress` / `log`）* → `done`。
    任务进入终态后服务端主动关流；数小时级任务到 `max_seconds` 后由前端重连。
    """
    user = current_user
    if user is None:
        raise UnauthorizedException("未提供认证凭证")

    await load_task_for_read_access(db, task_id=task_id, current_user=user)
    state = await load_task_state(db, task_id)
    if state is None:
        raise NotFoundException("任务不存在")

    session_factory = _resolve_session_factory(db)
    generator = stream_events(
        session_factory=session_factory,
        task_id=task_id,
        initial=state,
        poll_interval_seconds=settings.TASK_EVENT_POLL_INTERVAL_SECONDS,
        heartbeat_seconds=settings.TASK_EVENT_HEARTBEAT_SECONDS,
        max_duration_seconds=float(
            max_seconds if max_seconds is not None else settings.TASK_EVENT_MAX_DURATION_SECONDS
        ),
        include_logs=include_logs and settings.TASK_EVENT_INCLUDE_LOGS,
    )
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        # 关掉 Nginx / Ingress 的响应缓冲，否则事件会被攒到缓冲区满才下发。
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        _guarded_event_source(generator, request),
        media_type="text/event-stream",
        headers=headers,
    )


@router.get("/{task_id}", response_model=dict)
async def get_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取任务详情"""
    result = await db.execute(
        select(Task)
        .options(
            selectinload(Task.tool).selectinload(Tool.current_version),
            selectinload(Task.tool).selectinload(Tool.statistics),
            selectinload(Task.inputs),
            selectinload(Task.outputs)
        )
        .where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise NotFoundException("任务不存在")

    await _ensure_task_read_access(db, task=task, current_user=current_user)

    input_file_ids = task.inputs.file_ids if task.inputs and task.inputs.file_ids else []
    output_file_ids = []
    if task.outputs:
        output_file_ids = task.outputs.file_ids or _extract_file_ids_from_result(task.outputs.result)
    output_file_ids = _dedupe_file_ids([str(file_id) for file_id in output_file_ids])

    task_data = {
        "id": task.id,
        "name": _resolve_task_display_name(
            name=task.name,
            tool_name=task.tool.name if task.tool else None,
            created_at=task.created_at,
            task_id=task.id,
        ),
        "project_id": _task_project_id(task),
        "input_bindings": _task_input_bindings(task),
        "binding_decisions": _task_binding_decisions(task),
        "user_id": task.user_id,
        "tool_id": task.tool_id,
        "tool_version_id": task.tool_version_id,
        "tool_name": task.tool.name if task.tool else None,
        "tool_slug": task.tool.slug if task.tool else None,
        "tool": _serialize_task_tool(task.tool),
        "resource_snapshot": (task.extra_data or {}).get("resource_snapshot"),
        "mock": bool((task.extra_data or {}).get("mock")),
        "dispatch": (task.extra_data or {}).get("dispatch"),
        # docs/10 §8.3：任务详情页据此直接跳到追踪面板。老任务没有这个键（功能
        # 上线前建的），返回 None 而不是空串，前端按 falsy 处理即可不显示入口。
        "traceId": (task.extra_data or {}).get("traceId"),
        "status": _normalize_task_status(task.status),
        "priority": task.priority,
        "progress": task.progress,
        "progress_message": task.progress_message,
        "error_message": task.error_message,
        "failure_diagnostics": _task_failure_diagnostics(task),
        "resource_wait": _task_resource_wait(task),
        "started_at": task.started_at,
        "finished_at": task.finished_at,
        "completed_at": task.finished_at,
        "execution_time_sec": task.execution_time_sec,
        "retry_count": task.retry_count,
        "retry_of": task.retry_of,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "inputs": {
            "params": task.inputs.params if task.inputs else {},
            "file_ids": input_file_ids,
            "input_bindings": _task_input_bindings(task),
        },
        "outputs": {
            "result": task.outputs.result if task.outputs else None,
            "file_ids": output_file_ids,
            "output_type": task.outputs.output_type if task.outputs else "json",
        },
        "output_data": _extract_primary_output_data(task.outputs.result) if task.outputs else None,
        "input_files": await _load_files(db, input_file_ids),
        "output_files": await _load_files(db, output_file_ids),
    }

    return success_response(data=task_data)


@router.post("", response_model=dict)
@idempotent_route(path_template="/api/v1/tasks", resource_type="task")
async def create_task(
    task_data: TaskCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """创建任务

    支持 ``X-Idempotency-Key``（docs/05 §12）：同键同体返回首响快照、同键异体
    40905、首次仍在处理中 40904 + ``Retry-After``。没带该请求头时行为完全不变。

    项目配额（docs/04 §5.3）的准入检查不在这里，而在
    ``app.tasks.service.create_and_schedule_tool_task``：那是全平台唯一的建任务入口，
    k8s smoke、结构预测、workflow 节点、direct recovery 都走它。挂在路由上只能
    覆盖 HTTP 这一条路径，其他入口可以绕开配额无限提交。被拦时抛 429
    ``429 / 配额超出``，``detail`` 里带 ``dimension`` / ``limit`` / 已用量。
    """
    task = await create_and_schedule_tool_task(
        db=db,
        current_user=current_user,
        task_data=task_data,
        direct_runner=direct_task_runner,
    )
    task_result = await db.execute(
        select(Task)
        .options(
            selectinload(Task.tool).selectinload(Tool.current_version),
            selectinload(Task.tool).selectinload(Tool.statistics),
        )
        .where(Task.id == task.id)
    )
    task = task_result.scalar_one()

    return success_response(
        data={
            "id": task.id,
            "name": task.name,
            "project_id": _task_project_id(task),
            "input_bindings": _task_input_bindings(task),
            "binding_decisions": _task_binding_decisions(task),
            "user_id": task.user_id,
            "tool_id": task.tool_id,
            "tool_version_id": task.tool_version_id,
            "tool_name": task.tool.name if task.tool else None,
            "tool_slug": task.tool.slug if task.tool else None,
            "tool": _serialize_task_tool(task.tool),
            "resource_snapshot": (task.extra_data or {}).get("resource_snapshot"),
            "dispatch": (task.extra_data or {}).get("dispatch"),
            "traceId": (task.extra_data or {}).get("traceId"),
            "resource_wait": _task_resource_wait(task),
            "status": _normalize_task_status(task.status),
            "priority": task.priority,
            "progress": task.progress,
            "progress_message": task.progress_message,
            "error_message": task.error_message,
            "started_at": task.started_at,
            "finished_at": task.finished_at,
            "execution_time_sec": task.execution_time_sec,
            "retry_count": task.retry_count,
            "retry_of": task.retry_of,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        },
        message="任务创建成功"
    )


@router.post("/{task_id}/cancel", response_model=dict)
async def cancel_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """取消任务"""
    result = await db.execute(
        select(Task).where(Task.id == task_id).with_for_update()
    )
    task = result.scalar_one_or_none()

    if not task:
        raise NotFoundException("任务不存在")

    await _ensure_task_operation_access(db, task=task, current_user=current_user)

    # 只能取消待调度、排队中或运行中的任务
    if task.status not in [
        TaskStatus.PENDING.value,
        TaskStatus.QUEUED.value,
        TaskStatus.RUNNING.value,
    ]:
        raise ValidationException("任务状态不允许取消")

    await cancel_platform_task(
        db,
        task=task,
        current_user=current_user,
        direct_runner=direct_task_runner,
    )
    await db.commit()

    return success_response(message="任务已取消")


@router.post("/{task_id}/retry", response_model=dict)
async def retry_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """重试任务"""
    result = await db.execute(
        select(Task).where(Task.id == task_id).with_for_update()
    )
    task = result.scalar_one_or_none()

    if not task:
        raise NotFoundException("任务不存在")

    await _ensure_task_operation_access(db, task=task, current_user=current_user)

    # 只能重试失败、超时或取消的任务
    #
    # 被拒（REJECTED）**刻意不在这里**：本接口不做配额准入（配额只在
    # ``create_and_schedule_tool_task`` 里查），放进来就等于给「提交被拒 →
    # 点重试」开了一条绕过配额的路。被拒后应重新提交，走完整准入流程；
    # 那条被拒的行留在库里作为审计证据（docs/03 §3.4）。
    if task.status not in [
        TaskStatus.FAILURE.value,
        TaskStatus.TIMEOUT.value,
        TaskStatus.CANCELED.value,
    ]:
        raise ValidationException("任务状态不允许重试")
    if is_task_cancellation_pending(task):
        is_direct_runner_idle = False
        if use_direct_task_execution():
            is_task_active = getattr(direct_task_runner, "is_task_active", None)
            if callable(is_task_active):
                is_direct_runner_idle = not is_task_active(str(task.id))
        if is_direct_runner_idle:
            mark_task_execution_released(
                task,
                attempt_id=get_execution_attempt_id(task),
                reason="direct_runner_task_not_active",
            )
        else:
            raise ConflictException("上一次执行尚未确认停止，暂时不能重试")

    version_result = await db.execute(
        select(ToolVersion).where(ToolVersion.id == task.tool_version_id)
    )
    tool_version = version_result.scalar_one()

    user_result = await db.execute(
        select(User).where(User.id == task.user_id)
    )
    task_user = user_result.scalar_one()

    if not TaskStateMachine.can_retry(task):
        raise ValidationException(
            f"任务已达到最大重试次数 ({task.max_retries})，无法再次重试"
        )

    await release_task_resource_reservation(task, reason="task_retry_requested")

    # G-4：记录重试来源（重试链起点任务 id），且**只在为空时写一次**。
    # 本仓库的重提是就地复用同一 task 行（``TaskStateMachine.retry`` 不新建行），
    # 「上一次执行」只是同一行上的一次 execution attempt，并没有另一条 task 行可指。
    # 因此 ``retry_of`` 记「本次重试起源于哪个任务」：首次重试时链起点就是本行自身，
    # 写入 ``task.id``，语义退化为「本行是重试产物」的持久标记。写入后永不覆盖，
    # 否则后续每次重试都会把「最初从哪条任务开始重试」这条信息抹掉（见测试变异验证）。
    if not task.retry_of:
        task.retry_of = str(task.id)

    TaskStateMachine.retry(task)

    await db.commit()
    extra_data = task.extra_data if isinstance(task.extra_data, dict) else {}
    resource_snapshot = extra_data.get("resource_snapshot")
    await dispatch_tool_task(
        db=db,
        task=task,
        tool_version=tool_version,
        user_role=task_user.role,
        direct_runner=direct_task_runner,
        resource_snapshot=resource_snapshot if isinstance(resource_snapshot, dict) else None,
        failure_detail="任务重新分发失败",
    )

    return success_response(message="任务已重新提交")


@router.get("/{task_id}/logs", response_model=dict)
async def get_task_logs(
    task_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    level: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取任务日志"""
    # 检查任务是否存在和权限
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise NotFoundException("任务不存在")

    await _ensure_task_read_access(db, task=task, current_user=current_user)

    # 查询日志
    query = select(TaskLog).where(TaskLog.task_id == task_id)

    if level:
        query = query.where(TaskLog.level == level)

    # 计算总数
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # 分页
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(TaskLog.timestamp.asc())

    result = await db.execute(query)
    logs = result.scalars().all()

    return paginated_response(
        items=[_serialize_task_log(log) for log in logs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.delete("/{task_id}", response_model=dict)
async def delete_task(
    task_id: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """删除任务（管理员）"""
    result = await db.execute(
        select(Task).where(Task.id == task_id).with_for_update()
    )
    task = result.scalar_one_or_none()

    if not task:
        raise NotFoundException("任务不存在")

    if is_task_cancellation_pending(task):
        raise ConflictException("任务取消尚未确认停止，暂时不能删除")

    if task.status in {
        TaskStatus.PENDING.value,
        TaskStatus.QUEUED.value,
        TaskStatus.RUNNING.value,
    }:
        was_running = task.status == TaskStatus.RUNNING.value
        await cancel_platform_task(
            db,
            task=task,
            current_user=current_user,
            direct_runner=direct_task_runner,
        )
        if was_running:
            await db.commit()
            return success_response(message="运行中任务已发起取消，记录保留")
    else:
        await release_task_resource_reservation(task, reason="task_deleted")
    await db.delete(task)
    await db.commit()

    return success_response(message="任务删除成功")
