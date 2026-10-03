"""Ligand preparation option schema tests."""

from __future__ import annotations

from pydantic import ValidationError
import pytest

from app.schemas.ligand_preparation import LigandPreparationOptions


def test_ligand_preparation_options_have_safe_defaults() -> None:
    options = LigandPreparationOptions()

    assert options.remove_explicit_hydrogens is True
    assert options.remove_disconnected_fragments is True
    assert options.neutralize is True
    assert options.remove_pains is True
    assert options.remove_duplicates is True
    assert options.generate_3d is True


def test_ligand_preparation_rejects_invalid_molecular_weight_range() -> None:
    with pytest.raises(ValidationError):
        LigandPreparationOptions(min_molecular_weight=500, max_molecular_weight=100)
