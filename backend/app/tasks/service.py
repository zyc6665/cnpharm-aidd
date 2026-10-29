"""Reusable task creation and scheduling service."""

from __future__ import annotations

import inspect
import logging
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.config import settings, use_direct_task_execution
from app.common.exceptions import NotFoundException, QuotaExceededException, ValidationException
from app.common.trace import get_trace_id
from app.logging.audit import AuditAction, get_audit_logger
from app.database.base import utcnow
from app.models.statistics import ToolStatistics
from app.models.tasks import Task, TaskInput, TaskStatus
from app.models.tools import Tool, ToolVersion
from app.models.users import User
from app.schemas.tasks import TaskCreate
from app.services.project_migration import ensure_migration_project_for_owner
from app.services.project_quotas import check_submission_allowed
from app.services.rbac import require_project_action
from app.services.run_input_normalization import normalize_string_mapping
from app.services.workflow_task_lookup import find_existing_workflow_node_task
from app.services.run_preparation import PreparedRun, RunContext, RunPreparationInput, prepare_run
from app.services.tool_contracts import (
    build_tool_contract,
    contract_emits_standard_artifacts,
    tool_emits_standard_artifacts,
)
from app.tool_packages.config_resolver import tool_package_declares_mock
from app.services.standard_input_uploads import (
    accepts_materialized_standard_uploads,
    materialize_standard_input_uploads,
    standard_uploads_need_default_project,
    validate_standard_input_uploads,
)
from app.services.traceability import record_task_inputs
from app.tasks.attempts import (
    invoke_with_optional_attempt,
    new_execution_attempt_id,
    set_execution_attempt_id,
)
from app.tasks.commands import TaskCommand
from app.common.task_context import set_task_project_id, task_project_id
from app.tasks.direct_runner import direct_task_runner as default_direct_task_runner
from app.tasks.naming import (
    resolve_task_display_name,
)
from app.tasks.resource_profile import (
    ResourceRequest,
    build_task_resource_snapshot,
    resource_request_from_snapshot,
)
from app.tasks.resource_lease import WorkerResourceLeaseManager
from app.tasks.worker_capability_registry import WorkerCapabilityRegistry
from app.tasks.state_machine import TaskStateMachine


logger = logging.getLogger(__name__)


def _tool_config_emits_standard_artifacts(config: object) -> bool:
    if not isinstance(config, dict):
        return False
    tool = SimpleNamespace(
        slug=config.get("builtin_slug"),
        current_version=SimpleNamespace(config=config),
    )
    return contract_emits_standard_artifacts(build_tool_contract(tool))


async def record_tool_usage(db: AsyncSession, tool_id: str) -> None:
    """Ensure tool statistics exists, then record one use."""
    now = utcnow()

    update_result = await db.execute(
        update(ToolStatistics)
        .where(ToolStatistics.tool_id == tool_id)
        .values(
            usage_count=ToolStatistics.usage_count + 1,
            last_used_at=now,
            last_updated_at=now,
        )
    )
    if update_result.rowcount:
        return

    statistics = ToolStatistics(
        tool_id=tool_id,
        usage_count=1,
        last_used_at=now,
        last_updated_at=now,
    )
    db.add(statistics)
    await db.flush()


def _set_task_extra_data(task: Task, **values: object) -> None:
    base = task.extra_data if isinstance(task.extra_data, dict) else {}
    task.extra_data = {**base, **values}


def _resource_request_from_snapshot(
    *,
    tool_version: ToolVersion,
    resource_snapshot: dict[str, object],
) -> ResourceRequest:
    return resource_request_from_snapshot(tool_version.config, resource_snapshot)


def _enqueue_task_with_optional_priority(
    callback,
    *,
    enqueue_kwargs: dict[str, object],
    attempt_id: str,
):
    """兼容未升级的 enqueue_task 调用方，同时支持新的 priority 参数。"""
    kwargs = dict(enqueue_kwargs)
    try:
        parameters = inspect.signature(callback).parameters.values()
    except (TypeError, ValueError):
        parameters = ()

    accepts_priority = any(
        parameter.name == "priority"
        or parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters
    )
    if not accepts_priority:
        kwargs.pop("priority", None)
    return invoke_with_optional_attempt(
        callback,
        **kwargs,
        attempt_id=attempt_id,
    )


