"""Legacy Agent API shutdown routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_user


router = APIRouter(dependencies=[Depends(get_current_user)])

LEGACY_AGENT_REPLACEMENT = "/api/v1/projects/{project_id}/conversations"
LEGACY_AGENT_GONE_DETAIL = {
    "message": "旧 AIDD API 已下线，请使用项目会话 Agent Run 接口",
    "replacement": LEGACY_AGENT_REPLACEMENT,
}


def _raise_legacy_aidd_api_gone() -> None:
    raise HTTPException(status_code=410, detail=LEGACY_AGENT_GONE_DETAIL)


@router.post("/aidd/workflow-drafts", response_model=dict, deprecated=True)
async def create_aidd_workflow_draft():
    _raise_legacy_aidd_api_gone()


@router.api_route("/aidd/runs", methods=["GET", "POST"], response_model=dict, deprecated=True)
async def aidd_agent_runs():
    _raise_legacy_aidd_api_gone()


@router.api_route(
    "/aidd/runs/{run_id}",
    methods=["GET", "DELETE"],
    response_model=dict,
    deprecated=True,
)
async def aidd_agent_run(run_id: str):
    _raise_legacy_aidd_api_gone()


@router.post("/aidd/runs/{run_id}/cancel", response_model=dict, deprecated=True)
async def cancel_aidd_agent_run(run_id: str):
    _raise_legacy_aidd_api_gone()


@router.post("/aidd/runs/{run_id}/sync", response_model=dict, deprecated=True)
async def sync_aidd_agent_run(run_id: str):
    _raise_legacy_aidd_api_gone()
