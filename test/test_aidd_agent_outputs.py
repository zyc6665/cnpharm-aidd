"""AIDD semantic output extraction tests."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.aidd.capabilities import CapabilityOutput, ToolCapability, get_capability  # noqa: E402
from app.agents.aidd.outputs import extract_semantic_outputs, parse_sdf_smiles  # noqa: E402


def test_extracts_output_file_by_extension_and_filename() -> None:
    outputs = extract_semantic_outputs(
        capability=get_capability("lvpocket-pocket-prediction"),
        task_output_files=[
            {
                "id": "file-log",
                "filename": "run.log",
                "content_type": "text/plain",
                "url": "/log",
            },
            {
                "id": "file-pocket",
                "filename": "best_pocket.pdb",
                "content_type": "chemical/x-pdb",
                "url": "/pdb",
            },
        ],
        output_data={},
    )

    assert outputs["pocket_pdb"]["file_id"] == "file-pocket"


def test_lvpocket_prefers_protein_pocket_residues_for_generation() -> None:
    outputs = extract_semantic_outputs(
        capability=get_capability("lvpocket-pocket-prediction"),
        task_output_files=[
            {
                "id": "file-pocket0",
                "filename": "artifacts__lv_results__input__pocket0.pdb",
                "content_type": "chemical/x-pdb",
                "url": "/pocket0",
            },
            {
                "id": "file-residues",
                "filename": "artifacts__lv_results__input__protein_pocket_residues.pdb",
                "content_type": "chemical/x-pdb",
                "url": "/residues",
            },
        ],
        output_data={},
    )

    assert outputs["pocket_pdb"]["file_id"] == "file-residues"


def test_extracts_output_data_by_path() -> None:
    outputs = extract_semantic_outputs(
        capability=get_capability("msign-affinity-prediction"),
        task_output_files=[],
        output_data={"result": {"outputs": {"prediction": {"predicted_affinity": 7.2}}}},
    )

    assert outputs["affinity_report"]["value"]["predicted_affinity"] == 7.2


def test_extracts_output_data_by_unwrapped_path_from_wrapped_task_result() -> None:
    capability = ToolCapability(
        tool_slug="dynamic-msign",
        capability="affinity_prediction",
        stage="affinity_prediction",
        inputs=(),
        outputs=(
            CapabilityOutput(
                "affinity_report",
                "output_data",
                path="outputs.prediction",
            ),
        ),
    )

    outputs = extract_semantic_outputs(
        capability=capability,
        task_output_files=[],
        output_data={"result": {"outputs": {"prediction": {"predicted_affinity": 6.4}}}},
    )

    assert outputs["affinity_report"]["value"]["predicted_affinity"] == 6.4


def test_parse_sdf_smiles_extracts_smiles_properties() -> None:
    smiles = parse_sdf_smiles(
        """
Mol A
  generated

> <SMILES>
CCO

$$$$
Mol B
  generated

> <canonical_smiles>
c1ccccc1

$$$$
"""
    )

    assert smiles == ["CCO", "c1ccccc1"]


def test_generation_output_can_expose_existing_smiles_csv_file() -> None:
    outputs = extract_semantic_outputs(
        capability=get_capability("gcdm-pocket-generation"),
        task_output_files=[
            {
                "id": "file-sdf",
                "filename": "generated_molecules.sdf",
                "content_type": "chemical/x-mdl-sdfile",
                "url": "/sdf",
            },
            {
                "id": "file-smiles",
                "filename": "generated_smiles.csv",
                "content_type": "text/csv",
                "url": "/csv",
            },
        ],
        output_data={},
    )

    assert outputs["generated_ligand"]["file_id"] == "file-sdf"
    assert outputs["smiles_csv"]["file_id"] == "file-smiles"
