"""Public Tool Contract projection for managed resource profiles."""


def test_k8s_tool_contract_exposes_profile_id_without_inline_limits():
    from types import SimpleNamespace

    from app.services.tool_contracts import build_tool_contract

    tool = SimpleNamespace(
        id="tool-1",
        slug="managed-model",
        name="Managed model",
        description="Model",
        status="published",
        is_public=False,
        current_version=SimpleNamespace(
            id="version-1",
            version="1.0.0",
            is_active=True,
            deprecated=False,
            config={
                "type": "k8s_job",
                "resource_profile": "gpu-large",
                "input_schema": {"type": "object", "properties": {}},
                "output_schema": {"type": "object", "properties": {}},
            },
        ),
    )

    contract = build_tool_contract(tool)

    assert contract["executor"]["type"] == "k8s_job"
    assert contract["resource_profile"] == {"id": "gpu-large"}
