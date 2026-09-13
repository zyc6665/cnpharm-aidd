from __future__ import annotations

from app.services.workflow_node_states import initial_node_states  # noqa: E402


def test_initial_node_states_preserves_tool_and_artifact_metadata() -> None:
    definition = {
        "nodes": [
            {
                "id": "pocket_prediction",
                "kind": "tool",
                "tool_slug": "lvpocket-pocket-prediction",
                "tool_id": "tool-lvpocket",
                "tool_version": {"id": "version-lvpocket", "version": "2.0.0"},
                "semantic_inputs": {"protein": "workflow_input:protein_structure@1"},
                "artifact_inputs": {"protein": "workflow_input:protein_structure@1"},
                "artifact_input_slots": [
                    {"name": "protein", "type": "protein_structure@1", "required": True}
                ],
                "artifact_outputs": [
                    {"name": "pocket", "type": "binding_pocket@1", "required": True}
                ],
                "params": {"device": "auto"},
            }
        ],
    }

    states = initial_node_states(definition, ["pocket_prediction"])

    assert states == {
        "pocket_prediction": {
            "status": "pending",
            "tool_slug": "lvpocket-pocket-prediction",
            "tool_id": "tool-lvpocket",
            "tool_version_id": "version-lvpocket",
            "tool_version": {"id": "version-lvpocket", "version": "2.0.0"},
            "semantic_inputs": {"protein": "workflow_input:protein_structure@1"},
            "artifact_inputs": {"protein": "workflow_input:protein_structure@1"},
            "artifact_input_slots": [
                {"name": "protein", "type": "protein_structure@1", "required": True}
            ],
            "artifact_outputs": [
                {"name": "pocket", "type": "binding_pocket@1", "required": True}
            ],
            "params": {"device": "auto"},
        }
    }
