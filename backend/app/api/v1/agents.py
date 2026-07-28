"""Agent API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.aidd.service import (
    cancel_agent_run,
    cascade_delete_agent_run,
    create_agent_run,
    delete_agent_run,
    get_agent_run,
    list_agent_runs,
    reconcile_waiting_agent_steps,
)
from app.auth.dependencies import get_current_user
from app.common.responses import paginated_response, success_response
from app.database.session import get_db
from app.models.agent import AgentRun, AgentRunStep
from app.models.users import User
from app.schemas.agent import AIDDRunCreate


router = APIRouter()


def _serialize_step(step: AgentRunStep) -> dict[str, Any]:
    return {
        "id": step.id,
        "step_key": step.step_key,
        "tool_slug": step.tool_slug,
        "tool_id": step.tool_id,
        "task_id": step.task_id,
        "status": step.status,
        "sort_order": step.sort_order,
        "depends_on_step_ids": step.depends_on_step_ids or [],
        "semantic_inputs": step.semantic_inputs or {},
        "semantic_outputs": step.semantic_outputs or {},
        "params": step.params or {},
        "input_file_ids": step.input_file_ids or [],
        "output_file_ids": step.output_file_ids or [],
        "error_message": step.error_message,
        "started_at": step.started_at,
        "finished_at": step.finished_at,
        "created_at": step.created_at,
        "updated_at": step.updated_at,
    }


def _serialize_run(run: AgentRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "message": run.message,
        "intent": run.intent,
        "status": run.status,
        "input_type": run.input_type,
        "input_file_id": run.input_file_id,
        "input_files": (run.plan or {}).get("input_files") or {},
        "requested_outputs": run.requested_outputs or [],
        "plan": run.plan or {},
        "summary": run.summary,
        "error_message": run.error_message,
        "finished_at": run.finished_at,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "steps": [_serialize_step(step) for step in sorted(run.steps, key=lambda item: item.sort_order)],
    }


@router.post("/aidd/runs", response_model=dict)
async def create_aidd_agent_run(
    run_data: AIDDRunCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await create_agent_run(db, current_user=current_user, run_data=run_data)
    return success_response(data=_serialize_run(run), message="智能体运行创建成功")


@router.get("/aidd/runs", response_model=dict)
async def list_aidd_agent_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    runs = await list_agent_runs(db, current_user=current_user)
    total = len(runs)
    start = (page - 1) * page_size
    return paginated_response(
        items=[_serialize_run(run) for run in runs[start : start + page_size]],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/aidd/runs/{run_id}", response_model=dict)
async def get_aidd_agent_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await get_agent_run(db, current_user=current_user, run_id=run_id)
    return success_response(data=_serialize_run(run))


@router.post("/aidd/runs/{run_id}/cancel", response_model=dict)
async def cancel_aidd_agent_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await cancel_agent_run(db, current_user=current_user, run_id=run_id)
    return success_response(data=_serialize_run(run), message="智能体运行已取消")


@router.delete("/aidd/runs/{run_id}", response_model=dict)
async def delete_aidd_agent_run(
    run_id: str,
    cascade: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if cascade:
        result = await cascade_delete_agent_run(db, current_user=current_user, run_id=run_id)
        return success_response(data=result, message="智能体历史会话、任务和产物已删除")

    result = await delete_agent_run(db, current_user=current_user, run_id=run_id)
    return success_response(data=result, message="智能体历史会话已删除")


@router.post("/aidd/runs/{run_id}/sync", response_model=dict)
async def sync_aidd_agent_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_agent_run(db, current_user=current_user, run_id=run_id)
    await reconcile_waiting_agent_steps(db, run_id=run_id)
    run = await get_agent_run(db, current_user=current_user, run_id=run_id)
    return success_response(data=_serialize_run(run), message="智能体运行已同步")
