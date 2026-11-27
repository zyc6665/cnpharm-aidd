"""配体参数化内核的离线回归测试（不调用 gmx / antechamber / acpype）。

覆盖评审的 Blocker/Major：`# include` 空格变体与递归校验、ZIP 目录计数与
大小写重复、条件编译守卫、顶层 `[ molecules ]` 插入位置、混合精度 .gro、
ACPYPE 独立目录 + 精确非 OPLS 产物 + atomtypes 拆分 + ITP/GRO 一致性。
"""

from __future__ import annotations

import importlib.util
import os
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "deploy" / "model-images" / "k8s" / "gromacs" / "ligand_parameterizer.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("md_ligand_parameterizer_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ligand = _load_module()

LIGAND_ITP = """[ atomtypes ]
; name  at.num  mass  charge  ptype  sigma  epsilon
c3       6      12.01  0.0     A      0.34   0.46

[ moleculetype ]
LIG   3

[ atoms ]
  1  c3  1  LIG  C1  1  0.0  12.01
  2  c3  1  LIG  C2  2  0.0  12.01
"""
PRM = """[ atomtypes ]
na   11  22.99  1.0  A  0.33  0.01
"""
POSRE = "[ position_restraints ]\n  1  1  1000  1000  1000\n"


def _gro(atom_count: int = 2, resname: str = "LIG", precision: int = 3,
         box: str = "   5.00000   5.00000   5.00000") -> str:
    # GROMACS 的列宽规则是 5 + 小数位数（%8.3f → 8 列，%9.4f → 9 列），不是固定 8 列
    width = 5 + precision
    atoms = []
    for index in range(1, atom_count + 1):
        coordinates = "".join(f"{0.1 * index:{width}.{precision}f}" for _ in range(3))
        atoms.append(f"{index:5d}{resname:<5s}{'C' + str(index):<5s}{index:5d}{coordinates}")
    return "\n".join(["ligand", f"{atom_count:5d}", *atoms, box]) + "\n"


def _gro_from_atom_lines(atom_lines: list[str], box: str = "   5.00000   5.00000   5.00000") -> str:
    return "\n".join(["ligand", f"{len(atom_lines):5d}", *atom_lines, box]) + "\n"


def _zip(path: Path, members: dict[str, str], *, compression=zipfile.ZIP_DEFLATED) -> Path:
    with zipfile.ZipFile(path, "w", compression=compression) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return path


def _ethanol_sdf(tmp_path: Path, *, flat: bool = False) -> Path:
    from rdkit import Chem
    from rdkit.Chem import AllChem

    molecule = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    if flat:
        AllChem.Compute2DCoords(molecule)
    else:
        assert AllChem.EmbedMolecule(molecule, randomSeed=7) == 0
    molecule.SetProp("_Name", "LIG")
    path = tmp_path / "ligand.sdf"
    writer = Chem.SDWriter(str(path))
    writer.write(molecule)
    writer.close()
    return path


# ---------------------------------------------------------------------------
# 常量 / 残基名
# ---------------------------------------------------------------------------


def test_constants_are_locked():
    assert ligand.ALLOWED_CHARGE_METHODS == ("bcc", "gas")
    assert ligand.DEFAULT_LIGAND_RESNAME == "LIG"
    assert ligand.MAX_ZIP_FILES == 32
    assert ligand.MAX_ZIP_UNCOMPRESSED_BYTES == 50 * 1024 * 1024
    assert issubclass(ligand.LigandParameterizationError, ValueError)
    assert len(ligand.RESERVED_RESNAMES) >= 885
    for name in ("SO4", "PO4", "NO3", "CO3", "CU", "MN", "BR", "I", "CS", "RB", "SR", "BA", "HG", "CD", "PB",
                 "LI", "AL", "F", "HEM", "NAD", "NDP", "FAD", "FMN", "ATP", "ADP", "GDP", "GTP", "COA", "SAM"):
        assert name in ligand.RESERVED_RESNAMES


def test_validate_ligand_resname_accepts_and_rejects():
    assert ligand.validate_ligand_resname("LIG") == "LIG"
    assert ligand.validate_ligand_resname("A1") == "A1"
    for bad in ("lig", "LIGAND", "", "ALA", "HIE", "HID", "HIP", "HSD", "HSE", "HSP", "ASH", "GLH",
                "CYX", "CYM", "LYN", "ARN", "MSE", "SEP", "TPO", "PTR", "ACE", "NME", "SOL", "NA",
                "HOH", "HHO", "OH2", "OHH", "TIP", "SPC", "H2O", "SO4", "PO4", "NO3", "CO3", "CU",
                "MN", "BR", "I", "CS", "RB", "SR", "BA", "HG", "CD", "PB", "LI", "AL", "F", "HEM",
                "NAD", "NDP", "FAD", "FMN", "ATP", "ADP", "GDP", "GTP", "COA", "SAM", "SOD", "POT", "CLA"):
        with pytest.raises(ligand.LigandParameterizationError):
            ligand.validate_ligand_resname(bad)


# ---------------------------------------------------------------------------
# ZIP 解压防护
# ---------------------------------------------------------------------------


def test_safe_extract_happy_path_and_atomic_replace(tmp_path: Path):
    dest = tmp_path / "out"
    dest.mkdir()
    (dest / "stale.txt").write_text("old", encoding="utf-8")
    archive = _zip(tmp_path / "bundle.zip", {"ligand.itp": LIGAND_ITP, "sub\\ligand.gro": _gro()})
    extracted = ligand.safe_extract_topology_zip(archive, dest)
    assert len(extracted) == 2
    assert (dest / "sub" / "ligand.gro").is_file()
    assert not (dest / "stale.txt").exists()  # 原子替换，旧内容不残留


def test_safe_extract_blocks_traversal_and_absolute_paths(tmp_path: Path):
    for name in ("../escape.itp", "sub/../../escape.itp", "/abs.itp", "C:/abs.itp", "//server/share.itp"):
        archive = _zip(tmp_path / "evil.zip", {name: "x"})
        dest = tmp_path / f"out-{abs(hash(name))}"
        with pytest.raises(ligand.LigandParameterizationError):
            ligand.safe_extract_topology_zip(archive, dest)
        assert not dest.exists()


def test_safe_extract_blocks_symlinks(tmp_path: Path):
    archive = tmp_path / "link.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        info = zipfile.ZipInfo("link.itp")
        info.create_system = 3
        info.external_attr = 0o120777 << 16
        handle.writestr(info, "target")
    with pytest.raises(ligand.LigandParameterizationError):
        ligand.safe_extract_topology_zip(archive, tmp_path / "out")


def test_safe_extract_counts_directory_entries_against_limit(tmp_path: Path):
    archive = tmp_path / "dirs.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        for index in range(ligand.MAX_ZIP_FILES):
            handle.writestr(zipfile.ZipInfo(f"dir{index}/"), "")
        handle.writestr("ligand.itp", LIGAND_ITP)
    with pytest.raises(ligand.LigandParameterizationError, match="entries"):
        ligand.safe_extract_topology_zip(archive, tmp_path / "out")


def test_safe_extract_rejects_case_insensitive_duplicates(tmp_path: Path):
    archive = _zip(tmp_path / "dup.zip", {"Ligand.itp": LIGAND_ITP, "ligand.itp": LIGAND_ITP},
                   compression=zipfile.ZIP_STORED)
    with pytest.raises(ligand.LigandParameterizationError, match="duplicate"):
        ligand.safe_extract_topology_zip(archive, tmp_path / "out")


def test_safe_extract_rejects_directory_case_collisions(tmp_path: Path):
    # 目录条目也要归一化并参与大小写去重，否则大小写不敏感的文件系统上会静默覆盖
    dirs = tmp_path / "dirs.zip"
    with zipfile.ZipFile(dirs, "w") as handle:
        handle.writestr(zipfile.ZipInfo("params/"), "")
        handle.writestr(zipfile.ZipInfo("PARAMS/"), "")
    with pytest.raises(ligand.LigandParameterizationError, match="duplicate"):
        ligand.safe_extract_topology_zip(dirs, tmp_path / "out-dirs")

    # 文件与同名目录（大小写不同）同样冲突：不得写出 file 又在其下建子目录
    mixed = tmp_path / "mixed.zip"
    with zipfile.ZipFile(mixed, "w") as handle:
        handle.writestr("params", "x")
        handle.writestr("Params/extra.prm", PRM)
    with pytest.raises(ligand.LigandParameterizationError, match="collides"):
        ligand.safe_extract_topology_zip(mixed, tmp_path / "out-mixed")


def test_safe_extract_rejects_case_collisions_between_implicit_parent_directories(tmp_path: Path):
    # 没有任何目录条目，仅靠子文件隐式建出的父目录也必须参与大小写去重
    archive = _zip(tmp_path / "implicit.zip", {"params/extra.prm": PRM, "PARAMS/other.prm": PRM})
    with pytest.raises(ligand.LigandParameterizationError, match="case-insensitive"):
        ligand.safe_extract_topology_zip(archive, tmp_path / "out")
    assert not (tmp_path / "out").exists()
    assert not list(tmp_path.glob(".out.tmp-*"))  # 拒绝发生在写盘之前，暂存目录也被清掉


