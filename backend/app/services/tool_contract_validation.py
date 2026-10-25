"""Semantic validation for persisted ToolContract configuration."""

from __future__ import annotations

import re
from typing import Any

from app.artifact_standards.registry import (
    StandardArtifactRegistryError,
    validate_standard_artifact_roles,
)


SUPPORTED_TOOL_EXECUTOR_TYPES = {
    "docker_image",
    "python_script",
    "ssh_job",
    "k8s_job",
    "builtin",
}


def collect_tool_contract_config_validation_errors(
    *,
    tool_slug: str | None,
    config: Any,
    current_version_active: bool | None = True,
) -> list[str]:
    """Collect semantic ToolContract validation errors.

    Import-schema validation has already run before this point.
    """
    errors: list[str] = []

    if not isinstance(config, dict):
        return ["tool current version config must be an object"]

    executor_type = str(config.get("type") or "").strip()
    if not executor_type:
        errors.append("executor.type is required")
    elif executor_type not in SUPPORTED_TOOL_EXECUTOR_TYPES:
        supported = sorted(SUPPORTED_TOOL_EXECUTOR_TYPES)
        errors.append(f"executor.type must be one of {supported}")

    if executor_type == "k8s_job":
        runtime = config.get("runtime")
        image = runtime.get("image") if isinstance(runtime, dict) else None
        if not isinstance(image, str) or not re.search(r"@sha256:[a-fA-F0-9]{64}$", image):
            errors.append("k8s_job.runtime.image must use an immutable sha256 digest")
        profile_id = config.get("resource_profile")
        if not isinstance(profile_id, str) or not profile_id.strip():
            errors.append("k8s_job.resource_profile is required")
        else:
            from app.tasks.resource_profile import resolve_registered_resource_profile

            try:
                resolve_registered_resource_profile(profile_id)
            except ValueError:
                errors.append(
                    f"k8s_job.resource_profile is not registered: {profile_id}"
                )
        for platform_field in (
            "cluster_alias",
            "namespace",
            "credential_ref",
            "service_account",
            "token",
            "private_key",
            "password",
            "credentials",
        ):
            if platform_field in config:
                errors.append(
                    f"k8s_job.{platform_field} is platform-managed"
                )

    if current_version_active is not True:
        errors.append("current_version.is_active must be true")

    _collect_artifact_role_validation_errors(config, errors)

    raw_capability = config.get("agent_capability")
    if raw_capability is None:
        return errors
    if not isinstance(raw_capability, dict):
        errors.append("agent_capability must be an object when provided")
        return errors
    if raw_capability.get("enabled") is not True:
        return errors

    if not str(raw_capability.get("capability") or "").strip():
        errors.append(
            "agent_capability.capability is required when "
            "agent_capability.enabled=true"
        )
    if not str(raw_capability.get("stage") or "").strip():
        errors.append(
            "agent_capability.stage is required when "
            "agent_capability.enabled=true"
        )

    inputs = raw_capability.get("inputs")
    if not isinstance(inputs, list) or (
        not inputs and not _allows_parameter_only_capability(config)
    ):
        errors.append("agent_capability.inputs must include at least one item")
    else:
        for index, item in enumerate(inputs):
            input_path = f"agent_capability.inputs[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{input_path} must be an object")
                continue
            semantic_type = str(item.get("semantic_type") or "").strip()
            if not semantic_type:
                errors.append(f"{input_path}.semantic_type is required")

    outputs = raw_capability.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        errors.append(
            "agent_capability.outputs must include at least one item"
        )
    else:
        for index, item in enumerate(outputs):
            output_path = f"agent_capability.outputs[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{output_path} must be an object")
                continue
            semantic_type = str(item.get("semantic_type") or "").strip()
            if not semantic_type:
                errors.append(f"{output_path}.semantic_type is required")

            source = str(item.get("source") or "output_files").strip()
            if source not in {"output_files", "output_data", "artifact"}:
                errors.append(
                    f"{output_path}.source must be "
                    "output_files, output_data or artifact"
                )
            output_data_path = str(item.get("path") or "").strip()
            if source == "output_data" and not output_data_path:
                errors.append(
                    f"{output_path}.path is required for "
                    "output_data outputs"
                )

    return _dedupe_errors(errors)


def collect_tool_contract_validation_errors(tool: Any) -> list[str]:
    """Collect semantic validation errors for a persisted tool contract."""
    current_version = getattr(tool, "current_version", None)
    if current_version is None:
        return ["tool current_version is required"]

    return collect_tool_contract_config_validation_errors(
        tool_slug=getattr(tool, "slug", None),
        config=getattr(current_version, "config", None),
        current_version_active=getattr(current_version, "is_active", None),
    )


def _collect_artifact_role_validation_errors(
    config: dict[str, Any],
    errors: list[str],
) -> None:
    artifacts = config.get("artifacts")
    if not isinstance(artifacts, dict):
        return

    for direction, role_fields in (
        ("inputs", ("role_preferences", "required_roles")),
        ("outputs", ("provided_roles",)),
    ):
        slots = artifacts.get(direction)
        if not isinstance(slots, list):
            continue
        for index, slot in enumerate(slots):
            if not isinstance(slot, dict):
                continue
            artifact_type = str(slot.get("type") or "").strip()
            if not artifact_type:
                continue
            for role_field in role_fields:
                roles = slot.get(role_field)
                if not roles:
                    continue
                try:
                    validate_standard_artifact_roles(artifact_type, roles)
                except StandardArtifactRegistryError as exc:
                    errors.append(
                        f"artifacts.{direction}[{index}].{role_field}: {exc}"
                    )


def _allows_parameter_only_capability(config: dict[str, Any]) -> bool:
    """Allow data acquisition tools with schema parameters and no artifacts."""
    input_schema = config.get("input_schema")
    if not isinstance(input_schema, dict):
        return False
    properties = input_schema.get("properties")
    return isinstance(properties, dict) and bool(properties)


def _dedupe_errors(errors: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for error in errors:
        if error in seen:
            continue
        seen.add(error)
        ordered.append(error)
    return ordered
