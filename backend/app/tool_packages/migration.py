"""Idempotently migrate legacy ``ToolVersion.config`` records to Tool Package v1."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.tool_packages import ToolPackage, ToolPackageVersion
from app.models.tools import Tool, ToolVersion
from app.services.tool_contracts import collect_tool_contract_config_validation_errors
from app.tool_packages.schemas import ToolPackageManifest
from app.tool_packages.validator import validate_tool_package


_EXECUTORS = {
    "docker_image": ("container",),
    "python_script": ("cli",),
    "ssh_job": ("remote_job",),
    "remote_api": ("remote_job",),
}
_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class ToolPackageMigrationRecord:
    tool_slug: str
    version: str
    action: str
    validation_level: str
    errors: list[str] = field(default_factory=list)


@dataclass
class ToolPackageMigrationSummary:
    scanned: int = 0
    packages_created: int = 0
    versions_created: int = 0
    skipped: int = 0
    invalid: int = 0
    records: list[ToolPackageMigrationRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "packages_created": self.packages_created,
            "versions_created": self.versions_created,
            "skipped": self.skipped,
            "invalid": self.invalid,
            "records": [asdict(record) for record in self.records],
        }


async def migrate_tool_packages(
    db: AsyncSession,
    *,
    dry_run: bool = True,
) -> ToolPackageMigrationSummary:
    """Convert every legacy tool version without exposing legacy runtime secrets.

    The migration only writes when ``dry_run`` is false. Existing immutable package
    versions are detected by ``(package_id, version)`` and are never overwritten.
    """
    summary = ToolPackageMigrationSummary()
    versions = (
        (await db.execute(select(ToolVersion).options(selectinload(ToolVersion.tool))))
        .scalars()
        .all()
    )
    packages_by_slug = {
        package.slug: package
        for package in (await db.execute(select(ToolPackage))).scalars().all()
    }
    known_versions = {
        (package_id, version)
        for package_id, version in (
            await db.execute(
                select(ToolPackageVersion.package_id, ToolPackageVersion.version)
            )
        ).all()
    }

    for legacy_version in versions:
        tool = legacy_version.tool
        if tool is None:
            continue
        summary.scanned += 1
        manifest, errors = build_legacy_tool_manifest(tool, legacy_version)
        if errors:
            summary.invalid += 1
            summary.records.append(
                ToolPackageMigrationRecord(
                    tool_slug=tool.slug,
                    version=legacy_version.version,
                    action="invalid",
                    validation_level="invalid",
                    errors=errors,
                )
            )
            continue

        package = packages_by_slug.get(tool.slug)
        package_is_new = package is None
        if (
            package is not None
            and (package.id, legacy_version.version) in known_versions
        ):
            summary.skipped += 1
            summary.records.append(
                ToolPackageMigrationRecord(
                    tool_slug=tool.slug,
                    version=legacy_version.version,
                    action="skipped",
                    validation_level=_validation_level(manifest),
                )
            )
            continue

        if package_is_new:
            summary.packages_created += 1
        summary.versions_created += 1
        summary.records.append(
            ToolPackageMigrationRecord(
                tool_slug=tool.slug,
                version=legacy_version.version,
                action="would_apply" if dry_run else "applied",
                validation_level=_validation_level(manifest),
            )
        )
        if dry_run:
            continue

        if package is None:
            package = ToolPackage(
                owner_id=tool.owner_id,
                slug=tool.slug,
                name=tool.name,
                description=tool.description,
                status="draft",
            )
            db.add(package)
            await db.flush()
            packages_by_slug[tool.slug] = package

        package_version = ToolPackageVersion(
            package_id=package.id,
            version=legacy_version.version,
            manifest=manifest,
            manifest_digest=_manifest_digest(manifest),
            signature=None,
            is_signed=False,
            validation_status="valid",
            validation_errors=[],
        )
        db.add(package_version)
        await db.flush()
        package.current_version_id = package_version.id
        known_versions.add((package.id, legacy_version.version))

    return summary


def build_legacy_tool_manifest(
    tool: Tool,
    version: ToolVersion,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Build a safe manifest from declared contracts, never runtime connection data."""
    config = version.config if isinstance(version.config, dict) else {}
    errors = list(
        collect_tool_contract_config_validation_errors(
            tool_slug=tool.slug,
            config=config,
            current_version_active=version.is_active,
        )
    )
    if not _SLUG_PATTERN.fullmatch(tool.slug or ""):
        errors.append("tool.slug must match Tool Package slug format")
    capability = config.get("agent_capability")
    if not isinstance(capability, dict) or capability.get("enabled") is not True:
        errors.append("agent_capability.enabled=true is required for migration")

    executor_type = str(config.get("type") or "").strip()
    executor_types = _EXECUTORS.get(executor_type)
    if executor_types is None:
        errors.append(f'config.type {executor_type or "<missing>"} is not migratable')
    if executor_type == "docker_image" and not str(config.get("image") or "").strip():
        errors.append("config.image is required for docker_image migration")

    inputs = _artifact_declarations(capability, "inputs")
    outputs = _artifact_declarations(capability, "outputs")
    if not inputs:
        errors.append("agent_capability.inputs must include semantic_type declarations")
    if not outputs:
        errors.append(
            "agent_capability.outputs must include semantic_type declarations"
        )
    errors = _dedupe(errors)
    if errors:
        return None, errors

    image = (
        str(config.get("image") or "").strip()
        if executor_type == "docker_image"
        else None
    )
    variants = [
        _variant(
            "cpu",
            executor_types,
            inputs,
            outputs,
            image=image,
            cpu_verified=_has_golden_evidence(config, "cpu"),
        )
    ]
    if bool(getattr(tool, "gpu_required", False)):
        variants.extend(
            [
                _variant(
                    "nvidia_cuda",
                    executor_types,
                    inputs,
                    outputs,
                    image=image,
                    nvidia_verified=_has_golden_evidence(config, "nvidia_cuda"),
                ),
                _variant(
                    "haiguang_dcu",
                    executor_types,
                    inputs,
                    outputs,
                    image=image,
                    dcu_verified=_has_golden_evidence(config, "haiguang_dcu"),
                ),
            ]
        )
    manifest = {
        "api_version": "aidd.sciminer/v1",
        "kind": "ToolPackage",
        "metadata": {
            "slug": tool.slug,
            "name": tool.name,
            "version": version.version,
            "description": tool.description,
        },
        "artifacts": {"inputs": inputs, "outputs": outputs},
        "variants": variants,
    }
    try:
        parsed = ToolPackageManifest.model_validate(manifest)
    except ValueError as exc:
        return None, [f"generated manifest is invalid: {exc}"]
    validation = validate_tool_package(parsed)
    return (
        (None, validation.errors)
        if not validation.is_valid
        else (parsed.model_dump(mode="json"), [])
    )


