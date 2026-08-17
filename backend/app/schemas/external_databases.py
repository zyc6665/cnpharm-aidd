"""External database import API schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.research_boards import BoardPosition


ExternalDatabaseSource = Literal["pubchem", "rcsb"]
ExternalDatabaseEntityType = Literal["ligand", "protein"]


class ExternalDatabaseImportRequest(BaseModel):
    source: ExternalDatabaseSource
    entity_type: ExternalDatabaseEntityType
    identifier: str = Field(min_length=1, max_length=160)
    board_id: str | None = Field(default=None, min_length=1, max_length=36)
    position: BoardPosition | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_source_entity_pair(self):
        if self.source == "pubchem" and self.entity_type != "ligand":
            raise ValueError("PubChem import only supports ligand entities")
        if self.source == "rcsb" and self.entity_type != "protein":
            raise ValueError("RCSB import only supports protein entities")
        return self
