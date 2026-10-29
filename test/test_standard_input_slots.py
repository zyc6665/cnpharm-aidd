from types import SimpleNamespace

from app.services.standard_input_slots import (
    artifact_input_slots_by_name_for_tool,
    artifact_input_slots_for_run,
    tool_accepts_standard_input_bindings,
)
from app.tool_packages.schemas import TOOL_PACKAGE_API_VERSION


def test_artifact_input_slots_for_run_merges_contract_and_workflow_overrides():
    contract = {
        "artifacts": {
            "inputs": [
                {
                    "name": "protein",
                    "type": "protein_structure@1",
                    "required": True,
                },
                {
                    "name": "ligand",
                    "type": "ligand_structure@1",
                    "required": False,
                },
            ]
        }
    }
    workflow_node = {
        "artifact_input_slots": [
            {
                "name": "protein",
                "type": "protein_structure@1",
                "required": True,
                "role_preferences": ["prepared_pdb"],
            },
            {"name": "pocket", "type": "binding_pocket@1", "required": True},
        ]
    }

    slots = artifact_input_slots_for_run(contract, workflow_node)

    assert [slot["name"] for slot in slots] == ["protein", "ligand", "pocket"]
    assert slots[0]["role_preferences"] == ["prepared_pdb"]
    assert slots[1]["type"] == "ligand_structure@1"
    assert slots[2]["type"] == "binding_pocket@1"


def test_artifact_input_slots_by_name_for_tool_uses_contract_shape():
    tool_version = SimpleNamespace(
        config={
            "type": "remote_api",
            "artifacts": {
                "inputs": [
                    {
                        "name": "protein",
                        "type": "protein_structure@1",
                        "required": True,
                    },
                    "invalid",
                ]
            },
        }
    )
    tool = SimpleNamespace(
        id="tool-1",
        slug="remote-tool",
        name="Remote Tool",
        description=None,
        status="published",
        is_public=True,
    )

    slots = artifact_input_slots_by_name_for_tool(tool, tool_version)

    assert slots == {
        "protein": {
            "name": "protein",
            "type": "protein_structure@1",
            "required": True,
        }
    }


def test_tool_accepts_standard_input_bindings_for_v2_and_executor_contracts():
    assert tool_accepts_standard_input_bindings(
        {"tool_package_manifest": {"api_version": TOOL_PACKAGE_API_VERSION}}
    ) is True
    # 交付线移除了 remote_api 执行器，其旧契约不再被认作标准输入槽位来源。
    assert tool_accepts_standard_input_bindings(
        {
            "type": "remote_api",
            "artifacts": {
                "inputs": [{"name": "protein", "type": "protein_structure@1"}]
            },
        }
    ) is False
    assert tool_accepts_standard_input_bindings(
        {
            "type": "ssh_job",
            "artifacts": {
                "inputs": [{"name": "protein", "type": "protein_structure@1"}]
            },
        }
    ) is False
