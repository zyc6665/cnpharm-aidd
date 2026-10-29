"""Normalized tool contract serialization."""

from __future__ import annotations

from typing import Any

from app.artifact_standards.types import (
    is_supported_platform_artifact_type,
    normalize_platform_artifact_type,
)
from app.services.tool_contract_validation import (  # noqa: F401
    collect_tool_contract_config_validation_errors,
    collect_tool_contract_validation_errors,
)
from app.tool_packages.config_resolver import tool_package_manifest_data
from app.tool_packages.schemas import TOOL_PACKAGE_API_VERSION


TOOL_CONTRACT_VERSION = "1.0"

__all__ = [
    "TOOL_CONTRACT_VERSION",
    "build_tool_contract",
    "collect_tool_contract_config_validation_errors",
    "collect_tool_contract_validation_errors",
    "contract_emits_standard_artifacts",
    "tool_emits_standard_artifacts",
]


def build_tool_contract(
    tool: Any,
    *,
    capability: Any | None = None,
    tool_version: Any | None = None,
) -> dict[str, Any]:
    """Build the stable platform-facing contract for a persisted tool."""
    current_version = (
        tool_version
        if tool_version is not None
        else getattr(tool, "current_version", None)
    )
    package_manifest = _package_manifest_from_version(current_version)
    if isinstance(package_manifest, dict):
        return _build_tool_package_contract(tool, current_version, package_manifest)
    config = getattr(current_version, "config", None)
    if not isinstance(config, dict):
        config = {}
    artifacts = _artifacts_contract_for_tool(tool, config)

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
        "artifacts": artifacts,
        "capability": _capability_contract(
            tool_slug=str(getattr(tool, "slug", None) or ""),
            raw_capability=config.get("agent_capability"),
            capability=capability,
            artifacts=artifacts,
            virtual=False,
        ),
        "validation": {"status": "valid", "errors": []},
    }


def contract_emits_standard_artifacts(contract: dict[str, Any]) -> bool:
    """Return whether a normalized contract declares platform artifacts."""
    if not isinstance(contract, dict):
        return False

    artifacts = contract.get("artifacts")
    artifact_outputs = artifacts.get("outputs") if isinstance(artifacts, dict) else []
    for output in artifact_outputs or []:
        if not isinstance(output, dict):
            continue
        artifact_type = output.get("type")
        if artifact_type and is_supported_platform_artifact_type(str(artifact_type)):
            return True

    capability = contract.get("capability")
    capability_outputs = capability.get("outputs") if isinstance(capability, dict) else []
    for output in capability_outputs or []:
        if not isinstance(output, dict):
            continue
        if output.get("source") == "artifact":
            return True
        semantic_type = output.get("semantic_type")
        if semantic_type and is_supported_platform_artifact_type(str(semantic_type)):
            return True

    return False


def tool_emits_standard_artifacts(
    tool: Any,
    *,
    capability: Any | None = None,
    tool_version: Any | None = None,
) -> bool:
    """Return whether a persisted tool emits platform standard Artifacts."""
    return contract_emits_standard_artifacts(
        build_tool_contract(
            tool,
            capability=capability,
            tool_version=tool_version,
        )
    )


def _build_tool_package_contract(
    package: Any,
    current_version: Any,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Project a Tool Package manifest onto the stable contract shape."""
    if manifest.get("api_version") == TOOL_PACKAGE_API_VERSION:
        return _build_tool_package_manifest_contract(
            package, current_version, manifest
        )

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


def _build_tool_package_manifest_contract(
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
        "capability": _capability_from_manifest(metadata, inputs, outputs, exposure),
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
            tool_slug=str(slug or ""),
            raw_capability=None,
            capability=capability,
            artifacts={"inputs": [], "outputs": []},
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
    if isinstance(value, str) and value.strip():
        return {"id": value.strip()}
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


def _artifacts_contract_for_tool(tool: Any, config: dict[str, Any]) -> dict[str, Any]:
    contract = _artifacts_contract(config.get("artifacts"))
    slug = str(getattr(tool, "slug", None) or config.get("builtin_slug") or "")
    if slug != "lvpocket-pocket-prediction":
        return contract

    if not contract["inputs"]:
        contract["inputs"] = [
            {
                "name": "protein",
                "type": "protein_structure@1",
                "required": True,
                "role_preferences": ["prepared_pdb", "structure_file"],
                "readiness_policy": "prefer_prepared_warn_raw",
                "suggested_preparation_tool": "builtin-protein-preparation",
            }
        ]
    if not contract["outputs"]:
        contract["outputs"] = [
            {"name": "pocket", "type": "binding_pocket@1", "cardinality": "one", "required": True}
        ]
    return contract


def _package_manifest_from_version(current_version: Any | None) -> dict[str, Any] | None:
    manifest = getattr(current_version, "manifest", None)
    if isinstance(manifest, dict):
        return manifest
    config = getattr(current_version, "config", None)
    if not isinstance(config, dict):
        return None
    return tool_package_manifest_data(config)


def _artifact_input_slot(item: dict[str, Any]) -> dict[str, Any]:
    slot = {
        "name": item.get("name"),
        "type": _semantic_type(item.get("type")),
        "required": bool(item.get("required", True)),
    }
    if item.get("title"):
        slot["title"] = str(item.get("title"))
    if item.get("description"):
        slot["description"] = str(item.get("description"))
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
    slot = {
        "name": item.get("name"),
        "type": _semantic_type(item.get("type")),
        "cardinality": item.get("cardinality") or "one",
        "required": bool(item.get("required", True)),
    }
    provided_roles = _string_list(item.get("provided_roles"))
    if provided_roles:
        slot["provided_roles"] = provided_roles
    return slot


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


def _capability_from_manifest(
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
    tool_slug: str,
    raw_capability: Any,
    capability: Any | None,
    artifacts: dict[str, Any],
    virtual: bool,
) -> dict[str, Any]:
    if capability is not None:
        return _capability_object_contract(capability, virtual=virtual)

    if not isinstance(raw_capability, dict) or raw_capability.get("enabled") is not True:
        artifact_capability = _capability_from_artifact_contract(tool_slug, artifacts)
        if artifact_capability is not None:
            return artifact_capability
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


def _capability_from_artifact_contract(
    tool_slug: str,
    artifacts: dict[str, Any],
) -> dict[str, Any] | None:
    inputs = [item for item in artifacts.get("inputs", []) if isinstance(item, dict)]
    outputs = [
        item
        for item in artifacts.get("outputs", [])
        if isinstance(item, dict)
        and item.get("type")
        and is_supported_platform_artifact_type(str(item["type"]))
    ]
    if not outputs:
        return None

    capability_name, stage = _artifact_only_capability_identity(tool_slug)
    return {
        "enabled": True,
        "capability": capability_name,
        "stage": stage,
        "inputs": [
            {
                "semantic_type": item.get("type"),
                "field": item.get("name") or item.get("type"),
                "required": bool(item.get("required", True)),
                "accepted_extensions": [],
            }
            for item in inputs
            if item.get("type")
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


def _artifact_only_capability_identity(tool_slug: str) -> tuple[str, str]:
    if tool_slug == "lvpocket-pocket-prediction":
        return "pocket_prediction", "pocket_exploration"
    return tool_slug or "artifact_workflow_tool", tool_slug or "artifact_workflow"


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