async def _resource_admission_metadata(
    *,
    tool_version: ToolVersion,
    resource_snapshot: dict[str, object],
    reservation_id: str | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
) -> dict[str, object] | None:
    """评估当前在线 Worker，但只记录结果，不阻断任务入队。"""
    if not settings.WORKER_CAPABILITY_ADMISSION_ENABLED:
        return None

    try:
        from app.cache import get_cache

        request = _resource_request_from_snapshot(
            tool_version=tool_version,
            resource_snapshot=resource_snapshot,
        )
        registry = WorkerCapabilityRegistry(
            cache=get_cache(),
            ttl_seconds=settings.WORKER_CAPABILITY_TTL_SECONDS,
        )
        if (
            settings.WORKER_CAPABILITY_RESERVATION_ENABLED
            and reservation_id
        ):
            decision = await registry.reserve_worker(
                request,
                reservation_id=reservation_id,
                ttl_seconds=settings.RESOURCE_DISPATCH_RESERVATION_TTL_SECONDS,
                user_id=user_id,
                project_id=project_id,
            )
        else:
            decision = await registry.select_available_worker(request)
        if decision.reason == "no_registered_workers":
            return {
                "status": "unknown",
                "worker_id": None,
                "reason": "no_registered_workers",
            }

        if decision.admitted:
            metadata: dict[str, object] = {
                "status": "admitted",
                "worker_id": decision.worker_id,
                "reason": None,
            }
            if settings.WORKER_CAPABILITY_ROUTING_ENABLED and decision.queue:
                metadata["queue"] = decision.queue
            if (
                settings.WORKER_CAPABILITY_RESERVATION_ENABLED
                and reservation_id
            ):
                metadata["resource_reservation"] = {
                    "worker_id": decision.worker_id,
                    "lease_id": reservation_id,
                    "ttl_seconds": settings.RESOURCE_DISPATCH_RESERVATION_TTL_SECONDS,
                    "status": "reserved",
                }
            return metadata

        return {
            "status": "rejected",
            "worker_id": None,
            "reason": decision.reason,
        }
    except Exception as exc:
        logger.warning(
            "Resource admission observation unavailable for task tool version %s: %s",
            tool_version.id,
            exc,
        )
        return {
            "status": "unknown",
            "worker_id": None,
            "reason": "admission_check_unavailable",
        }


