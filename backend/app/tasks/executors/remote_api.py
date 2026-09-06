"""远程 API 工具执行器。"""

import hashlib
import json
import logging
import os
import shutil
import uuid
import asyncio
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.artifact_standards.registry import get_standard_artifact_spec, parse_standard_ref
from app.config import settings
from app.database.session import get_async_session
from app.files.remote_access_tokens import create_remote_file_access_token
from app.models.artifacts import ArtifactVersion, ArtifactVersionFile
from app.files.storage_path import get_file_path
from app.models.files import File as FileModel, FileSourceType
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
                        endpoint, params=self._flatten_params(request_data), headers=headers
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
        parameters = input_params.get("parameters") if isinstance(input_params, dict) else None
        if parameters is None:
            parameters = input_params if isinstance(input_params, dict) else {}
        return {
            "request_id": str(uuid.uuid4()),
            "task": {
                "id": str(self.task.id),
                "tool_slug": self.config.get("tool_slug") or self.config.get("slug"),
                "tool_version": getattr(self.tool_version, "version", None),
            },
            "inputs": await self._remote_tool_inputs(),
            "parameters": parameters,
            "context": {
                "project_id": (self.task.extra_data or {}).get("project_id"),
                "user_id": str(self.task.user_id) if self.task.user_id else None,
            },
        }

    async def _remote_tool_inputs(self) -> dict[str, Any]:
        example_inputs = self._remote_example_input_refs()
        if example_inputs:
            return await self._remote_example_inputs(example_inputs)
        bindings = self._standard_input_bindings()
        if bindings and self._remote_artifact_input_declarations():
            return await self._remote_standard_artifact_inputs(bindings)
        if self.task.inputs and self.task.inputs.file_ids:
            return await self._remote_legacy_file_inputs(self.task.inputs.file_ids)
        return {}

    def _remote_example_input_refs(self) -> dict[str, Any]:
        data = self.task.extra_data if isinstance(self.task.extra_data, dict) else {}
        inputs = data.get("remote_example_inputs")
        return dict(inputs) if isinstance(inputs, dict) else {}

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

    def _standard_input_bindings(self) -> dict[str, str]:
        data = self.task.extra_data if isinstance(self.task.extra_data, dict) else {}
        bindings = data.get("input_bindings")
        if not isinstance(bindings, dict):
            return {}
        return {
            str(input_name): str(version_id)
            for input_name, version_id in bindings.items()
            if str(input_name).strip() and str(version_id).strip()
        }

    async def _remote_standard_artifact_inputs(
        self,
        bindings: dict[str, str],
    ) -> dict[str, Any]:
        declarations = self._remote_artifact_input_declarations()
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
                self._validate_remote_artifact_input(declaration, version)
                inputs[input_name] = self._remote_artifact_input_payload(
                    declaration=declaration,
                    version=version,
                )
            break
        return inputs

    def _remote_artifact_input_declarations(self) -> list[dict[str, Any]]:
        artifacts = self.config.get("artifacts") if isinstance(self.config, dict) else None
        raw_inputs = artifacts.get("inputs") if isinstance(artifacts, dict) else None
        if not isinstance(raw_inputs, list):
            return []
        return [item for item in raw_inputs if isinstance(item, dict)]

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

    def _validate_remote_artifact_input(
        self,
        declaration: dict[str, Any],
        version: ArtifactVersion,
    ) -> None:
        input_name = str(declaration.get("name") or "")
        expected_ref = str(declaration.get("type") or "")
        actual_ref = self._artifact_version_ref(version)
        if actual_ref != parse_standard_ref(expected_ref).ref:
            raise TaskExecutionError(
                f"Input {input_name} expects {expected_ref}, got {actual_ref}"
            )

        spec = get_standard_artifact_spec(expected_ref)
        available_roles = {file_link.role for file_link in version.files}
        missing_roles = [
            role.role
            for role in spec.file_roles
            if role.required and role.role not in available_roles
        ]
        if missing_roles:
            raise TaskExecutionError(
                f"Input {input_name} missing required file roles: " + ", ".join(missing_roles)
            )

    def _artifact_version_ref(self, version: ArtifactVersion) -> str:
        artifact = version.artifact
        if artifact and artifact.standard_type and artifact.standard_version:
            return parse_standard_ref(f"{artifact.standard_type}@{artifact.standard_version}").ref
        manifest = version.manifest_json if isinstance(version.manifest_json, dict) else {}
        manifest_type = manifest.get("type")
        if manifest_type:
            return parse_standard_ref(str(manifest_type)).ref
        raise TaskExecutionError(f"ArtifactVersion {version.id} is not a standard ArtifactVersion")

    def _remote_artifact_input_payload(
        self,
        *,
        declaration: dict[str, Any],
        version: ArtifactVersion,
    ) -> dict[str, Any]:
        files: dict[str, dict[str, Any]] = {}
        for file_link in sorted(version.files, key=lambda item: item.sort_order):
            file_record = file_link.file
            if file_record is None:
                raise TaskExecutionError(
                    f"Input {declaration.get('name')} role {file_link.role} has no file record"
                )
            files[str(file_link.role)] = self._remote_file_payload(file_record)

        manifest = version.manifest_json if isinstance(version.manifest_json, dict) else {}
        metadata = manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {}
        return {
            "artifact_version_id": str(version.id),
            "type": str(declaration.get("type") or self._artifact_version_ref(version)),
            "files": files,
            "metadata": dict(metadata),
        }

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
        return {
            "url": self._remote_file_download_url(str(file_record.id)),
            "filename": file_record.filename,
            "sha256": str(file_record.sha256).lower(),
            "content_type": file_record.content_type,
        }

    def _remote_file_download_url(self, file_id: str) -> str:
        expires_in = int(self.config.get("input_url_expires_in_sec", 3600))
        token = create_remote_file_access_token(
            file_id=file_id,
            task_id=str(self.task.id),
            expires_in_seconds=expires_in,
        )
        base_url = str(
            self.config.get("platform_base_url")
            or getattr(settings, "PUBLIC_API_BASE_URL", "")
            or ""
        ).rstrip("/")
        return f"{base_url}/api/v1/files/{file_id}/download?token={quote(token)}"

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
            status_value = str(status_payload.get("status") or "").lower()
            message = _remote_status_message(status_payload)
            progress = _remote_status_progress(status_payload, status_value)
            log_cursor = await self._fetch_remote_logs(
                client,
                remote_run_id,
                log_cursor,
                progress=progress,
            )
            if self.progress_callback and progress is not None:
                await self.progress_callback(progress, message)
            if status_value == "success":
                return status_payload
            if status_value == "failure":
                raise TaskExecutionError(message)
            if status_value == "canceled":
                raise TaskExecutionError("Remote tool run was canceled")
            if status_value not in {"queued", "running"}:
                raise TaskExecutionError(f"Unsupported remote run status: {status_value}")
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
        artifacts = list(_iter_remote_result_artifacts(result_payload.get("artifacts")))
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
                        actual_sha256 = hashlib.sha256(content).hexdigest()
                        declared_sha256 = str(file_ref.get("sha256") or "").lower()
                        if declared_sha256 and actual_sha256 != declared_sha256:
                            raise TaskExecutionError(
                                f"Remote result file checksum mismatch for {file_ref.get('path') or role}: "
                                f"declared {declared_sha256}, actual {actual_sha256}"
                            )
                        filename = _remote_result_filename(file_ref, str(role))
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
        if url.startswith("/"):
            return f"{str(self.config.get('base_url') or '').rstrip('/')}{url}"
        return url

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
        base_url = str(self.config.get("base_url") or "").rstrip("/")
        if not base_url:
            raise TaskExecutionError("Missing base_url in remote_tool_v1 config")
        endpoints = self.config.get("endpoints") or {}
        path = endpoints.get(endpoint_name)
        if not isinstance(path, str) or not path.startswith("/"):
            raise TaskExecutionError(f"Missing endpoint path for remote tool endpoint: {endpoint_name}")
        if remote_run_id is not None:
            path = path.replace("{remote_run_id}", remote_run_id)
        return f"{base_url}{path}"

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
        if "params" in input_params and "input_files" in input_params:
            request_data = {
                "task_id": str(self.task.id),
                "params": input_params["params"],
                "input_files": input_params["input_files"],
            }
        else:
            request_data = {"task_id": str(self.task.id), "params": input_params}

        if self.task.inputs.file_ids:
            request_data["files"] = await self._download_input_files()
        return request_data

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

    @staticmethod
    def _flatten_params(data: dict[str, Any]) -> dict[str, str]:
        return {
            key: json.dumps(value) if isinstance(value, (dict, list)) else str(value)
            for key, value in data.items()
        }


