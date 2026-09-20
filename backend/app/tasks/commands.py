"""Explicit commands shared by task creation surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.run_input_normalization import normalize_string_mapping
from app.services.run_preparation import PreparedRun


@dataclass(frozen=True)
class TaskCommand:
    """Prepared, persistence-ready intent for one tool task."""

    user_id: str
    tool_id: str
    tool_version_id: str
    name: str | None
    priority: str
    prepared_run: PreparedRun
    extra_data: dict[str, object]

    @classmethod
    def from_prepared_run(
        cls,
        *,
        user_id: str,
        tool_id: str,
        tool_version_id: str,
        name: str | None,
        priority: str,
        prepared_run: PreparedRun,
        requested_input_bindings: dict[str, str] | None = None,
        extra_data: dict[str, object] | None = None,
    ) -> "TaskCommand":
        metadata = dict(extra_data or {})
        requested_bindings = normalize_string_mapping(requested_input_bindings)
        if prepared_run.input_bindings:
            metadata["input_bindings"] = dict(prepared_run.input_bindings)
        elif requested_bindings:
            metadata["input_bindings"] = requested_bindings
        if prepared_run.standard_input_uploads:
            metadata["standard_input_uploads"] = dict(
                prepared_run.standard_input_uploads
            )
        if prepared_run.binding_decisions:
            metadata["binding_decisions"] = dict(prepared_run.binding_decisions)

        return cls(
            user_id=user_id,
            tool_id=tool_id,
            tool_version_id=tool_version_id,
            name=name,
            priority=priority,
            prepared_run=prepared_run,
            extra_data=metadata,
        )

    @property
    def project_id(self) -> str | None:
        return self.prepared_run.project_id

    @property
    def task_input(self) -> dict[str, Any]:
        return {
            "params": dict(self.prepared_run.params),
            "file_ids": list(self.prepared_run.file_ids),
        }
