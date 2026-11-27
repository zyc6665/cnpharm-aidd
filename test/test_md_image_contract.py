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