def test_safe_extract_rejects_a_file_that_a_later_directory_treats_as_its_parent(tmp_path: Path):
    # 先出现文件 `params`、后出现目录 `params/empty/`：解出来要么 `params` 是文件又得是目录
    archive = tmp_path / "file-then-dir.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("params", "x")
        handle.writestr(zipfile.ZipInfo("params/empty/"), "")
    with pytest.raises(ligand.LigandParameterizationError, match="collides"):
        ligand.safe_extract_topology_zip(archive, tmp_path / "out-file-then-dir")
    assert not (tmp_path / "out-file-then-dir").exists()

    # 大小写不同也一样：文件 `Params` + 目录 `params/empty/` 在大小写不敏感文件系统上会互相覆盖
    mixed = tmp_path / "case-then-dir.zip"
    with zipfile.ZipFile(mixed, "w") as handle:
        handle.writestr("Params", "x")
        handle.writestr(zipfile.ZipInfo("params/empty/"), "")
    with pytest.raises(ligand.LigandParameterizationError, match="collides"):
        ligand.safe_extract_topology_zip(mixed, tmp_path / "out-case-then-dir")


def test_safe_extract_rejects_a_directory_that_a_later_file_reuses(tmp_path: Path):
    archive = tmp_path / "dir-then-file.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr(zipfile.ZipInfo("params/sub/"), "")
        handle.writestr("params", "x")
    with pytest.raises(ligand.LigandParameterizationError, match="collides"):
        ligand.safe_extract_topology_zip(archive, tmp_path / "out-dir-then-file")
    assert not (tmp_path / "out-dir-then-file").exists()


def test_safe_extract_restores_previous_results_when_publish_fails(tmp_path: Path, monkeypatch):
    dest = tmp_path / "out"
    dest.mkdir()
    (dest / "ligand.itp").write_text("previous result", encoding="utf-8")
    archive = _zip(tmp_path / "bundle.zip", {"ligand.itp": LIGAND_ITP})
    real_replace, calls = ligand.os.replace, []

    def flaky_replace(source, target):
        calls.append((Path(source), Path(target)))
        if len(calls) == 2:  # 第二次才是「暂存目录 → dest」，在这里失败
            raise OSError("disk full")
        return real_replace(source, target)

    monkeypatch.setattr(ligand.os, "replace", flaky_replace)
    with pytest.raises(OSError, match="disk full"):
        ligand.safe_extract_topology_zip(archive, dest)
    assert (dest / "ligand.itp").read_text(encoding="utf-8") == "previous result"  # 旧结果被还原
    assert not list(tmp_path.glob(".out.bak-*")) and not list(tmp_path.glob(".out.tmp-*"))


def test_safe_extract_rejects_unsupported_compression(tmp_path: Path):
    archive = tmp_path / "bz2.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("ligand.itp", LIGAND_ITP, compress_type=zipfile.ZIP_BZIP2)
    with pytest.raises(ligand.LigandParameterizationError, match="compression"):
        ligand.safe_extract_topology_zip(archive, tmp_path / "out")


def test_safe_extract_enforces_size_limit_and_cleans_up(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ligand, "MAX_ZIP_UNCOMPRESSED_BYTES", 8)
    archive = _zip(tmp_path / "big.zip", {"big.itp": "x" * 64})
    dest = tmp_path / "out"
    with pytest.raises(ligand.LigandParameterizationError, match="size limit"):
        ligand.safe_extract_topology_zip(archive, dest)
    assert not dest.exists()


def test_safe_extract_rejects_non_zip(tmp_path: Path):
    bogus = tmp_path / "not-a-zip.itp"
    bogus.write_text("hello", encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError):
        ligand.safe_extract_topology_zip(bogus, tmp_path / "out")


# ---------------------------------------------------------------------------
# ITP 递归安全校验
# ---------------------------------------------------------------------------


def test_validate_itp_security_recurses_through_include_variants(tmp_path: Path):
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "ligand.itp").write_text(LIGAND_ITP, encoding="utf-8")
    (root / "extra.prm").write_text(PRM, encoding="utf-8")
    (root / "top.top").write_text(
        '# include "ligand.itp"\n  #include "extra.prm"\n[ moleculetype ]\nTOP 1\n', encoding="utf-8")
    ligand.validate_itp_security(root / "top.top", root=root)


def test_validate_itp_security_rejects_missing_include_and_cycles(tmp_path: Path):
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "a.itp").write_text('#include "b.itp"\n[ moleculetype ]\nA 1\n', encoding="utf-8")
    (root / "b.itp").write_text('#include "missing.itp"\n[ moleculetype ]\nB 1\n', encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError, match="missing"):
        ligand.validate_itp_security(root / "a.itp", root=root)

    (root / "b.itp").write_text('#include "a.itp"\n[ moleculetype ]\nB 1\n', encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError, match="cycle"):
        ligand.validate_itp_security(root / "a.itp", root=root)


def test_validate_itp_security_rejects_absolute_traversal_and_escape(tmp_path: Path):
    root = tmp_path / "bundle"
    root.mkdir()
    for text in ('#include "/etc/passwd"\n[ moleculetype ]\nX 1\n',
                 '#include "../../secret.itp"\n[ moleculetype ]\nX 1\n'):
        path = root / "evil.itp"
        path.write_text(text, encoding="utf-8")
        with pytest.raises(ligand.LigandParameterizationError):
            ligand.validate_itp_security(path, root=root)
    outside = tmp_path / "outside.itp"
    outside.write_text(LIGAND_ITP, encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError, match="escapes"):
        ligand.validate_itp_security(outside, root=root)


def test_validate_itp_security_allows_diamond_dependencies_but_still_rejects_cycles(tmp_path: Path):
    # 菱形依赖（a、b 共享 common.prm）不是循环，必须放行；共享依赖只校验一次
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "common.prm").write_text(PRM, encoding="utf-8")
    for name in ("a.itp", "b.itp"):
        (root / name).write_text(f'#include "common.prm"\n[ moleculetype ]\n{name[0].upper()} 1\n'
                                 f"[ atoms ]\n 1 na 1 LIG {name[0].upper()}1 1\n", encoding="utf-8")
    (root / "ligand.itp").write_text('#include "a.itp"\n#include "b.itp"\n[ moleculetype ]\nLIG 1\n'
                                     "[ atoms ]\n 1 na 1 LIG C1 1\n", encoding="utf-8")
    ligand.validate_itp_security(root / "ligand.itp", root=root)

    # 但真正的递归（a → b → a）仍然必须报错
    (root / "b.itp").write_text('#include "a.itp"\n[ moleculetype ]\nB 1\n[ atoms ]\n 1 na 1 LIG B1 1\n',
                                encoding="utf-8")
    (root / "a.itp").write_text('#include "common.prm"\n#include "b.itp"\n[ moleculetype ]\nA 1\n'
                                "[ atoms ]\n 1 na 1 LIG A1 1\n", encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError, match="cycle"):
        ligand.validate_itp_security(root / "ligand.itp", root=root)


def test_validate_itp_security_resolves_includes_from_the_including_directory(tmp_path: Path):
    root = tmp_path / "bundle"
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "inner.itp").write_text('#include "deep.prm"\n[ moleculetype ]\nINNER 1\n', encoding="utf-8")
    (root / "sub" / "deep.prm").write_text(PRM, encoding="utf-8")
    (root / "ligand.itp").write_text('#include "sub/inner.itp"\n[ moleculetype ]\nLIG 1\n', encoding="utf-8")
    ligand.validate_itp_security(root / "ligand.itp", root=root)

    # GROMACS 从「发出 include 的文件所在目录」解析：把 deep.prm 挪到包根就必须被判定为缺失
    (root / "sub" / "deep.prm").unlink()
    (root / "deep.prm").write_text(PRM, encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError, match="missing"):
        ligand.validate_itp_security(root / "ligand.itp", root=root)


def test_validate_itp_security_rejects_empty_and_sectionless_files(tmp_path: Path):
    for name, text in {"empty.itp": "   \n", "comments.itp": "; only comments\n"}.items():
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        with pytest.raises(ligand.LigandParameterizationError, match="no GROMACS section"):
            ligand.validate_itp_security(path)


# ---------------------------------------------------------------------------
# atomtypes 拆分 / moleculetype
# ---------------------------------------------------------------------------


def test_split_atomtypes_moves_every_global_section(tmp_path: Path):
    source = tmp_path / "source.itp"
    source.write_text(
        "[ atomtypes ]\nc3 6 12.01 0.0 A 0.34 0.46\n\n"
        "[ bondtypes ]\nc3 c3 1 0.10 100.0\n\n"
        "[ cmaptypes ]\nC C 1 0 0 1 0 0 0 0 0 0.1 0.2 0.3\n\n"
        "[ moleculetype ]\nLIG 3\n\n"
        "[ atoms ]\n  1  c3  1  LIG  C1  1  0.0  12.01\n", encoding="utf-8")
    prm = tmp_path / "extra.prm"
    prm.write_text("; external params\n[ atomtypes ]\nna 11 22.99 1.0 A 0.33 0.01\n", encoding="utf-8")
    atomtypes, clean = ligand.split_atomtypes_from_itp(
        source, out_atomtypes_itp=tmp_path / "out" / "atomtypes.itp", out_clean_itp=tmp_path / "out" / "clean.itp",
        extra_prm=prm)
    assert atomtypes is not None
    text = atomtypes.read_text(encoding="utf-8")
    assert all(name in text for name in ("[ atomtypes ]", "[ bondtypes ]", "[ cmaptypes ]", "na "))
    assert "; external params" in text  # .prm 前导注释保留
    assert "atomtypes" not in clean.read_text(encoding="utf-8")


