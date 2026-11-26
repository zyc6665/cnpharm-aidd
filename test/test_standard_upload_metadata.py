from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.common.exceptions import ValidationException  # noqa: E402
from app.services.standard_upload_metadata import build_standard_upload_metadata  # noqa: E402


def _uploaded_file(tmp_path: Path, *, filename: str, content: bytes) -> SimpleNamespace:
    path = tmp_path / filename
    path.write_bytes(content)
    return SimpleNamespace(
        id=f"file-{filename}",
        filename=filename,
        sha256=hashlib.sha256(content).hexdigest(),
        storage_path=str(path),
    )


@pytest.mark.asyncio
async def test_molecule_table_upload_rejects_empty_csv(tmp_path: Path):
    uploaded_file = _uploaded_file(tmp_path, filename="molecules.csv", content=b"\n")

    with pytest.raises(ValidationException, match="标准 Artifact 上传内容无效"):
        await build_standard_upload_metadata(
            slot_name="molecules",
            standard_ref="molecule_table@1",
            uploaded_file=uploaded_file,
        )


@pytest.mark.asyncio
async def test_molecule_table_upload_rejects_invalid_json(tmp_path: Path):
    uploaded_file = _uploaded_file(tmp_path, filename="molecules.json", content=b"{")

    with pytest.raises(ValidationException, match="标准 Artifact 上传内容无效"):
        await build_standard_upload_metadata(
            slot_name="molecules",
            standard_ref="molecule_table@1",
            uploaded_file=uploaded_file,
        )


@pytest.mark.asyncio
async def test_protein_structure_upload_rejects_pdb_without_atoms(tmp_path: Path):
    uploaded_file = _uploaded_file(tmp_path, filename="protein.pdb", content=b"HEADER only\n")

    with pytest.raises(ValidationException, match="标准 Artifact 上传内容无效"):
        await build_standard_upload_metadata(
            slot_name="protein",
            standard_ref="protein_structure@1",
            uploaded_file=uploaded_file,
        )


@pytest.mark.asyncio
async def test_ligand_structure_upload_rejects_sdf_without_record_delimiter(tmp_path: Path):
    uploaded_file = _uploaded_file(tmp_path, filename="ligand.sdf", content=b"not an sdf\n")

    with pytest.raises(ValidationException, match="标准 Artifact 上传内容无效"):
        await build_standard_upload_metadata(
            slot_name="ligand",
            standard_ref="ligand_structure@1",
            uploaded_file=uploaded_file,
        )


@pytest.mark.asyncio
async def test_ligand_structure_upload_accepts_sdf(tmp_path: Path):
    uploaded_file = _uploaded_file(
        tmp_path,
        filename="fragment.sdf",
        content=b"fragment\n  RDKit\n\n  3  2  0  0  0  0  0  0  0  0999 V2000\nM  END\n$$$$\n",
    )

    metadata = await build_standard_upload_metadata(
        slot_name="fragment_sdf",
        standard_ref="ligand_structure@1",
        uploaded_file=uploaded_file,
    )

    assert metadata["ligand_id"] == "fragment"
    assert metadata["source_database"] == "manual"


@pytest.mark.asyncio
async def test_ligand_structure_upload_accepts_pdb_fragment(tmp_path: Path):
    uploaded_file = _uploaded_file(
        tmp_path,
        filename="fragment.pdb",
        content=b"HETATM    1  C1  LIG A   1       0.000   0.000   0.000  1.00  0.00           C\nEND\n",
    )

    metadata = await build_standard_upload_metadata(
        slot_name="fragment_sdf",
        standard_ref="ligand_structure@1",
        uploaded_file=uploaded_file,
    )

    assert metadata["ligand_id"] == "fragment"
    assert metadata["input_name"] == "fragment_sdf"


@pytest.mark.asyncio
async def test_ligand_structure_upload_accepts_mol_fragment(tmp_path: Path):
    uploaded_file = _uploaded_file(
        tmp_path,
        filename="fragment.mol",
        content=b"fragment\n  RDKit\n\n  3  2  0  0  0  0  0  0  0  0999 V2000\nM  END\n",
    )

    metadata = await build_standard_upload_metadata(
        slot_name="fragment_sdf",
        standard_ref="ligand_structure@1",
        uploaded_file=uploaded_file,
    )

    assert metadata["ligand_id"] == "fragment"


@pytest.mark.asyncio
async def test_ligand_structure_upload_accepts_mol2_fragment(tmp_path: Path):
    uploaded_file = _uploaded_file(
        tmp_path,
        filename="fragment.mol2",
        content=b"@<TRIPOS>MOLECULE\nfragment\n 3 2 0 0 0\n",
    )

    metadata = await build_standard_upload_metadata(
        slot_name="fragment_sdf",
        standard_ref="ligand_structure@1",
        uploaded_file=uploaded_file,
    )

    assert metadata["ligand_id"] == "fragment"


@pytest.mark.asyncio
async def test_ligand_structure_upload_rejects_pdb_fragment_without_atoms(tmp_path: Path):
    uploaded_file = _uploaded_file(tmp_path, filename="fragment.pdb", content=b"HEADER only\n")

    with pytest.raises(ValidationException, match="标准 Artifact 上传内容无效") as exc_info:
        await build_standard_upload_metadata(
            slot_name="fragment_sdf",
            standard_ref="ligand_structure@1",
            uploaded_file=uploaded_file,
        )

    assert exc_info.value.detail["reason"] == "ligand_structure@1 需要包含 ATOM 或 HETATM 记录"


@pytest.mark.asyncio
async def test_ligand_structure_upload_rejects_mol_without_end_marker(tmp_path: Path):
    uploaded_file = _uploaded_file(tmp_path, filename="fragment.mol", content=b"fragment\n")

    with pytest.raises(ValidationException, match="标准 Artifact 上传内容无效"):
        await build_standard_upload_metadata(
            slot_name="fragment_sdf",
            standard_ref="ligand_structure@1",
            uploaded_file=uploaded_file,
        )
