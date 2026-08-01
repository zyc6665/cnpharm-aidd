"""Cross-file and platform policy validation for Tool Packages."""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence

from pydantic import BaseModel, Field

from app.artifact_standards.registry import is_standard_artifact_ref
from app.tool_packages.loader import ToolPackageLoadError, load_tool_package
from app.tool_packages.schemas import (
    Accelerator,
    AnyToolPackageManifest,
    ToolPackageManifest,
    ToolPackageV2Manifest,
    ValidationStatus,
)


_IMAGE_DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


class ToolPackageValidationResult(BaseModel):
    is_valid: bool
    errors: list[str] = Field(default_factory=list)


def validate_tool_package(manifest: AnyToolPackageManifest) -> ToolPackageValidationResult:
    if isinstance(manifest, ToolPackageV2Manifest):
        return _validate_tool_package_v2(manifest)
    return _validate_tool_package_v1(manifest)


def _validate_tool_package_v1(manifest: ToolPackageManifest) -> ToolPackageValidationResult:
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


def _validate_tool_package_v2(manifest: ToolPackageV2Manifest) -> ToolPackageValidationResult:
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
    if parameter_schema:
        if parameter_schema.get("type") != "object":
            errors.append("parameters_schema.type must be object")
        required = parameter_schema.get("required", [])
        if isinstance(required, list) and "device" in required:
            errors.append(
                "parameters_schema.device belongs in variant execution context, "
                "not required business parameters"
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


def _validate_runtime_env(manifest: ToolPackageV2Manifest, errors: list[str]) -> None:
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
    if not weights.manifest_uri:
        errors.append("runtime.weights.manifest_uri is required")
    if not weights.manifest_sha256 or not _SHA256_RE.fullmatch(weights.manifest_sha256):
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
