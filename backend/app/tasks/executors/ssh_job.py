"""SSH 作业执行器。"""

import asyncio
import json
import logging
import os
import posixpath
import queue
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select

from app.database.session import get_async_session
from app.files.content import ensure_local_file
from app.execution.request_builder import (
    StandardExecutionBuildContext,
    StandardRequestBuilderError,
    build_standard_execution_request,
)
from app.models.files import File as FileModel
from app.services.legacy_file_projection import (
    legacy_file_fields,
    select_legacy_file_field,
    standard_input_file_path,
)
from app.tasks.executors.base import BaseExecutor
from app.tasks.executors.errors import TaskExecutionError, TaskTimeoutError
from app.tasks.executors.ssh_artifacts import prepare_output_files
from app.tasks.executors.ssh_auth import resolve_auth_settings
from app.tasks.executors.ssh_command import build_remote_exec_command
from app.tasks.executors.ssh_paths import build_remote_paths
from app.tasks.executors.ssh_payload import build_params_payload
from app.tasks.executors.ssh_result import load_result_json
from app.tasks.ssh_transport import ParamikoSSHTransport
from app.tool_packages.config_resolver import ToolPackageConfigError, validated_tool_package_manifest
from app.tool_packages.schemas import ToolPackageManifest

logger = logging.getLogger(__name__)