async def dispatch_tool_task(
    *,
    db: AsyncSession,
    task: Task,
    tool_version: ToolVersion,
    user_role: str | None,
    direct_runner=default_direct_task_runner,
    resource_snapshot: dict[str, object] | None = None,
    failure_detail: str = "任务分发失败",
    countdown: int = 0,
) -> None:
    """Dispatch a persisted task and keep dispatch metadata in sync."""
    reservation_metadata: dict[str, object] | None = None
    try:
        attempt_id = new_execution_attempt_id()
        set_execution_attempt_id(task, attempt_id)

        # 任务进入调度链路即视为「排队中」：新建未调度为 PENDING，入队后为 QUEUED。
        # 已是 QUEUED（例如资源不足重排后重新入队）则不重复转换。
        current_status = (
            TaskStatus(task.status) if isinstance(task.status, str) else task.status
        )
        if current_status != TaskStatus.QUEUED and TaskStateMachine.can_transition(
            current_status, TaskStatus.QUEUED
        ):
            TaskStateMachine.enqueue(task)

        if use_direct_task_execution():
            task.celery_task_id = None
            _set_task_extra_data(task, dispatch={"mode": "direct", "queue": None})
            await db.commit()
            invoke_with_optional_attempt(
                direct_runner.schedule_task,
                task_id=str(task.id),
                tool_version_id=str(tool_version.id),
                attempt_id=attempt_id,
            )
            logger.info("Task %s scheduled in direct mode", task.id)
            return

        from app.tasks.queue_manager import TaskQueueManager

        snapshot = resource_snapshot if isinstance(resource_snapshot, dict) else {}
        if not snapshot and isinstance(task.extra_data, dict):
            task_snapshot = task.extra_data.get("resource_snapshot")
            if isinstance(task_snapshot, dict):
                snapshot = task_snapshot
        gpu_required = snapshot.get("gpu_required")
        queue = TaskQueueManager.determine_queue(
            tool_config=tool_version.config,
            user_role=user_role,
            priority=task.priority,
            gpu_required=gpu_required if isinstance(gpu_required, bool) else None,
        )

        dispatch_metadata: dict[str, object] = {
            "mode": "celery",
            "queue": queue,
        }
        admission_metadata = await _resource_admission_metadata(
            tool_version=tool_version,
            resource_snapshot=snapshot,
            reservation_id=f"{task.id}:{attempt_id}",
            user_id=str(getattr(task, "user_id", "") or "") or None,
            project_id=str(getattr(task, "project_id", "") or "") or None,
        )
        if isinstance(admission_metadata, dict):
            candidate = admission_metadata.pop("resource_reservation", None)
            if isinstance(candidate, dict):
                reservation_metadata = candidate
                dispatch_metadata["resource_reservation"] = candidate
        if (
            settings.WORKER_CAPABILITY_ROUTING_ENABLED
            and isinstance(admission_metadata, dict)
            and isinstance(admission_metadata.get("queue"), str)
            and admission_metadata["queue"].strip()
        ):
            queue = admission_metadata["queue"].strip()
            dispatch_metadata["queue"] = queue
        priority_details = TaskQueueManager.get_dispatch_priority_details(
            queue,
            task_priority=task.priority,
            created_at=getattr(task, "created_at", None),
        )
        dispatch_metadata["queue_priority"] = priority_details["priority"]
        if priority_details["priority_boost"] > 0:
            dispatch_metadata.update(
                {
                    "wait_seconds": priority_details["wait_seconds"],
                    "priority_boost": priority_details["priority_boost"],
                }
            )
        if admission_metadata is not None:
            dispatch_metadata["resource_admission"] = admission_metadata
        _set_task_extra_data(task, dispatch=dispatch_metadata)
        await db.commit()
        enqueue_kwargs = {
            "task_id": str(task.id),
            "tool_version_id": str(tool_version.id),
            "queue": queue,
            "priority": int(dispatch_metadata["queue_priority"]),
        }
        if countdown > 0:
            enqueue_kwargs["countdown"] = int(countdown)
        celery_task = _enqueue_task_with_optional_priority(
            TaskQueueManager.enqueue_task,
            enqueue_kwargs=enqueue_kwargs,
            attempt_id=attempt_id,
        )

        task.celery_task_id = celery_task.id
        await db.commit()
        logger.info("Task %s enqueued to %s", task.id, queue)
    except Exception as exc:
        logger.error("Failed to dispatch task %s: %s", task.id, exc)
        if reservation_metadata:
            try:
                from app.cache import get_cache

                await WorkerResourceLeaseManager(cache=get_cache()).release(
                    worker_id=str(reservation_metadata.get("worker_id") or ""),
                    lease_id=str(reservation_metadata.get("lease_id") or ""),
                )
            except Exception as release_exc:
                logger.warning(
                    "Failed to release dispatch reservation for task %s: %s",
                    task.id,
                    release_exc,
                )
        TaskStateMachine.complete(
            task,
            success=False,
            error_message=f"{failure_detail}: {str(exc)}",
        )
        await db.commit()
        raise HTTPException(status_code=500, detail=failure_detail) from exc


async def _load_tool_and_version(
    db: AsyncSession,
    task_data: TaskCreate,
    *,
    allow_inactive_candidate: bool = False,
) -> tuple[Tool, ToolVersion, str]:
    result = await db.execute(
        select(Tool)
        .options(
            selectinload(Tool.current_version),
            joinedload(Tool.statistics),
        )
        .where(Tool.id == task_data.tool_id)
    )
    tool = result.scalar_one_or_none()

    if not tool:
        raise NotFoundException("工具不存在")

    version_id = task_data.tool_version_id
    if not version_id:
        if not tool.current_version_id:
            raise ValidationException("工具没有可用版本")
        version_id = tool.current_version_id

    version_result = await db.execute(
        select(ToolVersion).where(ToolVersion.id == version_id)
    )
    tool_version = version_result.scalar_one_or_none()
    if not tool_version:
        raise ValidationException("工具版本不存在")
    if tool_version.tool_id != tool.id:
        raise ValidationException("工具版本不属于该工具")
    if tool_version.deprecated:
        raise ValidationException("工具版本已废弃，不可运行")
    if not tool_version.is_active and not allow_inactive_candidate:
        raise ValidationException("工具版本未激活，不可运行")

    return tool, tool_version, str(version_id)


