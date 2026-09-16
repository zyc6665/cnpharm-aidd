from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.remote_tools.inputs import (
    RemoteToolInputError,
    artifact_version_ref,
    remote_artifact_input_declarations,
    remote_artifact_input_payload,
    remote_example_input_refs,
    standard_input_bindings,
    validate_remote_artifact_input,
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


def test_artifact_version_ref_prefers_standard_fields_then_manifest_type() -> None:
    assert artifact_version_ref(SimpleNamespace(
        id="version-1",
        artifact=SimpleNamespace(standard_type="protein_structure", standard_version=1),
        manifest_json={},
    )) == "protein_structure@1"
    assert artifact_version_ref(SimpleNamespace(
        id="version-2",
        artifact=None,
        manifest_json={"type": "ligand_structure@1"},
    )) == "ligand_structure@1"

    with pytest.raises(RemoteToolInputError, match="not a standard ArtifactVersion"):
        artifact_version_ref(SimpleNamespace(id="version-3", artifact=None, manifest_json={}))


def test_validate_remote_artifact_input_checks_type_and_required_roles() -> None:
    declaration = {"name": "protein", "type": "protein_structure@1"}
    valid_version = SimpleNamespace(
        id="version-1",
        artifact=SimpleNamespace(standard_type="protein_structure", standard_version=1),
        manifest_json={},
        files=[
            SimpleNamespace(role="structure_file"),
            SimpleNamespace(role="metadata_json"),
        ],
    )

    validate_remote_artifact_input(declaration, valid_version)

    with pytest.raises(RemoteToolInputError, match="expects protein_structure@1"):
        validate_remote_artifact_input(
            declaration,
            SimpleNamespace(
                id="version-2",
                artifact=SimpleNamespace(standard_type="ligand_structure", standard_version=1),
                manifest_json={},
                files=[SimpleNamespace(role="structure_file")],
            ),
        )

    with pytest.raises(RemoteToolInputError, match="missing required file roles: metadata_json"):
        validate_remote_artifact_input(
            declaration,
            SimpleNamespace(
                id="version-3",
                artifact=SimpleNamespace(standard_type="protein_structure", standard_version=1),
                manifest_json={},
                files=[SimpleNamespace(role="structure_file")],
            ),
        )


def test_remote_artifact_input_payload_sorts_files_and_copies_manifest_metadata() -> None:
    version = SimpleNamespace(
        id="version-1",
        artifact=SimpleNamespace(standard_type="protein_structure", standard_version=1),
        manifest_json={"metadata": {"chain": "A"}},
        files=[
            SimpleNamespace(
                role="metadata_json",
                sort_order=1,
                file=SimpleNamespace(id="file-metadata", filename="metadata.json"),
            ),
            SimpleNamespace(
                role="structure_file",
                sort_order=0,
                file=SimpleNamespace(id="file-structure", filename="protein.pdb"),
            ),
        ],
    )

    payload = remote_artifact_input_payload(
        declaration={"name": "protein", "type": "protein_structure@1"},
        version=version,
        file_payload=lambda file_record: {"filename": file_record.filename},
    )

    assert payload == {
        "artifact_version_id": "version-1",
        "type": "protein_structure@1",
        "files": {
            "structure_file": {"filename": "protein.pdb"},
            "metadata_json": {"filename": "metadata.json"},
        },
        "metadata": {"chain": "A"},
    }

    version.files[0].file = None
    with pytest.raises(RemoteToolInputError, match="role metadata_json has no file record"):
        remote_artifact_input_payload(
            declaration={"name": "protein", "type": "protein_structure@1"},
            version=version,
            file_payload=lambda file_record: {"filename": file_record.filename},
        )
