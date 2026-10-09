"""Render a platform execution request into a Kubernetes Job manifest."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from app.execution.adapters.kubernetes import KubernetesJobExecutionConfig
from app.execution.contracts import ExecutionRequest


class KubernetesManifestError(ValueError):
    """Raised when an execution request cannot become a safe Kubernetes Job."""


def build_kubernetes_job_manifest(
    request: ExecutionRequest,
    config: KubernetesJobExecutionConfig,
) -> dict[str, Any]:
    """Build a deterministic, platform-owned Job manifest from an execution request."""
    runtime = request.runtime
    image = runtime.get("image")
    if not isinstance(image, str) or not re.search(r"@sha256:[a-fA-F0-9]{64}$", image):
        raise KubernetesManifestError(
            "Kubernetes Job image must use an immutable sha256 digest"
        )

    resources = _resource_values(request.resources)
    labels = {
        "app.kubernetes.io/managed-by": "sciminer",
        "sciminer.io/task-id": _label_value(request.task_id or request.idempotency_key),
        "sciminer.io/attempt-id": _label_value(request.attempt_id or "current"),
        "sciminer.io/tool-version-id": _label_value(request.tool_version_id or request.tool_package_version_id),
    }
    container: dict[str, Any] = {
        "name": "tool",
        "image": image,
        "resources": _container_resources(resources),
    }

    command = runtime.get("entrypoint") or runtime.get("command")
    if command is not None:
        if not _is_string_list(command):
            raise KubernetesManifestError("runtime.entrypoint must be a list of strings")
        container["command"] = list(command)

    args = runtime.get("args")
    if args is not None:
        if not _is_string_list(args):
            raise KubernetesManifestError("runtime.args must be a list of strings")
        container["args"] = list(args)

    workdir = runtime.get("workdir", "/workspace")
    if not isinstance(workdir, str) or not workdir.startswith("/"):
        raise KubernetesManifestError("runtime.workdir must be an absolute path")
    container["workingDir"] = workdir

    env = runtime.get("env", {})
    if env:
        if not isinstance(env, dict):
            raise KubernetesManifestError("runtime.env must be an object")
        container["env"] = [
            {"name": str(name), "value": _env_value(value)}
            for name, value in sorted(env.items())
        ]

    platform_env = _object_storage_env(config, _job_name(config.job_name_prefix, request))
    input_env = _input_env(request)
    platform_env.extend(input_env)
    if platform_env:
        configured_names = {item["name"] for item in container.get("env", [])}
        platform_names = {item["name"] for item in platform_env}
        collisions = sorted(configured_names.intersection(platform_names))
        if collisions:
            raise KubernetesManifestError(
                "runtime.env cannot override platform object-storage variables: "
                + ", ".join(collisions)
            )
        container.setdefault("env", []).extend(platform_env)

    pod_spec: dict[str, Any] = {
        "restartPolicy": "Never",
        "serviceAccountName": config.service_account,
        "containers": [container],
    }
    if config.image_pull_secret_ref:
        pod_spec["imagePullSecrets"] = [{"name": config.image_pull_secret_ref}]

    job_spec: dict[str, Any] = {
        "backoffLimit": 0,
        "ttlSecondsAfterFinished": config.job_ttl_seconds,
        "template": {"metadata": {"labels": labels}, "spec": pod_spec},
    }
    timeout_sec = resources.get("timeout_sec")
    if timeout_sec is not None:
        job_spec["activeDeadlineSeconds"] = timeout_sec

    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": _job_name(config.job_name_prefix, request),
            "namespace": config.namespace,
            "labels": labels,
            "annotations": {"sciminer.io/idempotency-key": request.idempotency_key},
        },
        "spec": job_spec,
    }


def _resource_values(resources: dict[str, Any]) -> dict[str, Any]:
    snapshot = resources.get("resource_request")
    values = snapshot if isinstance(snapshot, dict) else resources
    normalized: dict[str, Any] = {}
    for key in ("cpu", "cpu_limit", "memory_gb", "memory_limit", "gpu_count", "timeout_sec"):
        if values.get(key) is not None:
            normalized[key] = values[key]
    return normalized


def _container_resources(resources: dict[str, Any]) -> dict[str, dict[str, str]]:
    requests: dict[str, str] = {}
    limits: dict[str, str] = {}
    cpu = resources.get("cpu")
    if cpu is not None:
        requests["cpu"] = _quantity(cpu)
        limits["cpu"] = _quantity(resources.get("cpu_limit", cpu))
    memory = resources.get("memory_limit")
    if memory is None and resources.get("memory_gb") is not None:
        memory = f"{_quantity(resources['memory_gb'])}Gi"
    if memory is not None:
        normalized_memory = _memory_quantity(memory)
        requests["memory"] = normalized_memory
        limits["memory"] = normalized_memory
    gpu_count = int(resources.get("gpu_count") or 0)
    if gpu_count > 0:
        requests["nvidia.com/gpu"] = str(gpu_count)
        limits["nvidia.com/gpu"] = str(gpu_count)
    if not requests:
        raise KubernetesManifestError("resource request must include CPU, memory, or GPU")
    return {"requests": requests, "limits": limits}


def _job_name(prefix: str, request: ExecutionRequest) -> str:
    identity = f"{request.task_id or request.idempotency_key}:{request.attempt_id or 'current'}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    normalized_prefix = _dns_value(prefix) or "sciminer"
    return f"{normalized_prefix[:50]}-{digest}"[:63].rstrip("-")


def _object_storage_env(
    config: KubernetesJobExecutionConfig,
    job_name: str,
) -> list[dict[str, Any]]:
    if not config.object_storage_endpoint and not config.object_storage_bucket:
        return []
    if not config.object_storage_endpoint or not config.object_storage_bucket:
        raise KubernetesManifestError(
            "object storage endpoint and bucket must be configured together"
        )
    if not config.object_storage_secret_ref:
        raise KubernetesManifestError(
            "object storage Secret ref is required for Kubernetes Job output upload"
        )
    prefix_parts = [
        part.strip("/")
        for part in (config.object_storage_output_prefix, config.namespace, job_name)
        if part.strip("/")
    ]
    if any(part in {".", ".."} or "/" in part for part in prefix_parts):
        raise KubernetesManifestError("object storage output prefix contains unsafe path segments")
    prefix = "/".join(prefix_parts)
    env: list[dict[str, Any]] = [
        {"name": "SCIMINER_OBJECT_STORAGE_ENDPOINT", "value": config.object_storage_endpoint},
        {"name": "SCIMINER_OBJECT_STORAGE_BUCKET", "value": config.object_storage_bucket},
        {"name": "SCIMINER_EXECUTION_OUTPUT_PREFIX", "value": prefix},
        {"name": "SCIMINER_RESULT_OBJECT", "value": f"{prefix}/result.json"},
    ]
    if config.object_storage_secret_ref:
        env.extend(
            [
                {
                    "name": "SCIMINER_OBJECT_STORAGE_ACCESS_KEY",
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": config.object_storage_secret_ref,
                            "key": "access-key",
                        }
                    },
                },
                {
                    "name": "SCIMINER_OBJECT_STORAGE_SECRET_KEY",
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": config.object_storage_secret_ref,
                            "key": "secret-key",
                        }
                    },
                },
            ]
        )
    return env


def _input_env(request: ExecutionRequest) -> list[dict[str, str]]:
    if not request.inputs:
        return []
    payload = [item.model_dump(exclude_none=True) for item in request.inputs]
    return [
        {
            "name": "SCIMINER_INPUTS_JSON",
            "value": json.dumps(payload, ensure_ascii=True, separators=(",", ":")),
        },
        {"name": "SCIMINER_INPUT_MANIFEST", "value": "/workspace/input/manifest.json"},
    ]


def _label_value(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value)).strip("-_.")
    return (normalized or "unknown")[:63].rstrip("-_.")


def _dns_value(value: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", str(value).lower()).strip("-")


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)


def _env_value(value: Any) -> str:
    if isinstance(value, (str, int, float, bool)):
        return str(value).lower() if isinstance(value, bool) else str(value)
    raise KubernetesManifestError("runtime.env values must be scalar values")


def _quantity(value: Any) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else str(number)


def _memory_quantity(value: Any) -> str:
    text = str(value).strip()
    if re.fullmatch(r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)g", text):
        return f"{text[:-1]}Gi"
    return text
