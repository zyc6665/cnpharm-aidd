"""Protein preparation option schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ProteinPreparationOutputFormat = Literal[
    "prepared_pdb",
    "receptor_pdbqt",
    "prepared_pqr",
]


class ProteinPreparationOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ph: float = Field(default=7.4, ge=0, le=14)
    remove_water: bool = True
    keep_metals: bool = True
    keep_cofactors: bool = True
    remove_non_target_ligands: bool = True
    output_formats: list[ProteinPreparationOutputFormat] = Field(
        default_factory=lambda: ["prepared_pdb", "receptor_pdbqt"]
    )
