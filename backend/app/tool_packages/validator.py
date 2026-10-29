"""Cross-file and platform policy validation for Tool Packages."""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterator, Sequence

from pydantic import BaseModel, Field

from app.artifact_standards.registry import is_standard_artifact_ref
from app.tool_packages.loader import ToolPackageLoadError, load_tool_package
from app.tool_packages.schemas import (
    Accelerator,
    AnyToolPackageManifest,
    LegacyToolPackageManifest,
    ToolPackageManifest,
    ValidationStatus,
)


_IMAGE_DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_PLATFORM_PARAMETER_NAMES = {
    "base_url",
    "command",
    "cpu",
    "devices",
    "endpoint",
    "entrypoint",
    "gpu_device",
    "gpu_memory_mb",
    "gpu_required",
    "memory_mb",
    "resource_profile",
    "resources",
    "script",
    "script_content",
    "script_path",
    "timeout_sec",
    "worker_id",
    "worker_queue",
}
_CREDENTIAL_PARAMETER_NAMES = {
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "credentials",
    "credential_ref",
    "headers",
    "password",
    "password_ref",
    "private_key",
    "secret",
    "secret_ref",
    "token",
}


class ToolPackageValidationResult(BaseModel):
    is_valid: bool
    errors: list[str] = Field(default_factory=list)


def validate_tool_package(manifest: AnyToolPackageManifest) -> ToolPackageValidationResult:
    if isinstance(manifest, LegacyToolPackageManifest):
        return _validate_tool_package_v1(manifest)
    return _validate_tool_package_spec(manifest)


def _validate_tool_package_v1(manifest: LegacyToolPackageManifest) -> ToolPackageValidationResult:
    errors: list[str] = []
    declared_inputs = {item.artifact_type for item in manifest.artifacts.inputs}
    declared_outputs = {item.artifact_type for item in manifest.artifacts.outputs}

    if not manifest.artifacts.inputs:
        errors.append("artifacts.inputs 必须声明至少一个语义输入")
    if not manifest.artifacts.outputs:
        errors.append("artifacts.outputs 必须声明至少一个语义输出")

    expected_outputs: tuple[str, ...] | None = None
    for variant in manifest.variants:
        for artifact_type in variant.inputs:
            if artifact_type not in declared_inputs:
                errors.append(f"变体 {variant.name} 引用了未声明的输入 Artifact 类型 {artifact_type}")
        for artifact_type in variant.outputs:
            if artifact_type not in declared_outputs:
                errors.append(f"变体 {variant.name} 引用了未声明的输出 Artifact 类型 {artifact_type}")

        output_contract = tuple(sorted(variant.outputs))
        if expected_outputs is None:
            expected_outputs = output_contract
        elif output_contract != expected_outputs:
            errors.append("所有运行变体必须提供一致的输出契约")

        if variant.accelerator == Accelerator.NVIDIA_CUDA:
            if not variant.resources.devices:
                errors.append(f"NVIDIA 变体 {variant.name} 必须声明 resources.devices")
            if not variant.resources.driver:
                errors.append(f"NVIDIA 变体 {variant.name} 必须声明 resources.driver")

        if (
            variant.accelerator == Accelerator.HAIGUANG_DCU
            and not variant.hardware_validated
            and variant.validation_status
            != ValidationStatus.ADAPTED_PENDING_HARDWARE_VALIDATION
        ):
            errors.append(
                f"DCU 变体 {variant.name} 未真机验证时必须使用 "
                "adapted_pending_hardware_validation"
            )

    return ToolPackageValidationResult(is_valid=not errors, errors=_dedupe(errors))


def _validate_tool_package_spec(manifest: ToolPackageManifest) -> ToolPackageValidationResult:
    errors: list[str] = []
    declared_inputs = {item.name for item in manifest.artifacts.inputs}
    declared_outputs = {item.name for item in manifest.artifacts.outputs}

    if not manifest.artifacts.inputs:
        errors.append("artifacts.inputs 必须声明至少一个标准输入")
    if not manifest.artifacts.outputs:
        errors.append("artifacts.outputs 必须声明至少一个标准输出")

    for item in [*manifest.artifacts.inputs, *manifest.artifacts.outputs]:
        if not is_standard_artifact_ref(item.type):
            errors.append(f"standard artifact type is unknown: {item.type}")

    parameter_schema = manifest.parameters_schema or {}
    for path in _undefined_required_parameter_paths(parameter_schema):
        errors.append(f"parameters_schema.{path} is required but has no property definition")
    required = parameter_schema.get("required", [])
    if isinstance(required, list) and "device" in required:
        errors.append(
            "parameters_schema.device belongs in variant execution context, "
            "not required business parameters"
        )
    for path, name, property_schema in _parameter_schema_fields(parameter_schema):
        normalized_name = name.strip().lower().replace("-", "_")
        if normalized_name in _PLATFORM_PARAMETER_NAMES:
            errors.append(
                f"parameters_schema.{path} belongs in variant execution context, "
                "not business parameters"
            )
        elif normalized_name in _CREDENTIAL_PARAMETER_NAMES:
            errors.append(
                f"parameters_schema.{path} must not collect credentials as task parameters"
            )
        if property_schema and property_schema.get("format") in {"file", "uri", "password"}:
            errors.append(
                f"parameters_schema.{path} uses a file or credential field format; "
                "declare standard Artifact inputs or platform credentials instead"
            )

    for adapter_input in manifest.adapter.input:
        if adapter_input.input not in declared_inputs:
            errors.append(f"adapter.input references unknown input: {adapter_input.input}")
    for adapter_output in manifest.adapter.output:
        if adapter_output.output not in declared_outputs:
            errors.append(f"adapter.output references unknown output: {adapter_output.output}")

    _validate_runtime_env(manifest, errors)

    for variant in manifest.variants:
        if variant.accelerator == Accelerator.NVIDIA_CUDA:
            if not variant.resources.devices:
                errors.append(f"NVIDIA 变体 {variant.name} 必须声明 resources.devices")
            if not variant.resources.driver:
                errors.append(f"NVIDIA 变体 {variant.name} 必须声明 resources.driver")

        if (
            variant.accelerator == Accelerator.HAIGUANG_DCU
            and not variant.hardware_validated
            and variant.validation_status
            != ValidationStatus.ADAPTED_PENDING_HARDWARE_VALIDATION
        ):
            errors.append(
                f"DCU 变体 {variant.name} 未真机验证时必须使用 "
                "adapted_pending_hardware_validation"
            )

    return ToolPackageValidationResult(is_valid=not errors, errors=_dedupe(errors))


