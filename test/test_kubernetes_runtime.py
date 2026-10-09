"""Kubernetes worker runtime bootstrap tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_in_cluster_provider_reads_service_account_credentials(tmp_path: Path):
    from app.execution.transports.kubernetes_runtime import InClusterSecretProvider

    token_file = tmp_path / "token"
    ca_file = tmp_path / "ca.crt"
    token_file.write_text("worker-token\n", encoding="utf-8")
    ca_file.write_text("CA DATA\n", encoding="utf-8")
    provider = InClusterSecretProvider(
        credential_ref="platform-k8s",
        api_server="https://kubernetes.default.svc",
        token_file=token_file,
        ca_file=ca_file,
    )

    credentials = await provider.resolve("platform-k8s")

    assert credentials.api_server == "https://kubernetes.default.svc"
    assert credentials.token == "worker-token"
    assert credentials.certificate_authority == "CA DATA\n"


@pytest.mark.asyncio
async def test_in_cluster_provider_rejects_wrong_reference_and_missing_files(tmp_path: Path):
    from app.execution.transports.kubernetes_runtime import (
        KubernetesCredentialConfigurationError,
        InClusterSecretProvider,
    )

    provider = InClusterSecretProvider(
        credential_ref="platform-k8s",
        api_server="https://kubernetes.default.svc",
        token_file=tmp_path / "missing-token",
        ca_file=tmp_path / "missing-ca",
    )

    with pytest.raises(KubernetesCredentialConfigurationError, match="credential reference"):
        await provider.resolve("other-cluster")
    with pytest.raises(KubernetesCredentialConfigurationError, match="ServiceAccount"):
        await provider.resolve("platform-k8s")


def test_runtime_factory_keeps_k8s_disabled_by_default(monkeypatch):
    from app.config import Settings
    from app.execution.transports.kubernetes_runtime import build_kubernetes_runtime

    settings = Settings(EXECUTOR_ENABLED_K8S=False)
    runtime = build_kubernetes_runtime(settings)

    assert runtime is None


def test_runtime_factory_requires_all_platform_bindings_when_enabled():
    from app.config import Settings
    from app.execution.transports.kubernetes_runtime import (
        KubernetesCredentialConfigurationError,
        build_kubernetes_runtime,
    )

    settings = Settings(
        EXECUTOR_ENABLED_K8S=True,
        K8S_ADAPTER_CLUSTER_ALIAS="platform",
        K8S_ADAPTER_NAMESPACE="model-jobs",
        K8S_ADAPTER_CREDENTIAL_REF="platform-k8s",
        K8S_ADAPTER_SERVICE_ACCOUNT="model-runner",
    )

    with pytest.raises(KubernetesCredentialConfigurationError, match="ServiceAccount"):
        build_kubernetes_runtime(settings)


def test_worker_runtime_configurator_does_not_replace_gateway_when_disabled():
    from app.execution.runtime import get_execution_service
    from app.worker.celery_app import configure_managed_execution_runtime

    original = get_execution_service()

    runtime = configure_managed_execution_runtime()

    assert runtime is None
    assert get_execution_service() is original


def test_direct_runtime_configurator_is_gated_by_direct_execution(monkeypatch):
    import app.main as main

    calls = []
    sentinel = object()

    monkeypatch.setattr(main, "use_direct_task_execution", lambda: True)
    monkeypatch.setattr(
        main,
        "configure_managed_execution_runtime",
        lambda: calls.append("configured") or sentinel,
    )

    assert main.configure_direct_managed_execution_runtime() is sentinel
    assert calls == ["configured"]


def test_direct_runtime_configurator_does_not_touch_managed_gateway_when_not_direct(monkeypatch):
    import app.main as main

    calls = []
    monkeypatch.setattr(main, "use_direct_task_execution", lambda: False)
    monkeypatch.setattr(
        main,
        "configure_managed_execution_runtime",
        lambda: calls.append("configured"),
    )

    assert main.configure_direct_managed_execution_runtime() is None
    assert calls == []