def test_split_atomtypes_returns_none_without_global_sections(tmp_path: Path):
    source = tmp_path / "ligand.itp"
    source.write_text("[ moleculetype ]\nLIG 3\n\n[ atoms ]\n  1  c3  1  LIG  C1  1\n", encoding="utf-8")
    atomtypes, clean = ligand.split_atomtypes_from_itp(
        source, out_atomtypes_itp=tmp_path / "a.itp", out_clean_itp=tmp_path / "c.itp")
    assert atomtypes is None and "moleculetype" in clean.read_text(encoding="utf-8")


def test_split_atomtypes_rejects_globals_inside_conditionals_and_unbalanced_scopes(tmp_path: Path):
    guarded = tmp_path / "guarded.itp"
    guarded.write_text("#ifdef X\n[ atomtypes ]\nc3 6 12.01 0.0 A 0.34 0.46\n#endif\n"
                       "[ moleculetype ]\nLIG 1\n[ atoms ]\n 1 c3 1 LIG C1 1\n", encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError, match="conditional"):
        ligand.split_atomtypes_from_itp(guarded, out_atomtypes_itp=tmp_path / "a.itp", out_clean_itp=tmp_path / "c.itp")
    unbalanced = tmp_path / "unbalanced.itp"
    unbalanced.write_text("#ifdef X\n[ moleculetype ]\nLIG 1\n[ atoms ]\n 1 c3 1 LIG C1 1\n", encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError, match="unbalanced"):
        ligand.split_atomtypes_from_itp(unbalanced, out_atomtypes_itp=tmp_path / "a.itp",
                                        out_clean_itp=tmp_path / "c.itp")
    stray = tmp_path / "stray.itp"
    stray.write_text("#endif\n[ moleculetype ]\nLIG 1\n[ atoms ]\n 1 c3 1 LIG C1 1\n", encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError, match="unexpected #endif"):
        ligand.split_atomtypes_from_itp(stray, out_atomtypes_itp=tmp_path / "a.itp",
                                        out_clean_itp=tmp_path / "c.itp")


def test_validate_delivered_topology_rejects_include_leaks_and_wrong_order(tmp_path: Path):
    clean = tmp_path / "ligand.itp"
    atomtypes = tmp_path / "atomtypes.itp"
    clean.write_text("[ moleculetype ]\nLIG 1\n[ atoms ]\n 1 c3 1 LIG C1 1\n", encoding="utf-8")
    atomtypes.write_text("[ atomtypes ]\nc3 6 12.01 0.0 A 0.34 0.46\n", encoding="utf-8")
    ligand.validate_delivered_topology(clean, atomtypes)
    ligand.validate_delivered_topology(clean, None)  # 没有全局节时只校验配体文件


def test_split_atomtypes_deduplicates_identical_atomtypes_across_sources(tmp_path: Path):
    source = tmp_path / "source.itp"
    source.write_text(
        "[ atomtypes ]\nc3 6 12.01 0.0 A 0.34 0.46\n\n"
        "[ moleculetype ]\nLIG 3\n\n[ atoms ]\n 1 c3 1 LIG C1 1 0.0 12.01\n",
        encoding="utf-8",
    )
    prm = tmp_path / "extra.prm"
    prm.write_text("[ atomtypes ]\nc3 6 12.0100 0.000 A 0.3400 0.4600\nna 11 22.99 1.0 A 0.33 0.01\n", encoding="utf-8")
    atomtypes, clean = ligand.split_atomtypes_from_itp(
        source, out_atomtypes_itp=tmp_path / "atomtypes.itp", out_clean_itp=tmp_path / "clean.itp", extra_prm=prm)
    assert atomtypes is not None
    text = atomtypes.read_text(encoding="utf-8")
    assert text.count("[ atomtypes ]") == 1
    assert sum(1 for line in text.splitlines() if line.strip().startswith("c3 ")) == 1
    assert "na 11" in text
    ligand.validate_delivered_topology(clean, atomtypes)


def test_split_atomtypes_rejects_conflicting_atomtypes_across_sources(tmp_path: Path):
    source = tmp_path / "source.itp"
    source.write_text("[ atomtypes ]\nc3 6 12.01 0.0 A 0.34 0.46\n[ moleculetype ]\nLIG 3\n", encoding="utf-8")
    prm = tmp_path / "extra.prm"
    prm.write_text("[ atomtypes ]\nc3 6 12.01 0.0 A 0.35 0.99\n", encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError, match="conflicting"):
        ligand.split_atomtypes_from_itp(
            source, out_atomtypes_itp=tmp_path / "atomtypes.itp", out_clean_itp=tmp_path / "clean.itp", extra_prm=prm)


def test_validate_delivered_topology_rejects_duplicate_atomtypes(tmp_path: Path):
    clean = tmp_path / "ligand.itp"
    clean.write_text("[ moleculetype ]\nLIG 1\n[ atoms ]\n 1 c3 1 LIG C1 1\n", encoding="utf-8")
    atomtypes = tmp_path / "atomtypes.itp"
    atomtypes.write_text("[ atomtypes ]\nc3 6 12.01 0.0 A 0.34 0.46\n[ atomtypes ]\nc3 6 12.01 0.0 A 0.34 0.46\n",
                         encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError, match="duplicate"):
        ligand.validate_delivered_topology(clean, atomtypes)

    clean.write_text('#include "x.prm"\n[ moleculetype ]\nLIG 1\n', encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError, match="still contains #include"):
        ligand.validate_delivered_topology(clean, atomtypes)

    clean.write_text("[ moleculetype ]\nLIG 1\n[ atomtypes ]\nc3 6 12.01 0.0 A 0.34 0.46\n", encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError, match="leaked"):
        ligand.validate_delivered_topology(clean, atomtypes)
    clean.write_text("[ moleculetype ]\nLIG 1\n[ atoms ]\n 1 c3 1 LIG C1 1\n", encoding="utf-8")

    atomtypes.write_text("[ moleculetype ]\nLIG 1\n[ atomtypes ]\nc3 6 12.01 0.0 A 0.34 0.46\n", encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError, match="non-global"):
        ligand.validate_delivered_topology(clean, atomtypes)

    atomtypes.write_text("[ bondtypes ]\nc3 c3 1 0.10 100.0\n\n[ atomtypes ]\nc3 6 12.01 0.0 A 0.34 0.46\n",
                         encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError, match="precedes"):
        ligand.validate_delivered_topology(clean, atomtypes)


def test_validate_delivered_topology_rejects_defaults_sections(tmp_path: Path):
    # GROMACS 读完 forcefield.itp 的 [ defaults ] 后再来一个就是重定义，交付文件里一律不许出现
    defaults = "[ defaults ]\n1 2 yes 0.5 0.8333\n\n"
    clean = tmp_path / "ligand.itp"
    atomtypes = tmp_path / "atomtypes.itp"
    atomtypes.write_text("[ atomtypes ]\nc3 6 12.01 0.0 A 0.34 0.46\n", encoding="utf-8")
    clean.write_text(defaults + "[ moleculetype ]\nLIG 1\n[ atoms ]\n 1 c3 1 LIG C1 1\n", encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError, match="defaults"):
        ligand.validate_delivered_topology(clean, atomtypes)

    clean.write_text("[ moleculetype ]\nLIG 1\n[ atoms ]\n 1 c3 1 LIG C1 1\n", encoding="utf-8")
    atomtypes.write_text(defaults + "[ atomtypes ]\nc3 6 12.01 0.0 A 0.34 0.46\n", encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError, match="defaults"):
        ligand.validate_delivered_topology(clean, atomtypes)


def test_detect_moleculetype_skips_directives_and_comments(tmp_path: Path):
    path = tmp_path / "ligand.itp"
    path.write_text("#ifdef POSRES\n[ moleculetype ]\nLIG 3\n#endif\n; [ moleculetype ] FAKE 1\n"
                    "[ atoms ]\n 1 c3 1 LIG C1 1\n", encoding="utf-8")
    assert ligand.detect_moleculetype_name(path) == "LIG"
    bare = tmp_path / "bare.itp"
    bare.write_text("[ atoms ]\n 1 c3 1 LIG C1 1\n", encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError):
        ligand.detect_moleculetype_name(bare)


# ---------------------------------------------------------------------------
# .gro 拼接
# ---------------------------------------------------------------------------


def test_merge_gro_files_normalises_precision_and_renumbers(tmp_path: Path):
    protein = tmp_path / "protein.gro"
    protein.write_text(_gro(2, "ALA", precision=4), encoding="utf-8")
    ligand_gro = tmp_path / "ligand.gro"
    ligand_gro.write_text(_gro(2, "LIG", precision=3), encoding="utf-8")
    assert ligand.merge_gro_files(protein, ligand_gro, tmp_path / "complex.gro") == 4
    lines = (tmp_path / "complex.gro").read_text(encoding="utf-8").splitlines()
    assert lines[1].strip() == "4"
    assert [line[15:20] for line in lines[2:6]] == ["    1", "    2", "    3", "    4"]
    assert [line[0:5] for line in lines[2:6]] == ["    1", "    2", "    3", "    4"]
    assert lines[2][20:28] == "   0.100"  # 4 位小数输入统一写回 8.3f
    assert lines[6].split() == ["5.00000", "5.00000", "5.00000"]


