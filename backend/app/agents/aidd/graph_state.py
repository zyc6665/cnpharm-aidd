"""LangGraph state definitions for AIDD agent orchestration."""

from __future__ import annotations

from typing import Any, TypedDict


class AIDDGraphState(TypedDict, total=False):
    run_id: str
    project_id: str
    conversation_id: str
    protein_artifact_version_id: str
    user_id: str
    message: str
    input_file_id: str
    input_filename: str
    input_files: dict[str, dict[str, Any]]
    input_type: str
    requested_outputs: list[str]
    params: dict[str, Any]
    semantic_inputs: dict[str, dict[str, Any]]
    configured_tool_slugs: list[str]
    available_tools: list[dict[str, Any]]
    planning_prompt: str
    raw_plan: str
    plan: dict[str, Any]
    reasoning_summary: str | None
    analysis_trace: list[str]
    observations: list[dict[str, Any]]
    final_outputs: dict[str, Any]
    configured_tools: list[dict[str, Any]]
    status: str
    error: str | None
    model_service: Any
