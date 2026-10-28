"""权重外置挂载：manifest 渲染与 schema 校验。

权重不进镜像（单模型 10~20 GB），改为节点本地目录只读挂载。这组用例守三件事：

1. 有声明就必须真的出现在 Pod 里（volumes + volumeMounts），否则模型读不到权重；
2. 没声明就不能凭空多出卷（历史任务的行为不能变）；
3. 路径写错要在生成阶段就报错，而不是等 Pod 卡住或模型读到空目录。
"""

from __future__ import annotations

import pytest

from app.execution.adapters.kubernetes import KubernetesJobExecutionConfig
from app.execution.adapters.kubernetes_manifest import (
    KubernetesManifestError,
    build_kubernetes_job_manifest,
)
from app.execution.contracts import ExecutionRequest
from app.tool_packages.schemas import RuntimeWeightsManifest

IMAGE = "registry.local/aidd/compute-lvpocket@sha256:" + "a" * 64


def _request(runtime: dict) -> ExecutionRequest:
    return ExecutionRequest(
        idempotency_key="task-1:1",
        project_id="project-1",
        requested_by="user-1",
        tool_package_version_id="tpv-1",
        variant="mock-local",
        executor_type="k8s_job",
        task_id="task-1",
        attempt_id="1",
        resources={"cpu": 2, "memory_gb": 4},
        runtime={"image": IMAGE, "entrypoint": ["/entrypoint.sh"], **runtime},
    )


def _config() -> KubernetesJobExecutionConfig:
    return KubernetesJobExecutionConfig(
        cluster_alias="dev",
        namespace="default",
        credential_ref="cred",
        service_account="default",
    )


def _pod(manifest: dict) -> dict:
    return manifest["spec"]["template"]["spec"]


def test_weight_mounts_are_rendered_as_read_only_host_paths() -> None:
    manifest = build_kubernetes_job_manifest(
        _request(
            {
                "weights": {
                    "mounts": [
                        {
                            "name": "lvpocket-weights",
                            "host_path": "/data/zhouyc/model-cache/lvpocket/v2/new_best",
                            "mount_path": "/opt/sciminer/model/new_best",
                        }
                    ]
                }
            }
        ),
        _config(),
    )
    pod = _pod(manifest)
    assert pod["volumes"] == [
        {
            "name": "lvpocket-weights",
            "hostPath": {
                "path": "/data/zhouyc/model-cache/lvpocket/v2/new_best",
                "type": "Directory",
            },
        }
    ]
    assert pod["containers"][0]["volumeMounts"] == [
        {
            "name": "lvpocket-weights",
            "mountPath": "/opt/sciminer/model/new_best",
            "readOnly": True,
        }
    ]


def test_no_weight_declaration_adds_no_volumes() -> None:
    pod = _pod(build_kubernetes_job_manifest(_request({}), _config()))
    assert "volumes" not in pod
    assert "volumeMounts" not in pod["containers"][0]


def test_relative_host_path_is_rejected() -> None:
    with pytest.raises(KubernetesManifestError, match="host_path must be an absolute path"):
        build_kubernetes_job_manifest(
            _request(
                {"weights": {"mounts": [{"name": "w", "host_path": "data/x", "mount_path": "/m"}]}}
            ),
            _config(),
        )


def test_duplicate_mount_name_is_rejected() -> None:
    with pytest.raises(KubernetesManifestError, match="duplicate"):
        build_kubernetes_job_manifest(
            _request(
                {
                    "weights": {
                        "mounts": [
                            {"name": "w", "host_path": "/a", "mount_path": "/m1"},
                            {"name": "w", "host_path": "/b", "mount_path": "/m2"},
                        ]
                    }
                }
            ),
            _config(),
        )


def test_schema_accepts_mounts_only() -> None:
    weights = RuntimeWeightsManifest.model_validate(
        {"mounts": [{"name": "w", "host_path": "/a", "mount_path": "/m"}]}
    )
    assert weights.manifest_uri == ""
    assert weights.mounts[0].read_only is True