def _remote_status_message(payload: dict[str, Any]) -> str:
    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        return message
    error = payload.get("error")
    if isinstance(error, dict):
        error_message = error.get("message")
        if isinstance(error_message, str) and error_message.strip():
            return error_message
    if isinstance(error, str) and error.strip():
        return error
    return "Remote tool run status updated"


def _remote_status_progress(payload: dict[str, Any], status_value: str) -> float | None:
    raw_progress = payload.get("progress")
    if isinstance(raw_progress, (int, float)):
        return float(max(0, min(100, raw_progress)))
    if status_value == "success":
        return 100.0
    return None


def _remote_result_filename(file_ref: dict[str, Any], role: str) -> str:
    explicit_name = file_ref.get("filename") or file_ref.get("name")
    if isinstance(explicit_name, str) and explicit_name.strip():
        return Path(explicit_name).name
    path = file_ref.get("path")
    if isinstance(path, str) and Path(path).name:
        return Path(path).name
    return f"{role}.dat"


def _iter_remote_result_artifacts(raw_artifacts: Any):
    if isinstance(raw_artifacts, list):
        for index, artifact in enumerate(raw_artifacts):
            if isinstance(artifact, dict):
                yield str(artifact.get("ref") or artifact.get("name") or index), artifact
        return
    if isinstance(raw_artifacts, dict):
        for artifact_ref, artifact in raw_artifacts.items():
            if isinstance(artifact, list):
                for index, item in enumerate(artifact):
                    if isinstance(item, dict):
                        yield f"{artifact_ref}[{index}]", item
            elif isinstance(artifact, dict):
                yield str(artifact_ref), artifact
