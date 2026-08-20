"""RDKit molecular property table generation."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol


PROPERTY_COLUMNS = [
    "molecular_weight",
    "logp",
    "tpsa",
    "hbd",
    "hba",
    "rotatable_bonds",
    "heavy_atoms",
    "qed",
    "lipinski_violations",
]
STATUS_COLUMN = "rdkit_status"


class DescriptorBackend(Protocol):
    name: str
    version: str

    def molecule_from_smiles(self, smiles: str) -> Any | None: ...

    def descriptors(self, molecule: Any) -> dict[str, float | int]: ...


@dataclass(frozen=True)
class PropertyTableSummary:
    row_count: int
    valid_molecule_count: int
    invalid_molecule_count: int
    property_columns: list[str]
    backend_name: str
    backend_version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RDKitDescriptorBackend:
    def __init__(self) -> None:
        try:
            from rdkit import Chem, rdBase
            from rdkit.Chem import Crippen, Descriptors, QED, rdMolDescriptors
        except ImportError as exc:  # pragma: no cover - depends on runtime image
            raise RuntimeError(
                "RDKit is required for rdkit-molecular-properties. "
                "Install the declared runtime image or conda environment."
            ) from exc
        self._chem = Chem
        self._crippen = Crippen
        self._descriptors = Descriptors
        self._qed = QED
        self._rd_mol_descriptors = rdMolDescriptors
        self.name = "RDKit"
        self.version = rdBase.rdkitVersion

    def molecule_from_smiles(self, smiles: str):
        return self._chem.MolFromSmiles(smiles)

    def descriptors(self, molecule) -> dict[str, float | int]:
        values = {
            "molecular_weight": float(self._descriptors.MolWt(molecule)),
            "logp": float(self._crippen.MolLogP(molecule)),
            "tpsa": float(self._rd_mol_descriptors.CalcTPSA(molecule)),
            "hbd": int(self._rd_mol_descriptors.CalcNumHBD(molecule)),
            "hba": int(self._rd_mol_descriptors.CalcNumHBA(molecule)),
            "rotatable_bonds": int(self._rd_mol_descriptors.CalcNumRotatableBonds(molecule)),
            "heavy_atoms": int(molecule.GetNumHeavyAtoms()),
            "qed": float(self._qed.qed(molecule)),
        }
        values["lipinski_violations"] = _lipinski_violations(values)
        return values


def calculate_properties_table(
    *,
    input_csv: Path,
    output_csv: Path,
    molecule_id_field: str,
    smiles_field: str,
    backend: DescriptorBackend | None = None,
) -> PropertyTableSummary:
    backend = backend or RDKitDescriptorBackend()
    with input_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("Molecule table must include a header row")
        _require_columns(reader.fieldnames, [molecule_id_field, smiles_field])
        rows = list(reader)

    fieldnames = _output_fieldnames(reader.fieldnames)
    valid_count = 0
    invalid_count = 0
    output_dir = output_csv.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            output_row = dict(row)
            smiles = str(row.get(smiles_field) or "").strip()
            molecule = backend.molecule_from_smiles(smiles) if smiles else None
            if molecule is None:
                invalid_count += 1
                output_row.update({column: "" for column in PROPERTY_COLUMNS})
                output_row[STATUS_COLUMN] = "invalid_smiles"
                writer.writerow(output_row)
                continue
            descriptors = backend.descriptors(molecule)
            valid_count += 1
            for column in PROPERTY_COLUMNS:
                output_row[column] = _format_value(descriptors[column])
            output_row[STATUS_COLUMN] = "ok"
            writer.writerow(output_row)

    return PropertyTableSummary(
        row_count=len(rows),
        valid_molecule_count=valid_count,
        invalid_molecule_count=invalid_count,
        property_columns=list(PROPERTY_COLUMNS),
        backend_name=backend.name,
        backend_version=backend.version,
    )


def _require_columns(fieldnames: list[str], required: list[str]) -> None:
    missing = [column for column in required if column not in fieldnames]
    if missing:
        raise ValueError("Molecule table missing required columns: " + ", ".join(missing))


def _output_fieldnames(input_fieldnames: list[str]) -> list[str]:
    fieldnames = list(input_fieldnames)
    for column in [*PROPERTY_COLUMNS, STATUS_COLUMN]:
        if column not in fieldnames:
            fieldnames.append(column)
    return fieldnames


def _format_value(value: float | int) -> str:
    if isinstance(value, int):
        return str(value)
    return f"{value:.4f}"


def _lipinski_violations(values: dict[str, float | int]) -> int:
    checks = (
        values["molecular_weight"] > 500,
        values["logp"] > 5,
        values["hbd"] > 5,
        values["hba"] > 10,
    )
    return sum(1 for failed in checks if failed)
