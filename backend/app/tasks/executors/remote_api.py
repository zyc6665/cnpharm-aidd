"""远程 API 工具执行器。"""

import hashlib
import json
import logging
import os
import shutil
import uuid
from typing import Any

import httpx
from sqlalchemy import select

from app.database.session import get_async_session
from app.files.storage_path import get_file_path
from app.models.files import File as FileModel, FileSourceType
from app.tasks.executors.base import BaseExecutor
from app.tasks.executors.errors import TaskExecutionError

logger = logging.getLogger(__name__)


class RemoteAPIExecutor(BaseExecutor):
    """远程 API 执行器。"""

    async def execute(self) -> dict[str, Any]:
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
