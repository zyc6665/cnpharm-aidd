"""Semantic validation for managed K8s Job tool contracts."""


def test_k8s_job_is_a_supported_tool_executor_type():
    from app.services.tool_contract_validation import collect_tool_contract_config_validation_errors

    errors = collect_tool_contract_config_validation_errors(
        tool_slug="managed-model",
        config={
            "type": "k8s_job",
            "runtime": {"image": f"registry.example/model@sha256:{'a' * 64}"},
            "resource_profile": "gpu-large",
        },
    )

    assert not any("executor.type" in error for error in errors)


def test_k8s_job_contract_rejects_tool_selected_cluster_credentials():
    from app.services.tool_contract_validation import collect_tool_contract_config_validation_errors

    errors = collect_tool_contract_config_validation_errors(
        tool_slug="managed-model",
        config={
            "type": "k8s_job",
            "resource_profile": "gpu-large",
            "runtime": {"image": f"registry.example/model@sha256:{'a' * 64}"},
            "namespace": "other-tenant",
        },
    )

    assert "k8s_job.namespace is platform-managed" in errors


def test_k8s_job_contract_rejects_unregistered_resource_profile():
    from app.services.tool_contract_validation import collect_tool_contract_config_validation_errors

    errors = collect_tool_contract_config_validation_errors(
        tool_slug="managed-model",
        config={
            "type": "k8s_job",
            "runtime": {"image": f"registry.example/model@sha256:{'a' * 64}"},
            "resource_profile": "unknown-profile",
        },
    )

    assert "k8s_job.resource_profile is not registered: unknown-profile" in errors
