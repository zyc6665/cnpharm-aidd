"""Protein preparation engine tests."""

from __future__ import annotations

from pathlib import Path

import pytest

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
    # 缺 obabel 时引擎会跳过 PDBQT（只记 warning），这条用例要覆盖「有 obabel」那条路
    monkeypatch.setattr(engine.shutil, "which", lambda name: "/usr/bin/obabel")
    monkeypatch.setattr(
        engine,
        "_run_open_source_preparation",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            engine.OpenSourcePreparationUnavailable("PDBFixer 不可用")
        ),
    )

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


def test_prepare_protein_can_emit_prepared_pdb_without_external_conversion(tmp_path, monkeypatch):
    source = tmp_path / "raw.pdb"
    source.write_text(
        "ATOM      1  N   ALA A   1       0.000   0.000   0.000\n"
        "HETATM    2  O   WAT A 101       1.000   1.000   1.000\n"
        "END\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        engine,
        "_run_open_source_preparation",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            engine.OpenSourcePreparationUnavailable("未安装开源蛋白修复依赖 PDBFixer，请安装 backend/requirements.txt")
        ),
    )
    result = engine.prepare_protein(
        source,
        ProteinPreparationOptions(output_formats=["prepared_pdb"]),
        advanced_options=None,
        output_dir=tmp_path / "out",
    )

    assert set(result.files) == {"prepared_pdb"}
    assert "WAT" not in result.files["prepared_pdb"].path.read_text(encoding="utf-8")
    assert result.report["fallback_reason"] == "未安装开源蛋白修复依赖 PDBFixer，请安装 backend/requirements.txt"
    assert result.warnings


def test_prepare_protein_auto_fallback_reports_unexecuted_advanced_steps(tmp_path, monkeypatch):
    source = tmp_path / "raw.pdb"
    source.write_text(
        "ATOM      1  N   ALA A   1       0.000   0.000   0.000\n"
        "END\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        engine,
        "_run_open_source_preparation",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            engine.OpenSourcePreparationUnavailable("PDBFixer 不可用")
        ),
    )

    result = engine.prepare_protein(
        source,
        ProteinPreparationOptions(output_formats=["prepared_pdb"]),
        output_dir=tmp_path / "out",
    )

    assert result.report["fallback_reason"] == "PDBFixer 不可用"
    assert result.report["warnings"] == result.warnings
    assert any("缺失侧链" in warning for warning in result.warnings)
    assert any("能量最小化" in warning for warning in result.warnings)


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


def test_prepare_protein_report_declares_open_source_backend(tmp_path, monkeypatch):
    source = tmp_path / "raw.pdb"
    source.write_text("ATOM      1  N   ALA A   1       0.000   0.000   0.000\nEND\n")
    monkeypatch.setattr(
        engine,
        "_run_open_source_preparation",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            engine.OpenSourcePreparationUnavailable("PDBFixer 不可用")
        ),
    )

    result = engine.prepare_protein(
        source,
        ProteinPreparationOptions(output_formats=["prepared_pdb"]),
        output_dir=tmp_path / "out",
    )

    assert result.report["engine"] == "open-source-basic-fallback"
    assert result.report["implementation"] == "open-source"
    assert result.report["status"] == "degraded"


def test_prepare_protein_keeps_prepared_pdb_when_obabel_is_missing(tmp_path, monkeypatch):
    """缺 obabel 只该少一个 PDBQT 产物，不该把整次制备判为失败。

    真机现象：结构详情页点「结构准备」，任务 10 秒就 failed，错误是
    「未知错误：蛋白制备需要 obabel 将 prepared PDB 转为 receptor PDBQT」——
    而 prepared.pdb 其实已经算出来了。环境缺件要写进 warnings / missing_tools，
    让用户看到「产物在、对接准备没做完」，而不是一句失败。
    """
    source = tmp_path / "raw.pdb"
    source.write_text("ATOM      1  N   ALA A   1       0.000   0.000   0.000\nEND\n")
    monkeypatch.setattr(
        engine,
        "_run_open_source_preparation",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            engine.OpenSourcePreparationUnavailable("PDBFixer 不可用")
        ),
    )
    monkeypatch.setattr(engine.shutil, "which", lambda name: None)

    result = engine.prepare_protein(
        source,
        ProteinPreparationOptions(output_formats=["prepared_pdb", "receptor_pdbqt"]),
        output_dir=tmp_path / "out",
    )

    assert set(result.files) == {"prepared_pdb"}
    assert result.files["prepared_pdb"].path.exists()
    assert result.report["missing_tools"] == ["obabel"]
    assert result.report["status"] == "degraded"
    assert any("obabel" in warning for warning in result.warnings)
