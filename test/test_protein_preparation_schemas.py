"""Protein preparation API schema tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.protein_preparation import ProteinPreparationRequest


def test_preparation_request_accepts_basic_options_and_advanced_extension():
    data = ProteinPreparationRequest.model_validate(
        {
            "artifact_id": "artifact-1",
            "source_node_id": "artifact-node-1",
            "position": {"x": 320, "y": 120},
            "preparation_profile": "docking_v1",
            "options": {
                "ph": 7.4,
                "remove_water": True,
                "keep_metals": True,
                "keep_cofactors": True,
                "remove_non_target_ligands": True,
                "output_formats": ["prepared_pdb", "receptor_pdbqt"],
            },
            "advanced_options": {"chain_selection": ["A"]},
        }
    )

    assert data.options.ph == 7.4
    assert data.options.output_formats == ["prepared_pdb", "receptor_pdbqt"]
    assert data.advanced_options == {"chain_selection": ["A"]}


def test_preparation_request_rejects_unknown_output_format():
    with pytest.raises(ValidationError):
        ProteinPreparationRequest.model_validate(
            {
                "artifact_id": "artifact-1",
                "preparation_profile": "docking_v1",
                "options": {"output_formats": ["mol2"]},
            }
        )