async def _prepare_tool_task_run(
    *,
    db: AsyncSession,
    current_user: User,
    task_data: TaskCreate,
    extra_data: dict[str, object] | None = None,
    assign_default_project: bool,
    allow_inactive_candidate: bool = False,
) -> tuple[Tool, ToolVersion, str, PreparedRun, dict[str, object]]:
    tool, tool_version, version_id = await _load_tool_and_version(
        db,
        task_data,
        allow_inactive_candidate=allow_inactive_candidate,
    )

    task_extra_data = dict(extra_data or {})
    if tool_package_declares_mock(tool_version.config):
        task_extra_data["mock"] = True
    task_extra_data["resource_snapshot"] = build_task_resource_snapshot(
        tool_version.config,
        gpu_required=tool.gpu_required,
        gpu_memory_mb=tool.gpu_memory_mb,
        params=task_data.params,
    )
    project_id = task_data.project_id
    if project_id:
        await require_project_action(
            db,
            project_id=project_id,
            user=current_user,
            action="run",
        )
        task_extra_data = set_task_project_id(task_extra_data, project_id)
    elif assign_default_project and (
        str((tool_version.config or {}).get("type") or "") == "k8s_job"
        or tool_emits_standard_artifacts(tool, tool_version=tool_version)
        or standard_uploads_need_default_project(
            task_data.standard_input_uploads,
            tool_version.config,
        )
    ):
        project = await ensure_migration_project_for_owner(db, current_user)
        project_id = str(project.id)
        task_extra_data = set_task_project_id(task_extra_data, project_id)

    input_bindings = normalize_string_mapping(task_data.input_bindings)
    standard_input_uploads = normalize_string_mapping(task_data.standard_input_uploads)
    if (
        assign_default_project
        and project_id
        and standard_input_uploads
        and accepts_materialized_standard_uploads(tool_version.config)
    ):
        materialized_bindings = await materialize_standard_input_uploads(
            db,
            current_user=current_user,
            tool=tool,
            tool_version=tool_version,
            project_id=project_id,
            standard_input_uploads=standard_input_uploads,
        )
        input_bindings = {**input_bindings, **materialized_bindings}
        task_extra_data["standard_input_uploads"] = standard_input_uploads
        task_extra_data["materialized_standard_input_bindings"] = materialized_bindings
        standard_input_uploads = {}
    elif standard_input_uploads and accepts_materialized_standard_uploads(tool_version.config):
        await validate_standard_input_uploads(
            db,
            tool=tool,
            tool_version=tool_version,
            project_id=project_id,
            standard_input_uploads=standard_input_uploads,
        )

    prepared = await prepare_run(
        db,
        input=RunPreparationInput(
            tool=tool,
            tool_version=tool_version,
            context=RunContext(
                surface="tool_detail",
                user_id=str(current_user.id),
                project_id=project_id,
            ),
            params=dict(task_data.params or {}),
            file_ids=list(task_data.file_ids or []),
            input_bindings=input_bindings,
            standard_input_uploads=standard_input_uploads,
        ),
    )
    return tool, tool_version, version_id, prepared, task_extra_data


async def prepare_tool_task_preview(
    *,
    db: AsyncSession,
    current_user: User,
    task_data: TaskCreate,
) -> dict[str, object]:
    """Prepare task inputs and readiness decisions without creating a task."""
    tool, _tool_version, version_id, prepared, extra_data = await _prepare_tool_task_run(
        db=db,
        current_user=current_user,
        task_data=task_data,
        assign_default_project=False,
    )

    return {
        "ready": prepared.ready,
        "project_id": prepared.project_id,
        "tool_id": str(tool.id),
        "tool_version_id": version_id,
        "params": prepared.params,
        "file_ids": prepared.file_ids,
        "input_bindings": prepared.input_bindings,
        "requested_input_bindings": normalize_string_mapping(
            task_data.input_bindings,
        ),
        "standard_input_uploads": prepared.standard_input_uploads,
        "binding_decisions": prepared.binding_decisions,
        "blocked_reason": prepared.blocked_reason,
        "resource_snapshot": extra_data.get("resource_snapshot"),
    }


