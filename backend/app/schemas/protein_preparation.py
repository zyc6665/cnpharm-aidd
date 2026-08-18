"""Protein preparation request schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.research_boards import BoardPosition


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


class ProteinPreparationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(min_length=1, max_length=36)
    artifact_version_id: str | None = Field(default=None, min_length=1, max_length=36)
    source_node_id: str | None = Field(default=None, min_length=1, max_length=120)
    position: BoardPosition | None = None
    preparation_profile: Literal["docking_v1"] = "docking_v1"
    options: ProteinPreparationOptions = Field(default_factory=ProteinPreparationOptions)
    advanced_options: dict[str, Any] = Field(default_factory=dict)

