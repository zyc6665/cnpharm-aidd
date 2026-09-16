from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.remote_tools.inputs import (
    remote_artifact_input_declarations,
    remote_example_input_refs,
    standard_input_bindings,
)


def test_remote_example_input_refs_returns_only_dict_payloads() -> None:
    assert remote_example_input_refs(None) == {}
    assert remote_example_input_refs({"remote_example_inputs": []}) == {}
    assert remote_example_input_refs({
        "remote_example_inputs": {
            "protein": {"type": "protein_structure@1"},
        }
    }) == {"protein": {"type": "protein_structure@1"}}


def test_standard_input_bindings_normalizes_non_empty_string_keys_and_values() -> None:
    assert standard_input_bindings(None) == {}
    assert standard_input_bindings({"input_bindings": []}) == {}
    assert standard_input_bindings({
        "input_bindings": {
            " protein ": " artifact-version-1 ",
            "": "ignored",
            "ligand": "",
            123: 456,
        }
    }) == {" protein ": " artifact-version-1 ", "123": "456"}


def test_remote_artifact_input_declarations_keeps_manifest_dict_items_only() -> None:
    assert remote_artifact_input_declarations({}) == []
    assert remote_artifact_input_declarations({"artifacts": {"inputs": "protein"}}) == []
    assert remote_artifact_input_declarations({
        "artifacts": {
            "inputs": [
                {"name": "protein", "type": "protein_structure@1"},
                "ignored",
                {"name": "ligand", "type": "ligand_structure@1", "required": False},
            ]
        }
    }) == [
        {"name": "protein", "type": "protein_structure@1"},
        {"name": "ligand", "type": "ligand_structure@1", "required": False},
    ]