def test_merge_gro_files_offsets_ligand_resid_past_protein_max(tmp_path: Path):
    protein = tmp_path / "protein.gro"
    protein.write_text(_gro_from_atom_lines([
        f"{1:5d}{'ALA':<5s}{'CA':<5s}{1:5d}   1.000   1.000   1.000",
        f"{50:5d}{'GLY':<5s}{'CA':<5s}{2:5d}   2.000   2.000   2.000",
    ]), encoding="utf-8")
    ligand_gro = tmp_path / "ligand.gro"
    ligand_gro.write_text(_gro(2, "LIG"), encoding="utf-8")
    assert ligand.merge_gro_files(protein, ligand_gro, tmp_path / "complex.gro") == 4
    lines = (tmp_path / "complex.gro").read_text(encoding="utf-8").splitlines()
    assert [line[0:5] for line in lines[2:6]] == ["    1", "   50", "   51", "   52"]
    assert [line[15:20] for line in lines[2:6]] == ["    1", "    2", "    3", "    4"]


def test_merge_gro_files_parses_nine_and_ten_column_coordinates(tmp_path: Path):
    # .gro 允许 3/4/5 位小数（8/9/10 列），不能一律按 8 列切片
    simple = tmp_path / "ligand.gro"
    simple.write_text(_gro(1), encoding="utf-8")
    prefix = f"{1:5d}{'ALA':<5s}{'CA':<5s}{1:5d}"
    four, five = (1.2345, -2.3456, 3.4567), (12.34567, -120.12345, 9.99999)
    velocities = (0.1111, -0.2222, 0.3333)
    cases = {
        "4dp": (prefix + "".join(f"{value:9.4f}" for value in four), four),
        "5dp": (prefix + "".join(f"{value:10.5f}" for value in five), five),
        # 符号紧贴在一起（前一个数正好占满 9 列，无分隔空格）也必须解析正确
        "glued": (prefix + "-123.4567-100.1234   0.0000", (-123.4567, -100.1234, 0.0)),
        # 9 列（4 位小数）+ 速度：速度区同样按 width = 5 + 小数位数 读取，不得当成坐标
        "velocity": (prefix + "".join(f"{value:9.4f}" for value in four)
                     + "".join(f"{value:9.4f}" for value in velocities), four),
    }
    for name, (line, values) in cases.items():
        protein = tmp_path / f"protein-{name}.gro"
        protein.write_text(_gro_from_atom_lines([line]), encoding="utf-8")
        output = tmp_path / f"complex-{name}.gro"
        ligand.merge_gro_files(protein, simple, output)
        atom = output.read_text(encoding="utf-8").splitlines()[2]
        assert atom[20:] == "".join(f"{value:8.3f}" for value in values), name


def test_merge_gro_files_rejects_non_finite_first_coordinate_with_velocity(tmp_path: Path):
    # 首坐标 nan 会破坏「首字段决定统一列宽」的判定；绝不能改用正则跳过坐标去读速度区
    prefix = f"{1:5d}{'ALA':<5s}{'CA':<5s}{1:5d}"
    nan_line = prefix + "      nan" + "".join(f"{value:9.4f}" for value in (1.0, 2.0, 0.1, 0.2, 0.3))
    protein = tmp_path / "nan.gro"
    protein.write_text(_gro_from_atom_lines([nan_line]), encoding="utf-8")
    ligand_gro = tmp_path / "ligand.gro"
    ligand_gro.write_text(_gro(1), encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError, match="coordinates"):
        ligand.merge_gro_files(protein, ligand_gro, tmp_path / "complex.gro")

    # 速度区出现 nan 同样必须报错，哪怕坐标本身完全正常
    velocity_nan = prefix + "".join(f"{value:8.3f}" for value in (1.0, 2.0, 3.0)) + "     nan   0.200   0.300"
    protein.write_text(_gro_from_atom_lines([velocity_nan]), encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError, match="coordinates"):
        ligand.merge_gro_files(protein, ligand_gro, tmp_path / "complex.gro")


def test_merge_gro_files_rejects_fields_past_the_sixth_column(tmp_path: Path):
    # .gro 原子行最多 3 坐标 + 3 速度；第 7 列起（多余 nan、多余数、乱码）必须报错而不是静默丢弃
    prefix = f"{1:5d}{'ALA':<5s}{'CA':<5s}{1:5d}"
    coordinates = "".join(f"{value:8.3f}" for value in (1.0, 2.0, 3.0))
    velocities = "".join(f"{value:8.3f}" for value in (0.1, 0.2, 0.3))
    ligand_gro = tmp_path / "ligand.gro"
    ligand_gro.write_text(_gro(1), encoding="utf-8")

    valid = tmp_path / "valid.gro"
    valid.write_text(_gro_from_atom_lines([prefix + coordinates + velocities]), encoding="utf-8")
    assert ligand.merge_gro_files(valid, ligand_gro, tmp_path / "valid-complex.gro") == 2

    for index, extra in enumerate(("     nan", "   0.500", "garbage", "  -9.999")):
        protein = tmp_path / f"extra-{index}.gro"
        protein.write_text(_gro_from_atom_lines([prefix + coordinates + velocities + extra]), encoding="utf-8")
        with pytest.raises(ligand.LigandParameterizationError):
            ligand.merge_gro_files(protein, ligand_gro, tmp_path / f"extra-{index}-complex.gro")


def test_merge_gro_files_preserves_nine_component_box(tmp_path: Path):
    box = "   5.00000   5.00000   5.00000   0.00000   0.00000   0.00000   0.00000   0.00000   0.00000"
    protein = tmp_path / "protein.gro"
    protein.write_text(_gro(1, "ALA", box=box), encoding="utf-8")
    ligand_gro = tmp_path / "ligand.gro"
    ligand_gro.write_text(_gro(1, "LIG", box=box), encoding="utf-8")
    ligand.merge_gro_files(protein, ligand_gro, tmp_path / "complex.gro")
    assert (tmp_path / "complex.gro").read_text(encoding="utf-8").splitlines()[-1] == " ".join(box.split())


def test_merge_gro_files_rejects_invalid_atoms_and_box(tmp_path: Path):
    bad_box = tmp_path / "bad_box.gro"
    bad_box.write_text(_gro(1, box="   1.0   1.0   1.0   1.0"), encoding="utf-8")
    good = tmp_path / "good.gro"
    good.write_text(_gro(1), encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError, match="box"):
        ligand.merge_gro_files(good, bad_box, tmp_path / "out.gro")

    negative = tmp_path / "negative.gro"
    negative.write_text("ligand\n   -1\n", encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError):
        ligand.merge_gro_files(negative, good, tmp_path / "out.gro")

    non_finite = tmp_path / "nan.gro"
    non_finite.write_text(_gro(1).replace("   0.100", "     nan", 1), encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError, match="coordinates"):
        ligand.merge_gro_files(non_finite, good, tmp_path / "out.gro")


# ---------------------------------------------------------------------------
# topol.top 改写
# ---------------------------------------------------------------------------


def test_patch_topol_top_is_idempotent_with_comments_and_indentation(tmp_path: Path):
    topol = tmp_path / "topol.top"
    topol.write_text(
        '; #include "ligand.itp"\n#include "amber99sb-ildn.forcefield.itp"\n\n'
        "  #include \"ligand.itp\"\n\n[ system ]\ncomplex\n\n[ molecules ]\nProtein_chain_A  1\n",
        encoding="utf-8")
    kwargs = {"ligand_itp_name": "ligand.itp", "moleculetype_name": "LIG",
              "atomtypes_itp_name": "ligand_atomtypes.itp", "posre_itp_name": "posre_ligand.itp"}
    first = ligand.patch_topol_top(topol, **kwargs)
    assert first == ligand.patch_topol_top(topol, **kwargs)
    stripped = [line.strip() for line in first.splitlines()]
    assert stripped.count('#include "ligand.itp"') == 1
    assert stripped.index('#include "ligand.itp"') + 1 == stripped.index("#ifdef POSRES_LIG")
    assert stripped.count("LIG 1") == 1 and stripped[-1] == "LIG 1"


def test_patch_topol_top_inserts_before_water_or_system(tmp_path: Path):
    water = tmp_path / "water.top"
    water.write_text('#include "amber99sb-ildn.forcefield.itp"\n#include "tip3p.itp"\n'
                     "[ system ]\nX\n[ molecules ]\nProtein 1\n", encoding="utf-8")
    text = ligand.patch_topol_top(water, ligand_itp_name="ligand.itp", moleculetype_name="LIG")
    lines = text.splitlines()
    assert lines.index('#include "ligand.itp"') < lines.index('#include "tip3p.itp"')

    dry = tmp_path / "dry.top"
    dry.write_text('#include "amber99sb-ildn.forcefield.itp"\n[ system ]\nX\n[ molecules ]\nProtein 1\n',
                   encoding="utf-8")
    lines = ligand.patch_topol_top(dry, ligand_itp_name="ligand.itp", moleculetype_name="LIG").splitlines()
    assert lines.index('#include "ligand.itp"') < lines.index("[ system ]")
    assert lines.index("LIG 1") > lines.index("[ molecules ]")  # molecules 条目只能出现在区块内


