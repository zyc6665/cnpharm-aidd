"""只读 K8s 算力总览：节点 GPU 与 model-jobs 命名空间内的 Job/Pod。

当前平台执行走 k8s_job（GPU 以 ``nvidia.com/gpu`` 申请），不使用 slots.yaml；
本模块通过平台已有的 out-of-cluster kubeconfig 直连 K8s API，为管理后台「算力队列」提供真实数据。
"""
from __future__ import annotations

import logging
import os
import ssl
import tempfile
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.config import settings
from app.execution.transports.kubernetes_kubeconfig import load_kubeconfig_credentials

logger = logging.getLogger(__name__)

GPU_RESOURCE = "nvidia.com/gpu"


def _gpu_quantity(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _node_roles(metadata: Dict[str, Any]) -> List[str]:
    labels = metadata.get("labels") or {}
    roles = [
        key.split("/", 1)[1]
        for key in labels
        if key.startswith("node-role.kubernetes.io/")
    ]
    return roles or ["worker"]


def _node_ready(node: Dict[str, Any]) -> bool:
    for condition in (node.get("status") or {}).get("conditions") or []:
        if condition.get("type") == "Ready":
            return condition.get("status") == "True"
    return False


def _pod_gpu(pod: Dict[str, Any]) -> int:
    total = 0
    for container in (pod.get("spec") or {}).get("containers") or []:
        requests = ((container.get("resources") or {}).get("requests") or {})
        total += _gpu_quantity(requests.get(GPU_RESOURCE))
    return total


def _build_client(credentials: Any) -> Tuple[httpx.AsyncClient, List[str]]:
    temp_files: List[str] = []
    verify: Any = True
    if credentials.certificate_authority:
        verify = ssl.create_default_context(cadata=credentials.certificate_authority)
    cert: Any = None
    if credentials.client_certificate and credentials.client_key:
        cert_file = tempfile.NamedTemporaryFile("w", suffix=".crt", delete=False)
        key_file = tempfile.NamedTemporaryFile("w", suffix=".key", delete=False)
        cert_file.write(credentials.client_certificate)
        key_file.write(credentials.client_key)
        cert_file.close()
        key_file.close()
        temp_files.extend([cert_file.name, key_file.name])
        cert = (cert_file.name, key_file.name)
    headers = {"Accept": "application/json"}
    if credentials.token:
        headers["Authorization"] = "Bearer %s" % credentials.token
    client = httpx.AsyncClient(
        base_url=str(credentials.api_server or "").rstrip("/"),
        verify=verify,
        cert=cert,
        headers=headers,
        timeout=float(getattr(settings, "K8S_ADAPTER_REQUEST_TIMEOUT_SECONDS", 30) or 30),
        trust_env=bool(getattr(settings, "K8S_ADAPTER_TRUST_ENV", False)),
    )
    return client, temp_files


async def build_k8s_compute_overview() -> Dict[str, Any]:
    kubeconfig_path = getattr(settings, "K8S_ADAPTER_KUBECONFIG", None)
    namespace = getattr(settings, "K8S_ADAPTER_NAMESPACE", None) or "sciminer-model-jobs"
    cluster_alias = getattr(settings, "K8S_ADAPTER_CLUSTER_ALIAS", None)
    if not kubeconfig_path or not os.path.exists(kubeconfig_path):
        return {
            "configured": False,
            "clusterAlias": cluster_alias,
            "namespace": namespace,
            "reason": "未配置 K8S_ADAPTER_KUBECONFIG",
            "nodes": [],
            "pods": [],
            "jobs": [],
            "gpuCapacity": 0,
            "gpuAllocatable": 0,
            "gpuAllocated": 0,
            "runningJobs": 0,
            "nodeCount": 0,
        }

    credentials = load_kubeconfig_credentials(
        kubeconfig_path,
        context=getattr(settings, "K8S_ADAPTER_KUBECONFIG_CONTEXT", None),
    )
    client, temp_files = _build_client(credentials)
    try:
        nodes_payload = (await client.get("/api/v1/nodes")).json()
        pods_payload = (await client.get("/api/v1/namespaces/%s/pods" % namespace)).json()
        jobs_payload = (
            await client.get("/apis/batch/v1/namespaces/%s/jobs" % namespace)
        ).json()
    finally:
        await client.aclose()
        for path in temp_files:
            try:
                os.unlink(path)
            except OSError:
                pass

    nodes: List[Dict[str, Any]] = []
    gpu_capacity = 0
    gpu_allocatable = 0
    for node in nodes_payload.get("items") or []:
        status = node.get("status") or {}
        capacity = status.get("capacity") or {}
        allocatable = status.get("allocatable") or {}
        cap = _gpu_quantity(capacity.get(GPU_RESOURCE))
        alloc = _gpu_quantity(allocatable.get(GPU_RESOURCE))
        gpu_capacity += cap
        gpu_allocatable += alloc
        nodes.append(
            {
                "name": (node.get("metadata") or {}).get("name"),
                "ready": _node_ready(node),
                "roles": _node_roles(node.get("metadata") or {}),
                "gpuCapacity": cap,
                "gpuAllocatable": alloc,
                "cpu": allocatable.get("cpu"),
                "memory": allocatable.get("memory"),
                "os": status.get("nodeInfo", {}).get("osImage"),
                "kubeletVersion": status.get("nodeInfo", {}).get("kubeletVersion"),
                "createdAt": (node.get("metadata") or {}).get("creationTimestamp"),
            }
        )

    pods: List[Dict[str, Any]] = []
    gpu_allocated = 0
    running_pods = 0
    for pod in pods_payload.get("items") or []:
        phase = (pod.get("status") or {}).get("phase")
        gpu = _pod_gpu(pod)
        active = phase in {"Pending", "Running"}
        if active:
            gpu_allocated += gpu
            running_pods += 1
        metadata = pod.get("metadata") or {}
        labels = metadata.get("labels") or {}
        pods.append(
            {
                "name": metadata.get("name"),
                "phase": phase,
                "node": (pod.get("spec") or {}).get("nodeName"),
                "gpu": gpu,
                "jobName": labels.get("job-name"),
                "startTime": (pod.get("status") or {}).get("startTime"),
            }
        )

    jobs: List[Dict[str, Any]] = []
    running_jobs = 0
    for job in jobs_payload.get("items") or []:
        status = job.get("status") or {}
        active = int(status.get("active") or 0)
        if active > 0:
            running_jobs += 1
        jobs.append(
            {
                "name": (job.get("metadata") or {}).get("name"),
                "active": active,
                "succeeded": int(status.get("succeeded") or 0),
                "failed": int(status.get("failed") or 0),
                "startTime": status.get("startTime"),
                "completionTime": status.get("completionTime"),
            }
        )

    pods.sort(key=lambda item: (item.get("phase") not in {"Running", "Pending"}, item.get("name") or ""))
    return {
        "configured": True,
        "clusterAlias": cluster_alias,
        "namespace": namespace,
        "apiServer": credentials.api_server,
        "nodeCount": len(nodes),
        "gpuCapacity": gpu_capacity,
        "gpuAllocatable": gpu_allocatable,
        "gpuAllocated": gpu_allocated,
        "runningPods": running_pods,
        "runningJobs": running_jobs,
        "nodes": nodes,
        "pods": pods[:50],
        "jobs": jobs[:50],
    }
