"""Managed Kubernetes Job task executor.

This executor owns task-facing request construction and lifecycle polling. The
provider-specific implementation is injected through ``ExecutionService`` so
the worker does not import or construct a Kubernetes SDK client.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.database.session import get_async_session
from app.execution.records import (
    task_execution_record_id,
    update_task_execution_record_external_id,
)
from app.execution.contracts import ExecutionRequest, ExecutionState
from app.execution.service import ExecutionService
from app.tasks.attempts import get_execution_attempt_id
from app.tasks.executors.base import BaseExecutor
from app.tasks.executors.errors import TaskExecutionError


class KubernetesJobExecutor(BaseExecutor):
    """Submit one task as a managed Kubernetes Job and collect its outputs."""

    def __init__(self, *args, execution_service: ExecutionService | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.execution_service = execution_service

    def _build_request(self) -> ExecutionRequest:
        extra_data = self.task.extra_data if isinstance(self.task.extra_data, dict) else {}
        project_id = str(extra_data.get("project_id") or getattr(self.task, "project_id", "") or "")
        if not project_id:
            raise TaskExecutionError("k8s_job 任务缺少 project_id")

        task_inputs = getattr(self.task, "inputs", None)
        parameters = task_inputs.params if task_inputs is not None else {}
        if not isinstance(parameters, dict):
            parameters = {}
        config = self.config
        attempt_id = get_execution_attempt_id(self.task) or "current"
        return ExecutionRequest(
            idempotency_key=f"task:{self.task.id}:attempt:{attempt_id}",
            project_id=project_id,
            requested_by=str(getattr(self.task, "user_id", "") or "system"),
            tool_package_version_id=str(
                config.get("tool_package_version_id") or self.tool_version.id
            ),
            variant=str(config.get("variant") or "default"),
            executor_type="k8s_job",
            parameters=parameters,
            resources=dict(extra_data.get("resource_snapshot") or {}),
            runtime={
                **(dict(config.get("runtime")) if isinstance(config.get("runtime"), dict) else {}),
                **({"image": config["image"]} if config.get("image") else {}),
            },
            task_id=str(self.task.id),
            attempt_id=attempt_id,
            tool_version_id=str(self.tool_version.id),
        )

    async def execute(self) -> dict[str, Any]:
        if self.execution_service is None:
            raise TaskExecutionError("k8s_job Executor Gateway 未配置 Kubernetes adapter")

        request = self._build_request()
        handle = await self.execution_service.submit(request)
        execution_id = handle.execution_id
        extra_data = dict(self.task.extra_data or {})
        extra_data["external_id"] = execution_id
        self.task.extra_data = extra_data
        await self._persist_external_id(execution_id)
        state = handle.state
        timeout = max(1, int(self.config.get("timeout_sec", 3600)))
        poll_interval = max(0.0, float(self.config.get("poll_interval_sec", 5)))
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        while state in {ExecutionState.QUEUED, ExecutionState.RUNNING}:
            if loop.time() >= deadline:
                await self.execution_service.cancel("k8s_job", execution_id)
                raise TaskExecutionError("Kubernetes Job execution timeout")
            state = await self.execution_service.reconcile("k8s_job", execution_id)
            if state in {ExecutionState.QUEUED, ExecutionState.RUNNING} and poll_interval:
                await asyncio.sleep(poll_interval)

        if state == ExecutionState.CANCELLED:
            raise TaskExecutionError("Kubernetes Job was cancelled")
        if state == ExecutionState.FAILED:
            raise TaskExecutionError("Kubernetes Job reported failure")
        if state != ExecutionState.SUCCEEDED:
            raise TaskExecutionError(f"Kubernetes Job returned unexpected state: {state}")

        artifacts = await self.execution_service.collect_artifacts("k8s_job", execution_id)
        output_file_ids = [artifact.file_id for artifact in artifacts if artifact.file_id]
        return {
            "success": True,
            "result": {
                "execution_id": execution_id,
                "state": state.value,
                "artifacts": [artifact.model_dump(exclude_none=True) for artifact in artifacts],
            },
            "output_file_ids": output_file_ids,
            "stdout": "",
            "stderr": "",
        }

    async def _persist_external_id(self, external_id: str) -> None:
        """Persist the provider handle before the first reconcile call."""
        if not task_execution_record_id(self.task):
            return
        try:
            async for session in get_async_session():
                try:
                    await update_task_execution_record_external_id(
                        session,
                        task=self.task,
                        external_id=external_id,
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise
                break
        except Exception as exc:
            try:
                await self.execution_service.cancel("k8s_job", external_id)
            except Exception as cancel_exc:
                exc = RuntimeError(f"{exc}; orphan Job cancel failed: {cancel_exc}")
            raise TaskExecutionError(
                "无法保存 Kubernetes Job 外部句柄",
                details={"error": str(exc)},
            ) from exc
