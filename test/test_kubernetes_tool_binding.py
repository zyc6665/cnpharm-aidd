"""Tool Package to Kubernetes registration binding tests."""

from __future__ import annotations

import pytest


def _manifest():
    from app.tool_packages.schemas import ToolPackageV2Manifest

    return ToolPackageV2Manifest.model_validate(
        {
            "api_version": "aidd.sciminer/tool-package.v2",
            "kind": "ToolPackage",
            "metadata": {
                "slug": "managed-model",
                "name": "Managed Model",
                "version": "1.0.0",
            },
            "artifacts": {"inputs": [], "outputs": []},
            "parameters_schema": {"type": "object", "properties": {}},
            "runtime": {
                "python": "3.11",
                "cuda": "12.4",
                "executor_support": ["k8s_job"],
                "selection_policy": "use immutable container image",
                "artifacts": {
                    "primary": {
                        "kind": "container",
                        "image": "registry.example/managed-model:1.0.0",
                        "image_digest": "sha256:" + "b" * 64,
                    },
                    "fallback": {
                        "kind": "conda_pack",
                        "uri": "artifacts://fallback.tar.gz",
                        "sha256": "c" * 64,
                    },
                },
                "weights": {
                    "manifest_uri": "artifacts://weights.json",
                    "manifest_sha256": "d" * 64,
                },
                "cache_policy": {
                    "key_fields": ["metadata.slug"],
                    "mutable_host_paths_forbidden": True,
                },
            },
            "variants": [
                {
                    "name": "nvidia-cuda",
                    "accelerator": "nvidia_cuda",
                    "executor_types": ["remote_job"],
                    "entrypoint": ["runner/platform_run_v2.sh"],
                    "resources": {
                        "cpu": 8,
                        "memory_mb": 16384,
                        "devices": ["nvidia.com/gpu"],
                    },
                }
            ],
        }
    )


def test_build_kubernetes_tool_config_binds_digest_variant_and_profile():
    from app.tool_packages.kubernetes_binding import build_kubernetes_tool_config

    config = build_kubernetes_tool_config(
        _manifest(),
        variant_name="nvidia-cuda",
        resource_profile="gpu-large",
    )

    assert config == {
        "type": "k8s_job",
        "variant": "nvidia-cuda",
        "runtime": {
            "image": "registry.example/managed-model:1.0.0@sha256:" + "b" * 64,
            "entrypoint": ["runner/platform_run_v2.sh"],
        },
        "resource_profile": "gpu-large",
    }


def test_build_kubernetes_tool_config_rejects_packages_without_k8s_support():
    from app.tool_packages.kubernetes_binding import KubernetesToolBindingError
    from app.tool_packages.kubernetes_binding import build_kubernetes_tool_config

    manifest = _manifest()
    manifest.runtime.executor_support = ["slurm"]

    with pytest.raises(KubernetesToolBindingError, match="executor_support"):
        build_kubernetes_tool_config(
            manifest,
            variant_name="nvidia-cuda",
            resource_profile="gpu-large",
        )
