"""Protein preparation engine tests."""

from __future__ import annotations

from pathlib import Path

from app.protein_preparation import engine
from app.schemas.protein_preparation import ProteinPreparationOptions


def test_prepare_protein_removes_water_and_returns_requested_roles(tmp_path, monkeypatch):
    source = tmp_path / "raw.pdb"
    source.write_text(
        "ATOM      1  N   ALA A   1       0.000   0.000   0.000\n"
        "HETATM    2  O   HOH A 101       1.000   1.000   1.000\n"
        "END\n",
        encoding="utf-8",
    )

    def fake_convert(prepared_pdb: Path, receptor_pdbqt: Path, *, rigid: bool):
        assert rigid is True
        assert "HOH" not in prepared_pdb.read_text(encoding="utf-8")
        receptor_pdbqt.write_text("REMARK receptor pdbqt\n", encoding="utf-8")

    monkeypatch.setattr(engine, "convert_prepared_pdb_to_pdbqt", fake_convert)

    result = engine.prepare_protein(
        source,
        ProteinPreparationOptions(remove_water=True),
        advanced_options={"chain_selection": ["A"]},
        output_dir=tmp_path / "out",
    )

    assert set(result.files) == {"prepared_pdb", "receptor_pdbqt"}
    assert "HOH" not in result.files["prepared_pdb"].path.read_text(encoding="utf-8")
    assert result.files["receptor_pdbqt"].content_type == "chemical/x-pdbqt"
    assert result.report["options"]["ph"] == 7.4
    assert result.report["advanced_options"] == {"chain_selection": ["A"]}


def test_prepare_protein_can_emit_prepared_pdb_without_external_conversion(tmp_path):
    source = tmp_path / "raw.pdb"
    source.write_text(
        "ATOM      1  N   ALA A   1       0.000   0.000   0.000\n"
        "HETATM    2  O   WAT A 101       1.000   1.000   1.000\n"
        "END\n",
        encoding="utf-8",
    )

    result = engine.prepare_protein(
        source,
        ProteinPreparationOptions(output_formats=["prepared_pdb"]),
        advanced_options=None,
        output_dir=tmp_path / "out",
    )

    assert set(result.files) == {"prepared_pdb"}
    assert "WAT" not in result.files["prepared_pdb"].path.read_text(encoding="utf-8")
    assert result.warnings == []


def test_convert_prepared_pdb_to_pdbqt_uses_rigid_openbabel_option(
    tmp_path,
    monkeypatch,
):
    source = tmp_path / "prepared.pdb"
    target = tmp_path / "receptor.pdbqt"
    source.write_text("ATOM      1  N   ALA A   1       0.000   0.000   0.000\nEND\n")
    captured: dict[str, list[str]] = {}

    class FakeCompletedProcess:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(argv, *, capture_output, text, check):
        captured["argv"] = argv
        target.write_text("REMARK receptor pdbqt\n", encoding="utf-8")
        return FakeCompletedProcess()

    monkeypatch.setattr(engine.shutil, "which", lambda name: "/usr/bin/obabel")
    monkeypatch.setattr(engine.subprocess, "run", fake_run)

    engine.convert_prepared_pdb_to_pdbqt(source, target, rigid=True)

    assert captured["argv"] == [
        "/usr/bin/obabel",
        "-ipdb",
        str(source),
        "-opdbqt",
        "-O",
        str(target),
        "-xr",
    ]

