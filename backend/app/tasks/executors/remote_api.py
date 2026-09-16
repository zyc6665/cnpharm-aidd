"""远程 API 工具执行器。"""

import hashlib
import logging
import os
import shutil
import uuid
import asyncio
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database.session import get_async_session
from app.models.artifacts import ArtifactVersion, ArtifactVersionFile
from app.files.storage_path import get_file_path
from app.models.files import File as FileModel, FileSourceType
from app.remote_tools.files import (
    remote_file_download_url,
    remote_file_payload,
)
from app.remote_tools.inputs import (
    RemoteToolInputError,
    remote_artifact_input_declarations,
    remote_artifact_input_payload,
    remote_example_input_refs,
    standard_input_bindings,
    validate_remote_artifact_input,
)
from app.remote_tools.invocation import (
    build_remote_tool_invoke_payload,
    remote_tool_parameters,
)
from app.remote_tools.legacy_api import (
    build_legacy_remote_api_request_data,
    flatten_legacy_remote_api_params,
)
from app.remote_tools.results import (
    RemoteToolResultError,
    iter_remote_result_artifacts,
    remote_result_filename,
    remote_status_state,
    verify_remote_result_file_checksum,
)
from app.remote_tools.urls import (
    RemoteToolUrlError,
    remote_endpoint_url,
    remote_result_url,
)
from app.tasks.executors.base import BaseExecutor
from app.tasks.executors.errors import TaskExecutionError

logger = logging.getLogger(__name__)


