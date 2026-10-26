"""Managed Kubernetes Job task executor.

This executor owns task-facing request construction and lifecycle polling. The
provider-specific implementation is injected through ``ExecutionService`` so
the worker does not import or construct a Kubernetes SDK client.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import PurePosixPath
from pathlib import Path
from typing import Any

from app.database.session import get_async_session
from app.config import settings
from app.execution.records import (
    task_execution_record_id,
    update_task_execution_record_external_id,
)
from app.execution.contracts import ExecutionRequest, ExecutionState
from app.execution.service import ExecutionService
from app.services.execution_artifacts import materialize_execution_artifacts
from app.services.kubernetes_input_staging import stage_kubernetes_inputs
from app.tasks.attempts import get_execution_attempt_id
from app.tasks.executors.base import BaseExecutor
from app.tasks.executors.errors import TaskExecutionError, TaskTimeoutError


class KubernetesJobExecutor(BaseExecutor):
    """Submit one task as a managed Kubernetes Job and collect its outputs."""

    def __init__(self, *args, execution_service: ExecutionService | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.execution_service = execution_service

    async def _build_request(self) -> ExecutionRequest:
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
        inputs = await self._stage_inputs(attempt_id)
        runtime = dict(config.get("runtime") or {})
        runtime["args"] = runtime.get("args") or _platform_entrypoint_args(
            task_id=str(self.task.id),
            variant=str(config.get("variant") or "default"),
            resources=dict(extra_data.get("resource_snapshot") or {}),
            runtime=runtime,
        )
        runtime_env = runtime.get("env")
        if runtime_env is None:
            runtime_env = {}
        if not isinstance(runtime_env, dict):
            raise TaskExecutionError("k8s_job runtime.env must be an object")
        if "SCIMINER_REQUEST_JSON" in runtime_env:
            raise TaskExecutionError("k8s_job runtime.env cannot override SCIMINER_REQUEST_JSON")
        runtime["env"] = {
            **runtime_env,
            "SCIMINER_REQUEST_JSON": json.dumps(
                await self._build_request_payload(inputs, parameters),
                ensure_ascii=True,
                separators=(",", ":"),
            ),
        }
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
            inputs=inputs,
            resources=dict(extra_data.get("resource_snapshot") or {}),
            runtime={**runtime, **({"image": config["image"]} if config.get("image") else {})},
            task_id=str(self.task.id),
            attempt_id=attempt_id,
            tool_version_id=str(self.tool_version.id),
        )

    async def _build_request_payload(
        self,
        inputs: list,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        task_id = str(self.task.id)
        tool_slug = await self._tool_slug()
        grouped_inputs: dict[str, dict[str, Any]] = {}
        for item in inputs:
            if not item.role or not item.artifact_type:
                raise TaskExecutionError(
                    "Kubernetes inputs require a materialized standard ArtifactVersion"
                )
            filename = PurePosixPath(item.uri).name
            if not filename:
                raise TaskExecutionError("Kubernetes input object key has no filename")
            staged_path = f"input/{item.name}/{filename}"
            artifact = grouped_inputs.get(item.name)
            if artifact is None:
                artifact = {
                    "artifact_version_id": item.artifact_version_id,
                    "type": item.artifact_type,
                    "files": {},
                    "metadata": dict(item.metadata or {}),
                }
                grouped_inputs[item.name] = artifact
            elif (
                artifact["artifact_version_id"] != item.artifact_version_id
                or artifact["type"] != item.artifact_type
            ):
                raise TaskExecutionError(
                    f"Kubernetes input slot has conflicting ArtifactVersions: {item.name}"
                )
            file_ref = {
                "path": staged_path,
                "sha256": item.sha256,
            }
            if item.content_type:
                file_ref["content_type"] = item.content_type
            artifact["files"][item.role] = file_ref

        resources = dict(getattr(self.task, "extra_data", {}).get("resource_snapshot") or {})
        gpu_count = int(resources.get("gpu_count") or 0)
        return {
            "request_version": "aidd.sciminer/request.v1",
            "task": {
                "id": task_id,
                "tool_slug": tool_slug,
                "tool_version": str(self.tool_version.version),
            },
            "inputs": grouped_inputs,
            "parameters": parameters,
            "execution": {
                "variant": str(self.config.get("variant") or "default"),
                "accelerator": "nvidia_cuda" if gpu_count else "cpu",
            },
        }

    async def _tool_slug(self) -> str:
        configured_slug = self.config.get("tool_slug")
        if configured_slug:
            return str(configured_slug)
        loaded_tool = getattr(self.task, "__dict__", {}).get("tool")
        loaded_slug = getattr(loaded_tool, "slug", None)
        if loaded_slug:
            return str(loaded_slug)
        if self.db_session is not None and getattr(self.task, "tool_id", None):
            from sqlalchemy import select

            from app.models.tools import Tool

            result = await self.db_session.execute(
                select(Tool.slug).where(Tool.id == str(self.task.tool_id))
            )
            slug = result.scalar_one_or_none()
            if slug:
                return str(slug)
        return str(getattr(self.task, "tool_id", "unknown-tool"))

    async def _stage_inputs(self, attempt_id: str):
        task_inputs = getattr(self.task, "inputs", None)
        file_ids = list(getattr(task_inputs, "file_ids", None) or [])
        extra_data = self.task.extra_data if isinstance(self.task.extra_data, dict) else {}
        has_bound_inputs = any(
            isinstance(extra_data.get(key), dict) and extra_data[key]
            for key in (
                "input_bindings",
                "standard_input_uploads",
                "materialized_standard_input_bindings",
            )
        )
        if not file_ids and not has_bound_inputs:
            return []
        if self.db_session is None:
            raise TaskExecutionError(
                "k8s_job 输入 staging requires the worker database session"
            )
        from app.storage.factory import get_storage_backend

        try:
            storage = get_storage_backend(settings.STORAGE_BACKEND)
            return await stage_kubernetes_inputs(
                self.db_session,
                task=self.task,
                attempt_id=attempt_id,
                storage=storage,
                prefix=getattr(
                    settings,
                    "K8S_ADAPTER_OBJECT_STORAGE_INPUT_PREFIX",
                    "inputs",
                ),
            )
        except Exception as exc:
            if isinstance(exc, TaskExecutionError):
                raise
            raise TaskExecutionError(f"Kubernetes input staging failed: {exc}") from exc

    async def execute(self) -> dict[str, Any]:
        if self.execution_service is None:
            raise TaskExecutionError("k8s_job Executor Gateway 未配置 Kubernetes adapter")

        request = await self._build_request()
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
                raise TaskTimeoutError(
                    f"Kubernetes Job execution timeout after {timeout}s",
                    timeout_sec=timeout,
                )
            state = await self.execution_service.reconcile("k8s_job", execution_id)
            if state in {ExecutionState.QUEUED, ExecutionState.RUNNING} and poll_interval:
                await asyncio.sleep(poll_interval)

        if state == ExecutionState.CANCELLED:
            raise TaskExecutionError("Kubernetes Job was cancelled")
        if state == ExecutionState.FAILED:
            raise TaskExecutionError("Kubernetes Job reported failure")
        if state != ExecutionState.SUCCEEDED:
            raise TaskExecutionError(f"Kubernetes Job returned unexpected state: {state}")

        collection = await self.execution_service.collect_result("k8s_job", execution_id)
        artifacts = list(collection.artifacts)
        if collection.source_root is not None:
            if self.db_session is None:
                raise TaskExecutionError(
                    "Kubernetes artifact collection requires the worker database session"
                )
            source_root = Path(collection.source_root)
            try:
                artifacts = await materialize_execution_artifacts(
                    self.db_session,
                    task=self.task,
                    artifacts=artifacts,
                    source_root=source_root,
                )
            finally:
                shutil.rmtree(source_root.parent, ignore_errors=True)
        output_file_ids = [artifact.file_id for artifact in artifacts if artifact.file_id]
        result_payload = collection.result_payload
        if result_payload is None:
            result_payload = {
                "execution_id": execution_id,
                "state": state.value,
                "artifacts": [artifact.model_dump(exclude_none=True) for artifact in artifacts],
            }
        return {
            "success": True,
            "result": result_payload,
            "execution_id": execution_id,
            "state": state.value,
            "artifacts": [artifact.model_dump(exclude_none=True) for artifact in artifacts],
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


def _platform_entrypoint_args(
    *,
    task_id: str,
    variant: str,
    resources: dict[str, Any],
    runtime: dict[str, Any],
) -> list[str]:
    gpu_count = int(resources.get("gpu_count") or 0)
    device = str(runtime.get("device") or ("cuda" if gpu_count or "cuda" in variant else "auto"))
    return [
        "--task-id",
        task_id,
        "--input-dir",
        "/workspace/input",
        "--output-dir",
        "/workspace/output",
        "--params-json",
        "/workspace/input/request.json",
        "--work-dir",
        "/workspace/work",
        "--device",
        device,
    ]
