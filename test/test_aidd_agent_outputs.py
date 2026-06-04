"""AIDD semantic output extraction tests."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.aidd.capabilities import get_capability  # noqa: E402
from app.agents.aidd.outputs import extract_semantic_outputs  # noqa: E402


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