def _artifact_declarations(capability: Any, direction: str) -> list[dict[str, Any]]:
    if not isinstance(capability, dict):
        return []
    declarations: list[dict[str, Any]] = []
    for item in capability.get(direction, []):
        if not isinstance(item, dict):
            continue
        semantic_type = str(item.get("semantic_type") or "").strip()
        if not semantic_type:
            continue
        match = item.get("match") if isinstance(item.get("match"), dict) else {}
        artifact_type = str(match.get("artifact_type") or semantic_type).strip()
        declarations.append(
            {
                "name": str(item.get("field") or semantic_type),
                "semantic_type": semantic_type,
                "artifact_type": artifact_type,
                "required": bool(item.get("required", True)),
            }
        )
    return declarations


def _variant(
    accelerator: str,
    executor_types: tuple[str, ...],
    inputs: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    *,
    image: str | None,
    cpu_verified: bool = False,
    nvidia_verified: bool = False,
    dcu_verified: bool = False,
) -> dict[str, Any]:
    resources: dict[str, Any] = {"cpu": 1, "memory_mb": 1024}
    if accelerator == "nvidia_cuda":
        resources.update({"devices": ["nvidia.com/gpu"], "driver": "unspecified"})
        validation_status = "validated" if nvidia_verified else "unvalidated"
        hardware_validated = nvidia_verified
    elif accelerator == "haiguang_dcu":
        resources.update({"devices": ["hygon.com/dcu"], "driver": "unspecified"})
        validation_status = (
            "validated" if dcu_verified else "adapted_pending_hardware_validation"
        )
        hardware_validated = dcu_verified
    else:
        validation_status = "validated" if cpu_verified else "unvalidated"
        hardware_validated = cpu_verified
    return {
        "name": accelerator.replace("_", "-"),
        "accelerator": accelerator,
        "executor_types": list(executor_types),
        "image": image,
        "entrypoint": ["tool-package-run"],
        "resources": resources,
        "validation_status": validation_status,
        "hardware_validated": hardware_validated,
        "inputs": [item["artifact_type"] for item in inputs],
        "outputs": [item["artifact_type"] for item in outputs],
    }


def _has_golden_evidence(config: dict[str, Any], accelerator: str) -> bool:
    """Accept only an explicit passed golden-validation record as verification evidence."""
    evidence = config.get("golden_validation")
    if not isinstance(evidence, dict):
        return False
    candidate = evidence.get(accelerator)
    return candidate is True or (
        isinstance(candidate, dict) and candidate.get("passed") is True
    )


def _validation_level(manifest: dict[str, Any]) -> str:
    variants = manifest.get("variants", [])
    if any(
        item.get("validation_status") == "adapted_pending_hardware_validation"
        for item in variants
    ):
        return "adapted_pending_hardware_validation"
    if any(item.get("validation_status") == "unvalidated" for item in variants):
        return "runnable_unverified"
    return "verified"


def _manifest_digest(manifest: dict[str, Any]) -> str:
    canonical = json.dumps(
        manifest, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _dedupe(errors: list[str]) -> list[str]:
    return list(dict.fromkeys(errors))
