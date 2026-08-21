"""Normalized tool contract serialization."""

from __future__ import annotations

from typing import Any

from app.artifact_standards.types import normalize_platform_artifact_type


TOOL_CONTRACT_VERSION = "1.0"
SUPPORTED_TOOL_EXECUTOR_TYPES = {"remote_api", "docker_image", "python_script", "ssh_job", "builtin"}


def build_tool_contract(tool: Any, *, capability: Any | None = None) -> dict[str, Any]:
    """Build the stable platform-facing contract for a persisted tool."""
    current_version = getattr(tool, "current_version", None)
    package_manifest = _package_manifest_from_version(current_version)
    if isinstance(package_manifest, dict):
        return _build_tool_package_contract(tool, current_version, package_manifest)
    config = getattr(current_version, "config", None)
    if not isinstance(config, dict):
        config = {}

    return {
        "contract_version": TOOL_CONTRACT_VERSION,
        "id": getattr(tool, "id", None),
        "slug": getattr(tool, "slug", None),
        "name": getattr(tool, "name", None),
        "description": getattr(tool, "description", None),
        "status": getattr(tool, "status", None),
        "is_public": getattr(tool, "is_public", None),
        "version": _version_contract(current_version),
        "executor": _executor_contract(tool, config),
        "resource_profile": _resource_profile_contract(config.get("resource_profile")),
        "schema": {
            "input": _schema_object(config.get("input_schema")),
            "output": _schema_object(config.get("output_schema")),
        },
        "artifacts": _artifacts_contract(config.get("artifacts")),
        "capability": _capability_contract(
            raw_capability=config.get("agent_capability"),
            capability=capability,
            virtual=False,
        ),
        "validation": {"status": "valid", "errors": []},
    }


