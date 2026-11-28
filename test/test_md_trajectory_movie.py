"""GROMACS 轨迹去溶剂化抽帧内核（PDB-movie）的纯净室回归测试。

不依赖 GPU、MDTraj 或真实 MD 引擎：轨迹通过注入的 fake ``Trajectory``
提供，RDKit 的 SDF 路径既用真实 RDKit（可用时）也用假模块覆盖，重点锁定
评审关心的行为：

* 去溶剂化剔除水/离子但强制保护配体，空结果分级降级；
* 配体补链号（避开已用链）、原子名去重、``TER`` 分界；
* 仅在最后一个 ``ENDMDL`` 之后写唯一一段 ``CONECT``，SDF 优先、ITP 兜底；
* 抽帧 0/1/2/5/200 边界、首尾必留、显式 stride 与体积预算压缩；
* nm→Å 坐标转换、PDB 固定列、超晶胞成像与 superpose 的优雅降级。
"""

from __future__ import annotations

import importlib.util
import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "deploy" / "model-images" / "k8s" / "gromacs" / "trajectory_movie.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("md_trajectory_movie_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


movie = _load_module()


def _pdb_line(
    serial: int,
    atom: str,
    resname: str,
    chain: str,
    seq: int,
    *,
    record: str = "ATOM",
    element: str = "C",
    altloc: str = " ",
    icode: str = " ",
    occupancy: float = 1.0,
    temp_factor: float = 20.0,
    x: float = 10.0,
    y: float = 10.0,
    z: float = 10.0,
) -> str:
    if len(atom) >= 4:
        name = atom[:4]  # PDB atom-name field is exactly four columns
    elif len(element) <= 1:
        name = f" {atom:<3}"
    else:
        name = f"{atom:<4}"
    return (
        f"{record:<6}{serial:5d} {name}{altloc}{resname:>3} {chain}{seq:4d}{icode}   "
        f"{x:8.3f}{y:8.3f}{z:8.3f}{occupancy:6.2f}{temp_factor:6.2f}          {element:>2}"
    )


def _write_pdb(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines + ["END"]) + "\n", encoding="utf-8")
    return path


def _complex_topology(path: Path) -> Path:
    """Protein (A/1) + ligand LIG (blank chain) + water + sodium + chloride."""
    return _write_pdb(
        path,
        [
            _pdb_line(1, "N", "MET", "A", 1, element="N"),
            _pdb_line(2, "CA", "MET", "A", 1),
            _pdb_line(3, "C", "MET", "A", 1),
            _pdb_line(4, "CB", "MET", "A", 1),
            _pdb_line(5, "C1", "LIG", "", 901, record="HETATM"),
            _pdb_line(6, "C2", "LIG", "", 901, record="HETATM"),
            _pdb_line(7, "O", "HOH", "A", 902, record="HETATM", element="O"),
            _pdb_line(8, "NA", "NA", "A", 903, record="HETATM", element="NA"),
            _pdb_line(9, "CL", "CL", "A", 904, record="HETATM", element="CL"),
        ],
    )


class FakeTrajectory:
    """Minimal mdtraj-like trajectory: ``slice`` then ``atom_slice`` are the API used."""

    raise_on_image = False

    def __init__(self, xyz, times, unitcell_vectors=None):
        self.xyz = xyz
        self.time = list(times)
        self.unitcell_vectors = unitcell_vectors
        self.n_frames = len(xyz)
        self.superpose_calls: list[list[int]] = []
        self.imaged = False

    def slice(self, indices, copy: bool = False):
        return FakeTrajectory(
            [self.xyz[index] for index in indices],
            [self.time[index] for index in indices],
            None if self.unitcell_vectors is None
            else [self.unitcell_vectors[0] for _ in indices],
        )

    def atom_slice(self, indices):
        sliced = FakeTrajectory(
            [[row[index] for index in indices] for row in self.xyz],
            self.time,
            self.unitcell_vectors,
        )
        sliced.raise_on_image = self.raise_on_image
        return sliced

    def superpose(self, reference, frame: int = 0, atom_indices=None):
        self.superpose_calls.append(list(atom_indices or []))

    def image_molecules(self, inplace: bool = False):
        if self.raise_on_image:
            raise RuntimeError("box is degenerate")
        self.imaged = True


class RecordingTrajectory(FakeTrajectory):
    """Records the sliced trajectory object so assertions see what mdtraj would see."""

    instances: list = []

    def slice(self, indices, copy: bool = False):
        return RecordingTrajectory(
            [self.xyz[index] for index in indices],
            [self.time[index] for index in indices],
            None if self.unitcell_vectors is None
            else [self.unitcell_vectors[0] for _ in indices],
        )

    def atom_slice(self, indices):
        sliced = FakeTrajectory.atom_slice(self, indices)
        RecordingTrajectory.instances.append(sliced)
        return sliced


class BrokenImagingTrajectory(FakeTrajectory):
    """``image_molecules`` always fails, to exercise the graceful degradation path."""

    def slice(self, indices, copy: bool = False):
        return BrokenImagingTrajectory(
            [self.xyz[index] for index in indices],
            [self.time[index] for index in indices],
            None if self.unitcell_vectors is None
            else [self.unitcell_vectors[0] for _ in indices],
        )

    def atom_slice(self, indices):
        return BrokenImagingTrajectory(
            [[row[index] for index in indices] for row in self.xyz],
            self.time,
            self.unitcell_vectors,
        )

    def image_molecules(self, inplace: bool = False):
        raise RuntimeError("box is degenerate")


def _xyz(frames: int, atoms: int, step: float = 0.1):
    return [
        [[step * (frame + 1) + 0.01 * position, 0.2, 0.3] for position in range(atoms)]
        for frame in range(frames)
    ]


# ---------------------------------------------------------------------------
# 常量与配置
# ---------------------------------------------------------------------------
def test_constants_and_default_config():
    assert movie.DEFAULT_MOVIE_MAX_FRAMES == 60
    assert movie.MIN_MOVIE_MAX_FRAMES == 1
    assert movie.MAX_MOVIE_MAX_FRAMES == 300
    assert movie.DEFAULT_MOVIE_MAX_BYTES == 25 * 1024 * 1024
    assert {"SOL", "HOH", "WAT", "TIP3P", "SPCE", "OPC", "OH2"} <= movie.WATER_RESNAMES
    assert {"NA", "CL", "K", "MG", "CA", "BR", "I"} <= movie.ION_RESNAMES

    config = movie.TrajectoryMovieConfig()
    assert config.max_frames == 60
    assert config.stride is None
    assert config.max_bytes == movie.DEFAULT_MOVIE_MAX_BYTES
    assert config.ligand_resname is None
    assert config.water_resname is None
    assert config.strip_ions is True
    assert config.superpose is True


# ---------------------------------------------------------------------------
# PDB 模板解析
# ---------------------------------------------------------------------------
def test_parse_pdb_atom_templates_preserves_fixed_columns(tmp_path: Path):
    pdb = _write_pdb(
        tmp_path / "topology.pdb",
        [
            _pdb_line(1, "N", "MET", "A", 1, element="N", altloc=" ", occupancy=1.0, temp_factor=20.0),
            _pdb_line(2, "CA", "MET", "A", 1, element="C", altloc="A", occupancy=0.5, temp_factor=21.5),
            "TER",
            _pdb_line(3, "C1", "LIG", "L", 901, record="HETATM", element="Cl"),
        ],
    )
    templates = movie.parse_pdb_atom_templates(pdb)

    assert [t.record for t in templates] == ["ATOM", "ATOM", "HETATM"]
    first, second, ligand = templates
    assert (first.atom_name, first.resname, first.chain_id, first.resseq) == ("N", "MET", "A", "1")
    assert second.atom_name == "CA" and second.altloc == "A"
    assert second.occupancy == pytest.approx(0.5)
    assert second.temp_factor == pytest.approx(21.5)
    assert first.element == "N" and second.element == "C"
    assert first.segment_index == 0 and second.segment_index == 0
    assert ligand.segment_index == 1 and ligand.element == "Cl"


def test_parse_pdb_atom_templates_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        movie.parse_pdb_atom_templates(tmp_path / "absent.pdb")


def test_parse_pdb_atom_templates_collapses_altlocs_like_mdtraj(tmp_path: Path):
    """Same residue/atom name with a new altLoc keeps only the first conformer, so
    the template count stays equal to what MDTraj loads from the same topology."""
    pdb = _write_pdb(
        tmp_path / "topology.pdb",
        [
            _pdb_line(1, "CA", "ALA", "A", 1, altloc="A"),
            _pdb_line(2, "CA", "ALA", "A", 1, altloc="B"),  # dropped alternate
            _pdb_line(3, "CB", "ALA", "A", 1, altloc="A"),
            _pdb_line(4, "CB", "ALA", "A", 1, altloc="B"),  # dropped alternate
            _pdb_line(5, "CA", "GLY", "A", 2, altloc="A"),  # new residue: kept
        ],
    )
    templates = movie.parse_pdb_atom_templates(pdb)
    assert [(t.resname, t.atom_name, t.altloc) for t in templates] == [
        ("ALA", "CA", "A"),
        ("ALA", "CB", "A"),
        ("GLY", "CA", "A"),
    ]


# ---------------------------------------------------------------------------
# 去溶剂化
# ---------------------------------------------------------------------------
def test_desolvation_removes_water_ions_and_keeps_ligand(tmp_path: Path):
    templates = movie.parse_pdb_atom_templates(_complex_topology(tmp_path / "topology.pdb"))
    kept = movie.select_desolvated_indices(templates, ligand_resname="LIG", water_resname="SOL")

    assert [templates[index].atom_name for index in kept] == ["N", "CA", "C", "CB", "C1", "C2"]

    strict = movie.select_desolvated_indices(templates, ligand_resname="LIG", strip_ions=True)
    assert kept == strict  # ions were already stripped


def test_desolvation_protects_ligand_named_like_an_ion(tmp_path: Path):
    pdb = _write_pdb(
        tmp_path / "topology.pdb",
        [
            _pdb_line(1, "CA", "ALA", "A", 1),
            _pdb_line(2, "NA", "NA", "L", 1, record="HETATM", element="NA"),
        ],
    )
    templates = movie.parse_pdb_atom_templates(pdb)
    kept = movie.select_desolvated_indices(templates, ligand_resname="NA", strip_ions=True)
    assert [templates[index].resname for index in kept] == ["ALA", "NA"]


def test_desolvation_empty_result_degrades_to_non_water(tmp_path: Path):
    pdb = _write_pdb(
        tmp_path / "topology.pdb",
        [
            _pdb_line(1, "O", "HOH", "A", 1, record="HETATM", element="O"),
            _pdb_line(2, "NA", "NA", "A", 2, record="HETATM", element="NA"),
        ],
    )
    templates = movie.parse_pdb_atom_templates(pdb)
    assert movie.select_desolvated_indices(templates) == [1]

    water_only = _write_pdb(
        tmp_path / "water.pdb",
        [_pdb_line(1, "O", "SOL", "A", 1, record="HETATM", element="O")],
    )
    assert movie.select_desolvated_indices(movie.parse_pdb_atom_templates(water_only)) == []


def test_desolvation_honours_custom_water_resname(tmp_path: Path):
    pdb = _write_pdb(
        tmp_path / "topology.pdb",
        [
            _pdb_line(1, "CA", "ALA", "A", 1),
            _pdb_line(2, "O", "SOLX", "A", 2, record="HETATM", element="O"),
        ],
    )
    templates = movie.parse_pdb_atom_templates(pdb)
    assert movie.select_desolvated_indices(templates, water_resname="solx") == [0]


# ---------------------------------------------------------------------------
# 配体规范化：链号、原子名去重、TER
# ---------------------------------------------------------------------------
def test_normalize_forces_hetatm_assigns_free_chain_and_dedupes_names():
    blank_chain = [
        movie.AtomTemplate("ATOM", "CA", "", "MET", "A", "1", "", 1.0, 0.0, "C", 0),
        movie.AtomTemplate("HETATM", "C1", "", "LIG", "", "901", "", 1.0, 0.0, "C", 0),
        movie.AtomTemplate("HETATM", "C1", "", "LIG", "", "901", "", 1.0, 0.0, "C", 0),
        movie.AtomTemplate("HETATM", "O1", "", "LIG", "", "901", "", 1.0, 0.0, "O", 0),
    ]
    layout = movie.normalize_movie_templates(blank_chain, ligand_resname="LIG")

    assert layout[0].atom.record == "ATOM"
    assert layout[1].atom.record == "HETATM"
    assert layout[1].atom.chain_id == "L"  # free chain id
    assert layout[2].atom.chain_id == "L"
    assert layout[1].atom.atom_name != layout[2].atom.atom_name
    assert len(layout[1].atom.atom_name) <= 4 and len(layout[2].atom.atom_name) <= 4
    assert layout[1].ter_before is True  # TER before the ligand
    assert layout[2].ter_before is False
    assert layout[3].atom.element == "O"

    taken = [
        movie.AtomTemplate("ATOM", "CA", "", "MET", "L", "1", "", 1.0, 0.0, "C", 0),
        movie.AtomTemplate("HETATM", "C1", "", "LIG", "", "901", "", 1.0, 0.0, "C", 0),
    ]
    assert movie.normalize_movie_templates(taken, ligand_resname="LIG")[1].atom.chain_id == "Z"


