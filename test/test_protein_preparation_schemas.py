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
    assert data.fill_missing_side_chains is True
    assert data.fill_missing_loops is True
    assert data.add_hydrogens is True
    assert data.optimize_hydrogen_bonding is True
    assert data.energy_minimization is True


def test_preparation_options_reject_unknown_output_format():
    with pytest.raises(ValidationError):
        ProteinPreparationOptions.model_validate({"output_formats": ["mol2"]})


def test_preparation_options_rejects_removed_proprietary_engine():
    with pytest.raises(ValidationError):
        ProteinPreparationOptions.model_validate({"engine": "proprietary"})
