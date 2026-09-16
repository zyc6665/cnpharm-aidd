"""Remote tool input protocol helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.artifact_standards.registry import get_standard_artifact_spec, parse_standard_ref


class RemoteToolInputError(ValueError):
    """Remote tool input payload cannot be built from the supplied data."""


def remote_example_input_refs(extra_data: Any) -> dict[str, Any]:
    data = extra_data if isinstance(extra_data, dict) else {}
    inputs = data.get("remote_example_inputs")
    return dict(inputs) if isinstance(inputs, dict) else {}


def standard_input_bindings(extra_data: Any) -> dict[str, str]:
    data = extra_data if isinstance(extra_data, dict) else {}
    bindings = data.get("input_bindings")
    if not isinstance(bindings, dict):
        return {}
    return {
        str(input_name): str(version_id)
        for input_name, version_id in bindings.items()
        if str(input_name).strip() and str(version_id).strip()
    }


def remote_artifact_input_declarations(config: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = config.get("artifacts") if isinstance(config, dict) else None
    raw_inputs = artifacts.get("inputs") if isinstance(artifacts, dict) else None
    if not isinstance(raw_inputs, list):
        return []
    return [item for item in raw_inputs if isinstance(item, dict)]


def artifact_version_ref(version: Any) -> str:
    artifact = getattr(version, "artifact", None)
    standard_type = getattr(artifact, "standard_type", None)
    standard_version = getattr(artifact, "standard_version", None)
    if standard_type and standard_version:
        return parse_standard_ref(f"{standard_type}@{standard_version}").ref

    manifest = getattr(version, "manifest_json", None)
    manifest = manifest if isinstance(manifest, dict) else {}
    manifest_type = manifest.get("type")
    if manifest_type:
        return parse_standard_ref(str(manifest_type)).ref
    raise RemoteToolInputError(
        f"ArtifactVersion {getattr(version, 'id', '')} is not a standard ArtifactVersion"
    )


def validate_remote_artifact_input(declaration: dict[str, Any], version: Any) -> None:
    input_name = str(declaration.get("name") or "")
    expected_ref = str(declaration.get("type") or "")
    actual_ref = artifact_version_ref(version)
    if actual_ref != parse_standard_ref(expected_ref).ref:
        raise RemoteToolInputError(
            f"Input {input_name} expects {expected_ref}, got {actual_ref}"
        )

    spec = get_standard_artifact_spec(expected_ref)
    available_roles = {file_link.role for file_link in version.files}
    missing_roles = [
        role.role
        for role in spec.file_roles
        if role.required and role.role not in available_roles
    ]
    if missing_roles:
        raise RemoteToolInputError(
            f"Input {input_name} missing required file roles: " + ", ".join(missing_roles)
        )


def remote_artifact_input_payload(
    *,
    declaration: dict[str, Any],
    version: Any,
    file_payload: Callable[[Any], dict[str, Any]],
) -> dict[str, Any]:
    files: dict[str, dict[str, Any]] = {}
    for file_link in sorted(version.files, key=lambda item: item.sort_order):
        file_record = file_link.file
        if file_record is None:
            raise RemoteToolInputError(
                f"Input {declaration.get('name')} role {file_link.role} has no file record"
            )
        files[str(file_link.role)] = file_payload(file_record)

    manifest = version.manifest_json if isinstance(version.manifest_json, dict) else {}
    metadata = manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {}
    return {
        "artifact_version_id": str(version.id),
        "type": str(declaration.get("type") or artifact_version_ref(version)),
        "files": files,
        "metadata": dict(metadata),
    }
