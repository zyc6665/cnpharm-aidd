"""AIDD 内建工具执行器。"""

from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.database.session import get_async_session
from app.tasks.executors.base import BaseExecutor
from app.tasks.executors.errors import TaskExecutionError


class BuiltinExecutor(BaseExecutor):
    """Execute supported AIDD built-ins through the platform task runtime."""

    async def execute(self) -> dict[str, Any]:
        from app.agents.aidd.builtin_tools import BuiltinToolFile, run_builtin_tool
        from app.models.files import File as FileModel
        from app.models.tasks import TaskInput

        builtin_slug = str(self.config.get("builtin_slug") or "")
        if not builtin_slug:
            raise TaskExecutionError("Missing builtin_slug in tool config")

        task_input = getattr(self.task, "inputs", None)
        if task_input is None:
            async for session in get_async_session():
                result = await session.execute(
                    select(TaskInput).where(TaskInput.task_id == self.task.id)
                )
                task_input = result.scalar_one_or_none()
                break

        params = task_input.params if task_input else {}
        semantic_file_ids = params.get("builtin_inputs") if isinstance(params, dict) else None
        if semantic_file_ids is None:
            semantic_file_ids = {}
        elif not isinstance(semantic_file_ids, dict):
            raise TaskExecutionError("Builtin task builtin_inputs must be a mapping")

        input_ids = [str(file_id) for file_id in semantic_file_ids.values() if file_id]
        files_by_id: dict[str, FileModel] = {}
        if input_ids:
            async for session in get_async_session():
                result = await session.execute(select(FileModel).where(FileModel.id.in_(input_ids)))
                files_by_id = {str(file.id): file for file in result.scalars().all()}
                break

        builtin_files: dict[str, BuiltinToolFile] = {}
        for semantic_type, file_id in semantic_file_ids.items():
            file_record = files_by_id.get(str(file_id))
            if not file_record or not file_record.storage_path:
                raise TaskExecutionError(f"Builtin input file is unavailable: {semantic_type}")
            builtin_files[str(semantic_type)] = BuiltinToolFile(
                file_id=str(file_record.id),
                filename=file_record.filename,
                path=Path(file_record.storage_path),
                content_type=file_record.content_type,
            )

        result = await run_builtin_tool(builtin_slug, builtin_files, params=params)
        output_dir = Path(self._get_work_dir()) / "output"
        artifact_paths: list[str] = []
        for artifact in result.artifacts:
            target = output_dir / artifact.filename
            target.write_bytes(artifact.content)
            artifact_paths.append(str(target))

        output_file_ids = await self._collect_output_files(
            artifact_paths,
            output_root=str(output_dir),
        )
        output_data = (
            result.standard_result
            if result.standard_result is not None
            else {output.semantic_type: output.data for output in result.outputs}
        )
        return {
            "success": True,
            "result": output_data,
            "output_file_ids": output_file_ids,
        }