def _validate_runtime_env(manifest: ToolPackageManifest, errors: list[str]) -> None:
    runtime = manifest.runtime
    primary = runtime.artifacts.primary
    fallback = runtime.artifacts.fallback

    if primary.kind != "container":
        errors.append("runtime.artifacts.primary.kind must be container")
    if not primary.image:
        errors.append("runtime.artifacts.primary.image is required")
    if not primary.image_digest or not _IMAGE_DIGEST_RE.fullmatch(primary.image_digest):
        errors.append("runtime.artifacts.primary.image_digest must be sha256:<64 hex>")

    if fallback.kind not in {"conda_pack", "venv_pack"}:
        errors.append("runtime.artifacts.fallback.kind must be conda_pack or venv_pack")
    if not fallback.uri:
        errors.append("runtime.artifacts.fallback.uri is required")
    if not fallback.sha256 or not _SHA256_RE.fullmatch(fallback.sha256):
        errors.append("runtime.artifacts.fallback.sha256 must be 64 hex")

    weights = runtime.weights
    if not weights.manifest_uri and not weights.mounts:
        errors.append("runtime.weights requires either manifest_uri or mounts")
    if weights.manifest_uri and (
        not weights.manifest_sha256 or not _SHA256_RE.fullmatch(weights.manifest_sha256)
    ):
        errors.append("runtime.weights.manifest_sha256 must be 64 hex")

    cache_policy = runtime.cache_policy
    if not cache_policy.mutable_host_paths_forbidden:
        errors.append("runtime.cache_policy.mutable_host_paths_forbidden must be true")
    required_cache_keys = {
        "runtime.artifacts.selected.digest_or_sha256",
        "runtime.weights.manifest_sha256",
    }
    missing_cache_keys = required_cache_keys - set(cache_policy.key_fields)
    for key in sorted(missing_cache_keys):
        errors.append(f"runtime.cache_policy.key_fields must include {key}")


def _dedupe(errors: list[str]) -> list[str]:
    return list(dict.fromkeys(errors))


def _parameter_schema_fields(
    schema: dict[str, object],
    parent: str = "",
) -> Iterator[tuple[str, str, dict[str, object] | None]]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return

    for raw_name, raw_property in properties.items():
        name = str(raw_name)
        path = f"{parent}.{name}" if parent else name
        property_schema = raw_property if isinstance(raw_property, dict) else None
        yield path, name, property_schema
        if isinstance(raw_property, dict):
            yield from _parameter_schema_fields(raw_property, path)
            items = raw_property.get("items")
            if isinstance(items, dict):
                yield from _parameter_schema_fields(items, f"{path}[]")


def _undefined_required_parameter_paths(
    schema: dict[str, object],
    parent: str = "",
) -> Iterator[str]:
    properties = schema.get("properties")
    required = schema.get("required")
    if isinstance(properties, dict) and isinstance(required, list):
        for raw_name in required:
            name = str(raw_name)
            if name not in properties:
                yield f"{parent}.{name}" if parent else name

    if not isinstance(properties, dict):
        return
    for raw_name, raw_property in properties.items():
        if not isinstance(raw_property, dict):
            continue
        name = str(raw_name)
        path = f"{parent}.{name}" if parent else name
        yield from _undefined_required_parameter_paths(raw_property, path)
        items = raw_property.get("items")
        if isinstance(items, dict):
            yield from _undefined_required_parameter_paths(items, f"{path}[]")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验 AIDD Tool Package v1")
    parser.add_argument("package_dir", help="包含 tool.yaml 的 Tool Package 目录")
    args = parser.parse_args(argv)
    try:
        manifest = load_tool_package(args.package_dir)
    except ToolPackageLoadError as exc:
        print(f"Tool Package 加载失败：{exc}", file=sys.stderr)
        return 2

    result = validate_tool_package(manifest)
    if not result.is_valid:
        for error in result.errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(
        f"Tool Package 有效：{manifest.metadata.slug}@{manifest.metadata.version} "
        f"({len(manifest.variants)} variants)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
