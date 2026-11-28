"""MD 结果页与镜像运行时契约测试（无容器、无真实 MD 引擎依赖）。

1. 锁定 RMSF / Rg 与 `rmsf_csv` 契约（`docs/26` H-3）；
2. 锁定 `gromacs_platform.py` 的蛋白/配体输入解析、GAFF2 / Mode 0 拓扑装配、
   PBC 居中兜底与 `interactions_analysis` 产物接入；
3. 锁定 `Dockerfile` 多阶段离线镜像依赖声明。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
IMAGE_DIR = REPO_ROOT / "deploy" / "model-images" / "k8s" / "gromacs"
STANDARD_YAML = REPO_ROOT / "backend" / "app" / "artifact_standards" / "schemas" / "md_trajectory.v1.yaml"

if str(IMAGE_DIR) not in sys.path:
    sys.path.insert(0, str(IMAGE_DIR))

_spec = importlib.util.spec_from_file_location("gromacs_platform_under_test", IMAGE_DIR / "gromacs_platform.py")
gromacs = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(gromacs)

PDB = """\
ATOM      1  N   MET A   1      11.000  10.000  10.000  1.00 20.00           N
ATOM      2  CA  MET A   1      10.000  10.000  10.000  1.00 20.00           C
ATOM      3  C   MET A   1       9.000  10.000  10.000  1.00 20.00           C
ATOM      4  CA  LYS A 745      10.000  11.000  10.000  1.00 20.00           C
ATOM      5  CA  LYS A 745      10.500  11.500  10.000  1.00 20.00           C
ATOM      6  CA  GLY B   2      12.000  12.000  12.000  1.00 20.00           C
HETATM    7  O   HOH A 900      13.000  13.000  13.000  1.00 20.00           O
"""


def test_standard_declares_rmsf_csv_role():
    text = STANDARD_YAML.read_text(encoding="utf-8")
    assert "role: rmsf_csv" in text
    assert "recommended_name: rmsf.csv" in text


def test_backbone_residues_uses_ca_atoms_in_order(tmp_path: Path):
    pdb = tmp_path / "topology.pdb"
    pdb.write_text(PDB, encoding="utf-8")
    assert gromacs.backbone_residues(pdb) == [
        ("A", "1", "MET"),
        ("A", "745", "LYS"),
        ("B", "2", "GLY"),
    ]


def test_backbone_residues_tolerates_missing_file(tmp_path: Path):
    assert gromacs.backbone_residues(tmp_path / "absent.pdb") == []


def test_analysis_and_rmsf_columns_are_declared():
    source = (IMAGE_DIR / "gromacs_platform.py").read_text(encoding="utf-8")
    # 回转半径进逐帧时间序列
    assert 'writer.writerow(columns + ["rmsd_nm", "rg_nm"])' in source
    assert '"gyrate"' in source
    # RMSF 单独一张逐残基表
    assert 'writer.writerow(["residue_seq", "residue_name", "rmsf_nm"])' in source
    assert '"rmsf_csv": file_ref(output_dir, "artifacts/rmsf.csv")' in source
    assert '"contacts_csv": file_ref(output_dir, "artifacts/contacts.csv")' in source
    assert '"interactions_json": file_ref(output_dir, "artifacts/interactions.json")' in source


def test_collect_input_slots_ignores_metadata_json_overwrites(tmp_path: Path):
    input_dir = tmp_path / "input"
    (input_dir / "protein_pdb").mkdir(parents=True)
    (input_dir / "ligand_sdf").mkdir(parents=True)
    prot = input_dir / "protein_pdb" / "receptor.pdb"
    prot_meta = input_dir / "protein_pdb" / "metadata.json"
    lig = input_dir / "ligand_sdf" / "ligand.sdf"
    lig_meta = input_dir / "ligand_sdf" / "ligand_sdf.metadata_json.json"
    prot.write_text(PDB, encoding="utf-8")
    prot_meta.write_text("{}", encoding="utf-8")
    lig.write_text("M  END\n", encoding="utf-8")
    lig_meta.write_text("{}", encoding="utf-8")

    manifest = [
        {"name": "protein_pdb", "path": "input/protein_pdb/receptor.pdb"},
        {"name": "protein_pdb", "path": "input/protein_pdb/metadata.json"},
        {"name": "ligand_sdf", "path": "input/ligand_sdf/ligand.sdf"},
        {"name": "ligand_sdf", "path": "input/ligand_sdf/ligand_sdf.metadata_json.json"},
    ]
    manifest_path = input_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    slots = gromacs.collect_input_slots(input_dir, {}, manifest_path)
    picked_protein = gromacs.pick_protein(slots, input_dir)
    picked_ligand = gromacs.pick_ligand_inputs(slots, input_dir, picked_protein)

    assert picked_protein == prot.resolve()
    assert picked_ligand["ligand_sdf"] == lig.resolve()
    assert picked_ligand["custom_itp"] is None


def test_pick_ligand_inputs_supports_custom_zip_and_itp_gro(tmp_path: Path):
    input_dir = tmp_path / "input"
    (input_dir / "protein_pdb").mkdir(parents=True)
    (input_dir / "ligand_topology").mkdir(parents=True)
    prot = input_dir / "protein_pdb" / "protein.pdb"
    top_zip = input_dir / "ligand_topology" / "bundle.zip"
    prot.write_text(PDB, encoding="utf-8")
    top_zip.write_bytes(b"PK\x05\x06" + b"\x00" * 18)

    slots = gromacs.collect_input_slots(
        input_dir,
        {"input_files": {"protein_pdb": str(prot), "ligand_topology": str(top_zip)}},
    )
    picked_protein = gromacs.pick_protein(slots, input_dir)
    picked_ligand = gromacs.pick_ligand_inputs(slots, input_dir, picked_protein)

    assert picked_protein == prot.resolve()
    assert picked_ligand["custom_zip"] == top_zip.resolve()
    assert picked_ligand["ligand_sdf"] is None


def test_stage_ligand_topology_and_center_pbc_fallback(tmp_path: Path, monkeypatch):
    work = tmp_path / "work"
    prep = tmp_path / "prep"
    work.mkdir()
    prep.mkdir()
    atomtypes = prep / "a.itp"
    lig_itp = prep / "l.itp"
    posre = prep / "p.itp"
    atomtypes.write_text("[ atomtypes ]\n", encoding="utf-8")
    lig_itp.write_text("[ moleculetype ]\n", encoding="utf-8")
    posre.write_text("[ position_restraints ]\n", encoding="utf-8")

    staged = gromacs._stage_ligand_topology_into_work(
        work,
        SimpleNamespace(atomtypes_itp=atomtypes, ligand_itp=lig_itp, posre_itp=posre),
    )
    assert staged == ("ligand_atomtypes.itp", "ligand.itp", "posre_ligand.itp")
    assert (work / "ligand_atomtypes.itp").is_file()
    assert (work / "ligand.itp").is_file()
    assert (work / "posre_ligand.itp").is_file()

    (work / "md.xtc").write_bytes(b"raw")
    (work / "md.gro").write_text("raw\n", encoding="utf-8")
    monkeypatch.setattr(gromacs, "run", lambda *a, **kw: (_ for _ in ()).throw(SystemExit("no Protein group")))
    xtc, gro = gromacs.center_pbc_trajectory(work)
    assert xtc == work / "md.xtc"
    assert gro == work / "md.gro"


def test_dockerfile_bundles_amber_prolif_mda_and_kernels():
    dockerfile = (IMAGE_DIR / "Dockerfile").read_text(encoding="utf-8")
    for token in (
        "ambertools",
        "acpype",
        "rdkit",
        "mdanalysis",
        "prolif",
        "networkx",
        "interactions_analysis.py",
        "ligand_parameterizer.py",
        "/opt/amber/anaconda3/envs/AmberTools",
    ):
        assert token in dockerfile, f"Dockerfile missing {token}"


def test_ensure_pdb_elements_populates_blank_columns_and_overrides_ligand(tmp_path: Path):
    pdb = tmp_path / "topology.pdb"
    pdb.write_text(
        "\n".join([
            "ATOM      1  N   ALA A   1      10.000  10.000  10.000  1.00  0.00",
            "ATOM      2  H   ALA A   1       9.500   9.500  10.000  1.00  0.00",
            "HETATM    3  C1  LIG     2      11.000  12.000  13.000  1.00  0.00",
            "HETATM    4  CL1 LIG     2      12.000  12.000  13.000  1.00  0.00",
            "END",
        ]) + "\n",
        encoding="utf-8",
    )
    ok = gromacs.ensure_pdb_elements(
        pdb,
        ["N", "H", "C", "C"],
        ligand_resname="LIG",
        ligand_elements=["C", "Cl"],
    )
    assert ok is True
    lines = pdb.read_text(encoding="utf-8").splitlines()
    assert lines[0][76:78] == " N"
    assert lines[1][76:78] == " H"
    assert lines[2][76:78] == " C"
    assert lines[3][76:78] == "Cl"


def test_run_interactions_postprocess_degrades_on_backend_error(tmp_path: Path, monkeypatch):
    import interactions_analysis

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated prolif crash")

    monkeypatch.setattr(interactions_analysis, "analyze_trajectory", _boom)
    payload = gromacs.run_interactions_postprocess(
        tmp_path / "topology.pdb",
        tmp_path / "md.xtc",
        tmp_path,
    )
    assert payload["engine"] == "skipped"
    assert payload["summary"]["total_interactions"] == 0
    assert "simulated prolif crash" in payload["warnings"][0]


# ---------------------------------------------------------------------------
# PR 2: GROMACS 轨迹去溶剂化抽帧（PDB-movie）镜像契约
# ---------------------------------------------------------------------------
def test_dockerfile_copies_trajectory_movie_module():
    dockerfile = (IMAGE_DIR / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY trajectory_movie_pdb.py /opt/aidd/gromacs/trajectory_movie_pdb.py" in dockerfile
    assert "COPY trajectory_movie.py /opt/aidd/gromacs/trajectory_movie.py" in dockerfile


def test_platform_declares_trajectory_movie_artifacts_and_metadata():
    source = (IMAGE_DIR / "gromacs_platform.py").read_text(encoding="utf-8")
    assert '"trajectory_movie_pdb": movie_ref' in source
    assert "def _publish_movie(" in source
    assert 'staging_dir / "trajectory_movie.pdb"' in source
    assert "def run_trajectory_movie_postprocess(" in source
    for key in ("movie_frames", "movie_stride", "movie_desolvated", "movie_aligned", "movie_time_ps"):
        assert f'"{key}"' in source, f"metadata.json missing {key}"
    # The movie is generated after the interaction post-process, never before.
    assert source.index("run_interactions_postprocess(") < source.index("run_trajectory_movie_postprocess(")


def test_trajectory_movie_module_exposes_clean_room_core():
    import trajectory_movie

    assert trajectory_movie.DEFAULT_MOVIE_MAX_FRAMES == 60
    assert trajectory_movie.MAX_MOVIE_MAX_FRAMES == 300
    assert callable(trajectory_movie.parse_pdb_atom_templates)
    assert callable(trajectory_movie.select_desolvated_indices)
    assert callable(trajectory_movie.export_desolvated_pdb_movie)


def test_run_trajectory_movie_postprocess_never_breaks_the_md_result(tmp_path: Path):
    payload = gromacs.run_trajectory_movie_postprocess(
        tmp_path / "topology.pdb",
        tmp_path / "md.xtc",
        tmp_path,
    )
    assert payload["written"] is False
    assert payload["movie_frames"] == 0
    assert payload["frame_indices"] == []
    assert payload["warnings"]


def test_movie_metadata_time_ps_is_a_per_model_list(tmp_path: Path):
    """The result page zips ``movie_time_ps`` with models: it must be an ordered list."""
    summary = {
        "written": True, "movie_frames": 3, "movie_stride": 4,
        "frame_times_ps": [0.0, 10.0, 20.0], "desolvated": True, "aligned": True,
    }
    metadata = tmp_path / "metadata.json"
    gromacs.write_json(metadata, gromacs._movie_metadata_fields(summary))
    payload = json.loads(metadata.read_text(encoding="utf-8"))

    assert isinstance(payload["movie_time_ps"], list)
    assert payload["movie_time_ps"] == [0.0, 10.0, 20.0]
    assert len(payload["movie_time_ps"]) == payload["movie_frames"] == 3


@pytest.mark.parametrize(
    "summary",
    [
        {"written": True, "movie_frames": 3, "frame_times_ps": [0.0, 10.0]},  # length mismatch
        {"written": True, "movie_frames": 2, "frame_times_ps": [0.0, float("nan")]},
        {"written": False, "movie_frames": 0, "frame_times_ps": [0.0]},
        {"written": True, "movie_frames": 0, "frame_times_ps": []},
    ],
)
def test_movie_metadata_time_ps_falls_back_to_empty_list(summary):
    fields = gromacs._movie_metadata_fields(summary)
    assert isinstance(fields["movie_time_ps"], list)
    assert fields["movie_time_ps"] == []


@pytest.mark.parametrize(
    ("value", "minimum", "maximum"),
    [(True, 1, None), ("inf", 1, None), ("nan", 1, None), (2.5, 1, None),
     (0, 1, None), (500, 1, 300), ("", 1, None), ("abc", 1, None)],
)
def test_strict_int_rejects_invalid_movie_settings(value, minimum, maximum):
    warnings: list[str] = []
    assert gromacs._strict_int(value, minimum=minimum, maximum=maximum, warnings=warnings, label="x") is None
    if value not in ("", None):
        assert warnings


def test_strict_int_accepts_integral_values_in_range():
    warnings: list[str] = []
    assert gromacs._strict_int("60", minimum=1, maximum=300, warnings=warnings, label="x") == 60
    assert gromacs._strict_int(60.0, minimum=1, maximum=300, warnings=warnings, label="x") == 60
    assert gromacs._strict_int(None, minimum=1, warnings=warnings, label="x") is None
    assert not warnings


def test_run_trajectory_movie_postprocess_warns_on_bad_params_without_crashing(tmp_path: Path):
    payload = gromacs.run_trajectory_movie_postprocess(
        tmp_path / "topology.pdb",
        tmp_path / "md.xtc",
        tmp_path,
        run_params={"movie_max_frames": "inf", "movie_max_bytes": 0},
    )
    assert payload["written"] is False
    assert any("movie_max_frames" in warning for warning in payload["warnings"])
    assert any("movie_max_bytes" in warning for warning in payload["warnings"])


# Issue 2: 不走 float()，杜绝 1024.000…01 被四舍五入、10**400 触发 OverflowError。
@pytest.mark.parametrize("value", ["1024.00000000000001", 10**400, "9" * 400])
def test_strict_int_rejects_float_artifact_and_huge_values(value):
    warnings: list[str] = []
    assert gromacs._strict_int(value, minimum=1, maximum=5000, warnings=warnings, label="x") is None
    assert warnings


def test_strict_int_accepts_integral_float_and_decimal_string():
    warnings: list[str] = []
    assert gromacs._strict_int(1024.0, minimum=1, maximum=5000, warnings=warnings, label="x") == 1024
    assert gromacs._strict_int("1024.0", minimum=1, maximum=5000, warnings=warnings, label="x") == 1024
    assert gromacs._strict_int("+2048", minimum=1, maximum=5000, warnings=warnings, label="x") == 2048
    assert not warnings


def test_bad_run_params_fall_back_instead_of_skipping_the_movie(tmp_path: Path):
    payload = gromacs.run_trajectory_movie_postprocess(
        tmp_path / "topology.pdb",
        tmp_path / "md.xtc",
        tmp_path,
        run_params={"movie_max_frames": 10**400, "movie_stride": "1024.00000000000001"},
    )
    assert payload["written"] is False  # 输入缺失才降级，绝不因单个坏参数抛错
    assert any("movie_max_frames" in warning for warning in payload["warnings"])
    assert any("movie_stride" in warning for warning in payload["warnings"])


# Issue 8: 旧影片的 unlink 与体积校验都放进 try 守卫；登记严格依赖 written 且文件非空。
def test_movie_file_ready_requires_written_true_and_nonempty(tmp_path: Path):
    path = tmp_path / "trajectory_movie.pdb"
    assert gromacs._movie_file_ready(path, {"written": True}) is False  # 文件不存在
    path.write_text("", encoding="utf-8")
    assert gromacs._movie_file_ready(path, {"written": True}) is False  # 空文件
    path.write_text("MODEL    1\n", encoding="utf-8")
    assert gromacs._movie_file_ready(path, {"written": True}) is True
    assert gromacs._movie_file_ready(path, {"written": False}) is False


def test_postprocess_removes_stale_movie_inside_guard(tmp_path: Path):
    stale = tmp_path / "trajectory_movie.pdb"
    stale.write_text("stale\n", encoding="utf-8")
    payload = gromacs.run_trajectory_movie_postprocess(
        tmp_path / "topology.pdb",
        tmp_path / "md.xtc",
        tmp_path,
    )
    assert payload["written"] is False
    assert not stale.exists()  # unlink 在 try 守卫内执行，异常也不会留下旧影片


# 第 8 项：哈希/移动抛 PermissionError 或 SystemExit 时降级为 None；影片在 artifacts 外暂存，
# 失败时不得留下不可读文件（上传器会在 result.json 之前读取 artifacts 下的每个文件）。
def test_publish_movie_returns_none_when_hashing_fails(tmp_path: Path, monkeypatch):
    output_dir = tmp_path / "out"
    (output_dir / "artifacts").mkdir(parents=True)
    target = tmp_path / "staging" / "trajectory_movie.pdb"
    target.parent.mkdir()
    target.write_text("MODEL    1\n", encoding="utf-8")
    warnings: list[str] = []

    def _denied(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(gromacs, "sha256_file", _denied)
    assert gromacs._publish_movie(output_dir, target, {"written": True}, warnings) is None
    assert warnings and "trajectory movie reference failed" in warnings[0]
    assert not (output_dir / "artifacts" / "trajectory_movie.pdb").exists()
    stale = output_dir / "artifacts" / "trajectory_movie.pdb"
    stale.write_text("stale\n", encoding="utf-8")
    assert gromacs._publish_movie(output_dir, target, {"written": False}, warnings) is None
    assert not stale.exists()  # 未写出时也必须清掉上一轮残留，避免无引用产物被上传
    assert len(warnings) == 1  # 未写出时根本不会哈希/移动

    # 哈希成功后移动阶段抛 SystemExit 同样降级，且不留下半成品
    monkeypatch.undo()
    monkeypatch.setattr(gromacs, "sha256_file", lambda path: "0" * 64)
    monkeypatch.setattr(gromacs.os, "replace", lambda *args: (_ for _ in ()).throw(SystemExit("gone")))
    sys_warnings: list[str] = []
    assert gromacs._publish_movie(output_dir, target, {"written": True}, sys_warnings) is None
    assert sys_warnings and "trajectory movie reference failed" in sys_warnings[0]
    assert not (output_dir / "artifacts" / "trajectory_movie.pdb").exists()


def test_main_registers_md_result_when_movie_ref_raises_system_exit(tmp_path: Path, monkeypatch):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "protein.pdb").write_text(PDB, encoding="utf-8")
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    params_path = tmp_path / "params.json"
    params_path.write_text(json.dumps({
        "input_files": {"protein_pdb": "protein.pdb"},
        "params": {"nsteps": 2500, "dt": 0.002, "temperature": 300.0},
    }), encoding="utf-8")

    def fake_run_pipeline(protein, work, **kwargs):
        work.mkdir(parents=True, exist_ok=True)
        (work / "topology.pdb").write_text(PDB, encoding="utf-8")
        (work / "trajectory.dcd").write_bytes(b"dcd")
        xtc = work / "md.xtc"
        xtc.write_bytes(b"xtc")
        gro = work / "md.gro"
        gro.write_text("gro\n", encoding="utf-8")
        return {"duration_ns": 5.0, "trajectory_xtc": str(xtc), "trajectory_gro": str(gro), "ligand": None}

    def fake_movie(topology_pdb, trajectory_path, out_dir, **kwargs):
        target = Path(out_dir) / "trajectory_movie.pdb"
        target.write_text("MODEL     1\nENDMDL\nEND\n", encoding="utf-8")
        return {
            "written": True, "movie_frames": 1, "total_source_frames": 1, "movie_stride": 1,
            "frame_indices": [0], "frame_times_ps": [0.0], "atom_count": 4, "desolvated": False,
            "aligned": False, "conect_count": 0, "size_bytes": target.stat().st_size, "warnings": [],
        }

    def fake_analysis(work, target, **kwargs):
        Path(target).write_text("time,potential\n", encoding="utf-8")

    real_sha256_file = gromacs.sha256_file

    def disappearing_sha256_file(path):
        if Path(path).name == "trajectory_movie.pdb":
            raise SystemExit("movie vanished")
        return real_sha256_file(path)

    monkeypatch.setattr(gromacs, "run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(gromacs, "write_analysis_csv", fake_analysis)
    monkeypatch.setattr(gromacs, "write_rmsf_csv", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        gromacs, "run_interactions_postprocess",
        lambda *args, **kwargs: {"mode": "skipped", "engine": "skipped", "summary": {}},
    )
    monkeypatch.setattr(gromacs, "run_trajectory_movie_postprocess", fake_movie)
    monkeypatch.setattr(gromacs, "sha256_file", disappearing_sha256_file)
    monkeypatch.setattr(sys, "argv", [
        "gromacs_platform.py", "--task-id", "t1",
        "--input-dir", str(input_dir), "--output-dir", str(output_dir),
        "--params-json", str(params_path), "--work-dir", str(tmp_path / "work"),
    ])

    class _ExitCalled(Exception):
        pass

    monkeypatch.setattr(gromacs.os, "_exit", lambda code: (_ for _ in ()).throw(_ExitCalled(code)))
    with pytest.raises(_ExitCalled):
        gromacs.main()

    result = json.loads((output_dir / "result.json").read_text(encoding="utf-8"))
    files = result["artifacts"]["trajectory"]["files"]
    assert "trajectory_movie_pdb" not in files
    assert {"topology_pdb", "trajectory_dcd", "metadata_json"} <= set(files)
    assert (output_dir / "artifacts" / "report.json").is_file()
    metadata = json.loads((output_dir / "artifacts" / "metadata.json").read_text(encoding="utf-8"))
    report = json.loads((output_dir / "artifacts" / "report.json").read_text(encoding="utf-8"))
    assert metadata["movie_frames"] == 0
    assert metadata["movie_time_ps"] == []
    assert report["movie_frames"] == 0
    assert any("trajectory movie reference failed" in warning for warning in metadata["movie_warnings"])
    assert not (output_dir / "artifacts" / "trajectory_movie.pdb").exists()


def test_main_registers_md_result_when_movie_ref_hash_fails(tmp_path: Path, monkeypatch):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "protein.pdb").write_text(PDB, encoding="utf-8")
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    params_path = tmp_path / "params.json"
    params_path.write_text(json.dumps({
        "input_files": {"protein_pdb": "protein.pdb"},
        "params": {"nsteps": 2500, "dt": 0.002, "temperature": 300.0},
    }), encoding="utf-8")

    def fake_run_pipeline(protein, work, **kwargs):
        work.mkdir(parents=True, exist_ok=True)
        (work / "topology.pdb").write_text(PDB, encoding="utf-8")
        (work / "trajectory.dcd").write_bytes(b"dcd")
        xtc = work / "md.xtc"
        xtc.write_bytes(b"xtc")
        gro = work / "md.gro"
        gro.write_text("gro\n", encoding="utf-8")
        return {"duration_ns": 5.0, "trajectory_xtc": str(xtc), "trajectory_gro": str(gro), "ligand": None}

    def fake_movie(topology_pdb, trajectory_path, out_dir, **kwargs):
        target = Path(out_dir) / "trajectory_movie.pdb"
        target.write_text("MODEL    1\nENDMDL\nEND\n", encoding="utf-8")
        return {
            "written": True, "movie_frames": 1, "total_source_frames": 1, "movie_stride": 1,
            "frame_indices": [0], "frame_times_ps": [0.0], "atom_count": 4, "desolvated": False,
            "aligned": False, "conect_count": 0, "size_bytes": target.stat().st_size, "warnings": [],
        }

    real_sha256_file = gromacs.sha256_file

    def flaky_sha256_file(path):
        if Path(path).name == "trajectory_movie.pdb":
            raise PermissionError("denied")
        return real_sha256_file(path)

    def fake_analysis(work, target, **kwargs):
        Path(target).write_text("time,potential\n", encoding="utf-8")

    monkeypatch.setattr(gromacs, "run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(gromacs, "write_analysis_csv", fake_analysis)
    monkeypatch.setattr(gromacs, "write_rmsf_csv", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        gromacs, "run_interactions_postprocess",
        lambda *args, **kwargs: {"mode": "skipped", "engine": "skipped", "summary": {}},
    )
    monkeypatch.setattr(gromacs, "run_trajectory_movie_postprocess", fake_movie)
    monkeypatch.setattr(gromacs, "sha256_file", flaky_sha256_file)
    monkeypatch.setattr(sys, "argv", [
        "gromacs_platform.py", "--task-id", "t1",
        "--input-dir", str(input_dir), "--output-dir", str(output_dir),
        "--params-json", str(params_path), "--work-dir", str(tmp_path / "work"),
    ])

    class _ExitCalled(Exception):
        pass

    def _exit(code):
        raise _ExitCalled(code)

    monkeypatch.setattr(gromacs.os, "_exit", _exit)
    with pytest.raises(_ExitCalled):
        gromacs.main()

    result = json.loads((output_dir / "result.json").read_text(encoding="utf-8"))
    files = result["artifacts"]["trajectory"]["files"]
    assert "trajectory_movie_pdb" not in files  # 哈希失败只丢引用，不丢 MD 结果
    assert {"topology_pdb", "trajectory_dcd", "metadata_json"} <= set(files)
    assert (output_dir / "artifacts" / "report.json").is_file()
    metadata = json.loads((output_dir / "artifacts" / "metadata.json").read_text(encoding="utf-8"))
    report = json.loads((output_dir / "artifacts" / "report.json").read_text(encoding="utf-8"))
    assert metadata["movie_frames"] == 0
    assert metadata["movie_time_ps"] == []
    assert report["movie_frames"] == 0
    assert any("trajectory movie reference failed" in warning for warning in metadata["movie_warnings"])
    # 哈希失败的电影在 artifacts 外暂存，不能留下不可读文件阻塞 result.json 发布
    assert not (output_dir / "artifacts" / "trajectory_movie.pdb").exists()


def test_main_skips_movie_when_gro_probe_is_denied(tmp_path: Path, monkeypatch):
    """``Path.is_file`` can raise ``PermissionError`` on an unreadable parent. The
    probe must run inside the movie guard: a finished MD result still publishes
    result.json, only without the optional movie."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "protein.pdb").write_text(PDB, encoding="utf-8")
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    params_path = tmp_path / "params.json"
    params_path.write_text(json.dumps({
        "input_files": {"protein_pdb": "protein.pdb"},
        "params": {"nsteps": 2500, "dt": 0.002, "temperature": 300.0},
    }), encoding="utf-8")

    def fake_run_pipeline(protein, work, **kwargs):
        work.mkdir(parents=True, exist_ok=True)
        (work / "topology.pdb").write_text(PDB, encoding="utf-8")
        (work / "trajectory.dcd").write_bytes(b"dcd")
        xtc = work / "md.xtc"
        xtc.write_bytes(b"xtc")
        gro = work / "md.gro"
        gro.write_text("gro\n", encoding="utf-8")
        return {"duration_ns": 5.0, "trajectory_xtc": str(xtc), "trajectory_gro": str(gro), "ligand": None}

    def fake_analysis(work, target, **kwargs):
        Path(target).write_text("time,potential\n", encoding="utf-8")

    real_is_file = Path.is_file

    def flaky_is_file(path):
        if path.name == "md.gro":
            raise PermissionError("denied")
        return real_is_file(path)

    monkeypatch.setattr(gromacs, "run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(gromacs, "write_analysis_csv", fake_analysis)
    monkeypatch.setattr(gromacs, "write_rmsf_csv", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        gromacs, "run_interactions_postprocess",
        lambda *args, **kwargs: {"mode": "skipped", "engine": "skipped", "summary": {}},
    )
    monkeypatch.setattr(Path, "is_file", flaky_is_file)
    monkeypatch.setattr(sys, "argv", [
        "gromacs_platform.py", "--task-id", "t1",
        "--input-dir", str(input_dir), "--output-dir", str(output_dir),
        "--params-json", str(params_path), "--work-dir", str(tmp_path / "work"),
    ])

    class _ExitCalled(Exception):
        pass

    monkeypatch.setattr(gromacs.os, "_exit", lambda code: (_ for _ in ()).throw(_ExitCalled(code)))
    with pytest.raises(_ExitCalled):
        gromacs.main()

    assert (output_dir / "result.json").is_file()
    metadata = json.loads((output_dir / "artifacts" / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["movie_frames"] == 0
    assert any("trajectory movie failed" in warning for warning in metadata["movie_warnings"])
    assert not (output_dir / "artifacts" / "trajectory_movie.pdb").exists()


def test_main_removes_stale_movie_when_staging_dir_fails(tmp_path: Path, monkeypatch):
    """A retry can find the previous attempt's movie in ``artifacts``. If the new
    staging directory cannot be created, that stale file must still be removed:
    the uploader enumerates every file before publishing ``result.json``."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "protein.pdb").write_text(PDB, encoding="utf-8")
    output_dir = tmp_path / "out"
    (output_dir / "artifacts").mkdir(parents=True)
    stale = output_dir / "artifacts" / "trajectory_movie.pdb"
    stale.write_text("MODEL     1\nENDMDL\nEND\n", encoding="utf-8")
    params_path = tmp_path / "params.json"
    params_path.write_text(json.dumps({
        "input_files": {"protein_pdb": "protein.pdb"},
        "params": {"nsteps": 2500, "dt": 0.002, "temperature": 300.0},
    }), encoding="utf-8")

    def fake_run_pipeline(protein, work, **kwargs):
        work.mkdir(parents=True, exist_ok=True)
        (work / "topology.pdb").write_text(PDB, encoding="utf-8")
        (work / "trajectory.dcd").write_bytes(b"dcd")
        xtc = work / "md.xtc"
        xtc.write_bytes(b"xtc")
        gro = work / "md.gro"
        gro.write_text("gro\n", encoding="utf-8")
        return {"duration_ns": 5.0, "trajectory_xtc": str(xtc), "trajectory_gro": str(gro), "ligand": None}

    def fake_analysis(work, target, **kwargs):
        Path(target).write_text("time,potential\n", encoding="utf-8")

    def no_staging(*args, **kwargs):
        raise OSError("staging denied")

    monkeypatch.setattr(gromacs, "run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(gromacs, "write_analysis_csv", fake_analysis)
    monkeypatch.setattr(gromacs, "write_rmsf_csv", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        gromacs, "run_interactions_postprocess",
        lambda *args, **kwargs: {"mode": "skipped", "engine": "skipped", "summary": {}},
    )
    monkeypatch.setattr(gromacs.tempfile, "mkdtemp", no_staging)
    monkeypatch.setattr(sys, "argv", [
        "gromacs_platform.py", "--task-id", "t1",
        "--input-dir", str(input_dir), "--output-dir", str(output_dir),
        "--params-json", str(params_path), "--work-dir", str(tmp_path / "work"),
    ])

    class _ExitCalled(Exception):
        pass

    monkeypatch.setattr(gromacs.os, "_exit", lambda code: (_ for _ in ()).throw(_ExitCalled(code)))
    with pytest.raises(_ExitCalled):
        gromacs.main()

    assert (output_dir / "result.json").is_file()
    result = json.loads((output_dir / "result.json").read_text(encoding="utf-8"))
    assert "trajectory_movie_pdb" not in result["artifacts"]["trajectory"]["files"]
    assert not stale.exists()  # 暂存失败也必须清掉上一轮影片
    metadata = json.loads((output_dir / "artifacts" / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["movie_frames"] == 0
    assert any("trajectory movie failed" in warning for warning in metadata["movie_warnings"])