def test_normalize_ter_between_segments_and_chains():
    templates = [
        movie.AtomTemplate("ATOM", "CA", "", "ALA", "A", "1", "", 1.0, 0.0, "C", 0),
        movie.AtomTemplate("ATOM", "CA", "", "GLY", "B", "1", "", 1.0, 0.0, "C", 0),
        movie.AtomTemplate("ATOM", "CA", "", "SER", "A", "2", "", 1.0, 0.0, "C", 1),
        movie.AtomTemplate("HETATM", "C1", "", "LIG", "A", "9", "", 1.0, 0.0, "C", 1),
    ]
    layout = movie.normalize_movie_templates(templates, ligand_resname="LIG")
    assert [entry.ter_before for entry in layout] == [False, True, True, True]


def test_normalize_keeps_distinct_ligand_residues_separate():
    templates = [
        movie.AtomTemplate("HETATM", "C1", "", "LIG", "L", "1", "", 1.0, 0.0, "C", 0),
        movie.AtomTemplate("HETATM", "C2", "", "LIG", "L", "2", "", 1.0, 0.0, "C", 0),
    ]
    layout = movie.normalize_movie_templates(templates, ligand_resname="LIG")
    assert [entry.ter_before for entry in layout] == [False, True]


# ---------------------------------------------------------------------------
# CONECT
# ---------------------------------------------------------------------------
def _ligand_templates() -> list:
    return [
        movie.AtomTemplate("ATOM", "CA", "", "ALA", "A", "1", "", 1.0, 0.0, "C", 0),
        movie.AtomTemplate("HETATM", "C1", "", "LIG", "L", "1", "", 1.0, 0.0, "C", 0),
        movie.AtomTemplate("HETATM", "C2", "", "LIG", "L", "1", "", 1.0, 0.0, "C", 0),
        movie.AtomTemplate("HETATM", "O1", "", "LIG", "L", "1", "", 1.0, 0.0, "O", 0),
        movie.AtomTemplate("HETATM", "H1", "", "LIG", "L", "1", "", 1.0, 0.0, "H", 0),
    ]


def test_conect_from_itp_maps_local_atoms_to_kept_serials(tmp_path: Path):
    itp = tmp_path / "ligand.itp"
    itp.write_text(
        """[ bonds ]
1 2 1
2 3 1
3 4 1
4 9 1
""",
        encoding="utf-8",
    )
    lines = movie.build_ligand_conect_lines(_ligand_templates(), ligand_resname="LIG", ligand_itp=itp)
    # Ligand atoms occupy model serials 2..5 (protein CA is 1); out-of-range ITP index 9 is ignored.
    assert lines == [
        "CONECT    2    3",
        "CONECT    3    2    4",
        "CONECT    4    3    5",
        "CONECT    5    4",
    ]


def test_conect_without_template_is_empty_and_large_movie_is_skipped():
    assert movie.build_ligand_conect_lines(_ligand_templates(), ligand_resname="LIG") == []
    warnings: list[str] = []
    huge = [_ligand_templates()[1]] * 100000
    assert movie.build_ligand_conect_lines(huge, ligand_resname="LIG", warnings=warnings) == []
    assert any("99999" in warning for warning in warnings)


def _fake_rdkit(bonds, atom_count, elements=None):
    fake_module = types.ModuleType("rdkit")

    class FakeBond:
        def __init__(self, first, second, order):
            self._first, self._second, self._order = first, second, order

        def GetBeginAtomIdx(self):
            return self._first

        def GetEndAtomIdx(self):
            return self._second

        def GetBondTypeAsDouble(self):
            return self._order

    class FakeAtom:
        def __init__(self, symbol):
            self._symbol = symbol

        def GetSymbol(self):
            return self._symbol

    class FakeMol:
        def GetNumAtoms(self):
            return atom_count

        def GetAtoms(self):
            return [FakeAtom(symbol) for symbol in (elements or ["C"] * atom_count)]

        def GetBonds(self):
            return [FakeBond(*bond) for bond in bonds]

    fake_module.Chem = types.SimpleNamespace(
        MolFromMolFile=lambda *args, **kwargs: FakeMol(),
        Kekulize=lambda *args, **kwargs: None,
    )
    return fake_module


