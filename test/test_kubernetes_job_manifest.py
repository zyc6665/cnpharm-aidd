"""Kubernetes Job manifest rendering contract tests."""

from __future__ import annotations

import pytest


def _request():
    from app.execution.contracts import ExecutionRequest

    return ExecutionRequest(
        idempotency_key="task:task-1:attempt:attempt-1",
        project_id="project-1",
        requested_by="user-1",
        tool_package_version_id="package-version-1",
        variant="nvidia-cuda",
        executor_type="k8s_job",
        runtime={
            "image": "registry.example/model@sha256:" + "a" * 64,
            "entrypoint": ["/app/run.sh"],
            "env": {"MODEL_VARIANT": "nvidia-cuda"},
            "workdir": "/workspace",
        },
        resources={
            "resource_request": {
                "cpu": 16,
                "memory_gb": 64,
                "cpu_limit": 16,
                "memory_limit": "64Gi",
                "gpu_count": 1,
                "timeout_sec": 1200,
            }
        },
        task_id="task-1",
        attempt_id="attempt-1",
        tool_version_id="tool-version-1",
    )


def test_render_manifest_maps_platform_resources_and_identity_labels():
    from app.execution.adapters.kubernetes import KubernetesJobExecutionConfig
    from app.execution.adapters.kubernetes_manifest import build_kubernetes_job_manifest

    config = KubernetesJobExecutionConfig(
        cluster_alias="platform",
        namespace="model-jobs",
        credential_ref="platform-k8s",
        service_account="model-runner",
        image_pull_secret_ref="registry-credentials",
    )

    manifest = build_kubernetes_job_manifest(_request(), config)

    assert manifest["metadata"]["namespace"] == "model-jobs"
    assert manifest["metadata"]["labels"] == {
        "app.kubernetes.io/managed-by": "sciminer",
        "sciminer.io/task-id": "task-1",
        "sciminer.io/attempt-id": "attempt-1",
        "sciminer.io/tool-version-id": "tool-version-1",
    }
    assert manifest["spec"]["backoffLimit"] == 0
    assert manifest["spec"]["activeDeadlineSeconds"] == 1200
    assert manifest["spec"]["ttlSecondsAfterFinished"] == 86400

    pod_spec = manifest["spec"]["template"]["spec"]
    assert pod_spec["serviceAccountName"] == "model-runner"
    assert pod_spec["imagePullSecrets"] == [{"name": "registry-credentials"}]
    assert pod_spec["restartPolicy"] == "Never"

    container = pod_spec["containers"][0]
    assert container["image"] == "registry.example/model@sha256:" + "a" * 64
    assert container["command"] == ["/app/run.sh"]
    assert container["workingDir"] == "/workspace"
    assert container["env"] == [{"name": "MODEL_VARIANT", "value": "nvidia-cuda"}]
    assert container["resources"] == {
        "requests": {"cpu": "16", "memory": "64Gi", "nvidia.com/gpu": "1"},
        "limits": {"cpu": "16", "memory": "64Gi", "nvidia.com/gpu": "1"},
    }


def test_render_manifest_normalizes_legacy_lowercase_memory_quantity():
    from app.execution.adapters.kubernetes import KubernetesJobExecutionConfig
    from app.execution.adapters.kubernetes_manifest import build_kubernetes_job_manifest

    request = _request()
    request.resources["resource_request"]["memory_limit"] = "64g"
    config = KubernetesJobExecutionConfig(
        cluster_alias="platform",
        namespace="model-jobs",
        credential_ref="platform-k8s",
        service_account="model-runner",
    )

    manifest = build_kubernetes_job_manifest(request, config)

    assert manifest["spec"]["template"]["spec"]["containers"][0]["resources"] == {
        "requests": {"cpu": "16", "memory": "64Gi", "nvidia.com/gpu": "1"},
        "limits": {"cpu": "16", "memory": "64Gi", "nvidia.com/gpu": "1"},
    }


