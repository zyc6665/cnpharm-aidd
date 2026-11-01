"""MSIGN SMILES -> 3D SDF 适配层测试（离线，不依赖平台/GPU）。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from rdkit import Chem


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SMILES_TO_SDF = (
    PROJECT_ROOT
    / "deploy"
    / "kubernetes"
    / "model-image-template"
    / "platform_adaptor"
    / "smiles_to_sdf.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("smiles_to_sdf", SMILES_TO_SDF)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_pdb(path: Path) -> list[tuple[float, float, float]]:
    atoms = [
        ("CA", "ALA", 1, 10.000, 10.000, 10.000),
        ("CB", "ALA", 1, 14.000, 10.000, 10.000),
        ("CA", "GLY", 2, 30.000, 30.000, 30.000),
    ]
    lines = []
    for index, (name, resname, resseq, x, y, z) in enumerate(atoms, start=1):
        lines.append(
            f"ATOM  {index:5d} {name:<4s}{resname:>3s} A{resseq:4d}    "
            f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00           C"
        )
    lines.append("END")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [(a[3], a[4], a[5]) for a in atoms]


def test_protein_centroid_returns_existing_atom_not_hollow_center(tmp_path: Path):
    module = _load_module()
    protein = tmp_path / "protein.pdb"
    coords = _write_pdb(protein)

    anchor = module._protein_centroid(protein)

    # 质心是 (18, 16.67, 16.67)，落在蛋白外部；锚点必须是某个真实原子坐标。
    assert anchor in coords


def test_convert_writes_valid_molecules_and_reports_parse_failures(tmp_path: Path):
    module = _load_module()
    protein = tmp_path / "protein.pdb"
    coords = _write_pdb(protein)
    csv_path = tmp_path / "ligands.csv"
    csv_path.write_text(
        "molecule_id,SMILES\naspirin,CC(=O)Oc1ccccc1C(=O)O\nbroken,C1CC\n",
        encoding="utf-8",
    )
    sdf_path = tmp_path / "out.sdf"
    errors_path = tmp_path / "errors.json"

    summary = module.convert(
        csv_path,
        sdf_path,
        errors_path,
        smiles_column=None,
        id_column=None,
        max_molecules=10,
        random_seed=42,
        center_from_protein=protein,
    )

    assert summary["requested_count"] == 2
    assert summary["written_count"] == 1
    assert summary["failed_count"] == 1
    assert summary["errors"][0]["molecule_id"] == "broken"
    assert sdf_path.is_file()
    supplier = Chem.SDMolSupplier(str(sdf_path), removeHs=False)
    molecules = [m for m in supplier if m is not None]
    assert len(molecules) == 1
    conformer = molecules[0].GetConformer()
    cx = sum(conformer.GetAtomPosition(i).x for i in range(molecules[0].GetNumAtoms()))
    cy = sum(conformer.GetAtomPosition(i).y for i in range(molecules[0].GetNumAtoms()))
    cz = sum(conformer.GetAtomPosition(i).z for i in range(molecules[0].GetNumAtoms()))
    n = molecules[0].GetNumAtoms()
    centroid = (cx / n, cy / n, cz / n)
    # 配体应被放到某个蛋白重原子附近（medoid 锚点），而不是原点。
    nearest = min(
        abs(centroid[0] - c[0]) + abs(centroid[1] - c[1]) + abs(centroid[2] - c[2])
        for c in coords
    )
    assert nearest < 3.0
    assert "broken" in errors_path.read_text(encoding="utf-8")


def test_convert_without_protein_centers_near_origin(tmp_path: Path):
    module = _load_module()
    csv_path = tmp_path / "ligands.csv"
    csv_path.write_text("molecule_id,SMILES\nethane,CC\n", encoding="utf-8")
    sdf_path = tmp_path / "out.sdf"

    summary = module.convert(
        csv_path,
        sdf_path,
        tmp_path / "errors.json",
        smiles_column=None,
        id_column=None,
        max_molecules=10,
        random_seed=42,
        center_from_protein=None,
    )

    assert summary["written_count"] == 1
    molecule = next(iter(Chem.SDMolSupplier(str(sdf_path), removeHs=False)))
    conformer = molecule.GetConformer()
    xs = [conformer.GetAtomPosition(i).x for i in range(molecule.GetNumAtoms())]
    assert max(abs(x) for x in xs) < 2.0
