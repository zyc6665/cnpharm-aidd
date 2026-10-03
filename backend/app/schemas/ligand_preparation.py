"""Ligand preparation option schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LigandPreparationOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    smiles_column: str = Field(default="SMILES", min_length=1, max_length=128)
    name_column: str | None = Field(default=None, max_length=128)
    remove_explicit_hydrogens: bool = True
    remove_disconnected_fragments: bool = True
    normalize_structure: bool = True
    reionize: bool = True
    neutralize: bool = True
    remove_pains: bool = True
    remove_duplicates: bool = True
    min_molecular_weight: float | None = Field(default=None, ge=0)
    max_molecular_weight: float | None = Field(default=None, ge=0)
    generate_3d: bool = True
    drop_3d_failures: bool = True
    forcefield: Literal["uff", "mmff"] = "uff"
    conformer_seed: int = 20260930

    @model_validator(mode="after")
    def validate_molecular_weight_range(self) -> "LigandPreparationOptions":
        if (
            self.min_molecular_weight is not None
            and self.max_molecular_weight is not None
            and self.min_molecular_weight > self.max_molecular_weight
        ):
            raise ValueError("min_molecular_weight 不能大于 max_molecular_weight")
        return self