def test_render_manifest_rejects_mutable_images():
    from app.execution.adapters.kubernetes import KubernetesJobExecutionConfig
    from app.execution.adapters.kubernetes_manifest import (
        KubernetesManifestError,
        build_kubernetes_job_manifest,
    )

    request = _request()
    request.runtime["image"] = "registry.example/model:latest"
    config = KubernetesJobExecutionConfig(
        cluster_alias="platform",
        namespace="model-jobs",
        credential_ref="platform-k8s",
        service_account="model-runner",
    )

    with pytest.raises(KubernetesManifestError, match="immutable sha256"):
        build_kubernetes_job_manifest(request, config)


def test_render_manifest_injects_platform_object_storage_contract_without_plaintext_credentials():
    from app.execution.adapters.kubernetes import KubernetesJobExecutionConfig
    from app.execution.adapters.kubernetes_manifest import build_kubernetes_job_manifest

    config = KubernetesJobExecutionConfig(
        cluster_alias="platform",
        namespace="model-jobs",
        credential_ref="platform-k8s",
        service_account="model-runner",
        object_storage_endpoint="http://sciminer-minio.sciminer-storage:9000",
        object_storage_bucket="scitool-files",
        object_storage_secret_ref="sciminer-minio-client",
        object_storage_output_prefix="executions",
    )

    manifest = build_kubernetes_job_manifest(_request(), config)
    env = {
        item["name"]: item
        for item in manifest["spec"]["template"]["spec"]["containers"][0]["env"]
    }

    assert env["SCIMINER_OBJECT_STORAGE_ENDPOINT"]["value"] == (
        "http://sciminer-minio.sciminer-storage:9000"
    )
    assert env["SCIMINER_OBJECT_STORAGE_BUCKET"]["value"] == "scitool-files"
    assert env["SCIMINER_EXECUTION_OUTPUT_PREFIX"]["value"].startswith("executions/")
    assert env["SCIMINER_OBJECT_STORAGE_ACCESS_KEY"]["valueFrom"]["secretKeyRef"] == {
        "name": "sciminer-minio-client",
        "key": "access-key",
    }
    assert env["SCIMINER_OBJECT_STORAGE_SECRET_KEY"]["valueFrom"]["secretKeyRef"] == {
        "name": "sciminer-minio-client",
        "key": "secret-key",
    }
    assert all("secret" not in item.get("value", "").lower() for item in env.values())


def test_render_manifest_injects_immutable_input_descriptors():
    from app.execution.adapters.kubernetes import KubernetesJobExecutionConfig
    from app.execution.adapters.kubernetes_manifest import build_kubernetes_job_manifest
    from app.execution.contracts import ExecutionInput

    request = _request()
    request.inputs = [
        ExecutionInput(
            artifact_version_id="artifact-version-1",
            name="protein",
            uri="executions/inputs/protein.pdb",
            sha256="b" * 64,
            role="residue_pocket_pdb",
            artifact_type="binding_pocket@1",
            content_type="chemical/x-pdb",
            metadata={"center": [32.0, 28.0, 36.0]},
        )
    ]
    config = KubernetesJobExecutionConfig(
        cluster_alias="platform",
        namespace="model-jobs",
        credential_ref="platform-k8s",
        service_account="model-runner",
    )

    manifest = build_kubernetes_job_manifest(request, config)
    env = manifest["spec"]["template"]["spec"]["containers"][0]["env"]

    assert env == [
        {"name": "MODEL_VARIANT", "value": "nvidia-cuda"},
        {
            "name": "SCIMINER_INPUTS_JSON",
            "value": (
                '[{"artifact_version_id":"artifact-version-1","name":"protein",'
                '"uri":"executions/inputs/protein.pdb",'
                '"sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",'
                '"role":"residue_pocket_pdb","artifact_type":"binding_pocket@1",'
                '"content_type":"chemical/x-pdb","metadata":{"center":[32.0,28.0,36.0]}}]'
            ),
        },
        {"name": "SCIMINER_INPUT_MANIFEST", "value": "/workspace/input/manifest.json"},
    ]