def test_patch_topol_top_never_inserts_inside_a_water_conditional(tmp_path: Path):
    top = tmp_path / "conditional.top"
    top.write_text('#include "amber99sb-ildn.forcefield.itp"\n'
                   '#ifdef WATER\n#include "tip3p.itp"\n#endif\n'
                   "[ system ]\nX\n[ molecules ]\nProtein 1\n", encoding="utf-8")
    lines = ligand.patch_topol_top(top, ligand_itp_name="ligand.itp", moleculetype_name="LIG",
                                   posre_itp_name="posre_ligand.itp").splitlines()
    # 配体 include 与 POSRES_LIG 都必须落在顶层：不能夹在 #ifdef WATER ... #endif 之间，
    # 否则关掉 WATER 时配体 moleculetype 与 posre 一起消失
    start, end = lines.index("#ifdef WATER"), lines.index("#endif", lines.index("#ifdef WATER"))
    ligand_index, posres = lines.index('#include "ligand.itp"'), lines.index("#ifdef POSRES_LIG")
    assert not start < ligand_index < end and not start < posres < end
    assert ligand_index < lines.index("[ system ]") and lines[posres + 1] == '#include "posre_ligand.itp"'
    assert lines[posres + 2] == "#endif" and lines.count('#include "ligand.itp"') == 1


def test_patch_topol_top_appends_to_the_existing_molecules_section(tmp_path: Path):
    topol = tmp_path / "topol.top"
    topol.write_text('#include "forcefield.itp"\n[ system ]\ncomplex\n\n[ molecules ]\nProtein_chain_A 1\n',
                     encoding="utf-8")
    text = ligand.patch_topol_top(topol, ligand_itp_name="ligand.itp", moleculetype_name="LIG", ligand_count=2)
    assert text.splitlines()[-1] == "LIG 2"
    again = ligand.patch_topol_top(topol, ligand_itp_name="ligand.itp", moleculetype_name="LIG", ligand_count=2)
    assert again == text  # 第二次调用不会追加重复条目


def test_patch_topol_top_requires_top_level_forcefield_and_molecules(tmp_path: Path):
    # 顶层没有 [ molecules ] 时必须报错：凭空追加区块会把条目写到 GROMACS 不读的位置
    no_molecules = tmp_path / "no-molecules.top"
    no_molecules.write_text('#include "forcefield.itp"\n[ system ]\ncomplex\n', encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError, match="molecules"):
        ligand.patch_topol_top(no_molecules, ligand_itp_name="ligand.itp", moleculetype_name="LIG")

    # 写在条件编译里的 [ molecules ] 同样不是顶层区块
    guarded = tmp_path / "guarded.top"
    guarded.write_text('#include "forcefield.itp"\n[ system ]\nX\n'
                       '#ifdef WATER\n[ molecules ]\nProtein 1\n#endif\n', encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError, match="molecules"):
        ligand.patch_topol_top(guarded, ligand_itp_name="ligand.itp", moleculetype_name="LIG")

    # forcefield.itp 只出现在条件编译里时不构成可用锚点
    conditional_forcefield = tmp_path / "conditional-ff.top"
    conditional_forcefield.write_text('#ifdef FF\n#include "forcefield.itp"\n#endif\n'
                                      "[ system ]\nX\n[ molecules ]\nProtein 1\n", encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError, match="forcefield"):
        ligand.patch_topol_top(conditional_forcefield, ligand_itp_name="ligand.itp", moleculetype_name="LIG")

    broken = tmp_path / "broken.top"
    broken.write_text("[ system ]\ncomplex\n", encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError, match="forcefield"):
        ligand.patch_topol_top(broken, ligand_itp_name="ligand.itp", moleculetype_name="LIG")


def test_patch_topol_top_ignores_a_ligand_include_hidden_in_a_conditional(tmp_path: Path):
    top = tmp_path / "hidden.top"
    top.write_text('#include "forcefield.itp"\n#ifdef EXTRA\n#include "ligand.itp"\n#endif\n'
                   "[ system ]\nX\n[ molecules ]\nProtein 1\n", encoding="utf-8")
    lines = ligand.patch_topol_top(top, ligand_itp_name="ligand.itp", moleculetype_name="LIG").splitlines()
    start, end = lines.index("#ifdef EXTRA"), lines.index("#endif", lines.index("#ifdef EXTRA"))
    top_level = [i for i, line in enumerate(lines)
                 if line.strip() == '#include "ligand.itp"' and not start < i < end]
    # 条件块里的那行原样保留，顶层另补一行（否则关掉 EXTRA 时配体就消失了）
    assert len(top_level) == 1 and top_level[0] < lines.index("[ system ]")
    assert lines.count('#include "ligand.itp"') == 2 and lines[-1] == "LIG 1"


def test_patch_topol_top_requires_a_top_level_system_section(tmp_path: Path):
    # [ system ] 只在条件块里时，配体 include 会落到 GROMACS 读不到/读错的位置：直接拒绝
    top = tmp_path / "conditional-system.top"
    top.write_text('#include "forcefield.itp"\n#ifdef WATER\n[ system ]\nX\n#endif\n'
                   "[ molecules ]\nProtein 1\n", encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError, match="system"):
        ligand.patch_topol_top(top, ligand_itp_name="ligand.itp", moleculetype_name="LIG")


def test_patch_topol_top_never_rewrites_a_ligand_count_inside_a_conditional(tmp_path: Path):
    top = tmp_path / "conditional-molecules.top"
    top.write_text('#include "forcefield.itp"\n[ system ]\nX\n[ molecules ]\nProtein 1\n'
                   "#ifdef DIMER\nLIG 2\n#endif\n", encoding="utf-8")
    lines = ligand.patch_topol_top(top, ligand_itp_name="ligand.itp", moleculetype_name="LIG").splitlines()
    start, end = lines.index("#ifdef DIMER"), lines.index("#endif", lines.index("#ifdef DIMER"))
    assert lines[start + 1] == "LIG 2"  # 条件块里的计数属于另一套体系，原样保留
    top_level = [line for index, line in enumerate(lines)
                 if not start < index < end and line.strip() == "LIG 1"]
    assert top_level  # 顶层另写一条，关掉 DIMER 时配体依然存在


def test_patch_topol_top_scans_past_a_section_header_inside_a_conditional(tmp_path: Path):
    # 条件块里的 [ other ] 不是顶层节标题：扫描终点不能被它截断，否则其后的顶层 LIG 3 会被忽略并再追加一条
    top = tmp_path / "conditional-header.top"
    top.write_text('#include "forcefield.itp"\n[ system ]\nX\n[ molecules ]\nProtein 1\n'
                   "#ifdef DIMER\n[ other ]\nLIG 2\n#endif\nLIG 3\n", encoding="utf-8")
    lines = ligand.patch_topol_top(top, ligand_itp_name="ligand.itp", moleculetype_name="LIG").splitlines()
    start, end = lines.index("#ifdef DIMER"), lines.index("#endif", lines.index("#ifdef DIMER"))
    top_level = [line.strip() for index, line in enumerate(lines)
                 if not start <= index <= end and line.split(";", 1)[0].strip().startswith("LIG ")]
    assert top_level == ["LIG 1"]  # 顶层已有条目被改写，不新增第二条
    assert lines[start + 1] == "[ other ]" and lines[start + 2] == "LIG 2"  # 条件块内的计数原样保留
    assert lines.index("LIG 1") > end


def test_patch_topol_top_rejects_atomtypes_after_an_existing_ligand_include(tmp_path: Path):
    # 配体 include 已排在 forcefield 之前时，把 atomtypes include 插到 forcefield 之后会晚于配体：
    # GROMACS 读到配体 [ atoms ] 时还不知道原子类型，必须报错而不是写出错误顺序
    top = tmp_path / "order.top"
    top.write_text('#include "ligand.itp"\n#include "amber99sb.ildn.forcefield.itp"\n[ system ]\nX\n'
                   "[ molecules ]\nProtein 1\n", encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError, match="before"):
        ligand.patch_topol_top(top, ligand_itp_name="ligand.itp", moleculetype_name="LIG",
                               atomtypes_itp_name="ligand_atomtypes.itp")


# ---------------------------------------------------------------------------
# RDKit 预处理
# ---------------------------------------------------------------------------


def test_prepare_ligand_writes_lig_resname_and_three_d_files(tmp_path: Path):
    prepared = ligand.prepare_ligand_with_rdkit(_ethanol_sdf(tmp_path), tmp_path / "prepared", ligand_resname="LIG")
    assert prepared["sdf"].is_file() and prepared["pdb"].is_file()
    assert prepared["atom_count"] == 9 and prepared["net_charge"] == 0
    pdb_lines = prepared["pdb"].read_text(encoding="utf-8").splitlines()
    residues = {line[17:20] for line in pdb_lines if line.startswith(("ATOM", "HETATM"))}
    assert residues == {"LIG"}


def test_prepare_ligand_uses_original_sdf_record_index(tmp_path: Path):
    from rdkit import Chem
    from rdkit.Chem import AllChem

    def block(smiles: str) -> str:
        molecule = Chem.AddHs(Chem.MolFromSmiles(smiles))
        assert AllChem.EmbedMolecule(molecule, randomSeed=7) == 0
        return Chem.MolToMolBlock(molecule) + "$$$$\n"

    path = tmp_path / "multi.sdf"
    bad = "BAD\n     RDKit          3D\n\n  x  1  0  0  0  0  0  0  0  0999 V2000\n$$$$\n"
    path.write_text(bad + block("CCO") + block("CC"), encoding="utf-8")
    assert Chem.SDMolSupplier(str(path))[0] is None
    # 坏记录不导致索引偏移：index=1 必须仍是原始第 2 条（乙醇 9 原子）
    prepared = ligand.prepare_ligand_with_rdkit(path, tmp_path / "p", ligand_index=1)
    assert prepared["atom_count"] == 9
    with pytest.raises(ligand.LigandParameterizationError, match="out of range"):
        ligand.prepare_ligand_with_rdkit(path, tmp_path / "p", ligand_index=9)