async def _enforce_project_quota(
    db: AsyncSession,
    *,
    prepared: PreparedRun,
    tool: Tool,
    extra_data: dict[str, object],
) -> None:
    """项目配额准入（docs/04 §5.3、docs/05 §9）。

    **为什么在这里而不在路由层**：``create_and_schedule_tool_task`` 是全平台唯一
    的建任务入口（HTTP ``POST /tasks``、k8s smoke、结构预测/准备/口袋预测、
    workflow 节点、direct recovery 都走它）。把准入挂在某个路由上时，其余入口
    完全不经过检查——一条 workflow 链路能无限刷算力。放在这里对所有入口一致生效。

    **为什么在 ``if not prepared.ready`` 之后**：``prepared`` 成型之前 ``project_id``
    还没定下来。更关键的是，``_prepare_tool_task_run`` 会把「没显式传项目」的
    k8s_job / 标准产物任务**自动挂到用户的迁移项目**（``ensure_migration_project_for_owner``
    + ``set_task_project_id``）。若拿 ``task_data.project_id`` 判定，这两类任务会以
    「没指定项目」为由被跳过，随后照样计入迁移项目的用量——配额形同虚设。
    所以判定口径必须是 ``prepared.project_id``（与真正写进 ``extra_data["project_id"]``
    的值同源）。

    **为什么在 ``TaskCommand.from_prepared_run`` 之前**：早于任何 ``db.add`` /
    ``flush``，被拦的提交不会留下 PENDING 空壳任务行。

    2026-10-27 变更（REJECTED 第 8 态）
    ----------------------------------
    上面「不留 PENDING 空壳」的口径仍然成立，但被拦的提交现在会留下一条
    **REJECTED** 终态行（见 ``create_and_schedule_tool_task`` 里的调用点）。
    原因是 docs/03 §3.4 的状态机里有 ``CREATED --> REJECTED``，而一个只在
    代码里抛异常、库里什么都看不到的「被拒」无法满足 M6 的「任务中心能看到
    这次提交被拒过」与配额纠纷时的可追溯性。本函数仍然只做判定、不写库。
    """
    if not settings.PROJECT_QUOTA_ENABLED:
        return
    project_id = (prepared.project_id or "").strip()
    if not project_id:
        # 仍存在无需项目上下文的分支：既没有显式 ``project_id``，工具也不是
        # k8s_job、不产出标准产物、不带需要默认项目的标准上传。这类任务不会写
        # ``extra_data["project_id"]``，因此不会被任何项目的用量统计捞到（
        # ``project_usage_*`` 按 ``Task.project_id_expression()`` 过滤）。
        # 对它们做配额校验只会拿一个空 project_id 去查库，没有意义。
        return
    await check_submission_allowed(
        db,
        project_id=project_id,
        requires_dcu=bool(tool.gpu_required),
        timeout_sec=_snapshot_timeout_sec(extra_data),
    )