def test_conect_from_sdf_repeats_double_bonds(tmp_path: Path, monkeypatch):
    sdf = tmp_path / "ligand.sdf"
    sdf.write_text("fake\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "rdkit", _fake_rdkit([(0, 1, 2.0), (1, 2, 1.0)], 4, ["C", "C", "O", "H"]))

    lines = movie.build_ligand_conect_lines(_ligand_templates(), ligand_resname="LIG", ligand_template_sdf=sdf)
    # local ligand atoms 0,1,2 -> serials 2,3,4; C1=C2 repeated twice.
    assert lines == [
        "CONECT    2    3    3",
        "CONECT    3    2    2    4",
        "CONECT    4    3",
    ]


def test_conect_lines_wrap_after_four_targets(tmp_path: Path, monkeypatch):
    sdf = tmp_path / "ligand.sdf"
    sdf.write_text("fake\n", encoding="utf-8")
    bonds = [(0, index, 1.0) for index in range(1, 7)]
    elements = ["C", "C", "O", "H", "H", "H", "H"]
    monkeypatch.setitem(sys.modules, "rdkit", _fake_rdkit(bonds, 7, elements))
    atoms = _ligand_templates() + [
        movie.AtomTemplate("HETATM", f"H{index}", "", "LIG", "L", "1", "", 1.0, 0.0, "H", 0)
        for index in range(2, 5)
    ]
    lines = movie.build_ligand_conect_lines(atoms, ligand_resname="LIG", ligand_template_sdf=sdf)
    assert "CONECT    2    3    4    5    6" in lines
    assert "CONECT    2    7    8" in lines
    # Columns 7-11 hold the source serial, then at most four 5-char targets.
    assert all(len(line) <= 11 + 4 * 5 for line in lines)


def test_conect_from_real_sdf_ethene(tmp_path: Path):
    pytest.importorskip("rdkit")
    sdf = tmp_path / "ethene.sdf"
    sdf.write_text(
        """ethene
  AIDD

  2  1  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.3300    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  2  0
M  END
""",
        encoding="utf-8",
    )
    atoms = [
        movie.AtomTemplate("ATOM", "CA", "", "ALA", "A", "1", "", 1.0, 0.0, "C", 0),
        movie.AtomTemplate("HETATM", "C1", "", "LIG", "L", "1", "", 1.0, 0.0, "C", 0),
        movie.AtomTemplate("HETATM", "C2", "", "LIG", "L", "1", "", 1.0, 0.0, "C", 0),
    ]
    lines = movie.build_ligand_conect_lines(atoms, ligand_resname="LIG", ligand_template_sdf=sdf)
    assert "CONECT    2    3    3" in lines
    assert "CONECT    3    2    2" in lines


def test_conect_sdf_atom_count_mismatch_falls_back_to_itp(tmp_path: Path, monkeypatch):
    sdf = tmp_path / "ligand.sdf"
    sdf.write_text("fake\n", encoding="utf-8")
    itp = tmp_path / "ligand.itp"
    itp.write_text("[ bonds ]\n1 2 1\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "rdkit", _fake_rdkit([(0, 1, 1.0)], atom_count=99))

    warnings: list[str] = []
    lines = movie.build_ligand_conect_lines(
        _ligand_templates(), ligand_resname="LIG", ligand_template_sdf=sdf, ligand_itp=itp, warnings=warnings
    )
    assert lines == ["CONECT    2    3", "CONECT    3    2"]
    assert any("SDF" in warning for warning in warnings)


def test_conect_itp_collapses_undirected_duplicate_bonds(tmp_path: Path):
    """ITP files sometimes list both ``1 2`` and ``2 1``; that is one bond, not two."""
    itp = tmp_path / "ligand.itp"
    itp.write_text("[ bonds ]\n1 2 1\n2 1 1\n1 2 1\n", encoding="utf-8")
    lines = movie.build_ligand_conect_lines(_ligand_templates(), ligand_resname="LIG", ligand_itp=itp)
    assert lines == ["CONECT    2    3", "CONECT    3    2"]


def test_conect_sdf_element_order_mismatch_falls_back_to_itp(tmp_path: Path, monkeypatch):
    """SDF atoms in a different element order (N,C vs C,N) must not be mapped positionally."""
    sdf = tmp_path / "ligand.sdf"
    sdf.write_text("fake\n", encoding="utf-8")
    itp = tmp_path / "ligand.itp"
    itp.write_text("[ bonds ]\n1 2 1\n", encoding="utf-8")
    # SDF says N,C,O,H but the topology is C,C,O,H -> mapping is untrustworthy.
    monkeypatch.setitem(sys.modules, "rdkit", _fake_rdkit([(0, 1, 2.0)], 4, ["N", "C", "O", "H"]))
    warnings: list[str] = []
    lines = movie.build_ligand_conect_lines(
        _ligand_templates(), ligand_resname="LIG", ligand_template_sdf=sdf, ligand_itp=itp, warnings=warnings
    )
    assert lines == ["CONECT    2    3", "CONECT    3    2"]  # ITP single bond, not SDF double
    assert any("element order" in warning for warning in warnings)


# ---------------------------------------------------------------------------
# 抽帧与体积预算
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("total", "max_frames", "expected"),
    [
        (0, 60, []),
        (1, 60, [0]),
        (1, 1, [0]),
        (2, 60, [0, 1]),
        (2, 1, [0, 1]),  # a multi-frame source never collapses to a single frame
        (5, 60, [0, 1, 2, 3, 4]),
    ],
)
def test_select_frame_indices_small_boundaries(total, max_frames, expected):
    assert movie.select_frame_indices(total, max_frames=max_frames) == expected


def test_select_frame_indices_200_frames_keeps_ends_and_is_strict():
    indices = movie.select_frame_indices(200, max_frames=60)
    assert len(indices) == 60
    assert indices[0] == 0 and indices[-1] == 199
    assert all(later > earlier for earlier, later in zip(indices, indices[1:]))


def test_select_frame_indices_explicit_stride_then_downsample():
    assert movie.select_frame_indices(25, stride=10) == [0, 10, 20, 24]
    assert movie.select_frame_indices(25, stride=10, max_frames=2) == [0, 24]
    assert movie.select_frame_indices(5, stride=0) == [0, 1, 2, 3, 4]
    assert movie.select_frame_indices(5, stride=1, max_frames=999) == [0, 1, 2, 3, 4]
    assert movie.select_frame_indices(5, max_frames=0) == [0, 4]


def test_byte_budget_reduces_frames_and_warns():
    warnings: list[str] = []
    reduced = movie._apply_byte_budget(list(range(60)), 5000, 1_000_000, warnings)
    # 5000 atoms * 82 + 48 ~= 410048 bytes per frame -> only 2 frames fit.
    assert reduced == [0, 59]
    assert warnings and "reduced frames" in warnings[0]

    warnings.clear()
    assert movie._apply_byte_budget(list(range(60)), 10, None, warnings) == list(range(60))
    assert movie._apply_byte_budget(list(range(60)), 10, 10**9, warnings) == list(range(60))
    assert not warnings


# ---------------------------------------------------------------------------
# 导出主流程（fake 轨迹）
# ---------------------------------------------------------------------------
def _fake_loader(trajectory):
    calls: list[tuple[Path, Path]] = []

    def loader(topology_pdb, trajectory_path):
        calls.append((Path(topology_pdb), Path(trajectory_path)))
        return trajectory

    return loader, calls


def test_export_desolvated_movie_end_to_end(tmp_path: Path):
    topology = _complex_topology(tmp_path / "topology.pdb")
    trajectory_file = tmp_path / "md.xtc"
    trajectory_file.write_bytes(b"xtc")
    trajectory = FakeTrajectory(_xyz(4, 6), times=[0.0, 10.0, 20.0, 30.0])
    loader, calls = _fake_loader(trajectory)

    stats = movie.export_desolvated_pdb_movie(
        topology,
        trajectory_file,
        tmp_path / "out" / "trajectory_movie.pdb",
        config=movie.TrajectoryMovieConfig(max_frames=2, ligand_resname="LIG"),
        trajectory_loader=loader,
    )

    assert calls == [(topology, trajectory_file)]
    assert stats["written"] is True
    assert stats["movie_frames"] == 2
    assert stats["total_source_frames"] == 4
    assert stats["frame_indices"] == [0, 3]
    assert stats["frame_times_ps"] == [0.0, 30.0]
    assert stats["atom_count"] == 6
    assert stats["desolvated"] is True
    assert stats["aligned"] is True
    assert stats["conect_count"] == 0
    assert stats["movie_stride"] == 3

    text = (tmp_path / "out" / "trajectory_movie.pdb").read_text(encoding="utf-8")
    assert text.count("MODEL ") == 2
    assert text.count("ENDMDL") == 2
    assert not any(line.startswith("CONECT") for line in text.splitlines())
    atom_lines = [line for line in text.splitlines() if line.startswith(("ATOM", "HETATM"))]
    assert len(atom_lines) == 12
    # nm -> Å: first kept atom first frame x = (0.1 + 0.0) nm = 1.000 Å.
    assert atom_lines[0][30:38] == "   1.000"
    assert atom_lines[0][76:78] == " N"
    assert "HOH" not in text and " NA " not in text and " CL " not in text
    assert text.rstrip().splitlines()[-1] == "END"


def _three_ca_topology(path: Path) -> Path:
    return _write_pdb(
        path,
        [
            _pdb_line(1, "CA", "ALA", "A", 1),
            _pdb_line(2, "CA", "GLY", "A", 2),
            _pdb_line(3, "CA", "SER", "A", 3),
            _pdb_line(4, "C1", "LIG", "L", 9, record="HETATM"),
            _pdb_line(5, "O", "HOH", "A", 10, record="HETATM", element="O"),
        ],
    )


def test_export_superposes_on_ca_atoms(tmp_path: Path):
    """The exported ``sampled`` trajectory is the object that sees ``superpose``."""
    RecordingTrajectory.instances.clear()
    topology = _three_ca_topology(tmp_path / "topology.pdb")
    trajectory_file = tmp_path / "md.xtc"
    trajectory_file.write_bytes(b"xtc")
    loader, _ = _fake_loader(RecordingTrajectory(_xyz(3, 5), times=[0.0, 5.0, 10.0]))

    stats = movie.export_desolvated_pdb_movie(
        topology,
        trajectory_file,
        tmp_path / "movie.pdb",
        config=movie.TrajectoryMovieConfig(max_frames=2, ligand_resname="LIG"),
        trajectory_loader=loader,
    )
    assert stats["aligned"] is True
    assert RecordingTrajectory.instances[-1].superpose_calls == [[0, 1, 2]]


def test_export_falls_back_to_protein_heavy_atoms_when_no_ca(tmp_path: Path):
    pdb = _write_pdb(
        tmp_path / "topology.pdb",
        [
            _pdb_line(1, "N", "ALA", "A", 1, element="N"),
            _pdb_line(2, "CB", "ALA", "A", 1),
            _pdb_line(3, "CG", "ALA", "A", 1),
            _pdb_line(4, "CD", "ALA", "A", 1),
        ],
    )
    trajectory_file = tmp_path / "md.xtc"
    trajectory_file.write_bytes(b"xtc")
    RecordingTrajectory.instances.clear()
    loader, _ = _fake_loader(RecordingTrajectory(_xyz(2, 4), times=[0.0, 1.0]))

    stats = movie.export_desolvated_pdb_movie(
        pdb,
        trajectory_file,
        tmp_path / "movie.pdb",
        config=movie.TrajectoryMovieConfig(max_frames=2),
        trajectory_loader=loader,
    )
    assert stats["aligned"] is True
    assert RecordingTrajectory.instances[-1].superpose_calls == [[0, 1, 2, 3]]
    assert not any("heavy atoms" in warning for warning in stats["warnings"])


def test_alignment_indices_fall_back_and_skip():
    protein = [
        movie.AtomTemplate("ATOM", "N", "", "ALA", "A", "1", "", 1.0, 0.0, "N", 0),
        movie.AtomTemplate("ATOM", "CB", "", "ALA", "A", "1", "", 1.0, 0.0, "C", 0),
        movie.AtomTemplate("ATOM", "CG", "", "ALA", "A", "1", "", 1.0, 0.0, "C", 0),
    ]
    ligand = movie.AtomTemplate("HETATM", "C1", "", "LIG", "L", "2", "", 1.0, 0.0, "C", 0)
    assert movie._alignment_indices(protein + [ligand]) == [0, 1, 2]
    assert movie._alignment_indices(protein[:2] + [ligand]) == []
    calphas = [replace(atom, atom_name="CA") for atom in protein]
    assert movie._alignment_indices(calphas + [ligand]) == [0, 1, 2]


def test_export_with_too_few_atoms_skips_alignment_and_writes(tmp_path: Path):
    pdb = _write_pdb(
        tmp_path / "topology.pdb",
        [
            _pdb_line(1, "CA", "GLY", "A", 1),
            _pdb_line(2, "CB", "GLY", "A", 1),
        ],
    )
    trajectory_file = tmp_path / "md.xtc"
    trajectory_file.write_bytes(b"xtc")
    loader, _ = _fake_loader(FakeTrajectory(_xyz(2, 2), times=[0.0, 1.0]))
    stats = movie.export_desolvated_pdb_movie(
        pdb,
        trajectory_file,
        tmp_path / "movie.pdb",
        config=movie.TrajectoryMovieConfig(max_frames=2),
        trajectory_loader=loader,
    )
    assert stats["written"] is True
    assert stats["aligned"] is False
    assert any("superposed" in warning for warning in stats["warnings"])


def test_export_applies_byte_budget(tmp_path: Path):
    topology = _complex_topology(tmp_path / "topology.pdb")
    trajectory_file = tmp_path / "md.xtc"
    trajectory_file.write_bytes(b"xtc")
    loader, _ = _fake_loader(FakeTrajectory(_xyz(10, 6), times=list(range(10))))

    stats = movie.export_desolvated_pdb_movie(
        topology,
        trajectory_file,
        tmp_path / "movie.pdb",
        config=movie.TrajectoryMovieConfig(max_frames=10, max_bytes=2000, ligand_resname="LIG"),
        trajectory_loader=loader,
    )
    # 6 atoms * 82 + 32 = 524 bytes/frame -> (2000 - 512) // 524 = 2 frames.
    assert stats["written"] is True
    assert stats["movie_frames"] == 2
    assert stats["frame_indices"] == [0, 9]
    assert stats["size_bytes"] <= 2000
    assert any("reduced frames" in warning for warning in stats["warnings"])


def test_export_skips_movie_when_budget_cannot_fit_two_frames(tmp_path: Path):
    topology = _complex_topology(tmp_path / "topology.pdb")
    trajectory_file = tmp_path / "md.xtc"
    trajectory_file.write_bytes(b"xtc")
    loader, _ = _fake_loader(FakeTrajectory(_xyz(10, 6), times=list(range(10))))

    stats = movie.export_desolvated_pdb_movie(
        topology,
        trajectory_file,
        tmp_path / "movie.pdb",
        config=movie.TrajectoryMovieConfig(max_frames=10, max_bytes=1200, ligand_resname="LIG"),
        trajectory_loader=loader,
    )
    assert stats["written"] is False
    assert any("cannot fit two frames" in warning for warning in stats["warnings"])
    assert not (tmp_path / "movie.pdb").exists()


def test_export_writes_unique_conect_between_last_endmdl_and_end(tmp_path: Path):
    topology = _complex_topology(tmp_path / "topology.pdb")
    trajectory_file = tmp_path / "md.xtc"
    trajectory_file.write_bytes(b"xtc")
    itp = tmp_path / "ligand.itp"
    itp.write_text("[ bonds ]\n1 2 1\n", encoding="utf-8")
    loader, _ = _fake_loader(FakeTrajectory(_xyz(3, 6), times=[0.0, 5.0, 10.0]))

    stats = movie.export_desolvated_pdb_movie(
        topology,
        trajectory_file,
        tmp_path / "movie.pdb",
        config=movie.TrajectoryMovieConfig(max_frames=3, ligand_resname="LIG", superpose=False),
        ligand_itp=itp,
        trajectory_loader=loader,
    )
    assert stats["conect_count"] == 2  # C1(5)-C2(6) both directions
    lines = (tmp_path / "movie.pdb").read_text(encoding="utf-8").splitlines()
    conect_lines = [line for line in lines if line.startswith("CONECT")]
    assert conect_lines == ["CONECT    5    6", "CONECT    6    5"]
    assert lines.index("ENDMDL") < lines.index(conect_lines[0])
    assert lines.index(conect_lines[-1]) < lines.index("END")
    assert lines.count("ENDMDL") == 3


def test_imaging_helper_detects_far_coordinates():
    inside = FakeTrajectory(_xyz(1, 2, step=0.1), times=[0.0], unitcell_vectors=[[[3, 0, 0], [0, 3, 0], [0, 0, 3]]])
    assert movie._needs_imaging(inside) is False

    far = FakeTrajectory([[[10.0, 0.0, 0.0]]], times=[0.0], unitcell_vectors=[[[3, 0, 0], [0, 3, 0], [0, 0, 3]]])
    assert movie._needs_imaging(far) is True
    assert movie._needs_imaging(FakeTrajectory([[[10.0, 0.0, 0.0]]], times=[0.0])) is False


def test_imaging_detects_split_molecule_inside_one_frame():
    """0.1 nm and 9.9 nm are 9.8 nm apart in a 10 nm box: same molecule split by PBC."""
    split = FakeTrajectory(
        [[[0.1, 0.1, 0.1], [9.9, 0.1, 0.1]]], times=[0.0],
        unitcell_vectors=[[[10, 0, 0], [0, 10, 0], [0, 0, 10]]],
    )
    assert movie._needs_imaging(split) is True


def test_imaging_detects_between_frame_wrap():
    wrapped = FakeTrajectory(
        [[[0.1, 0.1, 0.1]], [[9.9, 0.1, 0.1]]], times=[0.0, 1.0],
        unitcell_vectors=[[[10, 0, 0], [0, 10, 0], [0, 0, 10]]],
    )
    assert movie._needs_imaging(wrapped) is True


def test_coords_valid_rejects_non_finite_and_column_overflow():
    assert movie._coords_valid([[(1.0, 2.0, 3.0)]] * 2) is True
    assert movie._coords_valid([[(1.0, float("nan"), 3.0)]]) is False
    assert movie._coords_valid([[(float("inf"), 0.0, 0.0)]]) is False
    assert movie._coords_valid([[(9999.999, 0.0, 0.0)]]) is True
    assert movie._coords_valid([[(10000.0, 0.0, 0.0)]]) is False


def test_render_movie_places_model_serial_in_wwpdb_columns():
    model_lines = [line for line in movie._render_movie([], [[], [], []], [], []).splitlines()
                   if line.startswith("MODEL")]
    assert [line[10:14].strip() for line in model_lines] == ["1", "2", "3"]
    assert all(line[:6] == "MODEL " and not line[6:10].strip() for line in model_lines)


def test_imaging_failure_degrades_with_warning(tmp_path: Path):
    topology = _complex_topology(tmp_path / "topology.pdb")
    trajectory_file = tmp_path / "md.xtc"
    trajectory_file.write_bytes(b"xtc")

    far_xyz = [[[10.0, 1.0, 1.0] for _ in range(6)]]
    loader, _ = _fake_loader(
        BrokenImagingTrajectory(far_xyz, times=[0.0], unitcell_vectors=[[[3, 0, 0], [0, 3, 0], [0, 0, 3]]])
    )

    stats = movie.export_desolvated_pdb_movie(
        topology,
        trajectory_file,
        tmp_path / "movie.pdb",
        config=movie.TrajectoryMovieConfig(max_frames=1, ligand_resname="LIG"),
        trajectory_loader=loader,
    )
    assert stats["written"] is True
    assert any("PBC imaging failed" in warning for warning in stats["warnings"])


def test_export_rejects_missing_inputs(tmp_path: Path):
    trajectory_file = tmp_path / "md.xtc"
    trajectory_file.write_bytes(b"xtc")
    with pytest.raises(FileNotFoundError):
        movie.export_desolvated_pdb_movie(tmp_path / "absent.pdb", trajectory_file, tmp_path / "o.pdb")

    topology = _complex_topology(tmp_path / "topology.pdb")
    with pytest.raises(FileNotFoundError):
        movie.export_desolvated_pdb_movie(topology, tmp_path / "absent.xtc", tmp_path / "o.pdb")


def test_export_returns_not_written_when_everything_is_water(tmp_path: Path):
    topology = _write_pdb(
        tmp_path / "water.pdb",
        [_pdb_line(1, "O", "SOL", "A", 1, record="HETATM", element="O")],
    )
    trajectory_file = tmp_path / "md.xtc"
    trajectory_file.write_bytes(b"xtc")
    loader, calls = _fake_loader(FakeTrajectory(_xyz(1, 1), times=[0.0]))
    stats = movie.export_desolvated_pdb_movie(
        topology,
        trajectory_file,
        tmp_path / "movie.pdb",
        trajectory_loader=loader,
    )
    assert stats["written"] is False
    assert stats["warnings"]
    assert calls == []  # the trajectory is never loaded when nothing survives
    assert not (tmp_path / "movie.pdb").exists()


# ---------------------------------------------------------------------------
# 复审修复（Issue 1/3/4/5/6/7）
# ---------------------------------------------------------------------------
# Issue 1: 采样帧时间缺失时整列降级为 []，绝不伪造 0.0/1.0。
def test_strict_frame_times_never_fabricate_values():
    assert movie._strict_frame_times(None, [0, 1]) == []
    assert movie._strict_frame_times([0.0, 1.0], [0, 5]) == []          # 数组短于最大索引
    assert movie._strict_frame_times([0.0, "bad"], [0, 1]) == []
    assert movie._strict_frame_times([0.0, float("nan")], [0, 1]) == []
    assert movie._strict_frame_times([0.0, float("inf")], [0, 1]) == []
    assert movie._strict_frame_times([True, 1.0], [0, 1]) == []          # bool 不是实数
    assert movie._strict_frame_times([0.0, 2, 4.5], [0, 2]) == [0.0, 4.5]


def test_export_returns_empty_frame_times_when_array_is_unusable(tmp_path: Path):
    topology = _complex_topology(tmp_path / "topology.pdb")
    trajectory_file = tmp_path / "md.xtc"
    trajectory_file.write_bytes(b"xtc")
    trajectory = FakeTrajectory(_xyz(3, 6), times=[0.0, 5.0, 10.0])
    trajectory.time = [None, None, None]  # 每个采样帧都拿不到真实时间
    loader, _ = _fake_loader(trajectory)

    stats = movie.export_desolvated_pdb_movie(
        topology, trajectory_file, tmp_path / "movie.pdb",
        config=movie.TrajectoryMovieConfig(max_frames=2, ligand_resname="LIG"),
        trajectory_loader=loader,
    )
    assert stats["written"] is True
    assert stats["frame_times_ps"] == []  # 不是 [0.0, 0.0]


# Issue 3: SDF 与 ITP 键拓扑不一致时放弃 SDF 键级，回落 ITP 单键。
def test_conect_sdf_topology_mismatch_falls_back_to_itp(tmp_path: Path, monkeypatch):
    sdf = tmp_path / "ligand.sdf"
    sdf.write_text("fake\n", encoding="utf-8")
    itp = tmp_path / "ligand.itp"
    itp.write_text("[ bonds ]\n1 2 1\n2 3 1\n", encoding="utf-8")
    # 元素顺序相同，但 SDF 只连 0-2，与 ITP 的 {0-1,1-2} 不同。
    monkeypatch.setitem(sys.modules, "rdkit", _fake_rdkit([(0, 2, 1.0)], 4, ["C", "C", "O", "H"]))
    warnings: list[str] = []

    lines = movie.build_ligand_conect_lines(
        _ligand_templates(), ligand_resname="LIG",
        ligand_template_sdf=sdf, ligand_itp=itp, warnings=warnings,
    )
    assert any("SDF bond topology differs" in warning for warning in warnings)
    assert lines == ["CONECT    2    3", "CONECT    3    2    4", "CONECT    4    3"]


def test_conect_sdf_used_when_topology_matches_itp(tmp_path: Path, monkeypatch):
    sdf = tmp_path / "ligand.sdf"
    sdf.write_text("fake\n", encoding="utf-8")
    itp = tmp_path / "ligand.itp"
    itp.write_text("[ bonds ]\n1 2 1\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "rdkit", _fake_rdkit([(0, 1, 2.0)], 4, ["C", "C", "O", "H"]))
    warnings: list[str] = []

    lines = movie.build_ligand_conect_lines(
        _ligand_templates(), ligand_resname="LIG",
        ligand_template_sdf=sdf, ligand_itp=itp, warnings=warnings,
    )
    assert not any("differs" in warning for warning in warnings)
    assert lines == ["CONECT    2    3    3", "CONECT    3    2    2"]  # 保留 SDF 双键


# Issue 4a: altLoc 归并以 MDTraj 的 (segment, chain, resseq, icode) 为键，不含 resname。
def test_parse_merges_altlocs_by_chain_and_number_not_resname(tmp_path: Path):
    pdb = _write_pdb(
        tmp_path / "topology.pdb",
        [
            _pdb_line(1, "CA", "SER", "A", 10, altloc="A"),
            _pdb_line(2, "CA", "CYS", "A", 10, altloc="B"),
            _pdb_line(3, "CB", "SER", "A", 10, altloc="A"),
            _pdb_line(4, "CB", "CYS", "A", 10, altloc="B"),
        ],
    )
    templates = movie.parse_pdb_atom_templates(pdb)
    assert [atom.atom_name for atom in templates] == ["CA", "CB"]
    assert all(atom.resname == "SER" for atom in templates)  # 首个 resname 被锁定


# Issue 4b: 元素校验只针对保留下来的原子，被剔除的溶剂/虚拟位点（VS）不得整片失败。
class _TopoTrajectory:
    def __init__(self, n_atoms: int, symbols: list[str]):
        self.n_atoms = n_atoms
        self.topology = types.SimpleNamespace(
            atoms=[types.SimpleNamespace(element=types.SimpleNamespace(symbol=s)) for s in symbols]
        )


def test_validate_topology_ignores_removed_virtual_site_element_mismatch():
    templates = [
        movie.AtomTemplate("ATOM", "CA", "", "ALA", "A", "1", "", 1.0, 0.0, "C", 0),
        movie.AtomTemplate("ATOM", "N", "", "ALA", "A", "1", "", 1.0, 0.0, "N", 0),
        movie.AtomTemplate("HETATM", "O", "", "SOL", "A", "2", "", 1.0, 0.0, "", 0),
    ]
    # 被保留的蛋白原子元素一致；被剔除的水却报 GRO 虚拟位点 VS，不应抛错。
    movie._validate_trajectory_topology(_TopoTrajectory(3, ["C", "N", "VS"]), templates, keep_indices=[0, 1])
    # 保留原子的元素不一致时必须拒绝渲染。
    with pytest.raises(ValueError):
        movie._validate_trajectory_topology(_TopoTrajectory(3, ["O", "N", "VS"]), templates, keep_indices=[0, 1])


# Issue 5a: 两帧小影片在 1024 字节预算内必须成功（不再因粗略估计只容 1 帧而跳过）。
def _four_atom_topology(path: Path) -> Path:
    return _write_pdb(
        path,
        [
            _pdb_line(1, "N", "ALA", "A", 1, element="N"),
            _pdb_line(2, "CA", "ALA", "A", 1),
            _pdb_line(3, "C", "ALA", "A", 1),
            _pdb_line(4, "CB", "ALA", "A", 1),
        ],
    )


def test_two_frame_movie_fits_small_byte_budget(tmp_path: Path):
    topology = _four_atom_topology(tmp_path / "topology.pdb")
    trajectory_file = tmp_path / "md.xtc"
    trajectory_file.write_bytes(b"xtc")
    loader, _ = _fake_loader(FakeTrajectory(_xyz(2, 4), times=[0.0, 1.0]))

    stats = movie.export_desolvated_pdb_movie(
        topology, trajectory_file, tmp_path / "movie.pdb",
        config=movie.TrajectoryMovieConfig(max_frames=2, max_bytes=1024),
        trajectory_loader=loader,
    )
    assert stats["written"] is True
    assert stats["movie_frames"] == 2
    assert stats["size_bytes"] <= 1024


# Issue 5b: 依据实际 UTF-8 体积重采样后，帧索引/帧时间/stride 与 PDB 头部保持一致。
def _bonded_ligand_topology(path: Path, atoms: int) -> Path:
    lines = [_pdb_line(index + 1, "CA", "ALA", "A", index + 1) for index in range(3)]
    lines += [_pdb_line(4 + index, f"C{index + 1}", "LIG", "L", 9, record="HETATM") for index in range(atoms)]
    return _write_pdb(path, lines)


def test_resample_keeps_metadata_and_header_in_sync(tmp_path: Path):
    ligands = 99
    atoms = 3 + ligands
    topology = _bonded_ligand_topology(tmp_path / "topology.pdb", ligands)
    itp = tmp_path / "ligand.itp"
    itp.write_text("[ bonds ]\n" + "".join(f"{i} {i + 1} 1\n" for i in range(1, ligands)), encoding="utf-8")
    trajectory_file = tmp_path / "md.xtc"
    trajectory_file.write_bytes(b"xtc")
    loader, _ = _fake_loader(FakeTrajectory(_xyz(3, atoms), times=[0.0, 1.0, 2.0]))

    # 帧选择按每帧 82 字节/原子估算恰好保留 3 帧；真实 CONECT 块更大，触发按实际体积重采样。
    per_frame = atoms * movie._ATOM_LINE_BYTES + movie._MODEL_OVERHEAD_BYTES
    max_bytes = 3 * per_frame + movie._GLOBAL_OVERHEAD_BYTES
    stats = movie.export_desolvated_pdb_movie(
        topology, trajectory_file, tmp_path / "movie.pdb",
        config=movie.TrajectoryMovieConfig(max_frames=3, ligand_resname="LIG", max_bytes=max_bytes),
        ligand_itp=itp, trajectory_loader=loader,
    )
    assert stats["written"] is True
    assert stats["movie_frames"] < 3  # 实际体积超限触发重采样
    assert any("tightened frames" in warning for warning in stats["warnings"])
    assert len(stats["frame_times_ps"]) == stats["movie_frames"]
    assert len(stats["frame_indices"]) == stats["movie_frames"]
    header = next(line for line in (tmp_path / "movie.pdb").read_text(encoding="utf-8").splitlines()
                  if "selected" in line)
    assert f"selected {stats['movie_frames']} stride {stats['movie_stride']}" in header


# Issue 6a: 每一帧用各自的晶胞盒判定，NPT 变盒不会被第 0 帧的盒子掩盖。
def test_imaging_uses_each_frames_own_box_for_wraps():
    trajectory = FakeTrajectory(
        [[[1.9, 0.1, 0.1]], [[0.1, 0.1, 0.1]]], times=[0.0, 1.0],
        unitcell_vectors=[[[10, 0, 0], [0, 10, 0], [0, 0, 10]], [[2, 0, 0], [0, 2, 0], [0, 0, 2]]],
    )
    assert movie._needs_imaging(trajectory) is True  # 1.8 nm 跨帧跳变 > 第 1 帧半盒 1 nm


# Issue 6b: 即便 strip_ions=False 保留了钙，其 "CA" 也绝不能当作 Cα 对齐锚点。
def test_alignment_never_uses_retained_ion_ca():
    atoms = [
        movie.AtomTemplate("ATOM", "CA", "", "ALA", "A", "1", "", 1.0, 0.0, "C", 0),
        movie.AtomTemplate("ATOM", "CA", "", "GLY", "A", "2", "", 1.0, 0.0, "C", 0),
        movie.AtomTemplate("HETATM", "CA", "", "CA", "A", "3", "", 1.0, 0.0, "CA", 0),
    ]
    assert movie._alignment_indices(atoms, strip_ions=False) == []
    atoms.append(movie.AtomTemplate("ATOM", "CA", "", "SER", "A", "4", "", 1.0, 0.0, "C", 0))
    assert movie._alignment_indices(atoms, strip_ions=False) == [0, 1, 3]


# Issue 7a: 负坐标同样要按格式化后的列宽校验，9 列的 -1000.000 必须拒绝。
def test_coords_valid_rejects_negative_column_overflow():
    assert movie._coords_valid([[[-999.999, 0.0, 0.0]]]) is True
    assert movie._coords_valid([[[-1000.0, 0.0, 0.0]]]) is False


# Issue 7b: 链号或原子名候选耗尽时优雅跳过（返回 None / written=False），不再静默写歧义 PDB。
_CHAINS = "LZYXWVUTSRQPONMKJIHGFEDCBA0123456789"


def test_assign_chain_and_unique_atom_name_report_exhaustion():
    assert movie._assign_chain(set(_CHAINS)) == ""
    used = set()
    for number in range(1, 10000):
        digits = str(number)
        used.add(movie._format_atom_name(f"{'C'[: max(1, 4 - len(digits))]}{digits}", "C"))
    assert movie._unique_atom_name("C", used, "C") == ""


def test_export_skips_when_ligand_chain_candidates_exhausted(tmp_path: Path):
    lines = [_pdb_line(index + 1, "CA", "ALA", chain, 1) for index, chain in enumerate(_CHAINS)]
    lines.append(_pdb_line(len(_CHAINS) + 1, "C1", "LIG", "", 9, record="HETATM"))
    topology = _write_pdb(tmp_path / "topology.pdb", lines)
    trajectory_file = tmp_path / "md.xtc"
    trajectory_file.write_bytes(b"xtc")
    loader, _ = _fake_loader(FakeTrajectory(_xyz(2, len(lines)), times=[0.0, 1.0]))

    stats = movie.export_desolvated_pdb_movie(
        topology, trajectory_file, tmp_path / "movie.pdb",
        config=movie.TrajectoryMovieConfig(max_frames=2, ligand_resname="LIG"),
        trajectory_loader=loader,
    )
    assert stats["written"] is False
    assert any("exhausted" in warning for warning in stats["warnings"])
    assert not (tmp_path / "movie.pdb").exists()


# ---------------------------------------------------------------------------
# PR 2 第二轮复审修复（第 1/3/4/5/6/8 项）
# ---------------------------------------------------------------------------
# 第 1 项：MDTraj 的 XTC ``time`` 是 NumPy float32，必须按实数接受而不是整列丢弃。
def test_strict_frame_times_accepts_numpy_real_scalars():
    np = pytest.importorskip("numpy")
    float32 = np.array([0, 5, 10], dtype=np.float32)
    assert movie._strict_frame_times(float32, [0, 2]) == [0.0, 10.0]
    assert movie._strict_frame_times(np.array([0, 5, 10], dtype=np.int64), [1, 2]) == [5.0, 10.0]
    # NumPy 布尔仍不算实数，整列降级。
    assert movie._strict_frame_times(np.array([True, False]), [0, 1]) == []


def test_export_reads_float32_frame_times(tmp_path: Path):
    np = pytest.importorskip("numpy")
    topology = _complex_topology(tmp_path / "topology.pdb")
    trajectory_file = tmp_path / "md.xtc"
    trajectory_file.write_bytes(b"xtc")
    trajectory = FakeTrajectory(_xyz(3, 6), times=[0.0, 5.0, 10.0])
    trajectory.time = np.array([0, 5, 10], dtype=np.float32)
    loader, _ = _fake_loader(trajectory)

    stats = movie.export_desolvated_pdb_movie(
        topology, trajectory_file, tmp_path / "movie.pdb",
        config=movie.TrajectoryMovieConfig(max_frames=2, ligand_resname="LIG"),
        trajectory_loader=loader,
    )
    assert stats["written"] is True
    assert stats["frame_times_ps"] == [0.0, 10.0]  # 不是 []


# 第 3 项：ITP 的 [ bonds ] 为空也不能绕过 SDF 一致性校验。
def test_conect_empty_itp_bonds_do_not_bypass_sdf_topology_check(tmp_path: Path, monkeypatch):
    sdf = tmp_path / "ligand.sdf"
    sdf.write_text("fake\n", encoding="utf-8")
    itp = tmp_path / "ligand.itp"
    itp.write_text("[ bonds ]\n", encoding="utf-8")  # 成功读取，但没有任何键
    monkeypatch.setitem(sys.modules, "rdkit", _fake_rdkit([(0, 1, 2.0)], 4, ["C", "C", "O", "H"]))
    warnings: list[str] = []

    lines = movie.build_ligand_conect_lines(
        _ligand_templates(), ligand_resname="LIG",
        ligand_template_sdf=sdf, ligand_itp=itp, warnings=warnings,
    )
    assert any("SDF bond topology differs" in warning for warning in warnings)
    assert lines == []  # 回退到 ITP 的空键单键路径，绝不输出 SDF 双键


# 第 4 项：同一残基键内，后续 altLoc 独有的原子也要改写成首个锁定的 resname。
def test_parse_rewrites_unique_altloc_atoms_to_locked_resname(tmp_path: Path):
    pdb = _write_pdb(
        tmp_path / "topology.pdb",
        [
            _pdb_line(1, "CA", "SER", "A", 10, altloc="A"),
            _pdb_line(2, "CA", "CYS", "A", 10, altloc="B"),  # 第二个 CA 被剔除
            _pdb_line(3, "SG", "CYS", "A", 10, altloc="B", element="S"),  # 独有原子保留
        ],
    )
    templates = movie.parse_pdb_atom_templates(pdb)
    assert [(atom.atom_name, atom.resname, atom.altloc) for atom in templates] == [
        ("CA", "SER", "A"),
        ("SG", "SER", "B"),  # 与 MDTraj 一致：沿用首个 resname
    ]


# 第 5 项：预算按“真实 CONECT + 头尾固定开销”重估；3 帧超限、2 帧可容。
def _sixty_six_atom_ligand_topology(path: Path, ligands: int) -> Path:
    lines = [_pdb_line(index + 1, "CA", "ALA", "A", index + 1) for index in range(3)]
    lines += [_pdb_line(4 + index, f"C{index + 1}", "LIG", "L", 9, record="HETATM") for index in range(ligands)]
    return _write_pdb(path, lines)


def _over_budget_three_frame_export(tmp_path: Path, monkeypatch, *, force_keep_all: bool = False):
    ligands = 63
    atoms = 3 + ligands
    topology = _sixty_six_atom_ligand_topology(tmp_path / "topology.pdb", ligands)
    itp = tmp_path / "ligand.itp"
    itp.write_text(
        "[ bonds ]\n" + "".join(f"{index} {index + 1} 1\n" for index in range(1, ligands)),
        encoding="utf-8",
    )
    trajectory_file = tmp_path / "md.xtc"
    trajectory_file.write_bytes(b"xtc")
    loader, _ = _fake_loader(FakeTrajectory(_xyz(3, atoms), times=[0.0, 1.0, 2.0]))
    if force_keep_all:  # 模拟比例估算仍保留 3 帧，验证显式首尾两帧兜底
        monkeypatch.setattr(movie, "_uniform_subsample", lambda values, limit: list(values))
    return movie.export_desolvated_pdb_movie(
        topology, trajectory_file, tmp_path / "movie.pdb",
        config=movie.TrajectoryMovieConfig(max_frames=3, ligand_resname="LIG", max_bytes=17040),
        ligand_itp=itp, trajectory_loader=loader,
    )


def test_measured_resample_fits_three_frame_movie_into_17040_bytes(tmp_path: Path):
    stats = _over_budget_three_frame_export(tmp_path, None)
    assert stats["written"] is True
    assert stats["movie_frames"] == 2
    assert stats["frame_indices"] == [0, 2]
    assert stats["frame_times_ps"] == [0.0, 2.0]
    assert stats["size_bytes"] <= 17040
    assert any("tightened frames" in warning for warning in stats["warnings"])
    header = next(line for line in (tmp_path / "movie.pdb").read_text(encoding="utf-8").splitlines()
                  if "selected" in line)
    assert "selected 2 stride 2" in header


def test_second_resample_retries_first_and_last_two_frames(tmp_path: Path, monkeypatch):
    stats = _over_budget_three_frame_export(tmp_path, monkeypatch, force_keep_all=True)
    assert stats["written"] is True
    assert stats["movie_frames"] == 2
    assert stats["frame_indices"] == [0, 2]
    assert any("first and last" in warning for warning in stats["warnings"])
    assert stats["size_bytes"] <= 17040


# 第 6 项：成像前把可信配体键注入 GRO 拓扑，避免配体跨盒被拆散。
class _FakeTopology:
    def __init__(self, atom_count: int):
        self.atoms = [types.SimpleNamespace(index=index) for index in range(atom_count)]
        self.bonds: list = []
        self.added: list[tuple[int, int]] = []

    def add_bond(self, first, second):
        self.added.append((first.index, second.index))
        self.bonds.append((first.index, second.index))


class _TopologyTrajectory(FakeTrajectory):
    """Shares one topology through slice/atom_slice and snapshots bonds at imaging."""

    def __init__(self, xyz, times, topology, unitcell_vectors=None):
        super().__init__(xyz, times, unitcell_vectors)
        self.topology = topology

    def slice(self, indices, copy: bool = False):
        return _TopologyTrajectory(
            [self.xyz[index] for index in indices],
            [self.time[index] for index in indices],
            self.topology,
            None if self.unitcell_vectors is None
            else [self.unitcell_vectors[0] for _ in indices],
        )

    def atom_slice(self, indices):
        return _TopologyTrajectory(
            [[row[index] for index in indices] for row in self.xyz],
            self.time,
            self.topology,
            self.unitcell_vectors,
        )

    def image_molecules(self, inplace: bool = False):
        self.topology.snapshot = movie._topology_bond_pairs(self.topology)
        self.imaged = True


def _ligand_chain_topology(path: Path) -> Path:
    return _write_pdb(
        path,
        [
            _pdb_line(1, "CA", "ALA", "A", 1),
            _pdb_line(2, "CA", "GLY", "A", 2),
            _pdb_line(3, "CA", "SER", "A", 3),
            _pdb_line(4, "C1", "LIG", "L", 9, record="HETATM"),
            _pdb_line(5, "C2", "LIG", "L", 9, record="HETATM"),
            _pdb_line(6, "C3", "LIG", "L", 9, record="HETATM"),
        ],
    )


def test_imaging_injects_ligand_bonds_into_topology_before_image_molecules(tmp_path: Path):
    topology_path = _ligand_chain_topology(tmp_path / "topology.pdb")
    itp = tmp_path / "ligand.itp"
    itp.write_text("[ bonds ]\n1 3 1\n", encoding="utf-8")  # 非相邻键：仅 ITP 提供
    trajectory_file = tmp_path / "md.xtc"
    trajectory_file.write_bytes(b"xtc")
    topology = _FakeTopology(6)
    far_xyz = [[[10.0, 1.0, 1.0] for _ in range(6)]]
    loader, _ = _fake_loader(
        _TopologyTrajectory(far_xyz, [0.0], topology, [[[3, 0, 0], [0, 3, 0], [0, 0, 3]]])
    )

    stats = movie.export_desolvated_pdb_movie(
        topology_path, trajectory_file, tmp_path / "movie.pdb",
        config=movie.TrajectoryMovieConfig(max_frames=1, ligand_resname="LIG", superpose=False),
        ligand_itp=itp, trajectory_loader=loader,
    )
    assert stats["written"] is True
    assert topology.added == [(3, 5)]  # 蛋白 0-2，配体局部 3-5，ITP 1-3 => (3,5)
    assert (3, 5) in topology.snapshot  # 注入发生在 image_molecules 之前


def test_imaging_does_not_duplicate_existing_topology_bonds(tmp_path: Path):
    topology_path = _ligand_chain_topology(tmp_path / "topology.pdb")
    itp = tmp_path / "ligand.itp"
    itp.write_text("[ bonds ]\n1 3 1\n", encoding="utf-8")
    trajectory_file = tmp_path / "md.xtc"
    trajectory_file.write_bytes(b"xtc")
    topology = _FakeTopology(6)
    topology.bonds = [(3, 5)]
    loader, _ = _fake_loader(
        _TopologyTrajectory([[[10.0, 1.0, 1.0] for _ in range(6)]], [0.0], topology,
                            [[[3, 0, 0], [0, 3, 0], [0, 0, 3]]])
    )

    stats = movie.export_desolvated_pdb_movie(
        topology_path, trajectory_file, tmp_path / "movie.pdb",
        config=movie.TrajectoryMovieConfig(max_frames=1, ligand_resname="LIG", superpose=False),
        ligand_itp=itp, trajectory_loader=loader,
    )
    assert stats["written"] is True
    assert topology.added == []


def test_gro_topology_allows_halogen_and_protein_aliases_but_rejects_swapped_same_element(tmp_path: Path):
    """MDTraj GRO loader has no element column and parses ``CL1`` as ``C``, while
    normalizing GROMACS N/C-term aliases (``H1->H``, ``OC1->O``, ``OC2->OXT``, ``ILE CD->CD1``).
    All of those must render cleanly, whereas same-element swapped atoms must fail."""
    pdb = tmp_path / "topology.pdb"
    pdb.write_text(
        "\n".join(
            [
                _pdb_line(1, "H1", "MET", "A", 1, element="H"),
                _pdb_line(2, "N", "MET", "A", 1, element="N"),
                _pdb_line(3, "CA", "MET", "A", 1, element="C"),
                _pdb_line(4, "CD", "ILE", "A", 2, element="C"),
                _pdb_line(5, "OC1", "ALA", "A", 3, element="O"),
                _pdb_line(6, "OC2", "ALA", "A", 3, element="O"),
                _pdb_line(7, "C1", "LIG", "L", 9, record="HETATM", element="C"),
                _pdb_line(8, "C2", "LIG", "L", 9, record="HETATM", element="C"),
                _pdb_line(9, "CL1", "LIG", "L", 9, record="HETATM", element="Cl"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    gro = tmp_path / "md.gro"
    gro.write_text("test gro\n9\n" + "   5.00000   5.00000   5.00000\n", encoding="utf-8")
    xtc = tmp_path / "md.xtc"
    xtc.write_bytes(b"xtc")

    class _NamedAtom:
        def __init__(self, name: str, symbol: str, resname: str = ""):
            self.name = name
            self.element = types.SimpleNamespace(symbol=symbol)
            self.residue = types.SimpleNamespace(name=resname)

    gro_atoms = [
        _NamedAtom("H", "H", "MET"),
        _NamedAtom("N", "N", "MET"),
        _NamedAtom("CA", "C", "MET"),
        _NamedAtom("CD1", "C", "ILE"),
        _NamedAtom("O", "O", "ALA"),
        _NamedAtom("OXT", "O", "ALA"),
        _NamedAtom("C1", "C", "LIG"),
        _NamedAtom("C2", "C", "LIG"),
        _NamedAtom("CL1", "C", "LIG"),
    ]
    gro_traj = _TopologyTrajectory(
        [[[0.1 * i, 0.0, 0.0] for i in range(9)], [[0.1 * i, 0.1, 0.0] for i in range(9)]],
        [0.0, 10.0],
        types.SimpleNamespace(atoms=gro_atoms),
    )
    movie_out = tmp_path / "movie.pdb"
    stats = movie.export_desolvated_pdb_movie(
        pdb, xtc, movie_out,
        config=movie.TrajectoryMovieConfig(ligand_resname="LIG"),
        topology_gro=gro,
        trajectory_loader=lambda top, traj: gro_traj,
    )
    assert stats["written"] is True
    assert stats["movie_frames"] == 2
    assert movie_out.read_text(encoding="utf-8").count("ENDMDL") == 2

    swapped_atoms = [
        _NamedAtom("H", "H", "MET"),
        _NamedAtom("N", "N", "MET"),
        _NamedAtom("CA", "C", "MET"),
        _NamedAtom("CD1", "C", "ILE"),
        _NamedAtom("O", "O", "ALA"),
        _NamedAtom("OXT", "O", "ALA"),
        _NamedAtom("C2", "C", "LIG"),  # 同元素 C1/C2 错位
        _NamedAtom("C1", "C", "LIG"),
        _NamedAtom("CL1", "C", "LIG"),
    ]
    swapped_traj = _TopologyTrajectory(gro_traj.xyz, gro_traj.time, types.SimpleNamespace(atoms=swapped_atoms))
    with pytest.raises(ValueError, match="GRO trajectory atom order"):
        movie.export_desolvated_pdb_movie(
            pdb, xtc, tmp_path / "bad.pdb",
            config=movie.TrajectoryMovieConfig(ligand_resname="LIG"),
            topology_gro=gro,
            trajectory_loader=lambda top, traj: swapped_traj,
        )


class _NamedGroAtom:
    def __init__(
        self, name: str, symbol: str, resname: str = "",
        resindex: int | None = None, resseq: int | None = None,
        serial: int | None = None,
    ):
        self.name = name
        self.element = types.SimpleNamespace(symbol=symbol)
        self.residue = types.SimpleNamespace(name=resname, index=resindex, resSeq=resseq)
        self.serial = serial


def test_gro_topology_accepts_digit_prefixed_terminal_hydrogen(tmp_path: Path):
    """MDTraj renames GRO ``1H`` to ``H`` and derives element ``VS`` from the digit
    prefix; the canonical name match is authoritative and must not be re-rejected by
    the element comparison."""
    pdb = tmp_path / "topology.pdb"
    pdb.write_text(
        "\n".join(
            [
                _pdb_line(1, "1H", "MET", "A", 1, element="H"),
                _pdb_line(2, "N", "MET", "A", 1, element="N"),
                _pdb_line(3, "CA", "MET", "A", 1, element="C"),
                _pdb_line(4, "C", "MET", "A", 1, element="C"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    gro = tmp_path / "md.gro"
    gro.write_text("test gro\n4\n" + "   5.00000   5.00000   5.00000\n", encoding="utf-8")
    xtc = tmp_path / "md.xtc"
    xtc.write_bytes(b"xtc")

    gro_atoms = [
        _NamedGroAtom("H", "VS", "MET"),
        _NamedGroAtom("N", "N", "MET"),
        _NamedGroAtom("CA", "C", "MET"),
        _NamedGroAtom("C", "C", "MET"),
    ]
    gro_traj = _TopologyTrajectory(
        [[[0.1 * i, 0.0, 0.0] for i in range(4)], [[0.1 * i, 0.1, 0.0] for i in range(4)]],
        [0.0, 10.0],
        types.SimpleNamespace(atoms=gro_atoms),
    )
    stats = movie.export_desolvated_pdb_movie(
        pdb, xtc, tmp_path / "movie.pdb",
        topology_gro=gro,
        trajectory_loader=lambda top, traj: gro_traj,
    )
    assert stats["written"] is True
    assert stats["movie_frames"] == 2


def test_gro_topology_rejects_ligand_oxygen_alias_swap(tmp_path: Path):
    """Protein terminal aliases (O1->O) must not apply to ligands: a swapped
    ``LIG O``/``LIG O1`` pair shares an element and would otherwise pass the name
    check and bind trajectory coordinates to the wrong atom names."""
    pdb = tmp_path / "topology.pdb"
    pdb.write_text(
        "\n".join(
            [
                _pdb_line(1, "N", "ALA", "A", 1, element="N"),
                _pdb_line(2, "CA", "ALA", "A", 1, element="C"),
                _pdb_line(3, "C", "ALA", "A", 1, element="C"),
                _pdb_line(4, "O", "LIG", "L", 9, record="HETATM", element="O"),
                _pdb_line(5, "O1", "LIG", "L", 9, record="HETATM", element="O"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    gro = tmp_path / "md.gro"
    gro.write_text("test gro\n5\n" + "   5.00000   5.00000   5.00000\n", encoding="utf-8")
    xtc = tmp_path / "md.xtc"
    xtc.write_bytes(b"xtc")

    swapped_atoms = [
        _NamedGroAtom("N", "N", "ALA"),
        _NamedGroAtom("CA", "C", "ALA"),
        _NamedGroAtom("C", "C", "ALA"),
        _NamedGroAtom("O1", "O", "LIG"),  # 与 PDB 的 O/O1 顺序相反
        _NamedGroAtom("O", "O", "LIG"),
    ]
    swapped_traj = _TopologyTrajectory(
        [[[0.1 * i, 0.0, 0.0] for i in range(5)], [[0.1 * i, 0.1, 0.0] for i in range(5)]],
        [0.0, 10.0],
        types.SimpleNamespace(atoms=swapped_atoms),
    )
    with pytest.raises(ValueError, match="GRO trajectory atom order"):
        movie.export_desolvated_pdb_movie(
            pdb, xtc, tmp_path / "bad.pdb",
            config=movie.TrajectoryMovieConfig(ligand_resname="LIG"),
            topology_gro=gro,
            trajectory_loader=lambda top, traj: swapped_traj,
        )


def test_gro_topology_rejects_cross_residue_same_name_swap(tmp_path: Path):
    """Two residues can expose the same atom name (``CA``): an atom-name-only check
    accepts a swapped ALA/GLY order and writes coordinates onto the wrong residue,
    so the residue name and ordinal must match as well."""
    pdb = tmp_path / "topology.pdb"
    pdb.write_text(
        "\n".join(
            [
                _pdb_line(1, "CA", "ALA", "A", 1, element="C"),
                _pdb_line(2, "CA", "GLY", "A", 2, element="C"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    gro = tmp_path / "md.gro"
    gro.write_text("test gro\n2\n" + "   5.00000   5.00000   5.00000\n", encoding="utf-8")
    xtc = tmp_path / "md.xtc"
    xtc.write_bytes(b"xtc")

    swapped_atoms = [
        _NamedGroAtom("CA", "C", "GLY", resindex=1),
        _NamedGroAtom("CA", "C", "ALA", resindex=0),
    ]
    swapped_traj = _TopologyTrajectory(
        [[[0.1 * i, 0.0, 0.0] for i in range(2)], [[0.1 * i, 0.1, 0.0] for i in range(2)]],
        [0.0, 10.0],
        types.SimpleNamespace(atoms=swapped_atoms),
    )
    with pytest.raises(ValueError, match="GRO trajectory residue order"):
        movie.export_desolvated_pdb_movie(
            pdb, xtc, tmp_path / "bad.pdb",
            topology_gro=gro,
            trajectory_loader=lambda top, traj: swapped_traj,
        )


def test_gro_topology_rejects_same_resname_residue_swap(tmp_path: Path):
    """Same residue name and same atom name in both residues: only the residue
    ordinal distinguishes them, and a swap must still be refused."""
    pdb = tmp_path / "topology.pdb"
    pdb.write_text(
        "\n".join(
            [
                _pdb_line(1, "CA", "ALA", "A", 1, element="C"),
                _pdb_line(2, "CA", "ALA", "A", 2, element="C"),
                _pdb_line(3, "CB", "ALA", "A", 2, element="C"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    gro = tmp_path / "md.gro"
    gro.write_text("test gro\n3\n" + "   5.00000   5.00000   5.00000\n", encoding="utf-8")
    xtc = tmp_path / "md.xtc"
    xtc.write_bytes(b"xtc")

    swapped_atoms = [
        _NamedGroAtom("CA", "C", "ALA", resindex=1),
        _NamedGroAtom("CA", "C", "ALA", resindex=0),
        _NamedGroAtom("CB", "C", "ALA", resindex=1),
    ]
    swapped_traj = _TopologyTrajectory(
        [[[0.1 * i, 0.0, 0.0] for i in range(3)], [[0.1 * i, 0.1, 0.0] for i in range(3)]],
        [0.0, 10.0],
        types.SimpleNamespace(atoms=swapped_atoms),
    )
    with pytest.raises(ValueError, match="GRO trajectory residue order"):
        movie.export_desolvated_pdb_movie(
            pdb, xtc, tmp_path / "bad.pdb",
            topology_gro=gro,
            trajectory_loader=lambda top, traj: swapped_traj,
        )


def _two_frame_trajectory(atoms: list[_NamedGroAtom]):
    return _TopologyTrajectory(
        [[[0.1 * i, 0.0, 0.0] for i in range(len(atoms))],
         [[0.1 * i, 0.1, 0.0] for i in range(len(atoms))]],
        [0.0, 10.0],
        types.SimpleNamespace(atoms=atoms),
    )


def test_gro_topology_accepts_mdtraj_residue_and_atom_aliases(tmp_path: Path):
    """MDTraj rewrites HID/CYX residue names and their atom aliases while reading
    GRO, while topology.pdb keeps the GROMACS names. Both sides must be normalized
    with the same pdbNames.xml tables instead of being falsely rejected."""
    pdb = tmp_path / "topology.pdb"
    pdb.write_text(
        "\n".join(
            [
                _pdb_line(1, "HD", "HID", "A", 1, element="H"),
                _pdb_line(2, "SG1", "CYX", "A", 2, element="S"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    gro = tmp_path / "md.gro"
    gro.write_text("test gro\n2\n" + "   5.00000   5.00000   5.00000\n", encoding="utf-8")
    xtc = tmp_path / "md.xtc"
    xtc.write_bytes(b"xtc")

    gro_atoms = [
        _NamedGroAtom("HD2", "H", "HIS", resindex=0, resseq=1),
        _NamedGroAtom("SG", "S", "CYS", resindex=1, resseq=2),
    ]
    trajectory = _two_frame_trajectory(gro_atoms)
    stats = movie.export_desolvated_pdb_movie(
        pdb, xtc, tmp_path / "movie.pdb",
        topology_gro=gro,
        trajectory_loader=lambda top, traj: trajectory,
    )
    assert stats["written"] is True


def test_gro_topology_accepts_chain_boundary_merged_by_gro(tmp_path: Path):
    """GRO records carry no chain/insertion code: two adjacent residues with the
    same raw name and number are one MDTraj residue. The template ordinal must
    follow the GRO reader's own rule instead of splitting on the PDB chain."""
    pdb = tmp_path / "topology.pdb"
    pdb.write_text(
        "\n".join(
            [
                _pdb_line(1, "CA", "ALA", "A", 1, element="C"),
                _pdb_line(2, "CA", "ALA", "B", 1, element="C"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    gro = tmp_path / "md.gro"
    gro.write_text("test gro\n2\n" + "   5.00000   5.00000   5.00000\n", encoding="utf-8")
    xtc = tmp_path / "md.xtc"
    xtc.write_bytes(b"xtc")

    gro_atoms = [
        _NamedGroAtom("CA", "C", "ALA", resindex=0, resseq=1),
        _NamedGroAtom("CA", "C", "ALA", resindex=0, resseq=1),
    ]
    trajectory = _two_frame_trajectory(gro_atoms)
    stats = movie.export_desolvated_pdb_movie(
        pdb, xtc, tmp_path / "movie.pdb",
        topology_gro=gro,
        trajectory_loader=lambda top, traj: trajectory,
    )
    assert stats["written"] is True


def test_gro_topology_rejects_renumbering_without_atom_serial_proof(tmp_path: Path):
    """Residue numbers alone cannot prove atom order after a renumbering: a clean
    1..N rewrite would also accept two same-resname residues swapped in place.
    Without matching atom serials the movie must be skipped, not rendered."""
    pdb = tmp_path / "topology.pdb"
    pdb.write_text(
        "\n".join(
            [
                _pdb_line(1, "CA", "ALA", "A", 42, element="C"),
                _pdb_line(2, "CB", "ALA", "A", 43, element="C"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    gro = tmp_path / "md.gro"
    gro.write_text("test gro\n2\n" + "   5.00000   5.00000   5.00000\n", encoding="utf-8")
    xtc = tmp_path / "md.xtc"
    xtc.write_bytes(b"xtc")

    gro_atoms = [
        _NamedGroAtom("CA", "C", "ALA", resindex=0, resseq=1),
        _NamedGroAtom("CB", "C", "ALA", resindex=1, resseq=2),
    ]
    trajectory = _two_frame_trajectory(gro_atoms)
    with pytest.raises(ValueError, match="without atom-serial proof"):
        movie.export_desolvated_pdb_movie(
            pdb, xtc, tmp_path / "bad.pdb",
            topology_gro=gro,
            trajectory_loader=lambda top, traj: trajectory,
        )


def test_gro_topology_rejects_numbered_same_resname_residue_swap(tmp_path: Path):
    """MDTraj re-numbers residues by file order, so a swapped ALA/ALA pair keeps
    ordinals 0/1 and passes the positional check; only the GRO residue numbers
    still prove the swap."""
    pdb = tmp_path / "topology.pdb"
    pdb.write_text(
        "\n".join(
            [
                _pdb_line(1, "CA", "ALA", "A", 1, element="C"),
                _pdb_line(2, "CA", "ALA", "A", 2, element="C"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    gro = tmp_path / "md.gro"
    gro.write_text("test gro\n2\n" + "   5.00000   5.00000   5.00000\n", encoding="utf-8")
    xtc = tmp_path / "md.xtc"
    xtc.write_bytes(b"xtc")

    swapped_atoms = [
        _NamedGroAtom("CA", "C", "ALA", resindex=0, resseq=2),
        _NamedGroAtom("CA", "C", "ALA", resindex=1, resseq=1),
    ]
    swapped_traj = _two_frame_trajectory(swapped_atoms)
    with pytest.raises(ValueError, match="residue numbering"):
        movie.export_desolvated_pdb_movie(
            pdb, xtc, tmp_path / "bad.pdb",
            topology_gro=gro,
            trajectory_loader=lambda top, traj: swapped_traj,
        )


def test_gro_topology_accepts_per_residue_terminal_name_overrides(tmp_path: Path):
    """pdbNames.xml overrides the generic terminal mapping per residue: ACE
    ``HH31`` becomes ``H1`` and PRO ``HT1``/``HT2`` become ``H2``/``H3``. The
    template must be normalised once against the raw name; normalising the
    already-normalised trajectory name again would reject these atoms."""
    pdb = tmp_path / "topology.pdb"
    pdb.write_text(
        "\n".join(
            [
                _pdb_line(1, "HH31", "ACE", "A", 1, element="H"),
                _pdb_line(2, "HT1", "PRO", "A", 2, element="H"),
                _pdb_line(3, "HT2", "PRO", "A", 2, element="H"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    gro = tmp_path / "md.gro"
    gro.write_text("test gro\n3\n" + "   5.00000   5.00000   5.00000\n", encoding="utf-8")
    xtc = tmp_path / "md.xtc"
    xtc.write_bytes(b"xtc")

    gro_atoms = [
        _NamedGroAtom("H1", "H", "ACE", resindex=0, resseq=1, serial=1),
        _NamedGroAtom("H2", "H", "PRO", resindex=1, resseq=2, serial=2),
        _NamedGroAtom("H3", "H", "PRO", resindex=1, resseq=2, serial=3),
    ]
    trajectory = _two_frame_trajectory(gro_atoms)
    stats = movie.export_desolvated_pdb_movie(
        pdb, xtc, tmp_path / "movie.pdb",
        topology_gro=gro,
        trajectory_loader=lambda top, traj: trajectory,
    )
    assert stats["written"] is True


def test_gro_topology_accepts_nucleic_residue_and_atom_aliases(tmp_path: Path):
    """MDTraj renames DAD -> DA and THY -> DT and applies the nucleic acid table
    (``O1P`` -> ``OP1``); the template must follow the same mapping."""
    pdb = tmp_path / "topology.pdb"
    pdb.write_text(
        "\n".join(
            [
                _pdb_line(1, "O1P", "DAD", "A", 1, element="O"),
                _pdb_line(2, "C5M", "THY", "A", 2, element="C"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    gro = tmp_path / "md.gro"
    gro.write_text("test gro\n2\n" + "   5.00000   5.00000   5.00000\n", encoding="utf-8")
    xtc = tmp_path / "md.xtc"
    xtc.write_bytes(b"xtc")

    gro_atoms = [
        _NamedGroAtom("OP1", "O", "DA", resindex=0, resseq=1, serial=1),
        _NamedGroAtom("C7", "C", "DT", resindex=1, resseq=2, serial=2),
    ]
    trajectory = _two_frame_trajectory(gro_atoms)
    stats = movie.export_desolvated_pdb_movie(
        pdb, xtc, tmp_path / "movie.pdb",
        topology_gro=gro,
        trajectory_loader=lambda top, traj: trajectory,
    )
    assert stats["written"] is True


def test_gro_topology_accepts_renumbering_proved_by_atom_serials(tmp_path: Path):
    """A rebuilt topology can renumber GRO residues 1..N while topology.pdb keeps
    42/43; matching atom serials prove the order, so the residue-number heuristic
    must not run at all."""
    pdb = tmp_path / "topology.pdb"
    pdb.write_text(
        "\n".join(
            [
                _pdb_line(5, "CA", "ALA", "A", 42, element="C"),
                _pdb_line(9, "CB", "ALA", "A", 43, element="C"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    gro = tmp_path / "md.gro"
    gro.write_text("test gro\n2\n" + "   5.00000   5.00000   5.00000\n", encoding="utf-8")
    xtc = tmp_path / "md.xtc"
    xtc.write_bytes(b"xtc")

    gro_atoms = [
        _NamedGroAtom("CA", "C", "ALA", resindex=0, resseq=1, serial=5),
        _NamedGroAtom("CB", "C", "ALA", resindex=1, resseq=2, serial=9),
    ]
    trajectory = _two_frame_trajectory(gro_atoms)
    stats = movie.export_desolvated_pdb_movie(
        pdb, xtc, tmp_path / "movie.pdb",
        topology_gro=gro,
        trajectory_loader=lambda top, traj: trajectory,
    )
    assert stats["written"] is True


def test_gro_topology_rejects_serial_swap_of_same_resname_residues(tmp_path: Path):
    """Atom serials identify atoms even when a same-resname residue pair is swapped
    in place; the old residue-number multiset check misses that swap."""
    pdb = tmp_path / "topology.pdb"
    pdb.write_text(
        "\n".join(
            [
                _pdb_line(1, "CA", "ALA", "A", 1, element="C"),
                _pdb_line(2, "CB", "ALA", "A", 2, element="C"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    gro = tmp_path / "md.gro"
    gro.write_text("test gro\n2\n" + "   5.00000   5.00000   5.00000\n", encoding="utf-8")
    xtc = tmp_path / "md.xtc"
    xtc.write_bytes(b"xtc")

    swapped_atoms = [
        _NamedGroAtom("CA", "C", "ALA", resindex=0, resseq=1, serial=2),
        _NamedGroAtom("CB", "C", "ALA", resindex=1, resseq=2, serial=1),
    ]
    swapped_traj = _two_frame_trajectory(swapped_atoms)
    with pytest.raises(ValueError, match="atom serials"):
        movie.export_desolvated_pdb_movie(
            pdb, xtc, tmp_path / "bad.pdb",
            topology_gro=gro,
            trajectory_loader=lambda top, traj: swapped_traj,
        )


def test_gro_topology_rejects_partial_serial_swap_of_identical_atom_names(tmp_path: Path):
    """One missing serial must not disable the comparison of the remaining ones:
    swapping two identically named atoms still shows up at the known positions."""
    pdb = tmp_path / "topology.pdb"
    pdb.write_text(
        "\n".join(
            [
                _pdb_line(1, "CA", "ALA", "A", 1, element="C"),
                _pdb_line(2, "CA", "ALA", "A", 2, element="C"),
                _pdb_line(3, "CA", "ALA", "A", 3, element="C"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    gro = tmp_path / "md.gro"
    gro.write_text("test gro\n3\n" + "   5.00000   5.00000   5.00000\n", encoding="utf-8")
    xtc = tmp_path / "md.xtc"
    xtc.write_bytes(b"xtc")

    swapped_atoms = [
        _NamedGroAtom("CA", "C", "ALA", resindex=0, resseq=1, serial=2),
        _NamedGroAtom("CA", "C", "ALA", resindex=1, resseq=2, serial=1),
        _NamedGroAtom("CA", "C", "ALA", resindex=2, resseq=3),
    ]
    swapped_traj = _two_frame_trajectory(swapped_atoms)
    with pytest.raises(ValueError, match="atom serials"):
        movie.export_desolvated_pdb_movie(
            pdb, xtc, tmp_path / "bad.pdb",
            topology_gro=gro,
            trajectory_loader=lambda top, traj: swapped_traj,
        )


def test_gro_topology_accepts_non_contiguous_renumbering_with_serial_proof(tmp_path: Path):
    """After de-solvation the kept residues need not be a clean 1..N run: atom
    serials that match at every kept position prove the order, so 42/43 -> 1/3
    is legal even though it is not a contiguous renumbering."""
    pdb = tmp_path / "topology.pdb"
    pdb.write_text(
        "\n".join(
            [
                _pdb_line(5, "CA", "ALA", "A", 42, element="C"),
                _pdb_line(9, "CB", "ALA", "A", 43, element="C"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    gro = tmp_path / "md.gro"
    gro.write_text("test gro\n2\n" + "   5.00000   5.00000   5.00000\n", encoding="utf-8")
    xtc = tmp_path / "md.xtc"
    xtc.write_bytes(b"xtc")

    gro_atoms = [
        _NamedGroAtom("CA", "C", "ALA", resindex=0, resseq=1, serial=5),
        _NamedGroAtom("CB", "C", "ALA", resindex=1, resseq=3, serial=9),
    ]
    trajectory = _two_frame_trajectory(gro_atoms)
    stats = movie.export_desolvated_pdb_movie(
        pdb, xtc, tmp_path / "movie.pdb",
        topology_gro=gro,
        trajectory_loader=lambda top, traj: trajectory,
    )
    assert stats["written"] is True


def test_gro_topology_rejects_renumbering_when_serials_repeat(tmp_path: Path):
    """GROMACS writers store serial % 100000, so repeated serials cannot identify
    atoms. They must not be treated as proof for a changed residue numbering."""
    pdb = tmp_path / "topology.pdb"
    pdb.write_text(
        "\n".join(
            [
                _pdb_line(1, "CA", "ALA", "A", 42, element="C"),
                _pdb_line(1, "CB", "ALA", "A", 43, element="C"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    gro = tmp_path / "md.gro"
    gro.write_text("test gro\n2\n" + "   5.00000   5.00000   5.00000\n", encoding="utf-8")
    xtc = tmp_path / "md.xtc"
    xtc.write_bytes(b"xtc")

    gro_atoms = [
        _NamedGroAtom("CA", "C", "ALA", resindex=0, resseq=1, serial=2),
        _NamedGroAtom("CB", "C", "ALA", resindex=1, resseq=2, serial=2),
    ]
    trajectory = _two_frame_trajectory(gro_atoms)
    with pytest.raises(ValueError, match="without atom-serial proof"):
        movie.export_desolvated_pdb_movie(
            pdb, xtc, tmp_path / "bad.pdb",
            topology_gro=gro,
            trajectory_loader=lambda top, traj: trajectory,
        )


def test_gro_topology_counts_serials_before_desolvation(tmp_path: Path):
    """A kept atom's serial must be unique in the whole file, solvent included:
    when the same serial also repeats on a filtered water atom, it proves nothing
    and a 42/43 -> 1/3 renumbering must not be accepted."""
    pdb = tmp_path / "topology.pdb"
    pdb.write_text(
        "\n".join(
            [
                _pdb_line(1, "CA", "ALA", "A", 42, element="C"),
                _pdb_line(2, "CB", "ALA", "A", 43, element="C"),
                _pdb_line(1, "OW", "SOL", "A", 44, record="HETATM", element="O"),
                _pdb_line(2, "OW", "SOL", "A", 45, record="HETATM", element="O"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    gro = tmp_path / "md.gro"
    gro.write_text("test gro\n4\n" + "   5.00000   5.00000   5.00000\n", encoding="utf-8")
    xtc = tmp_path / "md.xtc"
    xtc.write_bytes(b"xtc")

    gro_atoms = [
        _NamedGroAtom("CA", "C", "ALA", resindex=0, resseq=1, serial=1),
        _NamedGroAtom("CB", "C", "ALA", resindex=1, resseq=3, serial=2),
        _NamedGroAtom("OW", "O", "SOL", resindex=2, resseq=44, serial=1),
        _NamedGroAtom("OW", "O", "SOL", resindex=3, resseq=45, serial=2),
    ]
    trajectory = _two_frame_trajectory(gro_atoms)
    with pytest.raises(ValueError, match="without atom-serial proof"):
        movie.export_desolvated_pdb_movie(
            pdb, xtc, tmp_path / "bad.pdb",
            topology_gro=gro,
            trajectory_loader=lambda top, traj: trajectory,
        )


def test_gro_topology_rejects_numbering_change_behind_hybrid36_residue(tmp_path: Path):
    """Hybrid-36 ``A000`` encodes 10000: it must decode and expose the mismatch
    against GRO 10001 instead of being skipped as unparsable while the second
    residue (43 == 43) matches."""
    ca_line = _pdb_line(0, "CA", "ALA", "A", 1, element="C")
    hybrid_line = ca_line[:22] + "A000" + ca_line[26:]
    pdb = tmp_path / "topology.pdb"
    pdb.write_text(
        "\n".join(
            [
                hybrid_line,
                _pdb_line(2, "CA", "ALA", "A", 43, element="C"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    gro = tmp_path / "md.gro"
    gro.write_text("test gro\n2\n" + "   5.00000   5.00000   5.00000\n", encoding="utf-8")
    xtc = tmp_path / "md.xtc"
    xtc.write_bytes(b"xtc")

    gro_atoms = [
        _NamedGroAtom("CA", "C", "ALA", resindex=0, resseq=10001),
        _NamedGroAtom("CA", "C", "ALA", resindex=1, resseq=43, serial=2),
    ]
    trajectory = _two_frame_trajectory(gro_atoms)
    with pytest.raises(ValueError, match="without atom-serial proof"):
        movie.export_desolvated_pdb_movie(
            pdb, xtc, tmp_path / "bad.pdb",
            topology_gro=gro,
            trajectory_loader=lambda top, traj: trajectory,
        )


def test_gro_topology_accepts_pdb_residue_fold_after_atom_serial_wrap(tmp_path: Path):
    """GROMACS folds atom serials modulo 100000 and PDB resSeq modulo 10000. In a
    100,004-atom system the solute serials 1/2 repeat on water, so residue
    identity rests on the numbers: PDB ``0`` (folded 10000) must match GRO
    ``10000`` instead of being rejected as a renumbering."""
    total_atoms = 100_004

    def folded_serial(position: int) -> int:
        return (position + 1) % 100_000

    pdb_lines = [
        _pdb_line(1, "CA", "ALA", "A", 9999, element="C"),
        _pdb_line(2, "C1", "LIG", "L", 0, record="HETATM", element="C"),
    ]
    for position in range(2, total_atoms):
        residue_number = 10000 + (position - 2) // 3
        pdb_lines.append(
            _pdb_line(
                folded_serial(position), "OW", "SOL", "A",
                residue_number % 10_000, record="HETATM", element="O",
            )
        )
    pdb = tmp_path / "topology.pdb"
    pdb.write_text("\n".join(pdb_lines) + "\n", encoding="utf-8")

    gro_atoms = [
        _NamedGroAtom("CA", "C", "ALA", resindex=0, resseq=9999, serial=1),
        _NamedGroAtom("C1", "C", "LIG", resindex=1, resseq=10000, serial=2),
    ]
    for position in range(2, total_atoms):
        residue_index = (position - 2) // 3
        gro_atoms.append(
            _NamedGroAtom(
                "OW", "O", "SOL",
                resindex=2 + residue_index,
                resseq=10000 + residue_index,
                serial=folded_serial(position),
            )
        )
    coordinates = [[0.1 * (index % 1000), 0.0, 0.0] for index in range(total_atoms)]
    trajectory = _TopologyTrajectory(
        [coordinates, coordinates], [0.0, 10.0], types.SimpleNamespace(atoms=gro_atoms)
    )
    gro = tmp_path / "md.gro"
    gro.write_text(f"test gro\n{total_atoms}\n   5.00000   5.00000   5.00000\n", encoding="utf-8")
    xtc = tmp_path / "md.xtc"
    xtc.write_bytes(b"xtc")

    stats = movie.export_desolvated_pdb_movie(
        pdb, xtc, tmp_path / "movie.pdb",
        config=movie.TrajectoryMovieConfig(ligand_resname="LIG"),
        topology_gro=gro,
        trajectory_loader=lambda top, traj: trajectory,
    )
    assert stats["written"] is True


def _folded_residue_fixture(tmp_path: Path, gro_atoms: list[_NamedGroAtom]):
    """PDB ALA 1 / GLY 2 / ALA 1 without serials; GRO carries the shuffled or
    original full numbers for the same three residues."""
    pdb = tmp_path / "topology.pdb"
    pdb.write_text(
        "\n".join(
            [
                _pdb_line(0, "CA", "ALA", "A", 1, element="C"),
                _pdb_line(0, "CA", "GLY", "A", 2, element="C"),
                _pdb_line(0, "CA", "ALA", "A", 1, element="C"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    gro = tmp_path / "md.gro"
    gro.write_text("test gro\n3\n" + "   5.00000   5.00000   5.00000\n", encoding="utf-8")
    xtc = tmp_path / "md.xtc"
    xtc.write_bytes(b"xtc")
    return pdb, gro, xtc, _two_frame_trajectory(gro_atoms)


def test_gro_topology_rejects_swapped_residues_that_fold_to_the_same_field(tmp_path: Path):
    """Swapping residues numbered 1 and 10001 keeps every folded pair congruent
    (1 vs 10001, 2 vs 2, 1 vs 1) and no serial is trustworthy, so only the
    order of GRO numbers exposes the swap: 10001 before 1 is a decrease."""
    gro_atoms = [
        _NamedGroAtom("CA", "C", "ALA", resindex=0, resseq=10001),
        _NamedGroAtom("CA", "C", "GLY", resindex=1, resseq=2),
        _NamedGroAtom("CA", "C", "ALA", resindex=2, resseq=1),
    ]
    pdb, gro, xtc, trajectory = _folded_residue_fixture(tmp_path, gro_atoms)
    with pytest.raises(ValueError, match="without atom-serial proof"):
        movie.export_desolvated_pdb_movie(
            pdb, xtc, tmp_path / "bad.pdb",
            topology_gro=gro,
            trajectory_loader=lambda top, traj: trajectory,
        )


def test_gro_topology_accepts_folded_residues_that_keep_their_order(tmp_path: Path):
    """The same residues in their original order read 1, 2, 10001; every pair is
    congruent and the GRO numbers increase, so the fold is genuine."""
    gro_atoms = [
        _NamedGroAtom("CA", "C", "ALA", resindex=0, resseq=1),
        _NamedGroAtom("CA", "C", "GLY", resindex=1, resseq=2),
        _NamedGroAtom("CA", "C", "ALA", resindex=2, resseq=10001),
    ]
    pdb, gro, xtc, trajectory = _folded_residue_fixture(tmp_path, gro_atoms)
    stats = movie.export_desolvated_pdb_movie(
        pdb, xtc, tmp_path / "movie.pdb",
        topology_gro=gro,
        trajectory_loader=lambda top, traj: trajectory,
    )
    assert stats["written"] is True


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("A000", 10000),
        ("ZZZZ", 1223055),
        ("9999", 9999),
        ("-999", -999),
        ("9ZZZ", None),
        ("a000", None),
        ("A00a", None),
        ("", None),
    ],
)
def test_gro_residue_number_only_decodes_valid_hybrid36(field: str, expected: int | None):
    """The upper-case block always starts with a letter; a digit-led field such
    as 9ZZZ is not hybrid-36 and must stay unparsable."""
    assert movie._residue_number(field) == expected


def test_gro_topology_ignores_invalid_hybrid36_residue_fields(tmp_path: Path):
    """``9ZZZ`` is not hybrid-36. It must not decode to 9999 and turn a valid
    GRO 42 into a numbering mismatch when the other residue (43 == 43) matches."""
    ca_line = _pdb_line(0, "CA", "ALA", "A", 1, element="C")
    invalid_line = ca_line[:22] + "9ZZZ" + ca_line[26:]
    pdb = tmp_path / "topology.pdb"
    pdb.write_text(
        "\n".join([invalid_line, _pdb_line(2, "CA", "ALA", "A", 43, element="C")]) + "\n",
        encoding="utf-8",
    )
    gro = tmp_path / "md.gro"
    gro.write_text("test gro\n2\n" + "   5.00000   5.00000   5.00000\n", encoding="utf-8")
    xtc = tmp_path / "md.xtc"
    xtc.write_bytes(b"xtc")

    gro_atoms = [
        _NamedGroAtom("CA", "C", "ALA", resindex=0, resseq=42),
        _NamedGroAtom("CA", "C", "ALA", resindex=1, resseq=43, serial=2),
    ]
    trajectory = _two_frame_trajectory(gro_atoms)
    stats = movie.export_desolvated_pdb_movie(
        pdb, xtc, tmp_path / "movie.pdb",
        topology_gro=gro,
        trajectory_loader=lambda top, traj: trajectory,
    )
    assert stats["written"] is True


def test_gro_topology_accepts_case_preserved_atom_names(tmp_path: Path):
    """MDTraj looks atom names up case-sensitively against the upper-case XML, so
    a raw ``h1`` stays ``h1``. Upper-casing only the template would map it to
    ``H`` and falsely reject a trajectory that also carries ``h1``."""
    pdb = tmp_path / "topology.pdb"
    pdb.write_text(
        _pdb_line(1, "h1", "ALA", "A", 1, element="H") + "\n",
        encoding="utf-8",
    )
    gro = tmp_path / "md.gro"
    gro.write_text("test gro\n1\n" + "   5.00000   5.00000   5.00000\n", encoding="utf-8")
    xtc = tmp_path / "md.xtc"
    xtc.write_bytes(b"xtc")

    gro_atoms = [_NamedGroAtom("h1", "H", "ALA", resindex=0, resseq=1)]
    trajectory = _two_frame_trajectory(gro_atoms)
    stats = movie.export_desolvated_pdb_movie(
        pdb, xtc, tmp_path / "movie.pdb",
        topology_gro=gro,
        trajectory_loader=lambda top, traj: trajectory,
    )
    assert stats["written"] is True


def test_gro_topology_accepts_nme_water_and_unmapped_residue_tables(tmp_path: Path):
    """NME and HOH have their own per-residue overrides; CYM/ASH are absent from
    pdbNames.xml and must stay untouched on both sides."""
    pdb_lines = [
        _pdb_line(1, "HH31", "NME", "A", 1, element="H"),
        _pdb_line(2, "OW", "HOH", "A", 2, element="O"),
        _pdb_line(3, "HW1", "HOH", "A", 2, element="H"),
        _pdb_line(4, "SG", "CYM", "A", 3, element="S"),
        _pdb_line(5, "HD2", "ASH", "A", 4, element="H"),
    ]
    pdb = tmp_path / "topology.pdb"
    pdb.write_text("\n".join(pdb_lines) + "\n", encoding="utf-8")
    gro = tmp_path / "md.gro"
    gro.write_text("test gro\n5\n" + "   5.00000   5.00000   5.00000\n", encoding="utf-8")
    xtc = tmp_path / "md.xtc"
    xtc.write_bytes(b"xtc")

    gro_atoms = [
        _NamedGroAtom("H1", "H", "NME", resindex=0, resseq=1),
        _NamedGroAtom("O", "O", "HOH", resindex=1, resseq=2),
        _NamedGroAtom("H1", "H", "HOH", resindex=1, resseq=2),
        _NamedGroAtom("SG", "S", "CYM", resindex=2, resseq=3),
        _NamedGroAtom("HD2", "H", "ASH", resindex=3, resseq=4),
    ]
    trajectory = _two_frame_trajectory(gro_atoms)
    stats = movie.export_desolvated_pdb_movie(
        pdb, xtc, tmp_path / "movie.pdb",
        topology_gro=gro,
        trajectory_loader=lambda top, traj: trajectory,
    )
    assert stats["written"] is True
