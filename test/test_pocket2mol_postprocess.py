"""Pocket2Mol 后处理：RDKit 描述符 / Lipinski / Murcko scaffold 富化测试。

后处理脚本位于 ``deploy/``，不是可导入的包，用 importlib 按路径加载；
整个过程不依赖平台、GPU 或对象存储。
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POSTPROCESS = (
    PROJECT_ROOT
    / "deploy"
    / "kubernetes"
    / "model-image-template"
    / "platform_adaptor"
    / "postprocess_result.py"
)

DESCRIPTOR_COLUMNS = [
    "molecular_weight",
    "logp",
    "hbd",
    "hba",
    "tpsa",
    "rotatable_bonds",
    "qed",
    "lipinski_violations",
    "scaffold",
]


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("postprocess_result", POSTPROCESS)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_sdf(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "generated_molecules.sdf").write_text("dummy sdf\n", encoding="utf-8")


def _run(
    module: ModuleType,
    tmp_path: Path,
    outputs: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> dict:
    (tmp_path / "result.json").write_text(
        json.dumps({"success": True, "outputs": outputs}), encoding="utf-8"
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "postprocess_result.py",
            "--model",
            "pocket2mol",
            "--output-dir",
            str(tmp_path),
            "--task-id",
            "task-pocket2mol",
        ],
    )
    assert module.main() == 0
    return json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_smiles_txt_postprocess_adds_descriptors_and_scaffold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "SMILES.txt").write_text(
        "CC(=O)Oc1ccccc1C(=O)O\nCCO\n", encoding="utf-8"
    )
    _write_sdf(tmp_path)

    payload = _run(
        module,
        tmp_path,
        {
            "smiles_file": "artifacts/SMILES.txt",
            "combined_sdf": "artifacts/generated_molecules.sdf",
        },
        monkeypatch,
    )

    table = payload["artifacts"]["molecules"]["files"]["table_file"]
    assert table["path"] == "artifacts/generated_molecules.csv"
    csv_path = tmp_path / table["path"]
    assert table["sha256"] == hashlib.sha256(csv_path.read_bytes()).hexdigest()

    rows = _read_rows(csv_path)
    assert list(rows[0].keys()) == ["smiles", *DESCRIPTOR_COLUMNS]
    aspirin = rows[0]
    assert aspirin["smiles"] == "CC(=O)Oc1ccccc1C(=O)O"
    assert abs(float(aspirin["molecular_weight"]) - 180.159) < 0.01
    assert aspirin["scaffold"] == "c1ccccc1"
    assert aspirin["lipinski_violations"] == "0"
    assert int(aspirin["hbd"]) == 1
    assert int(aspirin["hba"]) == 3
    assert 0.0 <= float(aspirin["qed"]) <= 1.0
    # 无环分子没有 Murcko scaffold，留空而不是报错。
    assert rows[1]["smiles"] == "CCO"
    assert rows[1]["scaffold"] == ""

    # 原始 SMILES.txt 保持原样。
    assert (artifacts / "SMILES.txt").read_text(encoding="utf-8").split() == [
        "CC(=O)Oc1ccccc1C(=O)O",
        "CCO",
    ]

    report = json.loads((artifacts / "report.json").read_text(encoding="utf-8"))
    assert report["molecule_count"] == 2
    assert report["valid_molecule_count"] == 2
    assert report["lipinski_pass_count"] == 2
    assert report["unique_scaffold_count"] == 1

    metadata = json.loads((artifacts / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["molecule_id_field"] == "smiles"
    assert payload["artifacts"]["molecules"]["metadata"]["molecule_id_field"] == "smiles"


def test_csv_input_keeps_extra_columns_next_to_descriptors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "molecules.csv").write_text(
        "molecule_id,smiles,score\nlig1,CCO,0.91\nlig2,CCN,0.77\n",
        encoding="utf-8",
    )
    _write_sdf(tmp_path)

    payload = _run(
        module,
        tmp_path,
        {
            "smiles_file": "artifacts/molecules.csv",
            "combined_sdf": "artifacts/generated_molecules.sdf",
        },
        monkeypatch,
    )

    rows = _read_rows(tmp_path / payload["artifacts"]["molecules"]["files"]["table_file"]["path"])
    # smiles 置首，原有列按原顺序保留，再追加描述符列。
    assert list(rows[0].keys()) == ["smiles", "molecule_id", "score", *DESCRIPTOR_COLUMNS]
    assert rows[0]["smiles"] == "CCO"
    assert rows[0]["molecule_id"] == "lig1"
    assert rows[0]["score"] == "0.91"
    assert rows[0]["molecular_weight"]
    assert rows[1]["molecule_id"] == "lig2"
    assert rows[1]["score"] == "0.77"


def test_invalid_smiles_row_is_kept_with_blank_descriptors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "SMILES.txt").write_text("CCO\nC1CC\n\n", encoding="utf-8")
    _write_sdf(tmp_path)

    _run(
        module,
        tmp_path,
        {
            "smiles_file": "artifacts/SMILES.txt",
            "combined_sdf": "artifacts/generated_molecules.sdf",
        },
        monkeypatch,
    )

    rows = _read_rows(tmp_path / "artifacts" / "generated_molecules.csv")
    assert len(rows) == 2
    assert rows[0]["molecular_weight"]
    assert rows[1]["smiles"] == "C1CC"
    for column in DESCRIPTOR_COLUMNS:
        assert rows[1][column] == ""

    report = json.loads((artifacts / "report.json").read_text(encoding="utf-8"))
    assert report["molecule_count"] == 2
    assert report["valid_molecule_count"] == 1
    assert report["lipinski_pass_count"] == 1


def test_missing_molecule_table_fails_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module()
    _write_sdf(tmp_path)

    with pytest.raises(SystemExit):
        _run(
            module,
            tmp_path,
            {
                "smiles_file": "artifacts/SMILES.txt",
                "combined_sdf": "artifacts/generated_molecules.sdf",
            },
            monkeypatch,
        )
