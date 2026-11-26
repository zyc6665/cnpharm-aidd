"""LDDM 平台适配层（lddm_platform.py 与 postprocess_result --model lddm）单测。"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LDDM_PLATFORM = ROOT / "deploy" / "model-images" / "k8s" / "lddm" / "lddm_platform.py"
POSTPROCESS = (
    ROOT
    / "deploy"
    / "kubernetes"
    / "model-image-template"
    / "platform_adaptor"
    / "postprocess_result.py"
)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_lddm_platform_prepare_with_center_probe_and_finalize(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("rdkit")
    mod = _load("_test_lddm_platform", LDDM_PLATFORM)

    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    work_dir = tmp_path / "work"
    in_dir.mkdir()
    out_dir.mkdir()
    work_dir.mkdir()

    pdb = in_dir / "protein.pdb"
    pdb.write_text(
        "ATOM      1  CA  ALA A   1      22.000   0.200  52.800  1.00 20.00           C\nEND\n",
        encoding="utf-8",
    )
    ckpt = tmp_path / "lddm.ckpt"
    ckpt.write_bytes(b"stub")

    params_json = tmp_path / "params.json"
    params_json.write_text(
        json.dumps(
            {
                "input_files": {"protein_pdb": "protein.pdb"},
                "params": {
                    "checkpoint": str(ckpt),
                    "num_samples": 12,
                    "batch_size": 4,
                    "n_steps": 50,
                    "sampler": "HeunSampler",
                    "center_x": 22.0,
                    "center_y": 0.2,
                    "center_z": 52.8,
                    "device": "cpu",
                },
            }
        ),
        encoding="utf-8",
    )

    env_out = work_dir / "env.sh"
    meta_out = work_dir / "meta.json"
    sdf_out = work_dir / "raw.sdf"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "lddm_platform.py",
            "prepare",
            "--task-id",
            "t-lddm-1",
            "--input-dir",
            str(in_dir),
            "--output-dir",
            str(out_dir),
            "--params-json",
            str(params_json),
            "--work-dir",
            str(work_dir),
            "--device",
            "cpu",
            "--env-out",
            str(env_out),
            "--metadata-out",
            str(meta_out),
            "--sdf-out",
            str(sdf_out),
        ],
    )
    assert mod.main() == 0

    meta = json.loads(meta_out.read_text(encoding="utf-8"))
    assert meta["ref_ligand_source"] == "params.center_xyz"
    assert meta["n_samples"] == 12
    assert meta["batch_size"] == 4
    assert meta["sampler"] == "HeunSampler"
    assert Path(meta["ref_ligand"]).is_file()

    # 模拟 sample.py 生成多分子 SDF 并测试 finalize + postprocess
    from rdkit import Chem
    from rdkit.Chem import AllChem

    writer = Chem.SDWriter(str(sdf_out))
    for smi in ("CC(=O)Oc1ccccc1C(=O)O", "Cn1cnc2c1c(=O)n(C)c(=O)n2C"):
        mol = Chem.MolFromSmiles(smi)
        AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
        writer.write(mol)
    writer.close()

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "lddm_platform.py",
            "finalize",
            "--task-id",
            "t-lddm-1",
            "--output-dir",
            str(out_dir),
            "--sdf-path",
            str(sdf_out),
            "--metadata-json",
            str(meta_out),
            "--start-ts",
            "1000",
        ],
    )
    assert mod.main() == 0

    legacy = json.loads((out_dir / "result.json").read_text(encoding="utf-8"))
    assert legacy["success"] is True
    assert legacy["outputs"]["molecule_count"] == 2

    post = _load("_test_lddm_postprocess", POSTPROCESS)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "postprocess_result.py",
            "--model",
            "lddm",
            "--output-dir",
            str(out_dir),
            "--task-id",
            "t-lddm-1",
        ],
    )
    assert post.main() == 0

    rows = list(csv.DictReader((out_dir / "artifacts" / "generated_molecules.csv").open(encoding="utf-8")))
    assert len(rows) == 2
    assert rows[0]["molecular_weight"]
    assert rows[0]["scaffold"]
    report = json.loads((out_dir / "artifacts" / "report.json").read_text(encoding="utf-8"))
    assert report["tool"] == "lddm-pocket-ligand-generation"


def test_lddm_platform_fragment_and_dock_modes(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("rdkit")
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mod = _load("_test_lddm_platform_modes", LDDM_PLATFORM)
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    work_dir = tmp_path / "work"
    in_dir.mkdir()
    out_dir.mkdir()
    work_dir.mkdir()

    (in_dir / "protein.pdb").write_text(
        "ATOM      1  CA  ALA A   1      10.000  10.000  10.000  1.00 20.00           C\nEND\n",
        encoding="utf-8",
    )
    frag_mol = Chem.MolFromSmiles("c1ccccc1")
    AllChem.EmbedMolecule(frag_mol, AllChem.ETKDGv3())
    Chem.MolToPDBFile(frag_mol, str(in_dir / "frag.pdb"))
    ckpt = tmp_path / "lddm.ckpt"
    ckpt.write_bytes(b"stub")

    params_json = tmp_path / "params_dock.json"
    params_json.write_text(
        json.dumps(
            {
                "input_files": {"protein_pdb": "protein.pdb", "fragment_sdf": "frag.pdb"},
                "params": {
                    "checkpoint": str(ckpt),
                    "generation_mode": "dock",
                    "atoms_to_dock": "0, 2, 4",
                    "center_x": 10.0,
                    "center_y": 10.0,
                    "center_z": 10.0,
                    "device": "cpu",
                },
            }
        ),
        encoding="utf-8",
    )
    env_out = work_dir / "env.sh"
    meta_out = work_dir / "meta.json"
    sdf_out = work_dir / "raw.sdf"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "lddm_platform.py",
            "prepare",
            "--task-id",
            "t-lddm-dock",
            "--input-dir",
            str(in_dir),
            "--output-dir",
            str(out_dir),
            "--params-json",
            str(params_json),
            "--work-dir",
            str(work_dir),
            "--device",
            "cpu",
            "--env-out",
            str(env_out),
            "--metadata-out",
            str(meta_out),
            "--sdf-out",
            str(sdf_out),
        ],
    )
    assert mod.main() == 0
    meta = json.loads(meta_out.read_text(encoding="utf-8"))
    assert meta["cli_mode"] == "dock"
    assert meta["atoms_to_dock"] == [0, 2, 4]
    assert meta["fragment_ligand"].endswith(".converted.sdf")
    assert Path(meta["fragment_ligand"]).is_file()

