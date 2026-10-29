"""Standard execution request/result envelope contract tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.execution.standard_contracts import (
    DeclaredArtifactOutput,
    StandardExecutionContractError,
    StandardExecutionRequest,
    StandardExecutionResult,
    safe_output_relative_path,
    validate_result_against_declared_outputs,
)


def test_request_inputs_are_keyed_by_manifest_input_name():
    request = StandardExecutionRequest.model_validate(
        {
            "request_version": "aidd.sciminer/request",
            "task": {
                "id": "task-1",
                "tool_slug": "pocket2mol",
                "tool_version": "1.0.0",
            },
            "inputs": {
                "pocket": {
                    "artifact_version_id": "artifact-version-1",
                    "type": "binding_pocket@1",
                    "files": {
                        "atom_pocket_pdb": {
                            "path": "input/pocket/atom.pdb",
                            "sha256": "a" * 64,
                        },
                    },
                    "metadata": {"center": [0, 0, 0]},
                }
            },
            "parameters": {"num_samples": 2},
            "execution": {
                "variant": "cuda",
                "accelerator": "nvidia_cuda",
                "work_dir": ".",
                "output_dir": "output",
            },
        }
    )

    assert list(request.inputs) == ["pocket"]
    assert request.inputs["pocket"].type == "binding_pocket@1"
    assert request.inputs["pocket"].files["atom_pocket_pdb"].path == "input/pocket/atom.pdb"


def test_result_artifact_keys_must_match_declared_output_names():
    result = StandardExecutionResult.model_validate(
        {
            "result_version": "aidd.sciminer/result",
            "artifacts": {
                "pocket": {
                    "type": "binding_pocket@1",
                    "files": {
                        "residue_pocket_pdb": {"path": "pocket/residue.pdb", "sha256": "b" * 64},
                        "atom_pocket_pdb": {"path": "pocket/atom.pdb", "sha256": "c" * 64},
                        "pocket_metadata_json": {
                            "path": "pocket/metadata.json",
                            "sha256": "d" * 64,
                        },
                    },
                }
            },
        }
    )
    declarations = [DeclaredArtifactOutput(name="pocket", type="binding_pocket@1")]

    validate_result_against_declared_outputs(result, declarations)

    with pytest.raises(StandardExecutionContractError, match="Unexpected output artifact"):
        validate_result_against_declared_outputs(
            result,
            [DeclaredArtifactOutput(name="pockets", type="binding_pocket@1")],
        )


def test_cardinality_many_output_accepts_a_list_of_artifacts():
    result = StandardExecutionResult.model_validate(
        {
            "result_version": "aidd.sciminer/result",
            "artifacts": {
                "generated_ligands": [
                    {
                        "name": "ligand_001",
                        "type": "ligand_structure@1",
                        "files": {
                            "structure_file": {"path": "ligands/001.sdf", "sha256": "e" * 64}
                        },
                    }
                ]
            },
        }
    )

    validate_result_against_declared_outputs(
        result,
        [
            DeclaredArtifactOutput(
                name="generated_ligands",
                type="ligand_structure@1",
                cardinality="many",
            )
        ],
    )

    with pytest.raises(StandardExecutionContractError, match="must be a single artifact"):
        validate_result_against_declared_outputs(
            result,
            [DeclaredArtifactOutput(name="generated_ligands", type="ligand_structure@1")],
        )


def test_output_paths_reject_absolute_and_parent_traversal():
    assert safe_output_relative_path("artifacts/pocket.pdb") == "artifacts/pocket.pdb"

    for unsafe_path in ("/etc/passwd", "../secret.txt", "artifacts/../../secret.txt"):
        with pytest.raises(StandardExecutionContractError, match="Unsafe output path"):
            safe_output_relative_path(unsafe_path)
        with pytest.raises(ValidationError):
            StandardExecutionResult.model_validate(
                {
                    "result_version": "aidd.sciminer/result",
                    "artifacts": {
                        "report": {
                            "type": "run_report@1",
                            "files": {
                                "report_json": {
                                    "path": unsafe_path,
                                    "sha256": "f" * 64,
                                }
                            },
                        }
                    },
                }
            )


def test_result_rejects_legacy_artifact_type_aliases():
    result = StandardExecutionResult.model_validate(
        {
            "result_version": "aidd.sciminer/result",
            "artifacts": {
                "pocket": {
                    "type": "pocket_pdb",
                    "files": {
                        "atom_pocket_pdb": {"path": "pocket/atom.pdb", "sha256": "1" * 64}
                    },
                }
            },
        }
    )

    with pytest.raises(StandardExecutionContractError, match="Unknown standard artifact type"):
        validate_result_against_declared_outputs(
            result,
            [DeclaredArtifactOutput(name="pocket", type="binding_pocket@1")],
        )
