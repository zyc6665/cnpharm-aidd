"""AIDD builtin tool unit tests."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.aidd import builtin_tools  # noqa: E402


def test_sdf_to_smiles_csv_uses_molp_compatible_header() -> None:
    content = builtin_tools._smiles_csv_content(["CCO"]).decode("utf-8")

    assert content == "SMILES,id\nCCO,mol_1\n"


def test_vina_receptor_pdbqt_conversion_uses_rigid_openbabel_option(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "protein.pdb"
    target = tmp_path / "protein.pdbqt"
    source.write_text("ATOM      1  N   ALA A   1       0.000   0.000   0.000\nEND\n")
    commands: list[list[str]] = []

    monkeypatch.setattr(builtin_tools.shutil, "which", lambda name: f"/usr/bin/{name}")

    def fake_run(argv, **kwargs):
        commands.append(list(argv))
        target.write_text("REMARK receptor\n")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(builtin_tools.subprocess, "run", fake_run)

    builtin_tools._convert_pdb_to_pdbqt(source, target, rigid=True)

    assert "-xr" in commands[0]


def test_vina_ligand_pdbqt_conversion_keeps_torsion_tree(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "ligand.pdb"
    target = tmp_path / "ligand.pdbqt"
    source.write_text("HETATM    1  C1  LIG A   1       0.000   0.000   0.000\nEND\n")
    commands: list[list[str]] = []

    monkeypatch.setattr(builtin_tools.shutil, "which", lambda name: f"/usr/bin/{name}")

    def fake_run(argv, **kwargs):
        commands.append(list(argv))
        target.write_text("ROOT\nENDROOT\n")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(builtin_tools.subprocess, "run", fake_run)

    builtin_tools._convert_pdb_to_pdbqt(source, target, rigid=False)

    assert "-xr" not in commands[0]


def test_vina_ligand_models_are_split_for_batch_ranking(tmp_path: Path) -> None:
    ligand = tmp_path / "ligands.pdb"
    ligand.write_text(
        "\n".join(
            [
                "MODEL        1",
                "HETATM    1  C1  LIG A   1       1.000   2.000   3.000",
                "ENDMDL",
                "MODEL        2",
                "HETATM    1  C1  LIG A   1       4.000   5.000   6.000",
                "ENDMDL",
                "END",
            ]
        )
        + "\n"
    )

    split_paths = builtin_tools._split_ligand_pdb_models(ligand, tmp_path)

    assert [path.name for path in split_paths] == ["ligand_1.pdb", "ligand_2.pdb"]
    assert "MODEL" not in split_paths[0].read_text()
    assert "ENDMDL" not in split_paths[0].read_text()
    assert "1.000   2.000   3.000" in split_paths[0].read_text()
    assert "4.000   5.000   6.000" in split_paths[1].read_text()