def test_prepare_ligand_rejects_2d_charge_mismatch_and_unknown_format(tmp_path: Path):
    with pytest.raises(ligand.LigandParameterizationError, match="3D"):
        ligand.prepare_ligand_with_rdkit(_ethanol_sdf(tmp_path, flat=True), tmp_path / "p")
    with pytest.raises(ligand.LigandParameterizationError, match="charge"):
        ligand.prepare_ligand_with_rdkit(_ethanol_sdf(tmp_path), tmp_path / "p", net_charge=1)
    bogus = tmp_path / "ligand.xyz"
    bogus.write_text("x", encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError, match="unsupported"):
        ligand.prepare_ligand_with_rdkit(bogus, tmp_path / "p")


# ---------------------------------------------------------------------------
# 命令行 / 环境
# ---------------------------------------------------------------------------


def test_build_acpype_command_and_validation(tmp_path: Path):
    command = ligand.build_acpype_command(tmp_path / "ligand.pdb", ligand_resname="LIG",
                                          charge_method="gas", net_charge=-1)
    assert command[:5] == ["acpype", "-i", str(tmp_path / "ligand.pdb"), "-b", "LIG"]
    assert command[command.index("-a") + 1] == "gaff2"
    assert command[command.index("-c") + 1] == "gas"
    assert command[command.index("-n") + 1] == "-1"
    assert command[-1] == "-d"
    with pytest.raises(ligand.LigandParameterizationError):
        ligand.build_acpype_command(tmp_path / "x.pdb", charge_method="resp")


def test_resolve_amber_env_layout():
    env = ligand.resolve_amber_env("/opt/amber", base_env={"PATH": "/usr/bin", "LD_LIBRARY_PATH": "/lib"})
    assert env["AMBERHOME"] == str(Path("/opt/amber/anaconda3/envs/AmberTools"))
    assert env["OPAL_PREFIX"] == str(Path("/opt/amber/anaconda3"))
    assert str(Path("/opt/amber/anaconda3/envs/AmberTools/bin")) in env["PATH"]
    assert env["PATH"].endswith("/usr/bin")


# ---------------------------------------------------------------------------
# Mode 0 / Mode 1 编排
# ---------------------------------------------------------------------------


def test_parameterize_custom_bundle_splits_atomtypes(tmp_path: Path):
    itp, prm, gro = tmp_path / "ligand.itp", tmp_path / "extra.prm", tmp_path / "ligand.gro"
    itp.write_text(LIGAND_ITP, encoding="utf-8")
    prm.write_text(PRM, encoding="utf-8")
    gro.write_text(_gro(), encoding="utf-8")
    result = ligand.parameterize_ligand(tmp_path / "work", config=ligand.LigandPrepConfig(mode="custom_itp"),
                                        custom_itp=itp, custom_prm=prm, custom_gro=gro)
    assert (result.mode, result.charge_method, result.moleculetype, result.atom_count) == \
        ("custom_itp", "custom", "LIG", 2)
    assert result.atomtypes_itp is not None and result.atomtypes_itp.is_file()
    assert "atomtypes" not in result.ligand_itp.read_text(encoding="utf-8")


def test_parameterize_custom_bundle_returns_actual_residue_name_from_topology(tmp_path: Path):
    # Mode 0 输入的 ITP 和 GRO 都写 UNL 而未改 config.ligand_resname 时，返回值必须反映真实 UNL
    unl_itp = LIGAND_ITP.replace(" LIG ", " UNL ").replace("\nLIG ", "\nUNL ")
    unl_gro = _gro().replace("LIG  ", "UNL  ")
    itp, gro = tmp_path / "unl.itp", tmp_path / "unl.gro"
    itp.write_text(unl_itp, encoding="utf-8")
    gro.write_text(unl_gro, encoding="utf-8")
    result = ligand.parameterize_ligand(tmp_path / "work", config=ligand.LigandPrepConfig(mode="custom_itp"),
                                        custom_itp=itp, custom_gro=gro)
    assert (result.ligand_resname, result.moleculetype, result.atom_count) == ("UNL", "UNL", 2)


def test_parameterize_custom_bundle_rejects_reserved_or_multiple_residue_names(tmp_path: Path):
    for reserved in ("ALA", "HIE", "HSD", "CYX", "SEP", "TPO", "PTR", "TIP", "HHO", "OH2", "OHH"):
        res_itp = tmp_path / f"{reserved}.itp"
        res_gro = tmp_path / f"{reserved}.gro"
        res_itp.write_text(
            LIGAND_ITP.replace(" LIG ", f" {reserved} ").replace("\nLIG ", f"\n{reserved} "), encoding="utf-8")
        res_gro.write_text(_gro().replace("LIG  ", f"{reserved:<5s}"), encoding="utf-8")
        with pytest.raises(ligand.LigandParameterizationError, match="reserved residue name"):
            ligand.parameterize_ligand(tmp_path / f"w-{reserved}", config=ligand.LigandPrepConfig(mode="custom_itp"),
                                        custom_itp=res_itp, custom_gro=res_gro)
    multi_itp = tmp_path / "multi.itp"
    multi_gro = tmp_path / "multi.gro"
    multi_itp.write_text(
        "[ moleculetype ]\nUNL 2\n\n[ atoms ]\n"
        "  1  c3  1  UNL  C1  1  0.0  12.01\n  2  c3  2  ABC  C2  2  0.0  12.01\n", encoding="utf-8")
    multi_gro.write_text(
        "multi\n2\n"
        f"{1:5d}{'UNL':<5s}{'C1':<5s}{1:5d}{0.1:8.3f}{0.1:8.3f}{0.1:8.3f}\n"
        f"{2:5d}{'ABC':<5s}{'C2':<5s}{2:5d}{0.2:8.3f}{0.2:8.3f}{0.2:8.3f}\n"
        "2.0 2.0 2.0\n", encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError, match="one ligand residue name"):
        ligand.parameterize_ligand(tmp_path / "w2", config=ligand.LigandPrepConfig(mode="custom_itp"),
                                    custom_itp=multi_itp, custom_gro=multi_gro)


def test_parameterize_custom_zip_validates_posre_and_auto_mode(tmp_path: Path):
    archive = _zip(tmp_path / "bundle.zip",
                   {"ligand.itp": LIGAND_ITP, "ligand.gro": _gro(), "posre_ligand.itp": POSRE})
    result = ligand.parameterize_ligand(tmp_path / "work", config=ligand.LigandPrepConfig(), custom_zip=archive)
    assert result.mode == "custom_itp" and result.posre_itp is not None
    assert result.ligand_itp.is_file() and result.ligand_gro.is_file()


def test_parameterize_custom_zip_rejects_unsafe_include(tmp_path: Path):
    archive = _zip(tmp_path / "bundle.zip", {"ligand.itp": LIGAND_ITP, "ligand.gro": _gro(),
                                             "posre_ligand.itp": '#include "/etc/passwd"\n' + POSRE})
    with pytest.raises(ligand.LigandParameterizationError):
        ligand.parameterize_ligand(tmp_path / "work", config=ligand.LigandPrepConfig(mode="custom_itp"),
                                   custom_zip=archive)


def test_parameterize_custom_bundle_requires_itp_and_gro(tmp_path: Path):
    itp = tmp_path / "ligand.itp"
    itp.write_text(LIGAND_ITP, encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError, match=".gro"):
        ligand.parameterize_ligand(tmp_path / "work", config=ligand.LigandPrepConfig(mode="custom_itp"),
                                   custom_itp=itp)


def test_parameterize_custom_bundle_inlines_relative_includes(tmp_path: Path):
    bundle = tmp_path / "bundle"
    (bundle / "params").mkdir(parents=True)
    (bundle / "params" / "extra.prm").write_text(PRM, encoding="utf-8")
    itp = bundle / "ligand.itp"
    itp.write_text('#include "params/extra.prm"\n' + LIGAND_ITP, encoding="utf-8")
    gro = tmp_path / "ligand.gro"
    gro.write_text(_gro(), encoding="utf-8")
    work = tmp_path / "work"
    result = ligand.parameterize_ligand(work, config=ligand.LigandPrepConfig(mode="custom_itp"),
                                        custom_itp=itp, custom_gro=gro)
    # 交付的 ITP 落在 work/，相对 include 在那里解析不到：必须内联，且不再复制任何外部文件
    delivered = result.ligand_itp.read_text(encoding="utf-8")
    assert "#include" not in delivered and "params/extra.prm" not in delivered
    assert not (work / "params").exists()
    # .prm 的全局参数并入 atomtypes_itp，顺序与预处理展开一致（atomtypes 在最前）
    atomtypes = result.atomtypes_itp.read_text(encoding="utf-8")
    assert atomtypes.startswith("[ atomtypes ]") and "na " in atomtypes and "c3 " in atomtypes


def test_parameterize_custom_zip_inlines_the_include_tree(tmp_path: Path):
    archive = _zip(tmp_path / "bundle.zip", {"ligand.itp": '#include "params/extra.prm"\n' + LIGAND_ITP,
                                             "params/extra.prm": PRM, "ligand.gro": _gro()})
    work = tmp_path / "work"
    result = ligand.parameterize_ligand(work, config=ligand.LigandPrepConfig(mode="custom_itp"), custom_zip=archive)
    assert (work / "custom_topology" / "params" / "extra.prm").is_file()  # 原始包保持原样
    assert not (work / "params").exists()
    assert result.ligand_itp == (work / "ligand.itp").resolve()
    assert "#include" not in result.ligand_itp.read_text(encoding="utf-8")
    assert "na " in result.atomtypes_itp.read_text(encoding="utf-8")


