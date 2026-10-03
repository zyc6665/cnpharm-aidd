"""RDKit ligand preparation behavior tests."""

from __future__ import annotations

from pathlib import Path

from app.chemistry.ligand_preparation import prepare_ligand_library
from app.schemas.ligand_preparation import LigandPreparationOptions


def test_ligand_preparation_normalizes_filters_and_deduplicates(tmp_path: Path) -> None:
    source = tmp_path / "molecules.smi"
    source.write_text(
        "CCO ethanol\n"
        "C[NH+](C)C.Cl dimethylammonium\n"
        "C[NH+](C)C.Cl duplicate\n"
        "not-a-smiles broken\n",
        encoding="utf-8",
    )

    result = prepare_ligand_library(
        source,
        LigandPreparationOptions(
            min_molecular_weight=50,
            max_molecular_weight=80,
            remove_pains=True,
            remove_duplicates=True,
            generate_3d=True,
        ),
    )

    assert [record.name for record in result.records] == ["dimethylammonium"]
    assert result.records[0].canonical_smiles == "CN(C)C"
    assert result.records[0].inchi_key
    assert result.records[0].has_3d is True
    assert result.stats == {
        "input_count": 4,
        "valid_count": 3,
        "output_count": 1,
        "invalid_count": 1,
        "filtered_by_molecular_weight": 1,
        "filtered_by_pains": 0,
        "filtered_by_duplicate": 1,
        "filtered_by_3d_failure": 0,
        "filtered_by_inchikey_failure": 0,
    }


def test_ligand_preparation_drops_molecules_without_inchikey_or_3d(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "molecules.txt"
    source.write_text("CCO ethanol\n", encoding="utf-8")

    monkeypatch.setattr(
        "app.chemistry.ligand_preparation._molecule_inchi_key",
        lambda _molecule: "",
    )

    result = prepare_ligand_library(source, LigandPreparationOptions())

    assert result.records == ()
    assert result.stats["filtered_by_inchikey_failure"] == 1


def test_ligand_preparation_skips_smiles_reader_failures_and_continues(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from app.chemistry.ligand_preparation import _RDKitBackend

    source = tmp_path / "molecules.smi"
    source.write_text("CCO reader-failure\nCCN valid\n", encoding="utf-8")
    original_reader = _RDKitBackend.molecule_from_smiles

    def read_molecule(backend, smiles: str):
        if smiles == "CCO":
            raise ValueError("molecule parse failed")
        return original_reader(backend, smiles)

    monkeypatch.setattr(_RDKitBackend, "molecule_from_smiles", read_molecule)

    result = prepare_ligand_library(
        source,
        LigandPreparationOptions(generate_3d=False),
    )

    assert [record.name for record in result.records] == ["valid"]
    assert result.stats["invalid_count"] == 1
    assert result.rejected_records[0]["reason"] == "molecule_read_failed"


def test_ligand_preparation_counts_inchikey_exceptions_as_key_failures(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "molecules.smi"
    source.write_text("CCO ethanol\n", encoding="utf-8")

    def fail_inchikey(_molecule):
        raise RuntimeError("InChI backend failed")

    monkeypatch.setattr(
        "app.chemistry.ligand_preparation._molecule_inchi_key",
        fail_inchikey,
    )

    result = prepare_ligand_library(source, LigandPreparationOptions())

    assert result.records == ()
    assert result.stats["filtered_by_inchikey_failure"] == 1
    assert result.stats["invalid_count"] == 0
    assert result.rejected_records[0]["reason"] == "inchikey_failed"


def test_ligand_preparation_skips_3d_generation_exceptions_and_continues(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from app.chemistry.ligand_preparation import _RDKitBackend

    source = tmp_path / "molecules.smi"
    source.write_text("CCO failed\nCCCC valid\n", encoding="utf-8")
    original_generator = _RDKitBackend.generate_3d

    def generate_conformer(backend, molecule, options):
        if molecule.GetNumHeavyAtoms() == 3:
            raise RuntimeError("conformer generation failed")
        return original_generator(backend, molecule, options)

    monkeypatch.setattr(_RDKitBackend, "generate_3d", generate_conformer)

    result = prepare_ligand_library(source, LigandPreparationOptions())

    assert [record.name for record in result.records] == ["valid"]
    assert result.stats["filtered_by_3d_failure"] == 1
    assert result.rejected_records[0]["reason"] == "3d_generation_failed"
