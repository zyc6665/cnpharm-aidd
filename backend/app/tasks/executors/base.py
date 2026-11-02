"""任务执行器共享基类。"""

import hashlib
import logging
import mimetypes
import os
import shutil
import uuid
from abc import ABC, abstractmethod
from collections.abc import Awaitable
from typing import TYPE_CHECKING, Any, Callable, Optional

from app.database.session import get_async_session
from app.files.storage_path import get_file_path
from app.files.writer import store_file_bytes
from app.config import settings
from app.models.files import File as FileModel, FileSourceType
from app.tasks.executors.errors import TaskExecutionError

if TYPE_CHECKING:
    from app.models.tasks import Task
    from app.models.tools import ToolVersion

logger = logging.getLogger(__name__)


class BaseExecutor(ABC):
    """执行器共享基类。"""

    def __init__(
        self,
        task: "Task",
        tool_version: "ToolVersion",
        config: Optional[dict[str, Any]] = None,
        progress_callback: Optional[Callable[[float, str], Awaitable[None]]] = None,
        db_session: Any | None = None,
    ):
        self.task = task
        self.tool_version = tool_version
        self.config = config if config is not None else tool_version.config
        self.work_dir: Optional[str] = None
        self.progress_callback = progress_callback
        self.db_session = db_session

    @abstractmethod
    async def execute(self) -> dict[str, Any]:
        """执行任务。"""

    def _get_work_dir(self) -> str:
        if not self.work_dir:
            base_dir = os.environ.get("TASK_WORK_DIR", "/tmp/tasks")
            self.work_dir = os.path.join(base_dir, str(self.task.id))
            os.makedirs(self.work_dir, exist_ok=True)
            os.makedirs(os.path.join(self.work_dir, "input"), exist_ok=True)
            os.makedirs(os.path.join(self.work_dir, "output"), exist_ok=True)
        return self.work_dir

    def _cleanup_work_dir(self) -> None:
        if self.work_dir and os.path.exists(self.work_dir):
            try:
                shutil.rmtree(self.work_dir)
                logger.debug("Cleaned up work directory: %s", self.work_dir)
            except Exception as exc:
                logger.warning("Failed to cleanup work directory: %s", exc)

    async def _collect_output_files(
        self,
        source_paths: list[str],
        *,
        output_root: Optional[str] = None,
        file_meta_builder: Optional[Callable[[str, str], Optional[dict[str, Any]]]] = None,
        filename_builder: Optional[Callable[[str, str], str]] = None,
        skip_names: Optional[set[str]] = None,
    ) -> list[str]:
        if self.db_session is not None:
            return await self._collect_output_files_with_session(
                self.db_session,
                source_paths,
                output_root=output_root,
                file_meta_builder=file_meta_builder,
                filename_builder=filename_builder,
                skip_names=skip_names,
                commit=False,
            )

        async for session in get_async_session():
            return await self._collect_output_files_with_session(
                session,
                source_paths,
                output_root=output_root,
                file_meta_builder=file_meta_builder,
                filename_builder=filename_builder,
                skip_names=skip_names,
                commit=True,
            )
        return []

    async def _collect_output_files_with_session(
        self,
        session: Any,
        source_paths: list[str],
        *,
        output_root: Optional[str],
        file_meta_builder: Optional[Callable[[str, str], Optional[dict[str, Any]]]],
        filename_builder: Optional[Callable[[str, str], str]],
        skip_names: Optional[set[str]],
        commit: bool,
    ) -> list[str]:
        uploaded_ids: list[str] = []
        skip_names = skip_names or set()

        try:
            for source_path in source_paths:
                if not os.path.isfile(source_path):
                    continue

                relative_path = (
                    os.path.relpath(source_path, output_root)
                    if output_root
                    else os.path.basename(source_path)
                )
                basename = os.path.basename(source_path)
                if basename in skip_names or relative_path in skip_names:
                    continue

                try:
                    with open(source_path, "rb") as file_handle:
                        content = file_handle.read()

                    filename = (
                        filename_builder(source_path, relative_path)
                        if filename_builder
                        else basename
                    )
                    content_type = mimetypes.guess_type(source_path)[0] or "application/octet-stream"
                    file_meta = (
                        file_meta_builder(source_path, relative_path)
                        if file_meta_builder
                        else None
                    )
                    if settings.STORAGE_BACKEND == "minio":
                        file_record = await store_file_bytes(
                            session,
                            content=content,
                            filename=filename,
                            content_type=content_type,
                            source_type=FileSourceType.TOOL_OUTPUT,
                            owner_id=self.task.user_id,
                            file_meta=file_meta,
                            is_public=False,
                            is_permanent=False,
                            sha256=hashlib.sha256(content).hexdigest(),
                        )
                    else:
                        file_id = str(uuid.uuid4())
                        storage_path = get_file_path(file_id, filename)
                        storage_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source_path, str(storage_path))
                        file_record = FileModel(
                            id=file_id,
                            filename=filename,
                            content_type=content_type,
                            size_bytes=len(content),
                            sha256=hashlib.sha256(content).hexdigest(),
                            storage_backend="local",
                            storage_path=str(storage_path),
                            source_type=FileSourceType.TOOL_OUTPUT.value,
                            owner_id=self.task.user_id,
                            is_public=False,
                            is_permanent=False,
                            file_meta=file_meta,
                        )
                        session.add(file_record)
                        await session.flush()
                    file_id = str(file_record.id)

                    uploaded_ids.append(file_id)
                    logger.info("Collected output file: %s -> %s", relative_path, file_id)
                except Exception as exc:
                    # 不再静默跳过：产物写入失败必须让任务失败，并把原因向上抛给
                    # worker 的失败处理链路写入 task.error_message（此前只 log 一行
                    # 后继续，任务会以「成功但缺产物」收场，问题被吞掉）。
                    logger.exception(
                        "Failed to collect output file %s (%s)",
                        source_path,
                        relative_path,
                    )
                    raise TaskExecutionError(
                        f"收集输出文件失败：{relative_path}：{exc}"
                    ) from exc

            if commit:
                await session.commit()
        except Exception as exc:
            logger.error("Failed to collect output files: %s", exc)
            if commit:
                await session.rollback()
            raise TaskExecutionError(f"收集输出文件失败：{exc}") from exc

        return uploaded_ids