def test_parameterize_custom_bundle_does_not_reinclude_an_inlined_posre(tmp_path: Path):
    # posre 已经通过 #include 内联进 ligand.itp：不能再返回独立 posre_itp 让 .top 二次 #include
    inlined = ('[ moleculetype ]\nLIG 2\n\n[ atoms ]\n 1 c3 1 LIG C1 1\n 2 c3 1 LIG C2 2\n\n'
               '#ifdef POSRES\n#include "posre_ligand.itp"\n#endif\n')
    archive = _zip(tmp_path / "bundle.zip",
                   {"ligand.itp": inlined, "posre_ligand.itp": POSRE, "ligand.gro": _gro()})
    result = ligand.parameterize_ligand(tmp_path / "work", config=ligand.LigandPrepConfig(mode="custom_itp"),
                                        custom_zip=archive)
    assert result.posre_itp is None
    assert "position_restraints" in result.ligand_itp.read_text(encoding="utf-8")


def test_parameterize_custom_bundle_inlines_a_separate_posre_file(tmp_path: Path):
    # 未内联的独立 posre 会交付到 work/：必须先把它的 #include 展开，交付文件才解析得到
    archive = _zip(tmp_path / "bundle.zip", {
        "ligand.itp": LIGAND_ITP, "ligand.gro": _gro(),
        "posre_ligand.itp": POSRE + '\n#include "restraints_body.itp"\n',
        "restraints_body.itp": "[ position_restraints ]\n  2  1  500  500  500\n"})
    result = ligand.parameterize_ligand(tmp_path / "work", config=ligand.LigandPrepConfig(mode="custom_itp"),
                                        custom_zip=archive)
    assert result.posre_itp is not None and result.posre_itp.name == "posre_ligand.itp"
    delivered = result.posre_itp.read_text(encoding="utf-8")
    assert "#include" not in delivered and "[ position_restraints ]" in delivered


def test_parameterize_custom_bundle_inlines_a_pure_include_posre_wrapper(tmp_path: Path):
    # 仅含 #include 的包装文件是合法的：节校验必须发生在展开之后，而不是对包装文件自身文本
    archive = _zip(tmp_path / "bundle.zip", {
        "ligand.itp": LIGAND_ITP, "ligand.gro": _gro(),
        "posre_ligand.itp": '#include "restraints_body.itp"\n',
        "restraints_body.itp": POSRE})
    result = ligand.parameterize_ligand(tmp_path / "work", config=ligand.LigandPrepConfig(mode="custom_itp"),
                                        custom_zip=archive)
    assert result.posre_itp is not None
    delivered = result.posre_itp.read_text(encoding="utf-8")
    assert "#include" not in delivered and "[ position_restraints ]" in delivered
    assert delivered.strip() == "[ position_restraints ]\n  1  1  1000  1000  1000"


def test_parameterize_custom_bundle_expands_a_posre_wrapper_over_data_rows(tmp_path: Path):
    # 包装文件自己带 [ position_restraints ]，再 #include 一个只含数据行（无节头）的子文件：GROMACS 合法，
    # 节校验必须在整棵 include 闭包展开后判定，不能因为子文件没有自己的 [ section ] 而拒绝。
    archive = _zip(tmp_path / "bundle.zip", {
        "ligand.itp": LIGAND_ITP, "ligand.gro": _gro(),
        "posre_ligand.itp": '[ position_restraints ]\n#include "posre_rows.itp"\n',
        "posre_rows.itp": "  1  1  1000  1000  1000\n  2  1  1000  1000  1000\n"})
    result = ligand.parameterize_ligand(tmp_path / "work", config=ligand.LigandPrepConfig(mode="custom_itp"),
                                        custom_zip=archive)
    assert result.posre_itp is not None
    delivered = result.posre_itp.read_text(encoding="utf-8")
    assert "#include" not in delivered and "[ position_restraints ]" in delivered
    assert delivered.count("1000  1000  1000") == 2  # 两行数据都已展开交付


def test_parameterize_custom_zip_prefers_the_itp_defining_moleculetype(tmp_path: Path):
    # ZIP 里字母序靠前的 00_atomtypes.itp 没有 [ moleculetype ]：不能被当成主拓扑，
    # 必须选中真正定义 [ moleculetype ] 的 ligand.itp，否则交付链路会缺 moleculetype 而失败。
    main = ('#include "00_atomtypes.itp"\n\n[ moleculetype ]\nLIG 2\n\n'
            "[ atoms ]\n  1  c3  1  LIG  C1  1  0.0  12.01\n  2  c3  1  LIG  C2  2  0.0  12.01\n")
    archive = _zip(tmp_path / "bundle.zip", {
        "00_atomtypes.itp": "[ atomtypes ]\nc3 6 12.01 0.0 A 0.34 0.46\n",
        "ligand.itp": main, "ligand.gro": _gro()})
    result = ligand.parameterize_ligand(tmp_path / "work", config=ligand.LigandPrepConfig(mode="custom_itp"),
                                        custom_zip=archive)
    assert (result.moleculetype, result.atom_count) == ("LIG", 2)
    assert result.atomtypes_itp is not None and "c3 " in result.atomtypes_itp.read_text(encoding="utf-8")
    assert "moleculetype" in result.ligand_itp.read_text(encoding="utf-8")


def test_parameterize_custom_zip_selects_a_pure_include_main_wrapper(tmp_path: Path):
    # 主入口只含 #include（自身没有节头）：闭包含 [ moleculetype ] 才合格；根包装优先于被 include 的子文件，
    # 00_atomtypes.itp 因闭包无 [ moleculetype ] 被排除，且 atomtypes 与 posre 都要完整交付。
    archive = _zip(tmp_path / "bundle.zip", {
        "00_atomtypes.itp": "[ atomtypes ]\nc3 6 12.01 0.0 A 0.34 0.46\n",
        "main_wrapper.itp": '#include "sub_mol.itp"\n',
        "sub_mol.itp": '#include "00_atomtypes.itp"\n[ moleculetype ]\nLIG 2\n\n'
                       "[ atoms ]\n  1  c3  1  LIG  C1  1  0.0  12.01\n  2  c3  1  LIG  C2  2  0.0  12.01\n",
        "posre_wrapper.itp": POSRE, "ligand.gro": _gro()})
    result = ligand.parameterize_ligand(tmp_path / "work", config=ligand.LigandPrepConfig(mode="custom_itp"),
                                        custom_zip=archive)
    assert (result.moleculetype, result.atom_count) == ("LIG", 2)
    assert "c3 " in result.atomtypes_itp.read_text(encoding="utf-8")
    assert result.posre_itp is not None and "position_restraints" in result.posre_itp.read_text(encoding="utf-8")


def test_parameterize_custom_zip_selects_a_posre_wrapper_over_earlier_data_rows(tmp_path: Path):
    # 00_posre_rows.itp（只有数据行、无节头）名字也含 posre 且排序靠前：不能盲取第一个，
    # 必须选闭包含 [ position_restraints ] 的根包装 posre_wrapper.itp，并展开交付两行限制。
    archive = _zip(tmp_path / "bundle.zip", {
        "ligand.itp": LIGAND_ITP, "ligand.gro": _gro(),
        "00_posre_rows.itp": "  1  1  1000  1000  1000\n  2  1  1000  1000  1000\n",
        "posre_wrapper.itp": '[ position_restraints ]\n#include "00_posre_rows.itp"\n'})
    result = ligand.parameterize_ligand(tmp_path / "work", config=ligand.LigandPrepConfig(mode="custom_itp"),
                                        custom_zip=archive)
    assert result.posre_itp is not None
    delivered = result.posre_itp.read_text(encoding="utf-8")
    assert "#include" not in delivered and delivered.count("1000  1000  1000") == 2


def test_parameterize_custom_bundle_rejects_a_posre_sharing_an_inlined_sub_include(tmp_path: Path):
    # 主 ITP 与独立 posre 共用同一个子 include：两边各交付一份会重复施加位置限制，必须报错
    shared = "[ position_restraints ]\n  1  1  1000  1000  1000\n"
    archive = _zip(tmp_path / "bundle.zip", {
        "ligand.itp": LIGAND_ITP + '#include "shared_restraints.itp"\n', "ligand.gro": _gro(),
        "posre_ligand.itp": '#include "shared_restraints.itp"\n', "shared_restraints.itp": shared})
    with pytest.raises(ligand.LigandParameterizationError, match="duplicate"):
        ligand.parameterize_ligand(tmp_path / "work", config=ligand.LigandPrepConfig(mode="custom_itp"),
                                   custom_zip=archive)


def test_parameterize_custom_bundle_rejects_a_posre_with_foreign_sections(tmp_path: Path):
    archive = _zip(tmp_path / "bundle.zip", {
        "ligand.itp": LIGAND_ITP, "ligand.gro": _gro(),
        "posre_ligand.itp": "[ atomtypes ]\nc3 6 12.01 0.0 A 0.34 0.46\n" + POSRE})
    with pytest.raises(ligand.LigandParameterizationError, match="non-restraint"):
        ligand.parameterize_ligand(tmp_path / "work", config=ligand.LigandPrepConfig(mode="custom_itp"),
                                   custom_zip=archive)


