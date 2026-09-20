"""Resolve persisted tool executor types to concrete task executors."""

from __future__ import annotations

from collections.abc import Mapping

from app.tasks.executors.base import BaseExecutor
from app.tasks.executors.errors import TaskExecutionError


class ExecutorResolver:
    """Small registry boundary for local task executor implementations."""

    def __init__(
        self,
        executors: Mapping[str, type[BaseExecutor]] | None = None,
    ) -> None:
        self._executors = dict(executors or self._default_executors())

    @staticmethod
    def _default_executors() -> dict[str, type[BaseExecutor]]:
        from app.tasks.executors.builtin import BuiltinExecutor
        from app.tasks.executors.docker import DockerExecutor
        from app.tasks.executors.python_script import PythonScriptExecutor
        from app.tasks.executors.remote_api import RemoteAPIExecutor
        from app.tasks.executors.ssh_job import SSHJobExecutor

        return {
            "builtin": BuiltinExecutor,
            "python_script": PythonScriptExecutor,
            "docker_image": DockerExecutor,
            "ssh_job": SSHJobExecutor,
            "remote_api": RemoteAPIExecutor,
        }

    def resolve(self, executor_type: str) -> type[BaseExecutor]:
        normalized = str(executor_type or "").strip()
        if not normalized:
            raise TaskExecutionError("Missing type in tool config")
        executor_class = self._executors.get(normalized)
        if executor_class is None:
            raise TaskExecutionError(f"Unsupported executor type: {normalized}")
        return executor_class

    def supported_types(self) -> tuple[str, ...]:
        return tuple(self._executors)
