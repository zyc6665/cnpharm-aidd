"""Shared helpers for materializing recovered task results."""

from __future__ import annotations

import logging
from typing import Any

from app.services.standard_artifacts import (
    StandardArtifactPersistenceResult,
    attach_standard_artifact_summary,
    persist_standard_artifacts_from_task_output,
)
from app.tasks.legacy_standardization import append_legacy_standard_result
from app.tasks.molecule_scoring import append_molecule_scoring_artifacts
from app.tasks.output import extract_output_file_ids, prepare_task_output

logger = logging.getLogger(__name__)


def is_workflow_node_task(task: Any) -> bool:
    params = (task.inputs.params or {}) if getattr(task, "inputs", None) else {}
    return bool(params.get("workflow_run_id") and params.get("workflow_node_id"))


async def prepare_recovered_task_output(
    db,
    *,
    task,
    tool_version,
    output_result: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], StandardArtifactPersistenceResult | None]:
    """Normalize and persist standard artifacts for a recovered result.

    第三个返回值是标准产物持久化结果，调用方用它做领域回写（docs/26 H-16）——
    补回的结果和正常跑完的结果必须走同一套投影逻辑。
    """
    try:
        output_result = await append_molecule_scoring_artifacts(
            db,
            task,
            tool_version,
            output_result,
        )
    except Exception as exc:
        # Recovery must keep the original result even if optional scoring fails.
        logger.warning(
            "Recovered task %s molecule scoring failed: %s",
            task.id,
            exc,
        )

    output_result = await append_legacy_standard_result(
        db,
        task=task,
        tool_version_config=tool_version.config,
        output_result=output_result,
        output_file_ids=extract_output_file_ids(output_result),
    )
    prepared_output = prepare_task_output(output_result)
    standard_persistence = await persist_standard_artifacts_from_task_output(
        db,
        task=task,
        tool_version_config=tool_version.config,
        output_result=output_result,
        output_file_ids=prepared_output["file_ids"],
    )
    if standard_persistence is not None:
        prepared_output["result"] = attach_standard_artifact_summary(
            prepared_output["result"],
            standard_persistence,
        )
    return prepared_output, output_result, standard_persistence