def test_parameterize_custom_bundle_rejects_a_posre_carrying_defaults(tmp_path: Path):
    archive = _zip(tmp_path / "bundle.zip", {
        "ligand.itp": LIGAND_ITP, "ligand.gro": _gro(),
        "posre_ligand.itp": "[ defaults ]\n1 2 yes 0.5 0.8333\n" + POSRE})
    with pytest.raises(ligand.LigandParameterizationError, match="non-restraint"):
        ligand.parameterize_ligand(tmp_path / "work", config=ligand.LigandPrepConfig(mode="custom_itp"),
                                   custom_zip=archive)


def test_parameterize_custom_bundle_rejects_globals_before_atomtypes(tmp_path: Path):
    itp, gro = tmp_path / "ligand.itp", tmp_path / "ligand.gro"
    itp.write_text("[ bondtypes ]\nc3 c3 1 0.10 100.0\n\n" + LIGAND_ITP, encoding="utf-8")
    gro.write_text(_gro(), encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError, match="precedes"):
        ligand.parameterize_ligand(tmp_path / "work", config=ligand.LigandPrepConfig(mode="custom_itp"),
                                   custom_itp=itp, custom_gro=gro)


def test_parameterize_custom_bundle_rejects_a_gro_with_fields_past_the_sixth_column(tmp_path: Path):
    # Mode 0 交付链路同样必须逐行校验坐标：第 6 列之后多出的 nan 不得被静默忽略
    prefix = f"{1:5d}{'LIG':<5s}{'C1':<5s}{1:5d}"
    coordinates = "".join(f"{value:8.3f}" for value in (0.1, 0.2, 0.3))
    itp, gro = tmp_path / "ligand.itp", tmp_path / "ligand.gro"
    itp.write_text(LIGAND_ITP, encoding="utf-8")
    second = f"{2:5d}{'LIG':<5s}{'C2':<5s}{2:5d}" + "".join(f"{value:8.3f}" for value in (0.4, 0.5, 0.6))
    gro.write_text(_gro_from_atom_lines([prefix + coordinates, second + "     nan"]), encoding="utf-8")
    with pytest.raises(ligand.LigandParameterizationError, match="coordinates"):
        ligand.parameterize_ligand(tmp_path / "work", config=ligand.LigandPrepConfig(mode="custom_itp"),
                                   custom_itp=itp, custom_gro=gro)


def _acpype_runner(itp: str = LIGAND_ITP, gro: str | None = None, *, returncode: int = 0,
                   cwd_seen: list[str] | None = None, files: dict[str, str] | None = None):
    def runner(command, cwd=None, env=None):
        if cwd_seen is not None:
            cwd_seen.append(str(cwd))
        # acpype 按 -b 命名产物目录与文件；替身必须照做，否则会掩盖 basename 不一致的真实缺陷
        basename = command[command.index("-b") + 1]
        output = Path(cwd) / f"{basename}.acpype"
        output.mkdir(parents=True, exist_ok=True)
        payload = files if files is not None else {
            f"{basename}_GMX.itp": itp,
            f"{basename}_GMX.gro": _gro() if gro is None else gro,
            f"posre_{basename}.itp": POSRE,
            f"{basename}_GMX_OPLS.itp": "[ moleculetype ]\nOPLS 1\n",
        }
        for name, text in payload.items():
            (output / name).write_text(text, encoding="utf-8")
        return SimpleNamespace(returncode=returncode, stderr="antechamber failed")

    return runner


def test_parameterize_gaff2_extracts_exact_non_opls_artifacts(tmp_path: Path):
    seen_command, seen_env = {}, {}

    def runner(command, cwd=None, env=None):
        seen_command["argv"] = command
        seen_env.update(env or {})
        return _acpype_runner()(command, cwd=cwd, env=env)

    result = ligand.parameterize_ligand(tmp_path / "work", config=ligand.LigandPrepConfig(),
                                        ligand_sdf=_ethanol_sdf(tmp_path), runner=runner)
    assert (result.mode, result.charge_method, result.moleculetype, result.atom_count) == \
        ("gaff2_acpype", "bcc", "LIG", 2)
    assert result.atomtypes_itp is not None and result.posre_itp is not None
    assert result.template_sdf is not None and result.template_sdf.is_file()
    assert "atomtypes" not in result.ligand_itp.read_text(encoding="utf-8")
    assert os.path.isabs(seen_command["argv"][seen_command["argv"].index("-i") + 1])
    assert seen_command["argv"][seen_command["argv"].index("-b") + 1] == "LIG"
    assert "AMBERHOME" in seen_env


def test_parameterize_gaff2_uses_fresh_directory_per_call(tmp_path: Path):
    seen: list[str] = []
    for _ in range(2):
        ligand.parameterize_ligand(tmp_path / "work", config=ligand.LigandPrepConfig(),
                                   ligand_sdf=_ethanol_sdf(tmp_path), runner=_acpype_runner(cwd_seen=seen))
    assert len(seen) == 2 and seen[0] != seen[1]


def test_parameterize_gaff2_rejects_stale_output_and_opls_only(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "ligand_GMX.itp").write_text(LIGAND_ITP, encoding="utf-8")  # 旧位置的残留文件
    (work / "ligand_GMX.gro").write_text(_gro(), encoding="utf-8")
    stale_runner = lambda *_a, cwd=None, **_k: SimpleNamespace(returncode=0, stderr="")  # noqa: E731
    with pytest.raises(ligand.LigandParameterizationError, match="incomplete"):
        ligand.parameterize_ligand(work, config=ligand.LigandPrepConfig(), ligand_sdf=_ethanol_sdf(tmp_path),
                                   runner=stale_runner)
    opls_only = _acpype_runner(files={"LIG_GMX_OPLS.itp": LIGAND_ITP, "LIG_GMX.gro": _gro()})
    with pytest.raises(ligand.LigandParameterizationError, match="incomplete"):
        ligand.parameterize_ligand(work, config=ligand.LigandPrepConfig(), ligand_sdf=_ethanol_sdf(tmp_path),
                                   runner=opls_only)


def test_parameterize_gaff2_rejects_artifacts_named_after_the_input_stem(tmp_path: Path):
    def stem_named_runner(command, cwd=None, env=None):
        # 旧实现按 input_path.stem（prepared/ligand.pdb → "ligand"）找产物；真实 acpype 用的是 -b 值
        output = Path(cwd) / "ligand.acpype"
        output.mkdir(parents=True, exist_ok=True)
        (output / "ligand_GMX.itp").write_text(LIGAND_ITP, encoding="utf-8")
        (output / "ligand_GMX.gro").write_text(_gro(), encoding="utf-8")
        return SimpleNamespace(returncode=0, stderr="")

    with pytest.raises(ligand.LigandParameterizationError, match="incomplete"):
        ligand.parameterize_ligand(tmp_path / "work", config=ligand.LigandPrepConfig(),
                                   ligand_sdf=_ethanol_sdf(tmp_path), runner=stem_named_runner)


def test_parameterize_gaff2_looks_up_artifacts_under_the_acpype_basename(tmp_path: Path):
    renamed = LIGAND_ITP.replace("LIG", "MOL")
    seen = {}

    def runner(command, cwd=None, env=None):
        seen["basename"] = command[command.index("-b") + 1]
        return _acpype_runner(renamed, _gro(resname="MOL"))(command, cwd=cwd, env=env)

    result = ligand.parameterize_ligand(tmp_path / "work", config=ligand.LigandPrepConfig(ligand_resname="MOL"),
                                        ligand_sdf=_ethanol_sdf(tmp_path), runner=runner)
    assert seen["basename"] == "MOL" == result.ligand_resname
    assert (result.moleculetype, result.ligand_gro.name) == ("MOL", "MOL_GMX.gro")
    assert result.ligand_gro.parent.name == "MOL.acpype"


def test_parameterize_gaff2_validates_itp_gro_consistency(tmp_path: Path):
    one_atom = LIGAND_ITP.replace("  2  c3  1  LIG  C2  2  0.0  12.01\n", "")
    with pytest.raises(ligand.LigandParameterizationError, match="atom count"):
        ligand.parameterize_ligand(tmp_path / "work", config=ligand.LigandPrepConfig(),
                                   ligand_sdf=_ethanol_sdf(tmp_path), runner=_acpype_runner(one_atom))

    wrong_resname = LIGAND_ITP.replace("LIG  C1", "UNL  C1").replace("LIG  C2", "UNL  C2")
    with pytest.raises(ligand.LigandParameterizationError, match="residue name"):
        ligand.parameterize_ligand(tmp_path / "work", config=ligand.LigandPrepConfig(),
                                   ligand_sdf=_ethanol_sdf(tmp_path), runner=_acpype_runner(wrong_resname))


def test_parameterize_gaff2_failure_raises_with_stderr(tmp_path: Path):
    with pytest.raises(ligand.LigandParameterizationError, match="antechamber failed"):
        ligand.parameterize_ligand(tmp_path / "work", config=ligand.LigandPrepConfig(),
                                   ligand_sdf=_ethanol_sdf(tmp_path), runner=_acpype_runner(returncode=1))


def test_parameterize_without_inputs_raises(tmp_path: Path):
    with pytest.raises(ligand.LigandParameterizationError):
        ligand.parameterize_ligand(tmp_path / "work", config=ligand.LigandPrepConfig())
    with pytest.raises(ligand.LigandParameterizationError):
        ligand.parameterize_ligand(tmp_path / "work", config=ligand.LigandPrepConfig(mode="unknown"))
