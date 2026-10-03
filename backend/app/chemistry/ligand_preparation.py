"""RDKit-backed ligand normalization and library preparation."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from app.common.exceptions import ValidationException
from app.schemas.ligand_preparation import LigandPreparationOptions


@dataclass(frozen=True)
class LigandInputRecord:
    source_index: int
    smiles: str
    name: str


@dataclass(frozen=True)
class PreparedLigandRecord:
    source_index: int
    name: str
    input_smiles: str
    canonical_smiles: str
    inchi_key: str
    molecular_weight: float
    formal_charge: int
    heavy_atoms: int
    has_3d: bool
    molecule: Any


@dataclass(frozen=True)
class LigandPreparationResult:
    records: tuple[PreparedLigandRecord, ...]
    stats: dict[str, int]
    backend_name: str
    backend_version: str
    rejected_records: tuple[dict[str, Any], ...] = ()


def prepare_ligand_library(
    source_path: Path,
    options: LigandPreparationOptions,
) -> LigandPreparationResult:
    """Normalize a SMILES library and return molecules ready for downstream use."""
    backend = _rdkit_backend()
    input_records = tuple(_read_input_records(source_path, options))
    stats = {
        "input_count": len(input_records),
        "valid_count": 0,
        "output_count": 0,
        "invalid_count": 0,
        "filtered_by_molecular_weight": 0,
        "filtered_by_pains": 0,
        "filtered_by_duplicate": 0,
        "filtered_by_inchikey_failure": 0,
        "filtered_by_3d_failure": 0,
    }
    records: list[PreparedLigandRecord] = []
    rejected_records: list[dict[str, Any]] = []
    seen_inchi_keys: set[str] = set()

    for input_record in input_records:
        try:
            molecule = backend.molecule_from_smiles(input_record.smiles)
        except Exception:
            stats["invalid_count"] += 1
            rejected_records.append(
                {
                    "source_index": input_record.source_index,
                    "name": input_record.name,
                    "reason": "molecule_read_failed",
                }
            )
            continue
        if molecule is None:
            stats["invalid_count"] += 1
            rejected_records.append({"source_index": input_record.source_index, "name": input_record.name, "reason": "invalid_smiles"})
            continue

        try:
            normalized = backend.normalize(molecule, options)
            canonical_smiles = backend.to_smiles(normalized)
        except Exception:
            stats["invalid_count"] += 1
            rejected_records.append({"source_index": input_record.source_index, "name": input_record.name, "reason": "normalization_failed"})
            continue

        stats["valid_count"] += 1
        try:
            inchi_key = _molecule_inchi_key(normalized)
        except Exception:
            inchi_key = ""
        if not inchi_key:
            stats["filtered_by_inchikey_failure"] += 1
            rejected_records.append({"source_index": input_record.source_index, "name": input_record.name, "reason": "inchikey_failed"})
            continue
        if options.remove_duplicates and inchi_key in seen_inchi_keys:
            stats["filtered_by_duplicate"] += 1
            rejected_records.append({"source_index": input_record.source_index, "name": input_record.name, "reason": "duplicate", "inchi_key": inchi_key})
            continue

        molecular_weight = float(backend.molecular_weight(normalized))
        if (
            options.min_molecular_weight is not None
            and molecular_weight < options.min_molecular_weight
        ) or (
            options.max_molecular_weight is not None
            and molecular_weight > options.max_molecular_weight
        ):
            stats["filtered_by_molecular_weight"] += 1
            rejected_records.append({"source_index": input_record.source_index, "name": input_record.name, "reason": "molecular_weight", "molecular_weight": molecular_weight})
            continue

        if options.remove_pains and backend.is_pains(normalized):
            stats["filtered_by_pains"] += 1
            rejected_records.append({"source_index": input_record.source_index, "name": input_record.name, "reason": "pains"})
            continue

        has_3d = True
        if options.generate_3d:
            try:
                has_3d = backend.generate_3d(normalized, options)
            except Exception:
                has_3d = False
            if not has_3d and options.drop_3d_failures:
                stats["filtered_by_3d_failure"] += 1
                rejected_records.append({"source_index": input_record.source_index, "name": input_record.name, "reason": "3d_generation_failed"})
                continue

        seen_inchi_keys.add(inchi_key)
        records.append(
            PreparedLigandRecord(
                source_index=input_record.source_index,
                name=input_record.name,
                input_smiles=input_record.smiles,
                canonical_smiles=canonical_smiles,
                inchi_key=inchi_key,
                molecular_weight=molecular_weight,
                formal_charge=int(backend.formal_charge(normalized)),
                heavy_atoms=int(backend.heavy_atoms(normalized)),
                has_3d=has_3d,
                molecule=normalized,
            )
        )

    stats["output_count"] = len(records)
    return LigandPreparationResult(
        records=tuple(records),
        stats=stats,
        rejected_records=tuple(rejected_records),
        backend_name="RDKit",
        backend_version=backend.version,
    )


def _read_input_records(
    source_path: Path,
    options: LigandPreparationOptions,
) -> Iterable[LigandInputRecord]:
    if not source_path.exists() or not source_path.is_file():
        raise ValidationException("小分子输入文件不存在")

    suffix = source_path.suffix.lower()
    text = source_path.read_text(encoding="utf-8-sig", errors="replace")
    if suffix == ".json":
        yield from _read_json_records(text, options)
        return
    if suffix == ".csv" or _looks_like_csv(text):
        yield from _read_csv_records(text, options)
        return
    yield from _read_smiles_records(text)


def _read_csv_records(text: str, options: LigandPreparationOptions) -> Iterable[LigandInputRecord]:
    reader = csv.DictReader(text.splitlines())
    fieldnames = [str(item) for item in (reader.fieldnames or [])]
    smiles_field = _find_field(fieldnames, options.smiles_column, ("smiles", "smi", "canonical_smiles"))
    if not smiles_field:
        raise ValidationException("CSV 中未找到 SMILES 列")
    name_field = _find_field(fieldnames, options.name_column, ("name", "id", "molecule_id"))
    for source_index, row in enumerate(reader, start=1):
        smiles = str(row.get(smiles_field) or "").strip()
        if smiles:
            yield LigandInputRecord(
                source_index=source_index,
                smiles=smiles,
                name=str(row.get(name_field) or f"mol_{source_index}") if name_field else f"mol_{source_index}",
            )


def _read_json_records(text: str, options: LigandPreparationOptions) -> Iterable[LigandInputRecord]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationException("JSON 小分子输入格式无效") from exc
    rows = payload.get("molecules", payload) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValidationException("JSON 小分子输入必须是数组或 molecules 数组")
    for source_index, row in enumerate(rows, start=1):
        if isinstance(row, str):
            smiles, name = _split_smiles_line(row)
        elif isinstance(row, dict):
            smiles = str(row.get(options.smiles_column) or row.get("smiles") or "").strip()
            name = str(row.get(options.name_column or "name") or row.get("id") or f"mol_{source_index}")
        else:
            continue
        if smiles:
            yield LigandInputRecord(source_index, smiles, name)


def _read_smiles_records(text: str) -> Iterable[LigandInputRecord]:
    for source_index, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if source_index == 1 and stripped.split()[0].lower() in {"smiles", "smi", "canonical_smiles"}:
            continue
        smiles, name = _split_smiles_line(stripped)
        if smiles:
            yield LigandInputRecord(source_index, smiles, name or f"mol_{source_index}")


def _split_smiles_line(line: str) -> tuple[str, str]:
    parts = line.split(None, 1)
    return parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""


def _find_field(fieldnames: list[str], preferred: str | None, fallbacks: tuple[str, ...]) -> str | None:
    candidates = [preferred, *fallbacks]
    normalized = {field.casefold(): field for field in fieldnames}
    for candidate in candidates:
        if candidate and candidate.casefold() in normalized:
            return normalized[candidate.casefold()]
    return None


def _looks_like_csv(text: str) -> bool:
    first_line = next((line for line in text.splitlines() if line.strip()), "")
    return "," in first_line or "\t" in first_line


def _molecule_inchi_key(molecule: Any) -> str:
    from rdkit.Chem import inchi

    return str(inchi.MolToInchiKey(molecule) or "").strip()


class _RDKitBackend:
    def __init__(self) -> None:
        from rdkit import Chem, rdBase
        from rdkit.Chem import AllChem, Descriptors, FilterCatalog
        from rdkit.Chem.MolStandardize import rdMolStandardize

        self.chem = Chem
        self.all_chem = AllChem
        self.descriptors = Descriptors
        self.standardize = rdMolStandardize
        self.pains_catalog = self._build_pains_catalog(FilterCatalog)
        self.version = rdBase.rdkitVersion

    @staticmethod
    def _build_pains_catalog(filter_catalog_module: Any) -> Any:
        params = filter_catalog_module.FilterCatalogParams()
        params.AddCatalog(params.FilterCatalogs.PAINS)
        return filter_catalog_module.FilterCatalog(params)

    def molecule_from_smiles(self, smiles: str) -> Any:
        return self.chem.MolFromSmiles(smiles)

    def normalize(self, molecule: Any, options: LigandPreparationOptions) -> Any:
        normalized = self.chem.Mol(molecule)
        if options.remove_explicit_hydrogens:
            normalized = self.chem.RemoveHs(normalized)
        if options.normalize_structure:
            normalized = self.standardize.Normalizer().normalize(normalized)
        if options.reionize:
            normalized = self.standardize.Reionizer().reionize(normalized)
        if options.neutralize:
            normalized = self.standardize.Uncharger().uncharge(normalized)
        if options.remove_disconnected_fragments:
            normalized = self.standardize.LargestFragmentChooser().choose(normalized)
        self.chem.SanitizeMol(normalized)
        return normalized

    def to_smiles(self, molecule: Any) -> str:
        return str(self.chem.MolToSmiles(molecule, canonical=True))

    def molecular_weight(self, molecule: Any) -> float:
        return float(self.descriptors.MolWt(molecule))

    def formal_charge(self, molecule: Any) -> int:
        return int(self.chem.GetFormalCharge(molecule))

    def heavy_atoms(self, molecule: Any) -> int:
        return int(molecule.GetNumHeavyAtoms())

    def is_pains(self, molecule: Any) -> bool:
        return bool(self.pains_catalog.HasMatch(molecule))

    def generate_3d(self, molecule: Any, options: LigandPreparationOptions) -> bool:
        molecule_with_hydrogens = self.chem.AddHs(molecule)
        embedding_options = self.all_chem.ETKDGv3()
        embedding_options.randomSeed = int(options.conformer_seed)
        if self.all_chem.EmbedMolecule(molecule_with_hydrogens, embedding_options) != 0:
            return False
        if options.forcefield == "mmff":
            if not self.all_chem.MMFFHasAllMoleculeParams(molecule_with_hydrogens):
                return False
            self.all_chem.MMFFOptimizeMolecule(molecule_with_hydrogens)
        else:
            self.all_chem.UFFOptimizeMolecule(molecule_with_hydrogens)
        dehydrogenated = self.chem.RemoveHs(molecule_with_hydrogens)
        molecule.RemoveAllConformers()
        molecule.AddConformer(dehydrogenated.GetConformer(), assignId=True)
        return molecule.GetNumConformers() > 0


def _rdkit_backend() -> _RDKitBackend:
    try:
        return _RDKitBackend()
    except ImportError as exc:
        raise ValidationException("RDKit 未安装，无法执行小分子规范化") from exc


def prepared_molecule_table_csv(result: LigandPreparationResult) -> bytes:
    output = io.StringIO()
    fieldnames = [
        "molecule_id",
        "name",
        "input_smiles",
        "canonical_smiles",
        "inchi_key",
        "molecular_weight",
        "formal_charge",
        "heavy_atoms",
        "has_3d",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for index, record in enumerate(result.records, start=1):
        writer.writerow(
            {
                "molecule_id": f"mol_{index}",
                "name": record.name,
                "input_smiles": record.input_smiles,
                "canonical_smiles": record.canonical_smiles,
                "inchi_key": record.inchi_key,
                "molecular_weight": f"{record.molecular_weight:.4f}",
                "formal_charge": record.formal_charge,
                "heavy_atoms": record.heavy_atoms,
                "has_3d": str(record.has_3d).lower(),
            }
        )
    return output.getvalue().encode("utf-8")


def prepared_ligand_sdf_content(result: LigandPreparationResult) -> bytes:
    from rdkit import Chem

    records: list[str] = []
    for record in result.records:
        molecule = Chem.Mol(record.molecule)
        molecule.SetProp("_Name", record.name)
        records.append(Chem.MolToMolBlock(molecule).rstrip() + "\n$$$$")
    return ("\n".join(records) + ("\n" if records else "")).encode("utf-8")


def preparation_metadata(result: LigandPreparationResult, *, source_file: str) -> dict[str, Any]:
    return {
        "molecule_id_field": "molecule_id",
        "source_task_id": source_file,
        "source_filename": source_file,
        "row_count": result.stats["output_count"],
        "input_count": result.stats["input_count"],
        "valid_molecule_count": result.stats["valid_count"],
        "backend_name": result.backend_name,
        "backend_version": result.backend_version,
    }