class RemoteAPIExecutor(BaseExecutor):
    """远程 API 执行器。"""

    async def execute(self) -> dict[str, Any]:
        if self.config.get("mode") == "remote_tool_v1":
            return await self._execute_remote_tool_v1()

        endpoint = self.config.get("endpoint")
        if not endpoint:
            raise TaskExecutionError("Missing endpoint in tool config")

        method = self.config.get("method", "POST").upper()
        headers = self.config.get("headers", {})
        timeout = self.config.get("timeout_sec", 600)
        request_data = await self._prepare_request_data()

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                logger.info("Executing remote API: %s %s", method, endpoint)
                if method == "POST":
                    response = await client.post(endpoint, json=request_data, headers=headers)
                elif method == "GET":
                    response = await client.get(
                        endpoint,
                        params=flatten_legacy_remote_api_params(request_data),
                        headers=headers,
                    )
                else:
                    raise TaskExecutionError(f"Unsupported HTTP method: {method}")

                response.raise_for_status()
                result = response.json()
                if "output_files" in result:
                    result["output_file_ids"] = await self._process_output_files(result["output_files"])
                return {"success": True, "result": result, "execution_time": timeout}
            except httpx.HTTPStatusError as exc:
                raise TaskExecutionError(
                    f"API returned error: {exc.response.status_code}",
                    details={"response_text": exc.response.text[:500]},
                ) from exc
            except httpx.TimeoutException as exc:
                raise TaskExecutionError("API request timeout") from exc
            except httpx.ConnectError as exc:
                raise TaskExecutionError(f"Failed to connect to API: {exc}") from exc
            except TaskExecutionError:
                raise
            except Exception as exc:
                raise TaskExecutionError(f"API request failed: {exc}") from exc

    async def _execute_remote_tool_v1(self) -> dict[str, Any]:
        payload = await self._remote_tool_invoke_payload()
        timeout = self.config.get("timeout_sec", 600)
        async with self._http_client(timeout=timeout) as client:
            try:
                invoke_response = await client.post(
                    self._remote_url("invoke"),
                    json=payload,
                    headers={"X-Sciminer-Request-Id": payload["request_id"]},
                )
                invoke_response.raise_for_status()
                invoke_result = invoke_response.json()
            except httpx.HTTPStatusError as exc:
                raise TaskExecutionError(
                    f"Remote tool invoke failed: HTTP {exc.response.status_code}",
                    details={"response_text": exc.response.text[:500]},
                ) from exc
            except httpx.HTTPError as exc:
                raise TaskExecutionError(f"Remote tool invoke failed: {exc}") from exc

            remote_run_id = str(invoke_result.get("remote_run_id") or "")
            if not remote_run_id:
                raise TaskExecutionError("Remote tool invoke response missing remote_run_id")
            self._set_task_extra("remote_run_id", remote_run_id)

            status_payload = await self._poll_remote_run(client, remote_run_id)
            result_payload = await self._fetch_remote_artifacts(client, remote_run_id)
            output_file_ids = await self._materialize_remote_result_files(client, result_payload)

        return {
            "success": True,
            "remote_run_id": remote_run_id,
            "remote_status": status_payload,
            "result": result_payload,
            "output_file_ids": output_file_ids,
        }

    async def _remote_tool_invoke_payload(self) -> dict[str, Any]:
        input_params = self.task.inputs.params if self.task.inputs else {}
        extra_data = self.task.extra_data if isinstance(self.task.extra_data, dict) else {}
        return build_remote_tool_invoke_payload(
            request_id=str(uuid.uuid4()),
            task_id=str(self.task.id),
            tool_slug=self.config.get("tool_slug") or self.config.get("slug"),
            tool_version=getattr(self.tool_version, "version", None),
            inputs=await self._remote_tool_inputs(),
            parameters=remote_tool_parameters(input_params),
            project_id=extra_data.get("project_id"),
            user_id=str(self.task.user_id) if self.task.user_id else None,
        )

    async def _remote_tool_inputs(self) -> dict[str, Any]:
        example_inputs = remote_example_input_refs(self.task.extra_data)
        if example_inputs:
            return await self._remote_example_inputs(example_inputs)
        bindings = standard_input_bindings(self.task.extra_data)
        if bindings and remote_artifact_input_declarations(self.config):
            return await self._remote_standard_artifact_inputs(bindings)
        if self.task.inputs and self.task.inputs.file_ids:
            return await self._remote_legacy_file_inputs(self.task.inputs.file_ids)
        return {}

    async def _remote_example_inputs(self, example_inputs: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        async for session in get_async_session():
            for input_name, input_ref in example_inputs.items():
                if not isinstance(input_ref, dict):
                    continue
                files_by_role: dict[str, dict[str, Any]] = {}
                file_refs = input_ref.get("files")
                if isinstance(file_refs, dict):
                    for role, file_id in file_refs.items():
                        file_record = await session.get(FileModel, str(file_id))
                        if file_record is None:
                            raise TaskExecutionError(f"Input file not found: {file_id}")
                        files_by_role[str(role)] = self._remote_file_payload(file_record)
                payload[str(input_name)] = {
                    "type": input_ref.get("type"),
                    "files": files_by_role,
                    "metadata": dict(input_ref.get("metadata") or {}),
                }
            break
        return payload

    async def _remote_standard_artifact_inputs(
        self,
        bindings: dict[str, str],
    ) -> dict[str, Any]:
        declarations = remote_artifact_input_declarations(self.config)
        declaration_by_name = {str(item.get("name")): item for item in declarations}
        unexpected_inputs = sorted(set(bindings) - set(declaration_by_name))
        if unexpected_inputs:
            raise TaskExecutionError(
                "Remote tool input binding references unknown manifest inputs: "
                + ", ".join(unexpected_inputs)
            )

        inputs: dict[str, Any] = {}
        async for session in get_async_session():
            for declaration in declarations:
                input_name = str(declaration.get("name") or "")
                version_id = bindings.get(input_name)
                if not version_id:
                    if declaration.get("required") is not False:
                        raise TaskExecutionError(f"Missing required remote tool input: {input_name}")
                    continue
                version = await self._load_artifact_version(session, version_id)
                try:
                    validate_remote_artifact_input(declaration, version)
                    inputs[input_name] = remote_artifact_input_payload(
                        declaration=declaration,
                        version=version,
                        file_payload=self._remote_file_payload,
                    )
                except RemoteToolInputError as exc:
                    raise TaskExecutionError(str(exc)) from exc
            break
        return inputs

    async def _load_artifact_version(self, session, version_id: str) -> ArtifactVersion:
        result = await session.execute(
            select(ArtifactVersion)
            .options(
                selectinload(ArtifactVersion.artifact),
                selectinload(ArtifactVersion.files).selectinload(ArtifactVersionFile.file),
            )
            .where(ArtifactVersion.id == version_id)
        )
        version = result.scalar_one_or_none()
        if version is None:
            raise TaskExecutionError(f"ArtifactVersion not found: {version_id}")
        return version

    async def _remote_legacy_file_inputs(self, file_ids: list[str]) -> dict[str, Any]:
        files: dict[str, dict[str, Any]] = {}
        async for session in get_async_session():
            for index, file_id in enumerate(file_ids):
                file_record = await session.get(FileModel, str(file_id))
                if file_record is None:
                    raise TaskExecutionError(f"Input file not found: {file_id}")
                files[f"file_{index + 1}"] = self._remote_file_payload(file_record)
            break
        return {"files": {"files": files, "metadata": {}}}

    def _remote_file_payload(self, file_record: FileModel) -> dict[str, Any]:
        return remote_file_payload(
            file_record,
            download_url=remote_file_download_url(
                file_id=str(file_record.id),
                task_id=str(self.task.id),
                config=self.config,
            ),
        )

    async def _poll_remote_run(
        self,
        client: httpx.AsyncClient,
        remote_run_id: str,
    ) -> dict[str, Any]:
        poll_interval = float(self.config.get("poll_interval_sec", 0))
        max_polls = int(self.config.get("max_polls", 3600))
        log_cursor: str | None = None
        for _ in range(max_polls):
            status_payload = await self._fetch_remote_status(client, remote_run_id)
            status_state = remote_status_state(status_payload)
            log_cursor = await self._fetch_remote_logs(
                client,
                remote_run_id,
                log_cursor,
                progress=status_state.progress,
            )
            if self.progress_callback and status_state.progress is not None:
                await self.progress_callback(status_state.progress, status_state.message)
            if status_state.is_success:
                return status_payload
            if status_state.error_message is not None:
                raise TaskExecutionError(status_state.error_message)
            if poll_interval > 0:
                await asyncio.sleep(poll_interval)
        raise TaskExecutionError("Remote tool run polling exceeded max_polls")

    async def _fetch_remote_status(
        self,
        client: httpx.AsyncClient,
        remote_run_id: str,
    ) -> dict[str, Any]:
        response = await client.get(self._remote_url("status", remote_run_id=remote_run_id))
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise TaskExecutionError("Remote status response must be an object")
        return payload

    async def _fetch_remote_logs(
        self,
        client: httpx.AsyncClient,
        remote_run_id: str,
        cursor: str | None,
        *,
        progress: float | None,
    ) -> str | None:
        params = {"cursor": cursor} if cursor else None
        response = await client.get(
            self._remote_url("logs", remote_run_id=remote_run_id),
            params=params,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            return cursor
        await self._publish_remote_log_messages(payload, progress=progress)
        return payload.get("next_cursor") or cursor

    async def _publish_remote_log_messages(
        self,
        payload: dict[str, Any],
        *,
        progress: float | None,
    ) -> None:
        if not self.progress_callback:
            return
        items = payload.get("items")
        if not isinstance(items, list):
            return
        current_progress = progress
        if current_progress is None:
            current_progress = float(getattr(self.task, "progress", 0.0) or 0.0)
        for item in items:
            if not isinstance(item, dict):
                continue
            message = item.get("message")
            if isinstance(message, str) and message.strip():
                await self.progress_callback(float(current_progress), message.strip())

    async def _fetch_remote_artifacts(
        self,
        client: httpx.AsyncClient,
        remote_run_id: str,
    ) -> dict[str, Any]:
        response = await client.get(self._remote_url("artifacts", remote_run_id=remote_run_id))
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise TaskExecutionError("Remote artifacts response must be an object")
        if payload.get("result_version") != "aidd.sciminer/result.v2":
            raise TaskExecutionError("Remote artifacts response must be result.v2")
        return payload

    async def _materialize_remote_result_files(
        self,
        client: httpx.AsyncClient,
        result_payload: dict[str, Any],
    ) -> list[str]:
        output_file_ids: list[str] = []
        artifacts = list(iter_remote_result_artifacts(result_payload.get("artifacts")))
        if not artifacts:
            result_payload["output_file_ids"] = output_file_ids
            return output_file_ids

        async for session in get_async_session():
            try:
                for artifact_ref, artifact in artifacts:
                    if not isinstance(artifact, dict):
                        continue
                    files = artifact.get("files")
                    if not isinstance(files, dict):
                        continue
                    for role, file_ref in files.items():
                        if not isinstance(file_ref, dict) or not file_ref.get("url"):
                            continue
                        content = await self._download_remote_result_file(client, str(file_ref["url"]))
                        try:
                            actual_sha256 = verify_remote_result_file_checksum(file_ref, str(role), content)
                        except RemoteToolResultError as exc:
                            raise TaskExecutionError(str(exc)) from exc
                        filename = remote_result_filename(file_ref, str(role))
                        file_record = FileModel(
                            filename=filename,
                            content_type=file_ref.get("content_type") or "application/octet-stream",
                            size_bytes=len(content),
                            sha256=actual_sha256,
                            storage_path="pending",
                            source_type=FileSourceType.TOOL_OUTPUT.value,
                            owner_id=self.task.user_id,
                            is_public=False,
                            is_permanent=False,
                            file_meta={
                                "remote_result_path": file_ref.get("path"),
                                "relative_path": file_ref.get("path"),
                                "artifact_ref": artifact.get("ref"),
                                "standard_artifact_output": artifact_ref,
                                "file_role": str(role),
                            },
                        )
                        session.add(file_record)
                        await session.flush()
                        storage_path = get_file_path(str(file_record.id), filename)
                        storage_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(storage_path, "wb") as file_handle:
                            file_handle.write(content)
                        file_record.storage_path = str(storage_path)
                        await session.flush()
                        file_ref["file_id"] = str(file_record.id)
                        output_file_ids.append(str(file_record.id))
                await session.commit()
                break
            except Exception:
                await session.rollback()
                raise
        result_payload["output_file_ids"] = output_file_ids
        return output_file_ids

    async def _download_remote_result_file(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> bytes:
        response = await client.get(self._remote_result_url(url))
        response.raise_for_status()
        return response.content

    def _remote_result_url(self, url: str) -> str:
        return remote_result_url(str(self.config.get("base_url") or ""), url)

    async def cancel_remote_run(self) -> dict[str, Any]:
        remote_run_id = str((self.task.extra_data or {}).get("remote_run_id") or "")
        if not remote_run_id:
            raise TaskExecutionError("Remote run id is not recorded for this task")
        async with self._http_client(timeout=self.config.get("timeout_sec", 600)) as client:
            response = await client.post(self._remote_url("cancel", remote_run_id=remote_run_id))
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise TaskExecutionError("Remote cancel response must be an object")
            return payload

    def _remote_url(self, endpoint_name: str, *, remote_run_id: str | None = None) -> str:
        try:
            return remote_endpoint_url(
                self.config,
                endpoint_name,
                remote_run_id=remote_run_id,
            )
        except RemoteToolUrlError as exc:
            raise TaskExecutionError(str(exc)) from exc

    def _http_client(self, *, timeout: float | int) -> httpx.AsyncClient:
        transport = self.config.get("httpx_transport")
        return httpx.AsyncClient(timeout=timeout, transport=transport)

    def _set_task_extra(self, key: str, value: Any) -> None:
        data = dict(self.task.extra_data or {})
        data[key] = value
        self.task.extra_data = data

    async def _prepare_request_data(self) -> dict[str, Any]:
        if not self.task.inputs:
            return {}

        input_params = self.task.inputs.params or {}
        input_file_paths = (
            await self._download_input_files()
            if self.task.inputs.file_ids else None
        )
        return build_legacy_remote_api_request_data(
            task_id=str(self.task.id),
            input_params=input_params,
            input_file_paths=input_file_paths,
        )

    async def _download_input_files(self) -> list[str]:
        file_paths: list[str] = []
        input_dir = os.path.join(self._get_work_dir(), "input")
        os.makedirs(input_dir, exist_ok=True)

        async for session in get_async_session():
            try:
                for file_id in self.task.inputs.file_ids:
                    result = await session.execute(select(FileModel).where(FileModel.id == file_id))
                    file_record = result.scalar_one_or_none()
                    if not file_record:
                        logger.warning("Input file %s not found, skipping", file_id)
                        continue
                    if not file_record.storage_path or not os.path.exists(file_record.storage_path):
                        logger.error("Input file %s not found in storage", file_record.filename)
                        continue
                    destination = os.path.join(input_dir, file_record.filename)
                    shutil.copy2(file_record.storage_path, destination)
                    file_paths.append(destination)
                    logger.info("Downloaded input file: %s", file_record.filename)
                break
            except Exception as exc:
                logger.error("Failed to download input files: %s", exc)
                raise TaskExecutionError(f"Failed to download input files: {exc}") from exc
        return file_paths

    async def _process_output_files(self, output_files: list[dict[str, Any]]) -> list[str]:
        uploaded_ids: list[str] = []
        async for session in get_async_session():
            try:
                for file_info in output_files:
                    url = file_info.get("url")
                    filename = file_info.get("name") or file_info.get("filename", f"output_{uuid.uuid4()}.dat")
                    if not url:
                        logger.warning("Output file %s missing URL, skipping", filename)
                        continue
                    try:
                        async with httpx.AsyncClient(timeout=300) as client:
                            response = await client.get(url)
                            response.raise_for_status()
                            content = response.content
                        file_record = FileModel(
                            filename=filename,
                            content_type=response.headers.get("content-type", "application/octet-stream"),
                            size_bytes=len(content),
                            sha256=hashlib.sha256(content).hexdigest(),
                            source_type=FileSourceType.TOOL_OUTPUT.value,
                            owner_id=self.task.user_id,
                            is_public=False,
                            is_permanent=False,
                        )
                        session.add(file_record)
                        await session.flush()
                        storage_path = get_file_path(file_record.id, filename)
                        storage_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(storage_path, "wb") as file_handle:
                            file_handle.write(content)
                        file_record.storage_path = str(storage_path)
                        await session.flush()
                        uploaded_ids.append(file_record.id)
                        logger.info("Processed output file from %s -> %s", url, file_record.id)
                    except httpx.HTTPError as exc:
                        logger.error("Failed to download output file from %s: %s", url, exc)
                    except Exception as exc:
                        logger.error("Failed to process output file %s: %s", filename, exc)
                await session.commit()
                break
            except Exception as exc:
                logger.error("Failed to process output files: %s", exc)
                await session.rollback()
                raise TaskExecutionError(f"Failed to process output files: {exc}") from exc
        return uploaded_ids
