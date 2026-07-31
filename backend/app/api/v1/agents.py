"""Agent API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.aidd.service import (
    cancel_agent_run,
    cascade_delete_agent_run,
    create_agent_run,
    create_workflow_draft,
    delete_agent_run,
    get_agent_run,
    list_agent_runs,
    reconcile_waiting_agent_steps,
)
from app.auth.dependencies import get_current_user
from app.common.responses import paginated_response, success_response
from app.database.session import get_db
from app.feature_flags import require_feature_flag
from app.models.agent import AgentRun, AgentRunStep
from app.models.users import User
from app.schemas.agent import AIDDRunCreate


router = APIRouter(
    dependencies=[Depends(require_feature_flag("LEGACY_AIDD_API_ENABLED"))]
)

LEGACY_AGENT_REPLACEMENT = "/api/v1/projects/{project_id}/conversations"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value:
        return [value]
    return []


def _safe_sort_order(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _with_deprecation(response: dict[str, Any]) -> dict[str, Any]:
    return {
        **response,
        "meta": {
            "deprecated": True,
            "replacement": LEGACY_AGENT_REPLACEMENT,
        },
    }


def _legacy_success_response(
    *,
    data: Any = None,
    message: str = "success",
) -> dict[str, Any]:
    return _with_deprecation(success_response(data=data, message=message))


def _serialize_step(step: AgentRunStep) -> dict[str, Any]:
    return {
        "id": step.id,
        "step_key": step.step_key,
        "tool_slug": step.tool_slug,
        "tool_id": step.tool_id,
        "task_id": step.task_id,
        "status": step.status,
        "sort_order": step.sort_order,
        "depends_on_step_ids": _as_list(step.depends_on_step_ids),
        "semantic_inputs": _as_dict(step.semantic_inputs),
        "semantic_outputs": _as_dict(step.semantic_outputs),
        "params": _as_dict(step.params),
        "input_file_ids": _as_list(step.input_file_ids),
        "output_file_ids": _as_list(step.output_file_ids),
        "error_message": step.error_message,
        "started_at": step.started_at,
        "finished_at": step.finished_at,
        "created_at": step.created_at,
        "updated_at": step.updated_at,
    }


def _serialize_run(run: AgentRun) -> dict[str, Any]:
    plan = _as_dict(run.plan)
    steps = list(run.steps or [])
    return {
        "id": run.id,
        "message": run.message,
        "intent": run.intent,
        "status": run.status,
        "input_type": run.input_type,
        "input_file_id": run.input_file_id,
        "input_files": _as_dict(plan.get("input_files")),
        "requested_outputs": _as_list(run.requested_outputs),
        "plan": plan,
        "summary": run.summary,
        "error_message": run.error_message,
        "finished_at": run.finished_at,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "steps": [
            _serialize_step(step)
            for step in sorted(steps, key=lambda item: _safe_sort_order(item.sort_order))
        ],
    }


@router.post("/aidd/runs", response_model=dict, deprecated=True)
async def create_aidd_agent_run(
    run_data: AIDDRunCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await create_agent_run(db, current_user=current_user, run_data=run_data)
    return _legacy_success_response(
        data=_serialize_run(run), message="智能体运行创建成功"
    )


@router.post("/aidd/workflow-drafts", response_model=dict, deprecated=True)
async def create_aidd_workflow_draft(
    run_data: AIDDRunCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    draft = await create_workflow_draft(
        db, current_user=current_user, run_data=run_data
    )
    return _legacy_success_response(
        data=draft.model_dump(), message="工作流草稿生成成功"
    )


@router.get("/aidd/runs", response_model=dict, deprecated=True)
async def list_aidd_agent_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    runs = await list_agent_runs(db, current_user=current_user)
    total = len(runs)
    start = (page - 1) * page_size
    return _with_deprecation(
        paginated_response(
            items=[_serialize_run(run) for run in runs[start : start + page_size]],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/aidd/runs/{run_id}", response_model=dict, deprecated=True)
async def get_aidd_agent_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await get_agent_run(db, current_user=current_user, run_id=run_id)
    return _legacy_success_response(data=_serialize_run(run))


@router.post("/aidd/runs/{run_id}/cancel", response_model=dict, deprecated=True)
async def cancel_aidd_agent_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await cancel_agent_run(db, current_user=current_user, run_id=run_id)
    return _legacy_success_response(
        data=_serialize_run(run), message="智能体运行已取消"
    )


@router.delete("/aidd/runs/{run_id}", response_model=dict, deprecated=True)
async def delete_aidd_agent_run(
    run_id: str,
    cascade: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if cascade:
        result = await cascade_delete_agent_run(
            db, current_user=current_user, run_id=run_id
        )
        return _legacy_success_response(
            data=result, message="智能体历史会话、任务和产物已删除"
        )

    result = await delete_agent_run(db, current_user=current_user, run_id=run_id)
    return _legacy_success_response(data=result, message="智能体历史会话已删除")


@router.post("/aidd/runs/{run_id}/sync", response_model=dict, deprecated=True)
async def sync_aidd_agent_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_agent_run(db, current_user=current_user, run_id=run_id)
    await reconcile_waiting_agent_steps(db, run_id=run_id)
    run = await get_agent_run(db, current_user=current_user, run_id=run_id)
    return _legacy_success_response(
        data=_serialize_run(run), message="智能体运行已同步"
    )