async def _record_quota_rejection(
    db: AsyncSession,
    *,
    exc: QuotaExceededException,
    command: TaskCommand,
    tool: Tool,
) -> None:
    """把一次被配额拦下的提交落成 ``REJECTED`` 终态行（docs/03 §3.4）。

    为什么落库而不只是抛 429
    ------------------------
    HTTP 429 只是这一次请求的响应，刷新页面就没了。用户在任务中心看不到
    「我昨天下午提交过、被配额拒了」，运维在配额纠纷时也拿不出证据。
    ``REJECTED`` 是状态机里明确存在的一态，落库才让它可查、可统计。

    为什么写 ``TaskInput`` 但不做输入快照、不计工具用量
    ---------------------------------------------------
    用户需要能在详情页看到「我当时提交的是什么参数」——否则被拒记录除了
    「被拒了」三个字之外没有任何信息量。但被拒的提交没有真的使用输入，也不该
    算作工具被使用过，所以跳过 ``record_task_inputs`` / ``record_tool_usage``。

    为什么不核销算力
    ----------------
    该任务从未入队、从未执行，``TaskStateMachine`` 的 ``_SETTLED_STATUSES``
    刻意不含 ``REJECTED``（docs/03 §7.3「REJECTED 不核销」）。因此这里只需
    状态迁移，不需要任何成本回填。

    拒绝原因写进 ``extra_data["rejection"]``，与 ``check_submission_allowed``
    抛出的 ``detail`` 同构（``dimension``/``limit``/``active`` 等），前端
    任务详情页直接展示，不必再解析中文错误串。

    本函数吞掉自身异常：记录失败不应该把一次明确的 429 变成 500。
    """
    try:
        task = Task(
            user_id=command.user_id,
            project_id=(command.extra_data or {}).get("project_id"),
            tool_id=command.tool_id,
            tool_version_id=command.tool_version_id,
            status=TaskStatus.PENDING.value,
            priority=command.priority,
            progress=0.0,
            extra_data=dict(command.extra_data),
        )
        db.add(task)
        await db.flush()
        task.name = resolve_task_display_name(
            name=command.name,
            tool_name=tool.name,
            created_at=task.created_at,
            task_id=task.id,
        )
        task_input = command.task_input
        db.add(
            TaskInput(
                task_id=task.id,
                params=task_input["params"],
                file_ids=task_input["file_ids"],
            )
        )

        detail = dict(exc.detail) if isinstance(exc.detail, dict) else {}
        extra_data = dict(task.extra_data or {})
        extra_data["rejection"] = {**detail, "message": exc.message}
        task.extra_data = extra_data
        TaskStateMachine.reject(task, error_message=exc.message)

        await db.commit()
        await db.refresh(task)
        logger.info(
            "任务提交被配额拒绝，已记录 REJECTED 行: task_id=%s dimension=%s",
            task.id,
            detail.get("dimension"),
        )
    except Exception:  # noqa: BLE001 - 记录失败不能改变 429 的语义
        logger.exception("记录 REJECTED 任务失败（不影响 429 响应）")
        await db.rollback()


def _snapshot_timeout_sec(extra_data: dict[str, object]) -> float | None:
    """从本次提交的资源快照里取墙钟超时（秒），取不到返回 ``None``。

    ``None`` 与 ``0`` 语义不同：``0`` 表示「声明的超时为 0」，``None`` 表示
    「没有快照可看」。``check_submission_allowed`` 只在拿到数时才校验单任务时长。
    """
    snapshot = extra_data.get("resource_snapshot")
    if not isinstance(snapshot, dict):
        return None
    value = snapshot.get("timeout_sec")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _workflow_node_key(params: dict[str, object]) -> tuple[str | None, str | None, int | None]:
    """Extract the workflow idempotency key from a prepared task's params.

    ``workflow_run_id``/``workflow_node_id`` are written by the workflow
    schedulers into every node task's params. Non-workflow tasks leave them
    absent, so the returned key is all ``None`` and the DB unique index does
    not apply (NULLs are distinct in a unique index).
    """
    run_id = params.get("workflow_run_id")
    node_id = params.get("workflow_node_id")
    if not run_id or not node_id:
        return None, None, None
    raw_attempt = params.get("workflow_node_attempt", 1)
    try:
        attempt = int(raw_attempt)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        attempt = 1
    return str(run_id), str(node_id), attempt


