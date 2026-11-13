"""Deployment baseline tests for the Kubernetes execution environment."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEPLOY_ROOT = ROOT / "deploy" / "kubernetes"


def _resources(filename: str) -> list[dict]:
    content = (DEPLOY_ROOT / filename).read_text(encoding="utf-8")
    return [item for item in yaml.safe_load_all(content) if item]


def _resource(filename: str, kind: str, name: str) -> dict:
    for item in _resources(filename):
        if item.get("kind") == kind and item.get("metadata", {}).get("name") == name:
            return item
    raise AssertionError(f"missing {kind}/{name} in {filename}")


def test_execution_rbac_is_namespace_scoped_and_has_no_wildcards():
    namespaces = {
        item["metadata"]["name"]
        for item in _resources("namespace.yaml")
        if item["kind"] == "Namespace"
    }
    assert {"sciminer-system", "sciminer-model-jobs", "sciminer-storage"} <= namespaces

    worker = _resource(
        "execution-rbac.yaml",
        "ServiceAccount",
        "sciminer-execution-worker",
    )
    assert worker["metadata"]["namespace"] == "sciminer-system"

    runner = _resource("execution-rbac.yaml", "ServiceAccount", "model-runner")
    assert runner["metadata"]["namespace"] == "sciminer-model-jobs"
    assert runner["automountServiceAccountToken"] is False

    role = _resource(
        "execution-rbac.yaml",
        "Role",
        "sciminer-execution-worker",
    )
    assert role["metadata"]["namespace"] == "sciminer-model-jobs"
    resources = {
        resource
        for rule in role["rules"]
        for resource in rule["resources"]
    }
    assert {"jobs", "pods", "pods/log", "events"} <= resources
    for rule in role["rules"]:
        assert "*" not in rule.get("verbs", [])
        assert "*" not in rule.get("resources", [])

    binding = _resource(
        "execution-rbac.yaml",
        "RoleBinding",
        "sciminer-execution-worker",
    )
    assert binding["metadata"]["namespace"] == "sciminer-model-jobs"
    assert binding["roleRef"] == {
        "apiGroup": "rbac.authorization.k8s.io",
        "kind": "Role",
        "name": "sciminer-execution-worker",
    }
    assert binding["subjects"] == [
        {
            "kind": "ServiceAccount",
            "name": "sciminer-execution-worker",
            "namespace": "sciminer-system",
        }
    ]


def test_dev_minio_uses_secret_credentials_and_persistent_storage():
    deployment = _resource("minio-dev.yaml", "Deployment", "sciminer-minio")
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert "latest" not in container["image"]
    assert container["image"].startswith("docker.1panel.live/minio/minio@sha256:")
    assert len(container["image"].rsplit(":", 1)[-1]) == 64
    env_by_name = {item["name"]: item for item in container["env"]}
    for name in ("MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD"):
        assert env_by_name[name]["valueFrom"]["secretKeyRef"]["name"] == (
            "sciminer-minio-credentials"
        )

    pvc = _resource("minio-dev.yaml", "PersistentVolumeClaim", "minio-data")
    assert pvc["spec"]["storageClassName"] == "local-path"
    assert pvc["spec"]["resources"]["requests"]["storage"] == "20Gi"

    service = _resource("minio-dev.yaml", "Service", "sciminer-minio")
    assert service["spec"]["type"] == "ClusterIP"
    assert {port["port"] for port in service["spec"]["ports"]} == {9000, 9001}


def test_dev_registry_exposure_is_disabled_by_default():
    """Registry 不应默认通过 NodePort 暴露；仅保留 ClusterIP 供 port-forward。"""
    service = _resource(
        "registry-dev-nodeport.yaml",
        "Service",
        "sciminer-registry-nodeport",
    )
    assert service["spec"]["type"] == "ClusterIP"
    assert all("nodePort" not in port for port in service["spec"]["ports"])

    kustomization = yaml.safe_load(
        (DEPLOY_ROOT / "kustomization.yaml").read_text(encoding="utf-8")
    )
    assert "registry-dev-nodeport.yaml" not in kustomization["resources"]


def test_smoke_image_writes_standard_result_manifest():
    dockerfile = (DEPLOY_ROOT / "smoke-image" / "Dockerfile").read_text(
        encoding="utf-8"
    )
    script = (DEPLOY_ROOT / "smoke-image" / "run-smoke.sh").read_text(
        encoding="utf-8"
    )

    assert "FROM alpine:3.20" in dockerfile
    assert "minio==7.2.3" in dockerfile
    assert "run-smoke.py" in dockerfile
    assert "set -eu" in script
    runner = (DEPLOY_ROOT / "smoke-image" / "run-smoke.py").read_text(
        encoding="utf-8"
    )
    assert '"aidd.sciminer/result"' in runner
    assert '"run_report@1"' in runner
    assert '"report_json"' in runner
    assert "sha256_file" in runner
    assert "put_object" in runner
    assert "get_object" in runner


def test_execution_worker_example_is_explicit_and_k8s_only():
    config = _resource(
        "execution-worker.example.yaml",
        "ConfigMap",
        "sciminer-execution-worker-config",
    )
    assert config["metadata"]["namespace"] == "sciminer-system"
    assert config["data"] == {
        "ENVIRONMENT": "production",
        "DEBUG": "false",
        "CORS_ORIGINS": '["https://sciminer.example.invalid"]',
        "ALLOWED_HOSTS": '["sciminer.example.invalid"]',
        "CACHE_BACKEND": "redis",
        "REDIS_HOST": "sciminer-redis.sciminer-system.svc.cluster.local",
        "REDIS_PORT": "6379",
        "REDIS_DB": "0",
        "STORAGE_BACKEND": "minio",
        "MINIO_ENDPOINT": "sciminer-minio.sciminer-storage.svc.cluster.local:9000",
        "MINIO_BUCKET": "scitool-files",
        "MINIO_SECURE": "true",
        "TASK_EXECUTION_BACKEND": "celery",
        "EXECUTOR_ENABLED_K8S": "true",
        "EXECUTOR_ENABLED_SSH": "true",
        "K8S_ADAPTER_CLUSTER_ALIAS": "platform",
        "K8S_ADAPTER_NAMESPACE": "sciminer-model-jobs",
        "K8S_ADAPTER_CREDENTIAL_REF": "platform-k8s",
        "K8S_ADAPTER_SERVICE_ACCOUNT": "model-runner",
        "K8S_ADAPTER_JOB_NAME_PREFIX": "sciminer",
        "K8S_ADAPTER_API_SERVER": "https://kubernetes.default.svc",
        "K8S_ADAPTER_REQUEST_TIMEOUT_SECONDS": "30",
        "K8S_ADAPTER_OBJECT_STORAGE_ENDPOINT": (
            "https://sciminer-minio.sciminer-storage.svc.cluster.local:9000"
        ),
        "K8S_ADAPTER_OBJECT_STORAGE_BUCKET": "scitool-files",
        "K8S_ADAPTER_OBJECT_STORAGE_SECRET_REF": "sciminer-minio-client",
        "K8S_ADAPTER_OBJECT_STORAGE_INPUT_PREFIX": "inputs",
        "K8S_ADAPTER_OBJECT_STORAGE_OUTPUT_PREFIX": "executions",
        "K8S_ADAPTER_OBJECT_STORAGE_STAGING_ROOT": "/tmp/sciminer-k8s-artifacts",
        "WORKER_CAPABILITY_ADMISSION_ENABLED": "true",
        "WORKER_CAPABILITY_ROUTING_ENABLED": "true",
        "WORKER_CAPABILITY_RESERVATION_ENABLED": "true",
        "WORKER_LISTEN_QUEUES": (
            "default,tool_tasks,high_priority,cpu_queue,heavy_compute,gpu_queue,"
            "maintenance,monitoring"
        ),
        "WORKER_CAPABILITY_HEARTBEAT_QUEUES": (
            "default,tool_tasks,high_priority,cpu_queue,heavy_compute,gpu_queue"
        ),
    }

    deployment = _resource(
        "execution-worker.example.yaml",
        "Deployment",
        "sciminer-execution-worker",
    )
    assert deployment["metadata"]["namespace"] == "sciminer-system"
    pod_spec = deployment["spec"]["template"]["spec"]
    assert pod_spec["serviceAccountName"] == "sciminer-execution-worker"
    assert pod_spec["automountServiceAccountToken"] is True
    container = pod_spec["containers"][0]
    assert container["image"] == (
        "registry.example.com/sciminer/backend@sha256:"
        "REPLACE_WITH_BACKEND_IMAGE_DIGEST"
    )
    assert "latest" not in container["image"]
    assert container["command"] == ["celery"]
    assert container["args"][:4] == [
        "-A",
        "app.worker.celery_app",
        "worker",
        "--loglevel=info",
    ]
    # 任务执行是「提交 Job 后轮询等结果」，全程 I/O 等待，所以用线程池而不是 prefork；
    # 并发数要覆盖「10 人同时提交」，否则长任务会把后面的任务全堵在队列里。
    assert "--pool=threads" in container["args"]
    assert "--concurrency=16" in container["args"]
    assert (
        "--queues=default,tool_tasks,high_priority,cpu_queue,heavy_compute,"
        "gpu_queue,maintenance,monitoring"
    ) in container["args"]
    assert container["envFrom"] == [
        {"configMapRef": {"name": "sciminer-execution-worker-config"}}
    ]
    secret_env = {
        item["name"]: item["valueFrom"]["secretKeyRef"]
        for item in container["env"]
        if "secretKeyRef" in item.get("valueFrom", {})
    }
    assert secret_env == {
        name: {"name": "sciminer-execution-worker-secrets", "key": name}
        for name in (
            "DATABASE_URL",
            "JWT_SECRET_KEY",
            "SETTINGS_ENCRYPTION_KEY",
            "REDIS_PASSWORD",
            "CELERY_BROKER_URL",
            "CELERY_RESULT_BACKEND",
            "MINIO_ACCESS_KEY",
            "MINIO_SECRET_KEY",
            "SSH_PASSWORD_REF_SSH_4090_ZHOUYC",
        )
    }
    env_by_name = {item["name"]: item for item in container["env"]}
    assert env_by_name["HOSTNAME"]["valueFrom"] == {
        "fieldRef": {"fieldPath": "metadata.name"}
    }
    assert env_by_name["WORKER_CAPABILITY_JSON"]["value"].startswith(
        '{"worker_id":"sciminer-k8s-$(HOSTNAME)"'
    )
    assert {volume["name"] for volume in pod_spec["volumes"]} == {
        "k8s-artifacts"
    }

    kustomization = (DEPLOY_ROOT / "kustomization.yaml").read_text(encoding="utf-8")
    assert "execution-worker.example.yaml" not in kustomization


def test_dev_data_services_are_pinned_and_host_reachable():
    postgres = _resource(
        "data-services-dev.yaml",
        "Deployment",
        "sciminer-postgres",
    )
    redis = _resource("data-services-dev.yaml", "Deployment", "sciminer-redis")
    assert postgres["metadata"]["namespace"] == "sciminer-system"
    assert redis["metadata"]["namespace"] == "sciminer-system"

    postgres_container = postgres["spec"]["template"]["spec"]["containers"][0]
    redis_container = redis["spec"]["template"]["spec"]["containers"][0]
    assert postgres_container["image"] == (
        "docker.1panel.live/library/postgres@sha256:"
        "721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea"
    )
    assert redis_container["image"] == (
        "docker.1panel.live/library/redis@sha256:"
        "858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499"
    )
    for container in (postgres_container, redis_container):
        assert "latest" not in container["image"]

    postgres_service = _resource(
        "data-services-dev.yaml",
        "Service",
        "sciminer-postgres",
    )
    redis_service = _resource(
        "data-services-dev.yaml",
        "Service",
        "sciminer-redis",
    )
    assert postgres_service["spec"]["type"] == "ClusterIP"
    assert redis_service["spec"]["type"] == "ClusterIP"
    assert all("nodePort" not in port for port in postgres_service["spec"]["ports"])
    assert all("nodePort" not in port for port in redis_service["spec"]["ports"])

    for filename, deployment_name in (
        ("data-services-dev.yaml", "sciminer-postgres"),
        ("data-services-dev.yaml", "sciminer-redis"),
    ):
        deployment = _resource(filename, "Deployment", deployment_name)
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        assert container["env"][0]["valueFrom"]["secretKeyRef"]["name"].startswith(
            "sciminer-"
        )


def test_default_kustomization_contains_the_complete_hybrid_dev_infrastructure():
    kustomization = yaml.safe_load(
        (DEPLOY_ROOT / "kustomization.yaml").read_text(encoding="utf-8")
    )

    assert set(kustomization["resources"]) == {
        "namespace.yaml",
        "execution-rbac.yaml",
        "data-services-dev.yaml",
        "minio-dev.yaml",
        "registry-dev.yaml",
        "network-policies-dev.yaml",
    }
    for resource in kustomization["resources"]:
        assert (DEPLOY_ROOT / resource).is_file()
    assert "execution-worker.example.yaml" not in kustomization["resources"]


def test_hybrid_deployment_guide_documents_the_single_apply_entrypoint():
    readme = (DEPLOY_ROOT / "README.md").read_text(encoding="utf-8")

    assert "kubectl apply -k deploy/kubernetes" in readme
    for component in ("PostgreSQL", "Redis", "MinIO", "Registry"):
        assert component in readme
    assert "平台 API 仍运行在当前开发机" in readme
    assert "execution-worker.example.yaml" in readme


def test_dev_workloads_run_non_root_and_drop_capabilities():
    """数据面工作负载必须具备基础 Pod/容器安全上下文。"""
    targets = (
        ("data-services-dev.yaml", "sciminer-postgres"),
        ("data-services-dev.yaml", "sciminer-redis"),
        ("minio-dev.yaml", "sciminer-minio"),
        ("registry-dev.yaml", "sciminer-registry"),
    )
    for filename, name in targets:
        deployment = _resource(filename, "Deployment", name)
        pod_spec = deployment["spec"]["template"]["spec"]
        pod_security = pod_spec["securityContext"]
        assert pod_security["runAsNonRoot"] is True
        assert pod_security["seccompProfile"]["type"] == "RuntimeDefault"
        container_security = pod_spec["containers"][0]["securityContext"]
        assert container_security["runAsNonRoot"] is True
        assert container_security["allowPrivilegeEscalation"] is False
        assert container_security["capabilities"]["drop"] == ["ALL"]


def test_dev_network_policies_default_deny_and_allow_only_required_ports():
    """开发数据面必须有默认拒绝策略，且只放行必要端口。"""
    policies = _resources("network-policies-dev.yaml")
    by_name = {}
    for policy in policies:
        assert policy["kind"] == "NetworkPolicy"
        assert policy["spec"]["podSelector"]
        by_name.setdefault(policy["metadata"]["name"], []).append(policy)

    for name in (
        "sciminer-default-deny-data",
        "sciminer-default-deny-storage",
        "sciminer-allow-data-ingress",
        "sciminer-allow-storage-ingress",
        "sciminer-allow-dns-egress",
    ):
        assert name in by_name

    for policy in by_name["sciminer-default-deny-data"] + by_name[
        "sciminer-default-deny-storage"
    ]:
        assert set(policy["spec"]["policyTypes"]) == {"Ingress", "Egress"}
        assert "ingress" not in policy["spec"]
        assert "egress" not in policy["spec"]

    allowed_ports = {
        port["port"]
        for name in ("sciminer-allow-data-ingress", "sciminer-allow-storage-ingress")
        for policy in by_name[name]
        for rule in policy["spec"]["ingress"]
        for port in rule["ports"]
    }
    assert allowed_ports <= {5432, 6379, 9000, 9001, 5000}


# --- 4090 共享数据服务（deploy/k8s-dev/cnpharm-aidd） ---------------------------------
#
# 这组测试对应 #111：MinIO 集群里的 env / volumeMounts / command 曾经被一个只写了
# image 的覆盖清单 apply 掉，Pod 于是用镜像默认口令启动、桶也丢了挂载。回归防线就是
# 让「清单里少字段」在本地测试阶段直接失败，而不是等别人连环境时才发现。

SHARED_DEPLOY_ROOT = ROOT / "deploy" / "k8s-dev" / "cnpharm-aidd"
SHARED_CREDENTIALS_SECRET = "cnpharm-aidd-credentials"
SHARED_BUCKETS = (
    "scitool-files",
    "drp-assets",
    "drp-bulk",
    "drp-logs",
    "drp-models",
    "drp-results",
    "drp-temp",
)


def _shared_resources() -> list[tuple[str, dict]]:
    collected: list[tuple[str, dict]] = []
    for path in sorted(SHARED_DEPLOY_ROOT.glob("*.yaml")):
        content = path.read_text(encoding="utf-8")
        for item in yaml.safe_load_all(content):
            if item:
                collected.append((path.name, item))
    return collected


def _shared_resource(kind: str, name: str) -> dict:
    for filename, item in _shared_resources():
        if item.get("kind") == kind and item.get("metadata", {}).get("name") == name:
            return item
    raise AssertionError(f"missing {kind}/{name} under {SHARED_DEPLOY_ROOT}")


def test_shared_data_services_define_each_workload_once():
    """同一个 Deployment/Service/Job 只能出现在一个文件里。

    曾经用 `11-image-4090.yaml` 单独覆盖 minio 的镜像，`kubectl apply` 的三方合并
    把上一版有、这一版没写的字段全删了。只写 image 的覆盖文件一律不允许存在。
    """
    seen: dict[tuple[str, str], str] = {}
    for filename, item in _shared_resources():
        kind = item.get("kind")
        if kind not in {"Deployment", "Service", "Job", "StatefulSet"}:
            continue
        key = (kind, item["metadata"]["name"])
        assert key not in seen, f"{kind}/{key[1]} 在 {seen[key]} 与 {filename} 重复定义"
        seen[key] = filename


def test_shared_minio_keeps_secret_credentials_and_persistent_volume():
    """minio 必须挂 secret 凭据、挂 PVC、显式给启动命令。"""
    deployment = _shared_resource("Deployment", "cnpharm-minio")
    containers = deployment["spec"]["template"]["spec"]["containers"]
    assert len(containers) == 1
    container = containers[0]

    assert ":latest" not in container["image"]
    assert container.get("command"), "minio 容器缺少 command，会退回镜像默认 entrypoint"

    env_by_name = {entry["name"]: entry for entry in container.get("env", [])}
    for name in ("MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD"):
        secret_ref = env_by_name[name]["valueFrom"]["secretKeyRef"]
        assert secret_ref["name"] == SHARED_CREDENTIALS_SECRET
        assert secret_ref["key"] == name

    mounts = {mount["name"]: mount["mountPath"] for mount in container["volumeMounts"]}
    assert mounts.get("data") == "/data"
    volumes = {
        volume["name"]: volume.get("persistentVolumeClaim", {}).get("claimName")
        for volume in deployment["spec"]["template"]["spec"]["volumes"]
    }
    assert volumes.get("data") == "cnpharm-minio-data"


def test_shared_minio_init_job_recreates_buckets_idempotently():
    """建桶 Job 必须幂等，且覆盖平台会用到的全部 7 个桶。"""
    job = _shared_resource("Job", "cnpharm-minio-init")
    container = job["spec"]["template"]["spec"]["containers"][0]
    script = container["args"][-1]

    assert "mc mb --ignore-existing" in script
    for bucket in SHARED_BUCKETS:
        assert bucket in script, f"建桶脚本缺少 {bucket}"

    env_by_name = {entry["name"]: entry for entry in container.get("env", [])}
    for name in ("MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD"):
        assert env_by_name[name]["valueFrom"]["secretKeyRef"]["name"] == (
            SHARED_CREDENTIALS_SECRET
        )
