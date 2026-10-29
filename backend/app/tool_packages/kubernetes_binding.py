"""Bind a validated Tool Package variant to the managed Kubernetes executor."""

from __future__ import annotations

import re
from typing import Any

from app.tool_packages.schemas import ToolPackageManifest
from app.tasks.resource_profile import resolve_registered_resource_profile


class KubernetesToolBindingError(ValueError):
    """Raised when a Tool Package cannot be registered for Kubernetes execution."""


def build_kubernetes_tool_config(
    manifest: ToolPackageManifest,
    *,
    variant_name: str,
    resource_profile: str,
) -> dict[str, Any]:
    """Create the platform-owned ``tool_config`` for a K8s-backed Tool Version."""
    if "k8s_job" not in manifest.runtime.executor_support:
        raise KubernetesToolBindingError(
            "runtime.executor_support must include k8s_job"
        )

    try:
        resolve_registered_resource_profile(resource_profile)
    except ValueError as exc:
        raise KubernetesToolBindingError(str(exc)) from exc

    primary = manifest.runtime.artifacts.primary
    if primary.kind != "container" or not primary.image or not primary.image_digest:
        raise KubernetesToolBindingError(
            "Kubernetes registration requires a primary container image and digest"
        )
    if not re.fullmatch(r"sha256:[a-fA-F0-9]{64}", primary.image_digest):
        raise KubernetesToolBindingError(
            "primary image_digest must be a sha256 digest"
        )

    variant = next((item for item in manifest.variants if item.name == variant_name), None)
    if variant is None:
        raise KubernetesToolBindingError(f"variant is not registered: {variant_name}")

    image = primary.image
    if "@" in image:
        image = image.split("@", 1)[0]

    return {
        "type": "k8s_job",
        "variant": variant.name,
        "runtime": {
            "image": f"{image}@{primary.image_digest}",
            "entrypoint": list(variant.entrypoint),
        },
        "resource_profile": resource_profile,
    }