async def create_and_schedule_tool_task(
    *,
    db: AsyncSession,
    current_user: User,
    task_data: TaskCreate,
    direct_runner=default_direct_task_runner,
    extra_data: dict[str, object] | None = None,
    allow_inactive_candidate: bool = False,
) -> Task:
    """Create a normal platform task and schedule it through the configured backend."""
    tool, tool_version, version_id, prepared, extra_data = await _prepare_tool_task_run(
        db=db,
        current_user=current_user,
        task_data=task_data,
        extra_data=extra_data,
        assign_default_project=True,
        allow_inactive_candidate=allow_inactive_candidate,
    )
    # docs/10 §8.3：trace_id 要能写进任务元数据，任务详情页才能直接跳追踪面板。
    # 本仓库的 Task 没有独立 ``env_json`` 列，等价物就是 ``extra_data``（JSON 列，
    # 已是 project_id / resource_snapshot 等的落点），所以键名保留 docs 里的
    # ``traceId`` 以便前端与文档同名字段对得上。
    # 非 HTTP 入口（direct recovery 回填、k8s smoke、workflow 节点）没有请求上下文，
    # ``get_trace_id()`` 为 None —— 此时**不写这个键**，避免详情页拿到一个
    # "有字段但永远为空" 的 traceId 而误以为可跳转。
    trace_id = get_trace_id()
    if trace_id:
        extra_data = {**extra_data, "traceId": trace_id}
    if not prepared.ready:
        raise ValidationException(
            "标准 Artifact 输入尚未满足工具要求",
            detail={"binding_decisions": prepared.binding_decisions},
        )
    command = TaskCommand.from_prepared_run(
        user_id=str(current_user.id),
        tool_id=str(task_data.tool_id),
        tool_version_id=version_id,
        name=task_data.name,
        priority=task_data.priority,
        prepared_run=prepared,
        requested_input_bindings=task_data.input_bindings,
        extra_data=extra_data,
    )
    try:
        await _enforce_project_quota(
            db,
            prepared=prepared,
            tool=tool,
            extra_data=extra_data,
        )
    except QuotaExceededException as exc:
        # 配额被拒 → 先落一条 REJECTED 终态行（docs/03 §3.4 ``CREATED --> REJECTED``），
        # 再把原异常抛出去保持 429 契约不变（docs/05 §9 的 42902 / 40303 口径）。
        await _record_quota_rejection(db, exc=exc, command=command, tool=tool)
        raise
    task_input = command.task_input
    workflow_run_id, workflow_node_id, workflow_node_attempt = _workflow_node_key(
        task_input["params"]
    )

    task = Task(
        user_id=command.user_id,
        project_id=(command.extra_data or {}).get("project_id"),
        tool_id=command.tool_id,
        tool_version_id=command.tool_version_id,
        status=TaskStatus.PENDING.value,
        priority=command.priority,
        progress=0.0,
        extra_data=command.extra_data,
        workflow_run_id=workflow_run_id,
        workflow_node_id=workflow_node_id,
        workflow_node_attempt=workflow_node_attempt,
    )

    try:
        db.add(task)
        await db.flush()
        task.name = resolve_task_display_name(
            name=command.name,
            tool_name=tool.name,
            created_at=task.created_at,
            task_id=task.id,
        )

        db.add(
            TaskInput(
                task_id=task.id,
                params=task_input["params"],
                file_ids=task_input["file_ids"],
            )
        )

        # 输入快照与任务同事务写入（docs/04 §9.2 只追加）：任务一旦存在，它的输入
        # 就已是历史事实，不允许事后从活表反推。
        await record_task_inputs(
            db,
            task=task,
            tool_version=tool_version,
            prepared=prepared,
            extra_data=command.extra_data,
        )

        await record_tool_usage(db, str(tool.id))

        await db.commit()
        await db.refresh(task)
    except IntegrityError:
        await db.rollback()
        if workflow_run_id is None or workflow_node_id is None:
            raise
        # 并发/重复调度同一工作流节点：唯一约束已拒绝第二条插入，回查先落库
        # 的那条并原样返回（幂等语义），不让它冒成 500。
        existing = await find_existing_workflow_node_task(
            db,
            run_id=workflow_run_id,
            node_id=workflow_node_id,
            attempt=workflow_node_attempt or 1,
        )
        if existing is None:
            raise
        logger.info(
            "工作流节点任务已存在，返回既有任务: run_id=%s node_id=%s task_id=%s",
            workflow_run_id,
            workflow_node_id,
            existing.id,
        )
        return existing

    # 提交审计（计划 §3.5 / docs/12 TC-NFR-04）：任务一旦 commit 即为历史事实，
    # 必须在派发前留痕，避免「任务已建但审计缺失」。
    get_audit_logger().log_task_operation(
        user_id=str(current_user.id),
        action=AuditAction.TASK_SUBMIT,
        task_id=str(task.id),
        tool_id=str(task.tool_id),
        project_id=task_project_id(task),
        tool_version_id=str(task.tool_version_id) if task.tool_version_id else None,
    )

    await dispatch_tool_task(
        db=db,
        task=task,
        tool_version=tool_version,
        user_role=current_user.role,
        direct_runner=direct_runner,
        resource_snapshot=command.extra_data.get("resource_snapshot"),
    )

    return task
