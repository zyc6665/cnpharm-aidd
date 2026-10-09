"""Infer internal AIDD semantic file roles from uploaded files."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path

from app.files.content import read_file_bytes
from app.models.files import File as FileModel


@dataclass(frozen=True)
class ClassifiedInputFile:
    semantic_type: str
    file: FileModel
    confidence: float
    reason: str


async def _read_text_sample(file_record: FileModel, max_bytes: int = 8192) -> str:
    if not file_record.storage_path:
        return ""
    try:
        content = await read_file_bytes(file_record)
    except FileNotFoundError:
        return ""
    return content[:max_bytes].decode("utf-8", errors="ignore")


def _csv_has_smiles_column(sample: str) -> bool:
    if not sample.strip():
        return False
    try:
        rows = csv.reader(io.StringIO(sample))
        header = next(rows, [])
    except csv.Error:
        return False
    return any(cell.strip().lower() in {"smiles", "canonical_smiles"} for cell in header)


async def classify_aidd_input_file(
    file_record: FileModel,
    *,
    message: str,
    used_semantic_types: set[str] | None = None,
) -> ClassifiedInputFile:
    used = used_semantic_types or set()
    filename = file_record.filename.lower()
    suffix = Path(filename).suffix.lower()
    content_type = (file_record.content_type or "").lower()
    sample = await _read_text_sample(file_record)
    lowered_message = message.lower()

    if suffix == ".csv" or "csv" in content_type:
        if _csv_has_smiles_column(sample) or "smiles" in filename:
            return ClassifiedInputFile("smiles_csv", file_record, 0.96, "CSV contains a SMILES column")
        return ClassifiedInputFile("smiles_csv", file_record, 0.62, "CSV is treated as molecule table input")

    if suffix == ".sdf" or "mdl-sdfile" in content_type:
        return ClassifiedInputFile("generated_ligand", file_record, 0.94, "SDF can be converted to SMILES")

    if suffix in {".pdb", ".ent", ".cif"} or "pdb" in content_type:
        pocket_markers = ("pocket", "binding_site", "binding-site", "active_site", "active-site", "site")
        ligand_markers = ("ligand", "pose", "dock", "docked", "compound", "molecule")
        protein_markers = ("protein", "receptor", "target", "enzyme", "complex")

        if any(marker in filename for marker in pocket_markers):
            return ClassifiedInputFile("pocket_pdb", file_record, 0.92, "filename looks like a pocket structure")
        if any(marker in filename for marker in ligand_markers):
            return ClassifiedInputFile("ligand_pdb", file_record, 0.9, "filename looks like a ligand structure")
        if any(marker in filename for marker in protein_markers):
            return ClassifiedInputFile("protein_pdb", file_record, 0.9, "filename looks like a protein structure")

        atom_count = sample.count("\nATOM")
        hetatm_count = sample.count("\nHETATM")
        if hetatm_count > 0 and atom_count == 0:
            return ClassifiedInputFile("ligand_pdb", file_record, 0.82, "PDB has ligand-like HETATM records")
        if atom_count > 0:
            return ClassifiedInputFile("protein_pdb", file_record, 0.78, "PDB has protein-like ATOM records")

        if "配体" in lowered_message or "ligand" in lowered_message:
            if "ligand_pdb" not in used:
                return ClassifiedInputFile("ligand_pdb", file_record, 0.68, "message mentions ligand")
        if "口袋" in lowered_message or "pocket" in lowered_message:
            if "pocket_pdb" not in used:
                return ClassifiedInputFile("pocket_pdb", file_record, 0.68, "message mentions pocket")

        semantic_type = "ligand_pdb" if "protein_pdb" in used and "ligand_pdb" not in used else "protein_pdb"
        return ClassifiedInputFile(semantic_type, file_record, 0.55, "fallback PDB role assignment")

    return ClassifiedInputFile("protein_pdb", file_record, 0.35, "fallback structural input")