def _build_tool_package_contract(
    package: Any,
    current_version: Any,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Project a Tool Package manifest onto the stable contract shape."""
    if manifest.get("api_version") == "aidd.sciminer/tool-package.v2":
        return _build_tool_package_v2_contract(package, current_version, manifest)

    metadata = manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {}
    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), dict) else {}
    variants = [item for item in manifest.get("variants", []) if isinstance(item, dict)]
    inputs = [item for item in artifacts.get("inputs", []) if isinstance(item, dict)]
    outputs = [item for item in artifacts.get("outputs", []) if isinstance(item, dict)]
    validation_errors = list(getattr(current_version, "validation_errors", None) or [])
    validation_status = getattr(current_version, "validation_status", None)
    return {
        "contract_version": TOOL_CONTRACT_VERSION,
        "id": getattr(package, "id", None),
        "slug": getattr(package, "slug", None) or metadata.get("slug"),
        "name": getattr(package, "name", None) or metadata.get("name"),
        "description": getattr(package, "description", None) or metadata.get("description"),
        "status": getattr(package, "status", None),
        "is_public": getattr(package, "status", None) == "published",
        "version": {
            "id": getattr(current_version, "id", None),
            "version": getattr(current_version, "version", None) or metadata.get("version"),
            "is_active": True,
            "deprecated": False,
        },
        "executor": {
            "type": "tool_package",
            "timeout_sec": None,
        },
        "resource_profile": {},
        "schema": {"input": {}, "output": {}},
        "capability": {
            "enabled": True,
            "capability": metadata.get("slug"),
            "stage": None,
            "inputs": [
                {
                    "semantic_type": item.get("semantic_type"),
                    "field": item.get("name"),
                    "required": bool(item.get("required", True)),
                    "accepted_extensions": [],
                }
                for item in inputs
                if item.get("semantic_type")
            ],
            "outputs": [
                {
                    "semantic_type": item.get("semantic_type"),
                    "source": "artifact",
                    "match": {"artifact_type": item.get("artifact_type")},
                    "path": None,
                    "required": bool(item.get("required", True)),
                }
                for item in outputs
                if item.get("semantic_type")
            ],
            "defaults": {},
            "virtual": False,
        },
        "package": {
            "api_version": manifest.get("api_version"),
            "kind": manifest.get("kind"),
        },
        "variants": variants,
        "validation": {
            "status": "valid" if validation_status == "valid" and not validation_errors else "invalid",
            "errors": validation_errors,
        },
    }


def _build_tool_package_v2_contract(
    package: Any,
    current_version: Any,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    metadata = manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {}
    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), dict) else {}
    variants = [item for item in manifest.get("variants", []) if isinstance(item, dict)]
    inputs = [item for item in artifacts.get("inputs", []) if isinstance(item, dict)]
    outputs = [item for item in artifacts.get("outputs", []) if isinstance(item, dict)]
    exposure = _exposure_contract(manifest.get("exposure"))
    validation_errors = list(getattr(current_version, "validation_errors", None) or [])
    validation_status = getattr(current_version, "validation_status", None)
    return {
        "contract_version": TOOL_CONTRACT_VERSION,
        "id": getattr(package, "id", None),
        "slug": getattr(package, "slug", None) or metadata.get("slug"),
        "name": getattr(package, "name", None) or metadata.get("name"),
        "description": getattr(package, "description", None) or metadata.get("description"),
        "status": getattr(package, "status", None),
        "is_public": _is_public_package_or_tool(package),
        "version": {
            "id": getattr(current_version, "id", None),
            "version": getattr(current_version, "version", None) or metadata.get("version"),
            "is_active": getattr(current_version, "is_active", True),
            "deprecated": getattr(current_version, "deprecated", False),
        },
        "executor": {
            "type": "tool_package",
            "timeout_sec": None,
        },
        "resource_profile": {},
        "schema": {"input": _schema_object(manifest.get("parameters_schema")), "output": {}},
        "artifacts": {
            "inputs": [_artifact_input_slot(item) for item in inputs],
            "outputs": [_artifact_output_slot(item) for item in outputs],
        },
        "exposure": exposure,
        "capability": _capability_from_v2_manifest(metadata, inputs, outputs, exposure),
        "package": {
            "api_version": manifest.get("api_version"),
            "kind": manifest.get("kind"),
        },
        "variants": variants,
        "validation": {
            "status": "valid" if _version_valid(validation_status, validation_errors) else "invalid",
            "errors": validation_errors,
        },
    }


def build_virtual_tool_contract(capability: Any) -> dict[str, Any]:
    """Build a contract for an Agent-only virtual tool."""
    slug = getattr(capability, "tool_slug", None)
    return {
        "contract_version": TOOL_CONTRACT_VERSION,
        "id": None,
        "slug": slug,
        "name": slug,
        "description": None,
        "status": "virtual",
        "is_public": True,
        "version": None,
        "executor": {"type": "builtin", "timeout_sec": None},
        "resource_profile": {},
        "schema": {"input": {}, "output": {}},
        "capability": _capability_contract(
            raw_capability=None,
            capability=capability,
            virtual=True,
        ),
        "validation": {"status": "valid", "errors": []},
    }


def tool_contract_to_agent_summary(contract: dict[str, Any]) -> dict[str, Any]:
    """Convert a ToolContract into the current planner-facing Agent summary."""
    capability = contract.get("capability") if isinstance(contract.get("capability"), dict) else {}
    tool_version = contract.get("version") if isinstance(contract.get("version"), dict) else None
    artifacts = contract.get("artifacts") if isinstance(contract.get("artifacts"), dict) else {}
    slug = str(contract.get("slug") or "")
    return {
        "id": contract.get("id"),
        "slug": slug,
        "tool_slug": slug,
        "name": contract.get("name") or slug,
        "contract_version": contract.get("contract_version"),
        "tool_version": tool_version,
        "capability": capability.get("capability"),
        "stage": capability.get("stage"),
        "input_bindings": list(capability.get("inputs") or []),
        "output_rules": list(capability.get("outputs") or []),
        "inputs": [
            item.get("semantic_type")
            for item in capability.get("inputs", [])
            if isinstance(item, dict) and item.get("semantic_type")
        ],
        "outputs": [
            item.get("semantic_type")
            for item in capability.get("outputs", [])
            if isinstance(item, dict) and item.get("semantic_type")
        ],
        "defaults": dict(capability.get("defaults") or {}),
        "virtual": bool(capability.get("virtual")),
        "artifacts": artifacts,
        "artifact_inputs": list(artifacts.get("inputs") or []),
        "artifact_outputs": list(artifacts.get("outputs") or []),
        "exposure": dict(contract.get("exposure") or {}),
        "executor": contract.get("executor") or {},
        "resource_profile": dict(contract.get("resource_profile") or {}),
        "validation": contract.get("validation") or {},
    }


def collect_tool_contract_config_validation_errors(
    *,
    tool_slug: str | None,
    config: Any,
    current_version_active: bool | None = True,
) -> list[str]:
    """Collect semantic ToolContract validation errors beyond import-schema checks."""
    errors: list[str] = []

    if not isinstance(config, dict):
        return ["tool current version config must be an object"]

    executor_type = str(config.get("type") or "").strip()
    if not executor_type:
        errors.append("executor.type is required")
    elif executor_type not in SUPPORTED_TOOL_EXECUTOR_TYPES:
        errors.append(
            f"executor.type must be one of {sorted(SUPPORTED_TOOL_EXECUTOR_TYPES)}"
        )

    if current_version_active is not True:
        errors.append("current_version.is_active must be true")

    raw_capability = config.get("agent_capability")
    if raw_capability is None:
        return errors
    if not isinstance(raw_capability, dict):
        errors.append("agent_capability must be an object when provided")
        return errors
    if raw_capability.get("enabled") is not True:
        return errors

    if not str(raw_capability.get("capability") or "").strip():
        errors.append("agent_capability.capability is required when agent_capability.enabled=true")
    if not str(raw_capability.get("stage") or "").strip():
        errors.append("agent_capability.stage is required when agent_capability.enabled=true")

    inputs = raw_capability.get("inputs")
    if not isinstance(inputs, list) or (not inputs and not _allows_parameter_only_capability(config)):
        errors.append("agent_capability.inputs must include at least one item")
    else:
        for index, item in enumerate(inputs):
            if not isinstance(item, dict):
                errors.append(f"agent_capability.inputs[{index}] must be an object")
                continue
            semantic_type = str(item.get("semantic_type") or "").strip()
            if not semantic_type:
                errors.append(f"agent_capability.inputs[{index}].semantic_type is required")

    outputs = raw_capability.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        errors.append("agent_capability.outputs must include at least one item")
    else:
        for index, item in enumerate(outputs):
            if not isinstance(item, dict):
                errors.append(f"agent_capability.outputs[{index}] must be an object")
                continue
            semantic_type = str(item.get("semantic_type") or "").strip()
            if not semantic_type:
                errors.append(f"agent_capability.outputs[{index}].semantic_type is required")

            source = str(item.get("source") or "output_files").strip()
            if source not in {"output_files", "output_data", "artifact"}:
                errors.append(
                    f"agent_capability.outputs[{index}].source must be output_files, output_data or artifact"
                )
            if source == "output_data" and not str(item.get("path") or "").strip():
                errors.append(
                    f"agent_capability.outputs[{index}].path is required for output_data outputs"
                )

    return _dedupe_errors(errors)


def _allows_parameter_only_capability(config: dict[str, Any]) -> bool:
    """Allow data acquisition tools that consume only schema parameters, not artifacts."""
    input_schema = config.get("input_schema")
    if not isinstance(input_schema, dict):
        return False
    properties = input_schema.get("properties")
    return isinstance(properties, dict) and bool(properties)


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


def _version_contract(current_version: Any | None) -> dict[str, Any] | None:
    if current_version is None:
        return None
    return {
        "id": getattr(current_version, "id", None),
        "version": getattr(current_version, "version", None),
        "is_active": getattr(current_version, "is_active", None),
        "deprecated": getattr(current_version, "deprecated", None),
    }


def _executor_contract(tool: Any, config: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": str(config.get("type") or ""),
        "timeout_sec": config.get("timeout_sec", getattr(tool, "timeout_sec", None)),
    }


def _resource_profile_contract(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _schema_object(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _artifacts_contract(value: Any) -> dict[str, Any]:
    artifacts = value if isinstance(value, dict) else {}
    inputs = [item for item in artifacts.get("inputs", []) if isinstance(item, dict)]
    outputs = [item for item in artifacts.get("outputs", []) if isinstance(item, dict)]
    return {
        "inputs": [_artifact_input_slot(item) for item in inputs],
        "outputs": [_artifact_output_slot(item) for item in outputs],
    }


def _package_manifest_from_version(current_version: Any | None) -> dict[str, Any] | None:
    manifest = getattr(current_version, "manifest", None)
    if isinstance(manifest, dict):
        return manifest
    config = getattr(current_version, "config", None)
    if not isinstance(config, dict):
        return None
    manifest = config.get("tool_package_manifest")
    tool_package_config = config.get("tool_package")
    if not isinstance(manifest, dict) and isinstance(tool_package_config, dict):
        manifest = tool_package_config.get("manifest")
    return manifest if isinstance(manifest, dict) else None


def _artifact_input_slot(item: dict[str, Any]) -> dict[str, Any]:
    slot = {
        "name": item.get("name"),
        "type": item.get("type"),
        "required": bool(item.get("required", True)),
    }
    if "role_preferences" in item:
        slot["role_preferences"] = _string_list(item.get("role_preferences"))
    if "required_roles" in item:
        slot["required_roles"] = _string_list(item.get("required_roles"))
    if item.get("readiness_policy"):
        slot["readiness_policy"] = str(item.get("readiness_policy"))
    if item.get("suggested_preparation_tool"):
        slot["suggested_preparation_tool"] = str(item.get("suggested_preparation_tool"))
    return slot


def _artifact_output_slot(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": item.get("name"),
        "type": item.get("type"),
        "cardinality": item.get("cardinality") or "one",
        "required": bool(item.get("required", True)),
    }


def _exposure_contract(value: Any) -> dict[str, bool]:
    raw = value if isinstance(value, dict) else {}
    return {
        "agent": bool(raw.get("agent", True)),
        "workflow": bool(raw.get("workflow", True)),
        "direct_run": bool(raw.get("direct_run", True)),
    }


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _capability_from_v2_manifest(
    metadata: dict[str, Any],
    inputs: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    exposure: dict[str, bool],
) -> dict[str, Any]:
    return {
        "enabled": bool(exposure.get("agent", True)),
        "capability": metadata.get("slug"),
        "stage": metadata.get("slug"),
        "inputs": [
            {
                "semantic_type": item.get("type"),
                "field": item.get("name"),
                "required": bool(item.get("required", True)),
                "accepted_extensions": [],
            }
            for item in inputs
            if item.get("type") and item.get("name")
        ],
        "outputs": [
            {
                "semantic_type": item.get("type"),
                "source": "artifact",
                "match": {"type": item.get("type")},
                "path": item.get("name"),
                "required": bool(item.get("required", True)),
            }
            for item in outputs
            if item.get("type")
        ],
        "defaults": {},
        "virtual": False,
    }


def _is_public_package_or_tool(package: Any) -> bool | None:
    is_public = getattr(package, "is_public", None)
    if is_public is not None:
        return is_public
    status = getattr(package, "status", None)
    if status is None:
        return None
    return status == "published"


def _version_valid(validation_status: Any, validation_errors: list[Any]) -> bool:
    return validation_status in {None, "valid"} and not validation_errors


def _capability_contract(
    *,
    raw_capability: Any,
    capability: Any | None,
    virtual: bool,
) -> dict[str, Any]:
    if capability is not None:
        return _capability_object_contract(capability, virtual=virtual)

    if not isinstance(raw_capability, dict) or raw_capability.get("enabled") is not True:
        return {
            "enabled": False,
            "capability": None,
            "stage": None,
            "inputs": [],
            "outputs": [],
            "defaults": {},
            "virtual": virtual,
        }

    return {
        "enabled": True,
        "capability": raw_capability.get("capability"),
        "stage": raw_capability.get("stage"),
        "inputs": [
            _capability_input_contract(item)
            for item in raw_capability.get("inputs", [])
            if isinstance(item, dict) and item.get("semantic_type")
        ],
        "outputs": [
            _capability_output_contract(item)
            for item in raw_capability.get("outputs", [])
            if isinstance(item, dict) and item.get("semantic_type")
        ],
        "defaults": dict(raw_capability.get("defaults") or {}),
        "virtual": virtual,
    }


def _capability_object_contract(capability: Any, *, virtual: bool) -> dict[str, Any]:
    return {
        "enabled": True,
        "capability": getattr(capability, "capability", None),
        "stage": getattr(capability, "stage", None),
        "inputs": [
            {
                "semantic_type": _semantic_type(getattr(item, "semantic_type", None)),
                "field": getattr(item, "field", None),
                "required": getattr(item, "required", True),
                "accepted_extensions": list(getattr(item, "accepted_extensions", ()) or ()),
            }
            for item in getattr(capability, "inputs", ()) or ()
        ],
        "outputs": [
            {
                "semantic_type": _semantic_type(getattr(item, "semantic_type", None)),
                "source": getattr(item, "source", None),
                "match": _output_match_contract(getattr(item, "match", None)),
                "path": getattr(item, "path", None),
                "required": getattr(item, "required", True),
            }
            for item in getattr(capability, "outputs", ()) or ()
        ],
        "defaults": dict(getattr(capability, "defaults", {}) or {}),
        "virtual": virtual,
    }


def _capability_input_contract(item: dict[str, Any]) -> dict[str, Any]:
    semantic_type = _semantic_type(item.get("semantic_type"))
    return {
        "semantic_type": semantic_type,
        "field": item.get("field") or semantic_type,
        "required": bool(item.get("required", True)),
        "accepted_extensions": list(item.get("accepted_extensions") or []),
    }


def _capability_output_contract(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "semantic_type": _semantic_type(item.get("semantic_type")),
        "source": item.get("source") or "output_files",
        "match": _schema_object(item.get("match")),
        "path": item.get("path"),
        "required": bool(item.get("required", True)),
    }


def _output_match_contract(match: Any | None) -> dict[str, Any] | None:
    if match is None:
        return None
    return {
        "extension": getattr(match, "extension", None),
        "filename_contains_any": list(getattr(match, "filename_contains_any", ()) or ()),
        "content_type": getattr(match, "content_type", None),
    }


def _semantic_type(value: Any) -> str | None:
    if value is None:
        return None
    return normalize_platform_artifact_type(str(value))


def _dedupe_errors(errors: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for error in errors:
        if error in seen:
            continue
        seen.add(error)
        ordered.append(error)
    return ordered
