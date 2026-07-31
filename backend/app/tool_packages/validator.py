"""Cross-file and platform policy validation for Tool Package v1."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from pydantic import BaseModel, Field

from app.tool_packages.loader import ToolPackageLoadError, load_tool_package
from app.tool_packages.schemas import Accelerator, ToolPackageManifest, ValidationStatus


class ToolPackageValidationResult(BaseModel):
    is_valid: bool
    errors: list[str] = Field(default_factory=list)


def validate_tool_package(manifest: ToolPackageManifest) -> ToolPackageValidationResult:
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
