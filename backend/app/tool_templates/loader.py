"""Load static tool templates and project them into existing tool configs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from app.tool_templates.schemas import (
    SUPPORTED_TEMPLATE_EXECUTOR_TYPES,
    DrugDiscoveryToolTemplate,
)


class ToolTemplateLoadError(ValueError):
    """Raised when a static tool template cannot be loaded or applied."""


TEMPLATE_ROOT = Path(__file__).resolve().parent


def load_tool_template(template_key: str, *, family: str = "drug_discovery") -> DrugDiscoveryToolTemplate:
    """Load one template by key from a template family directory."""
    _validate_family(family)
    _validate_template_key(template_key)
    path = TEMPLATE_ROOT / family / f"{template_key}.yaml"
    if not path.is_file():
        raise ToolTemplateLoadError(f"tool template not found: {family}/{template_key}")
    return _read_template_file(path)


def load_tool_templates(family: str = "drug_discovery") -> list[DrugDiscoveryToolTemplate]:
    """Load all templates for a family in deterministic key order."""
    _validate_family(family)
    directory = TEMPLATE_ROOT / family
    if not directory.is_dir():
        raise ToolTemplateLoadError(f"tool template family not found: {family}")

    templates = [_read_template_file(path) for path in sorted(directory.glob("*.yaml"))]
    seen: set[str] = set()
    for template in templates:
        key = template.metadata.template_key
        if key in seen:
            raise ToolTemplateLoadError(f"duplicate tool template key: {key}")
        seen.add(key)
    return templates


def build_tool_import_config_from_template(
    template: DrugDiscoveryToolTemplate,
    *,
    executor_type: str,
    executor_config: dict[str, Any],
) -> dict[str, Any]:
    """Build current platform tool import config from a static template."""
    if executor_type not in SUPPORTED_TEMPLATE_EXECUTOR_TYPES:
        raise ToolTemplateLoadError(f"unsupported executor type for tool template: {executor_type}")
    if executor_type not in template.executor_types:
        raise ToolTemplateLoadError(
            f"executor {executor_type} is not supported by template {template.metadata.template_key}"
        )
    if not isinstance(executor_config, dict):
        raise ToolTemplateLoadError("executor_config must be an object")

    timeout_sec = int(template.resource_profile.timeout_minutes * 60)
    gpu_memory_mb = int(template.resource_profile.gpu_memory_gb * 1024)
    tool_config = {
        **executor_config,
        "type": executor_type,
        "input_schema": template.input_schema,
        "output_schema": template.output_schema,
        "agent_capability": template.agent_capability.model_dump(mode="json"),
        "resource_profile": template.resource_profile.model_dump(mode="json"),
        "template_key": template.metadata.template_key,
        "tool_family": template.metadata.family,
        "smoke_test": template.smoke_test.model_dump(mode="json"),
        "sample_inputs": [sample.model_dump(mode="json") for sample in template.sample_inputs],
    }
    tool_config.setdefault("timeout_sec", timeout_sec)

    return {
        "name": template.metadata.name,
        "slug": template.metadata.slug,
        "version": template.metadata.version,
        "description": template.metadata.description,
        "gpu_required": template.resource_profile.gpu_required,
        "gpu_memory_mb": gpu_memory_mb,
        "timeout_sec": timeout_sec,
        "tool_config": tool_config,
    }


def _read_template_file(path: Path) -> DrugDiscoveryToolTemplate:
    raw = _read_yaml_object(path)
    try:
        return DrugDiscoveryToolTemplate.model_validate(raw)
    except ValidationError as exc:
        raise ToolTemplateLoadError(f"{path.name} does not match tool template schema: {exc}") from exc


def _read_yaml_object(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ToolTemplateLoadError(f"failed to read tool template {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise ToolTemplateLoadError(f"{path.name} top level must be an object")
    return value


def _validate_family(value: str) -> None:
    if value != "drug_discovery":
        raise ToolTemplateLoadError(f"unsupported tool template family: {value}")


def _validate_template_key(value: str) -> None:
    if not value or "/" in value or ".." in value:
        raise ToolTemplateLoadError("template_key must be a plain filename key")
