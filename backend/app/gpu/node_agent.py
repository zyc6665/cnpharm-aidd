"""drp-node-agent HTTP 客户端（平台侧主通道）。

依据 `docs/13` §4.1~§4.4：

* **主通道 A**：平台 Pod → Agent ``:8780``，负责「提交、取消、查状态」。
  唯一调用方应当是调度侧；页面与业务代码不得直连 Agent。
* **辅通道 C**：Agent → 平台网关，负责心跳、进度、事件上报。本模块只做服务端接收，
  出站方向见本文件的 :class:`NodeAgentClient`。
* Agent **不做调度决策**，只执行「在 A3 卡位启动 boltz2 任务 tsk_xxx」这一条指令；
  因此这里的方法都刻意做得极窄：一个方法对应一条指令。

离线约束：内网地址由 ``DRP_NODE_AGENT_BASE_URL`` 或 ``slots.yaml`` 的 ``agentEndpoint``
提供，代码里不出现任何公网域名（`docs/03` §10 约束 C-1）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Mapping

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

AGENT_SUBMIT_PATH = "/api/v1/jobs"
AGENT_CANCEL_PATH = "/api/v1/jobs/{job_id}:cancel"
AGENT_STATUS_PATH = "/api/v1/jobs/{job_id}"

AGENT_STATE_PENDING = "PENDING"
AGENT_STATE_RUNNING = "RUNNING"
AGENT_STATE_SUCCEEDED = "SUCCEEDED"
AGENT_STATE_FAILED = "FAILED"
AGENT_STATE_CANCELED = "CANCELED"
AGENT_STATE_TIMEOUT = "TIMEOUT"
AGENT_STATE_FAULT = "FAULT"

_TERMINAL_AGENT_STATES = frozenset(
    {
        AGENT_STATE_SUCCEEDED,
        AGENT_STATE_FAILED,
        AGENT_STATE_CANCELED,
        AGENT_STATE_TIMEOUT,
        AGENT_STATE_FAULT,
    }
)


class NodeAgentError(RuntimeError):
    """Agent 不可达或返回非预期结果。"""


@dataclass(frozen=True)
class AgentJobRequest:
    """一条「在某个卡位启动某镜像」的指令（`docs/13` §4.4 的纪律：Agent 只接受这个）。"""

    task_id: str
    slot_id: str
    image: str
    model_entry: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)
    docker_args: tuple[str, ...] = ()
    max_minutes: int | None = None
    heartbeat_seconds: int = 10

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "taskId": self.task_id,
            "slotId": self.slot_id,
            "image": self.image,
            "env": dict(self.env),
            "dockerArgs": list(self.docker_args),
            "heartbeatSeconds": self.heartbeat_seconds,
        }
        if self.model_entry:
            payload["modelEntry"] = list(self.model_entry)
        if self.max_minutes is not None:
            payload["maxMinutes"] = self.max_minutes
        return payload


@dataclass(frozen=True)
class AgentJobStatus:
    """Agent 回报的任务状态。"""

    job_id: str
    state: str
    slot_id: str | None = None
    progress: float | None = None
    message: str | None = None
    exit_code: int | None = None
    device_count: int | None = None

    @property
    def terminal(self) -> bool:
        return self.state in _TERMINAL_AGENT_STATES


def _agent_token() -> str | None:
    token = getattr(settings, "DRP_NODE_AGENT_TOKEN", None)
    return str(token).strip() or None if token else None


def _agent_timeout() -> float:
    return float(getattr(settings, "DRP_NODE_AGENT_TIMEOUT_SECONDS", 5.0) or 5.0)


def _normalize_endpoint(endpoint: str | None) -> str | None:
    value = (endpoint or "").strip()
    if not value:
        fallback = getattr(settings, "DRP_NODE_AGENT_BASE_URL", None)
        value = str(fallback).strip() if fallback else ""
    return value.rstrip("/") or None


class NodeAgentClient:
    """与单台节点的 Agent 通信。

    ``endpoint`` 缺省时回退到 ``settings.DRP_NODE_AGENT_BASE_URL``；
    两者都没有时调用会抛 :class:`NodeAgentError`，由上层决定是排队等还是失败。
    """

    def __init__(
        self,
        endpoint: str | None = None,
        *,
        token: str | None = None,
        timeout: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.endpoint = _normalize_endpoint(endpoint)
        self._token = token if token is not None else _agent_token()
        self._timeout = timeout if timeout is not None else _agent_timeout()
        self._transport = transport

    @property
    def configured(self) -> bool:
        return bool(self.endpoint)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _url(self, path: str) -> str:
        if not self.endpoint:
            raise NodeAgentError(
                "未配置 drp-node-agent 地址（DRP_NODE_AGENT_BASE_URL 或 slots.yaml 的 agentEndpoint）"
            )
        return f"{self.endpoint}{path}"

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = self._url(path)
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = await client.request(method, url, headers=self._headers(), **kwargs)
        except httpx.HTTPError as exc:
            raise NodeAgentError(f"调用 drp-node-agent 失败: {url}: {exc}") from exc

        if response.status_code >= 400:
            raise NodeAgentError(
                f"drp-node-agent 返回 {response.status_code}: {response.text[:200]}"
            )
        if not response.content:
            return {}
        try:
            payload = response.json()
        except ValueError as exc:
            raise NodeAgentError(f"drp-node-agent 响应不是 JSON: {response.text[:200]}") from exc
        return payload if isinstance(payload, dict) else {"data": payload}

    async def submit(self, request: AgentJobRequest) -> str:
        """提交一条卡位作业，返回 Agent 侧 job_id。"""
        payload = await self._request("POST", AGENT_SUBMIT_PATH, json=request.to_payload())
        job_id = str(payload.get("jobId") or payload.get("id") or "").strip()
        if not job_id:
            raise NodeAgentError("drp-node-agent 未返回 jobId")
        logger.info(
            "Agent job submitted: task=%s slot=%s job=%s",
            request.task_id,
            request.slot_id,
            job_id,
        )
        return job_id

    async def cancel(self, job_id: str, *, reason: str | None = None) -> None:
        body = {"reason": reason} if reason else None
        await self._request("POST", AGENT_CANCEL_PATH.format(job_id=job_id), json=body)

    async def status(self, job_id: str) -> AgentJobStatus:
        payload = await self._request("GET", AGENT_STATUS_PATH.format(job_id=job_id))
        state = str(payload.get("state") or payload.get("status") or "").strip().upper()
        if not state:
            raise NodeAgentError("drp-node-agent 未返回任务状态")
        return AgentJobStatus(
            job_id=str(payload.get("jobId") or job_id),
            state=state,
            slot_id=(str(payload.get("slotId")).strip() or None) if payload.get("slotId") else None,
            progress=_optional_float(payload.get("progress")),
            message=(str(payload.get("message")).strip() or None) if payload.get("message") else None,
            exit_code=_optional_int(payload.get("exitCode")),
            device_count=_optional_int(payload.get("deviceCount")),
        )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_agent_client(agent_endpoint: str | None = None) -> NodeAgentClient:
    """按卡位声明的 ``agentEndpoint`` 构造客户端。"""
    return NodeAgentClient(agent_endpoint)


__all__ = [
    "AGENT_STATE_CANCELED",
    "AGENT_STATE_FAULT",
    "AGENT_STATE_FAILED",
    "AGENT_STATE_PENDING",
    "AGENT_STATE_RUNNING",
    "AGENT_STATE_SUCCEEDED",
    "AGENT_STATE_TIMEOUT",
    "AgentJobRequest",
    "AgentJobStatus",
    "NodeAgentClient",
    "NodeAgentError",
    "build_agent_client",
]
