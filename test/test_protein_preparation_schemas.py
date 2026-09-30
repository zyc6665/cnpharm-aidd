"""Protein preparation API schema tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.protein_preparation import ProteinPreparationOptions


def test_preparation_options_accept_supported_settings():
    data = ProteinPreparationOptions.model_validate(
        {
            "ph": 7.4,
            "remove_water": True,
            "keep_metals": True,
            "keep_cofactors": True,
            "remove_non_target_ligands": True,
            "output_formats": ["prepared_pdb", "receptor_pdbqt"],
        }
    )

    assert data.ph == 7.4
    assert data.output_formats == ["prepared_pdb", "receptor_pdbqt"]


def test_preparation_options_reject_unknown_output_format():
    with pytest.raises(ValidationError):
        ProteinPreparationOptions.model_validate({"output_formats": ["mol2"]})
