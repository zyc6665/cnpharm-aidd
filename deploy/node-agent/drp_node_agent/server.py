"""FastAPI 服务：平台主通道 A（:8780）。"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from .config import AgentSettings, load_nodes, load_settings
from .core import AgentCore
from .reporter import SlotReporter

logger = logging.getLogger(__name__)

settings: AgentSettings = load_settings()
nodes = load_nodes(settings)
core = AgentCore(settings, nodes)
reporter = SlotReporter(core, settings)

app = FastAPI(title="drp-node-agent", version="1.0.0")


class JobSubmit(BaseModel):
    taskId: str
    slotId: str
    image: str
    nodeId: Optional[str] = None
    env: Dict[str, str] = Field(default_factory=dict)
    dockerArgs: List[str] = Field(default_factory=list)
    modelEntry: List[str] = Field(default_factory=list)
    maxMinutes: Optional[int] = None
    heartbeatSeconds: int = 10


class CancelBody(BaseModel):
    reason: Optional[str] = None


def require_token(request: Request) -> None:
    expected = settings.api_token
    if not expected:
        return
    header = request.headers.get("Authorization", "")
    if header != "Bearer %s" % expected:
        raise HTTPException(status_code=401, detail="invalid agent token")


@app.on_event("startup")
async def _startup() -> None:
    logger.info("drp-node-agent started: node=%s slots=%s", core.node_id, len(core.slot_snapshot()))
    reporter.start()


@app.on_event("shutdown")
async def _shutdown() -> None:
    await reporter.stop()


@app.get("/healthz")
async def healthz() -> Dict[str, object]:
    return {
        "status": "ok",
        "nodeId": core.node_id,
        "slots": len(core.slot_snapshot()),
        "jobs": len(core._jobs),  # noqa: SLF001 - 只读观测
    }


@app.post("/api/v1/jobs", dependencies=[Depends(require_token)])
async def submit_job(payload: JobSubmit) -> Dict[str, str]:
    try:
        job = core.submit(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=409 if "忙" in str(exc) else 400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"jobId": job.job_id}


@app.post("/api/v1/jobs/{job_id}:cancel", dependencies=[Depends(require_token)])
async def cancel_job(job_id: str, body: Optional[CancelBody] = None) -> Dict[str, object]:
    try:
        job = core.cancel(job_id, body.reason if body else None)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return job.to_status()


@app.get("/api/v1/jobs/{job_id}", dependencies=[Depends(require_token)])
async def get_job(job_id: str) -> Dict[str, object]:
    try:
        job = core.status(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return job.to_status()


@app.get("/api/v1/slots", dependencies=[Depends(require_token)])
async def list_slots() -> List[Dict[str, object]]:
    return core.slot_snapshot()