class SSHJobExecutor(BaseExecutor):
    """上传任务输入、运行远端入口并回收 SSH 作业结果。"""

    SUPPORTED_RUNNER_MODES = {"docker_exec", "shell"}

    async def recover_remote_result(self) -> Optional[dict[str, Any]]:
        """补抓远端已完成任务的 result.json 与产物文件。"""
        try:
            download_root = await asyncio.to_thread(
                self._recover_remote_outputs_sync,
                self._resolve_auth_settings(),
                self._build_remote_paths(),
            )
            if download_root is None:
                return None

            result = self._load_result_json(download_root)
            output_file_ids = await self._collect_output_files(download_root)
            result = self._attach_output_file_ids(result, output_file_ids)
            return {
                "success": True,
                "result": result,
                "output_file_ids": output_file_ids,
                "stdout": "",
                "stderr": "",
            }
        finally:
            self._cleanup_work_dir()

    async def execute(self) -> dict[str, Any]:
        """通过 SSH 上传输入、调用远端脚本并拉回输出。"""
        timeout = int(self.config.get("timeout_sec", 3600))
        local_bundle = await self._prepare_local_task_bundle()
        remote_paths = self._build_remote_paths()
        auth_settings = self._resolve_auth_settings()
        progress_events: queue.Queue[tuple[float, str] | None] = queue.Queue()
        progress_pump_task: asyncio.Task[None] | None = None

        if self.progress_callback is not None:
            progress_pump_task = asyncio.create_task(self._pump_progress_events(progress_events))

        def progress_sink(progress: float, message: str) -> None:
            if self.progress_callback is None:
                return
            progress_events.put((progress, message))

        try:
            remote_result = await asyncio.to_thread(
                self._run_remote_workflow_sync,
                local_bundle,
                remote_paths,
                auth_settings,
                timeout,
                progress_sink if self.progress_callback is not None else None,
            )
            if progress_pump_task is not None:
                progress_events.put(None)
                await progress_pump_task
                progress_pump_task = None
            download_root = remote_result.get("download_root")
            result = (
                self._load_result_json(download_root)
                if download_root
                else {
                    "success": False,
                    "message": "SSH 作业未产出 output/result.json 即失败",
                }
            )
            output_file_ids = await self._collect_output_files(download_root)
            result = self._attach_output_file_ids(result, output_file_ids)

            cleanup_error = remote_result.get("cleanup_error")
            if cleanup_error:
                logger.warning("Failed to cleanup remote SSH job directory: %s", cleanup_error)
            if remote_result["exit_status"] != 0:
                raise TaskExecutionError(
                    f"SSH 作业执行失败，退出码 {remote_result['exit_status']}",
                    details={
                        "stdout": (remote_result.get("stdout") or "")[:1000],
                        "stderr": (remote_result.get("stderr") or "")[:1000],
                        "remote_host": self.config.get("host"),
                        "result": result,
                    },
                )
            if not result.get("success", True):
                error = result.get("error") or {}
                raise TaskExecutionError(
                    result.get("message") or error.get("code") or "SSH 作业报告执行失败",
                    details={"result": result},
                )
            return {
                "success": True,
                "result": result,
                "output_file_ids": output_file_ids,
                "stdout": remote_result.get("stdout", ""),
                "stderr": remote_result.get("stderr", ""),
            }
        except TimeoutError as exc:
            raise TaskTimeoutError(
                "SSH 作业执行超时",
                timeout_sec=self.config.get("timeout_sec"),
            ) from exc
        except TaskExecutionError:
            raise
        except Exception as exc:
            raise TaskExecutionError(f"SSH 作业执行异常：{exc}") from exc
        finally:
            if progress_pump_task is not None:
                progress_events.put(None)
                await progress_pump_task
            self._cleanup_work_dir()

    async def _pump_progress_events(
        self,
        progress_events: queue.Queue[tuple[float, str] | None],
    ) -> None:
        """串行转发同步 SSH 线程产生的进度事件。"""
        while True:
            item = await asyncio.to_thread(progress_events.get)
            if item is None:
                return
            progress, message = item
            await self._emit_progress(progress, message)

    async def _emit_progress(self, progress: float, message: str) -> None:
        """更新任务进度；进度上报失败不应中断远端任务。"""
        if self.progress_callback is None:
            return
        try:
            await self.progress_callback(progress, message)
        except Exception as exc:
            logger.warning("Failed to publish SSH job progress: %s", exc)

    @staticmethod
    def _attach_output_file_ids(result: dict[str, Any], output_file_ids: list[str]) -> dict[str, Any]:
        """Attach platform file IDs to legacy results without polluting result.v2."""
        if not output_file_ids:
            return result
        if result.get("result_version") == "aidd.sciminer/result":
            return result
        enriched = dict(result)
        enriched["output_file_ids"] = output_file_ids
        return enriched

    def _run_remote_workflow_sync(
        self,
        local_bundle: dict[str, str],
        remote_paths: dict[str, str],
        auth_settings: dict[str, Optional[str]],
        timeout: int,
        progress_sink: Callable[[float, str], None] | None = None,
    ) -> dict[str, Any]:
        """在线程中执行完整的 SSH/SFTP 工作流。"""
        transport = self._create_transport(auth_settings, min(timeout, 60))
        cleanup_error: Optional[str] = None
        workflow_result: Optional[dict[str, Any]] = None
        try:
            transport.connect()
            for remote_dir in (
                remote_paths["host_task_dir"],
                remote_paths["host_input_dir"],
                remote_paths["host_output_dir"],
                remote_paths["host_work_dir"],
            ):
                transport.ensure_dir(remote_dir)
            transport.upload_tree(local_bundle["input_dir"], remote_paths["host_input_dir"])
            transport.upload_file(local_bundle["params_path"], remote_paths["host_params_file"])
            if progress_sink is not None:
                progress_sink(12.0, "远端任务目录已准备，正在启动模型")

            def publish_remote_log(line: str) -> None:
                if progress_sink is None:
                    return
                message = line if line.startswith("远端") else f"远端运行中：{line}"
                progress_sink(35.0, message)

            command_result = transport.run_command(
                self._build_remote_exec_command(remote_paths),
                timeout=timeout,
                progress_callback=publish_remote_log if progress_sink is not None else None,
                progress_log_paths=self._remote_progress_log_paths(remote_paths),
                progress_poll_interval=float(self.config.get("progress_poll_interval_sec", 10.0)),
            )
            if progress_sink is not None:
                progress_sink(80.0, "远端模型执行结束，正在下载输出")
            download_root: Optional[str] = None
            try:
                transport.download_tree(
                    remote_paths["host_output_dir"],
                    os.path.join(local_bundle["download_root"], "output"),
                )
                download_root = local_bundle["download_root"]
                if progress_sink is not None:
                    progress_sink(90.0, "远端输出已下载，正在收集产物")
            except Exception as exc:
                if command_result.exit_status == 0:
                    raise TaskExecutionError(
                        "下载 SSH 作业输出失败",
                        details={
                            "error": str(exc),
                            "remote_output_dir": remote_paths["host_output_dir"],
                        },
                    ) from exc
                logger.warning("Failed to download SSH job outputs after remote failure: %s", str(exc)[:500])
            workflow_result = {
                "exit_status": command_result.exit_status,
                "stdout": command_result.stdout,
                "stderr": command_result.stderr,
                "download_root": download_root,
            }
        finally:
            if self.config.get("cleanup_remote", True):
                try:
                    transport.remove_tree(remote_paths["host_task_dir"])
                except Exception as exc:
                    cleanup_error = str(exc)
            transport.close()
        if workflow_result is None:
            raise TaskExecutionError("SSH 作业执行未产生工作流结果")
        workflow_result["cleanup_error"] = cleanup_error
        return workflow_result

    @staticmethod
    def _remote_progress_log_paths(remote_paths: dict[str, str]) -> list[str]:
        """返回可被 SFTP 增量读取的宿主机侧日志路径。"""
        return [
            posixpath.join(remote_paths["host_output_dir"], "logs", "run.log"),
            posixpath.join(remote_paths["host_work_dir"], "legacy-output", "logs", "run.log"),
            posixpath.join(remote_paths["host_work_dir"], "legacy-work", "logs", "run.log"),
        ]

    def _recover_remote_outputs_sync(
        self,
        auth_settings: dict[str, Optional[str]],
        remote_paths: dict[str, str],
    ) -> Optional[str]:
        """通过 Paramiko 检查并下载可恢复的远端输出。"""
        transport = self._create_transport(auth_settings, 60)
        try:
            transport.connect()
            result_path = posixpath.join(remote_paths["host_output_dir"], "result.json")
            if not transport.path_exists(result_path):
                return None
            download_root = os.path.join(self._get_work_dir(), "download")
            transport.download_tree(
                remote_paths["host_output_dir"],
                os.path.join(download_root, "output"),
            )
            return download_root
        finally:
            transport.close()

    def _create_transport(
        self,
        auth_settings: dict[str, Optional[str]],
        timeout: int,
    ) -> ParamikoSSHTransport:
        return ParamikoSSHTransport(
            host=self.config["host"],
            port=int(self.config.get("port", 22)),
            username=self.config["username"],
            auth_settings=auth_settings,
            strict_host_key_checking=self.config.get("strict_host_key_checking", True),
            timeout=timeout,
        )

    async def _prepare_local_task_bundle(self) -> dict[str, str]:
        work_dir = self._get_work_dir()
        input_dir = os.path.join(work_dir, "input")
        params_path = os.path.join(work_dir, "params.json")
        download_root = os.path.join(work_dir, "download")
        os.makedirs(download_root, exist_ok=True)
        with open(params_path, "w", encoding="utf-8") as params_file:
            json.dump(
                await self._prepare_params_payload(work_dir, input_dir),
                params_file,
                ensure_ascii=False,
                indent=2,
            )
        return {
            "work_dir": work_dir,
            "input_dir": input_dir,
            "params_path": params_path,
            "download_root": download_root,
        }

    async def _prepare_params_payload(self, work_dir: str, input_dir: str) -> dict[str, Any]:
        manifest = self._validated_tool_package_manifest()
        input_bindings = self._standard_input_bindings() if manifest is not None else {}
        if input_bindings:
            payload = await self._build_standard_request_payload(
                manifest=manifest,
                input_bindings=input_bindings,
                work_dir=Path(work_dir),
            )
            return self._append_legacy_standard_compat_payload(payload, manifest)
        return self._build_params_payload(await self._prepare_input_files(input_dir))

    async def _prepare_input_files(self, input_dir: str) -> list[dict[str, str]]:
        inputs = self.task.inputs
        if not inputs or not inputs.file_ids:
            return []
        staged_files: list[dict[str, str]] = []
        async for session in get_async_session():
            try:
                for file_id in inputs.file_ids:
                    file_record = (
                        await session.execute(select(FileModel).where(FileModel.id == file_id))
                    ).scalar_one_or_none()
                    if not file_record:
                        logger.warning("Input file %s not found, skipping", file_id)
                        continue
                    destination_path = os.path.join(input_dir, file_record.filename)
                    try:
                        await ensure_local_file(file_record, Path(destination_path))
                    except FileNotFoundError as exc:
                        raise TaskExecutionError(
                            f"输入文件 {file_record.filename} 在存储中不存在",
                            details={"file_id": file_id, "storage_path": file_record.storage_path},
                        ) from exc
                    staged_files.append(
                        {
                            "file_id": str(file_id),
                            "filename": file_record.filename,
                            "relative_path": posixpath.join("input", file_record.filename),
                            "local_path": destination_path,
                        }
                    )
                break
            except TaskExecutionError:
                raise
            except Exception as exc:
                raise TaskExecutionError(f"准备 SSH 输入文件失败：{exc}") from exc
        return staged_files

    def _build_params_payload(self, staged_files: list[dict[str, str]]) -> dict[str, Any]:
        raw_params = self.task.inputs.params if self.task.inputs else {}
        return build_params_payload(str(self.task.id), raw_params, staged_files)

    async def _build_standard_request_payload(
        self,
        *,
        manifest: ToolPackageManifest,
        input_bindings: dict[str, str],
        work_dir: Path,
    ) -> dict[str, Any]:
        try:
            async for session in get_async_session():
                request = await build_standard_execution_request(
                    session,
                    task=self.task,
                    tool_package_manifest=manifest,
                    input_bindings=input_bindings,
                    parameters=self._task_parameters(),
                    work_dir=work_dir,
                    execution_context=self._standard_execution_context(manifest),
                )
                return request.model_dump(mode="json")
        except StandardRequestBuilderError as exc:
            raise TaskExecutionError(f"构建标准请求 request.v1 失败：{exc}") from exc
        raise TaskExecutionError("打开数据库会话以构建标准请求 request.v1 失败")

    def _standard_input_bindings(self) -> dict[str, str]:
        data = getattr(self.task, "extra_data", None)
        if not isinstance(data, dict):
            return {}
        bindings = data.get("input_bindings")
        if not isinstance(bindings, dict):
            return {}
        return {
            str(input_name): str(version_id)
            for input_name, version_id in bindings.items()
            if input_name and version_id
        }

    def _task_parameters(self) -> dict[str, Any]:
        raw_params = self.task.inputs.params if self.task.inputs else {}
        if not isinstance(raw_params, dict):
            return {}
        if "params" in raw_params or "input_files" in raw_params:
            nested = raw_params.get("params")
            if isinstance(nested, dict):
                return dict(nested)
            return {
                key: value
                for key, value in raw_params.items()
                if key not in {"params", "input_files"}
            }
        return dict(raw_params)

    def _append_legacy_standard_compat_payload(
        self,
        payload: dict[str, Any],
        manifest: ToolPackageManifest,
    ) -> dict[str, Any]:
        """Expose v2 standard inputs through legacy params/input_files for old SSH runners."""
        enriched = dict(payload)
        parameters = self._task_parameters()
        if parameters and not isinstance(enriched.get("params"), dict):
            enriched["params"] = parameters

        projected_input_files = self._project_standard_inputs_to_legacy_fields(payload, manifest)
        if projected_input_files:
            existing = (
                enriched.get("input_files")
                if isinstance(enriched.get("input_files"), dict)
                else {}
            )
            enriched["input_files"] = {**projected_input_files, **existing}
        return enriched

    def _project_standard_inputs_to_legacy_fields(
        self,
        payload: dict[str, Any],
        manifest: ToolPackageManifest,
    ) -> dict[str, str]:
        inputs = payload.get("inputs")
        if not isinstance(inputs, dict):
            return {}
        file_fields = legacy_file_fields(self.config)
        if not file_fields:
            return {}

        projected: dict[str, str] = {}
        used_fields: set[str] = set()
        for declaration in manifest.artifacts.inputs:
            standard_input = inputs.get(declaration.name)
            if not isinstance(standard_input, dict):
                continue
            file_field = select_legacy_file_field(
                input_name=declaration.name,
                standard_type=declaration.type,
                file_fields=file_fields,
                used_fields=used_fields,
            )
            if not file_field:
                continue
            path = standard_input_file_path(standard_input, declaration.type)
            if not path:
                continue
            projected[file_field] = path
            used_fields.add(file_field)
        return projected

    def _validated_tool_package_manifest(self) -> ToolPackageManifest | None:
        try:
            return validated_tool_package_manifest(self.config)
        except ToolPackageConfigError as exc:
            raise TaskExecutionError(str(exc)) from exc

    def _standard_execution_context(
        self,
        manifest: ToolPackageManifest,
    ) -> StandardExecutionBuildContext:
        variant_name = str(
            self.config.get("variant")
            or self.config.get("variant_name")
            or (manifest.variants[0].name if manifest.variants else "cpu")
        )
        variant = next(
            (item for item in manifest.variants if item.name == variant_name),
            manifest.variants[0] if manifest.variants else None,
        )
        accelerator = self.config.get("accelerator")
        if accelerator is None and variant is not None:
            accelerator = variant.accelerator.value
        return StandardExecutionBuildContext(
            variant=variant_name,
            accelerator=str(accelerator or "cpu"),
        )

    def _build_remote_paths(self) -> dict[str, str]:
        return build_remote_paths(self.config, str(self.task.id))

    def _resolve_auth_settings(self) -> dict[str, Optional[str]]:
        return resolve_auth_settings(self.config)

    def _build_remote_exec_command(self, remote_paths: dict[str, str]) -> str:
        return build_remote_exec_command(self.config, str(self.task.id), remote_paths)

    def _load_result_json(self, download_root: Optional[str]) -> dict[str, Any]:
        return load_result_json(download_root)

    async def _collect_output_files(self, download_root: Optional[str]) -> list[str]:
        if not download_root:
            return []
        output_root = os.path.join(download_root, "output")
        if not os.path.exists(output_root):
            return []
        matched_files = self._prepare_output_files_for_collection(download_root, output_root)
        if not matched_files:
            return []
        return await super()._collect_output_files(
            matched_files,
            output_root=output_root,
            filename_builder=lambda _source, relative: relative.replace(os.sep, "__"),
            file_meta_builder=lambda _source, relative: {"relative_path": relative},
            skip_names={"result.json"},
        )

    def _prepare_output_files_for_collection(self, download_root: str, output_root: str) -> list[str]:
        return prepare_output_files(self.config, download_root, output_root)
