"""AIDD builtin tool unit tests."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.aidd import builtin_tools  # noqa: E402
from app.agents.aidd.capabilities import AIDD_TOOL_CAPABILITIES  # noqa: E402
from app.common.exceptions import ValidationException  # noqa: E402
from app.execution.result_parser import parse_standard_result  # noqa: E402
from app.execution.standard_contracts import DeclaredArtifactOutput  # noqa: E402
from app.external_databases.providers import ExternalArtifactFile, ExternalArtifactPayload  # noqa: E402


def test_sdf_to_smiles_csv_uses_molp_compatible_header() -> None:
    content = builtin_tools._smiles_csv_content(["CCO"]).decode("utf-8")

    assert content == "SMILES,id\nCCO,mol_1\n"


def test_builtin_sdf_conversion_normalizes_missing_header_line() -> None:
    sdf_content = b"""RDKit          3D

  3  2  0  0  0  0            999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.2000    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
    0.0000    1.1000    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0
  1  3  1  0
M  END
$$$$
"""

    normalized = builtin_tools._first_sdf_record_bytes(sdf_content)
    lines = normalized.splitlines()
    counts_index = next(index for index, line in enumerate(lines) if b"V2000" in line)

    assert counts_index == 3
    assert normalized.endswith(b"$$$$\n")


def test_convert_sdf_to_smiles_rejects_openbabel_title_only_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sdf_path = tmp_path / "ligand.sdf"
    sdf_path.write_text("mock sdf", encoding="utf-8")
    monkeypatch.setattr(
        builtin_tools.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="\tRDKit          3D\n", stderr=""),
    )

    with pytest.raises(ValidationException, match="未返回任何 SMILES"):
        builtin_tools.convert_sdf_to_smiles_with_tool(sdf_path)


def test_sdf_to_smiles_csv_builtin_emits_standard_molecule_table(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sdf_path = tmp_path / "ligand.sdf"
    sdf_path.write_text("mock sdf", encoding="utf-8")
    monkeypatch.setattr(builtin_tools, "parse_sdf_smiles", lambda _text: ["CCO"])

    result = builtin_tools._run_sdf_to_smiles_csv_tool(
        {
            "ligand_structure@1": builtin_tools.BuiltinToolFile(
                file_id="ligand-file",
                filename="ligand.sdf",
                path=sdf_path,
                content_type="chemical/x-mdl-sdfile",
            )
        }
    )

    artifacts = {artifact.filename: artifact for artifact in result.artifacts}
    assert "ligand_smiles.csv" in artifacts
    assert "ligand_smiles_metadata.json" in artifacts
    assert artifacts["ligand_smiles.csv"].content.decode("utf-8") == "SMILES,id\nCCO,mol_1\n"
    assert result.standard_result is not None
    molecules = result.standard_result["artifacts"]["molecules"]
    assert molecules["type"] == "molecule_table@1"
    assert set(molecules["files"]) == {"table_file", "metadata_json"}
    assert molecules["metadata"]["molecule_id_field"] == "id"


def test_sdf_to_pdb_builtin_emits_standard_ligand_structure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sdf_path = tmp_path / "ligand.sdf"
    sdf_path.write_text("mock sdf", encoding="utf-8")
    monkeypatch.setattr(
        builtin_tools,
        "convert_sdf_to_pdb_with_tool",
        lambda _path: b"HETATM    1  C   LIG A   1       0.000   0.000   0.000\nEND\n",
    )

    result = builtin_tools._run_sdf_to_pdb_tool(
        {
            "ligand_structure@1": builtin_tools.BuiltinToolFile(
                file_id="ligand-file",
                filename="ligand.sdf",
                path=sdf_path,
                content_type="chemical/x-mdl-sdfile",
            )
        }
    )

    artifacts = {artifact.filename: artifact for artifact in result.artifacts}
    assert "ligand_ligand.pdb" in artifacts
    assert result.standard_result is not None
    ligand = result.standard_result["artifacts"]["ligand"]
    assert ligand["type"] == "ligand_structure@1"
    assert set(ligand["files"]) == {"structure_file"}
    assert ligand["metadata"]["ligand_id"] == "ligand"


def test_placeholder_scientific_capabilities_are_not_executable() -> None:
    placeholder_slugs = {
        "builtin-admet-prediction",
        "builtin-toxicity-prediction",
        "builtin-synthetic-accessibility",
        "builtin-molecular-dynamics",
        "builtin-interaction-analysis",
    }

    assert not (placeholder_slugs & set(AIDD_TOOL_CAPABILITIES))


def test_rdkit_properties_builtin_emits_property_table_and_standard_result(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FakeBackend:
        name = "FakeRDKit"
        version = "0.0-test"

        def molecule_from_smiles(self, smiles: str):
            if smiles == "invalid":
                return None
            return {"smiles": smiles}

        def descriptors(self, molecule):
            smiles = molecule["smiles"]
            return {
                "molecular_weight": float(len(smiles) * 10),
                "logp": 1.5,
                "tpsa": 20.0,
                "hbd": 1,
                "hba": 2,
                "rotatable_bonds": 3,
                "heavy_atoms": len(smiles),
                "qed": 0.7,
                "lipinski_violations": 0,
            }

    monkeypatch.setattr(builtin_tools, "_rdkit_descriptor_backend", lambda: FakeBackend())
    csv_path = tmp_path / "molecules.csv"
    csv_path.write_text(
        "molecule_id,SMILES\nethanol,CCO\nbad,invalid\n",
        encoding="utf-8",
    )

    result = builtin_tools._run_rdkit_properties_tool(
        {
            "smiles_csv": builtin_tools.BuiltinToolFile(
                file_id="file-smiles",
                filename="molecules.csv",
                path=csv_path,
                content_type="text/csv",
            )
        }
    )

    artifacts = {artifact.filename: artifact for artifact in result.artifacts}
    assert "rdkit_properties.csv" in artifacts
    rows = list(csv.DictReader(io.StringIO(artifacts["rdkit_properties.csv"].content.decode("utf-8"))))
    assert rows[0]["molecular_weight"] == "30.0000"
    assert rows[0]["rdkit_status"] == "ok"
    assert rows[1]["rdkit_status"] == "invalid_smiles"
    assert result.standard_result is not None
    assert result.standard_result["result_version"] == "aidd.sciminer/result.v2"
    properties = result.standard_result["artifacts"]["properties"]
    assert properties["type"] == "molecule_table@1"
    assert properties["metadata"]["valid_molecule_count"] == 1
    assert properties["metadata"]["invalid_molecule_count"] == 1

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    for artifact in result.artifacts:
        (output_dir / artifact.filename).write_bytes(artifact.content)
    (output_dir / "result.json").write_text(
        json.dumps(result.standard_result, ensure_ascii=False),
        encoding="utf-8",
    )
    parsed = parse_standard_result(
        result_path=output_dir / "result.json",
        output_dir=output_dir,
        declared_outputs=[
            DeclaredArtifactOutput(name="properties", type="molecule_table@1"),
            DeclaredArtifactOutput(name="report", type="run_report@1", required=False),
        ],
    )
    assert [artifact.output_name for artifact in parsed.artifacts] == ["properties", "report"]


@pytest.mark.asyncio
async def test_run_builtin_tool_routes_rdkit_properties(monkeypatch, tmp_path: Path) -> None:
    csv_path = tmp_path / "molecules.csv"
    csv_path.write_text("SMILES,id\nCCO,mol_1\n", encoding="utf-8")
    called: dict[str, object] = {}

    def fake_handler(files, params=None):
        called["files"] = files
        called["params"] = params
        return builtin_tools.BuiltinToolResult()

    monkeypatch.setattr(builtin_tools, "_run_rdkit_properties_tool", fake_handler)

    await builtin_tools.run_builtin_tool(
        "builtin-rdkit-properties",
        {
            "smiles_csv": builtin_tools.BuiltinToolFile(
                file_id="file-smiles",
                filename="molecules.csv",
                path=csv_path,
                content_type="text/csv",
            )
        },
        params={"smiles_field": "SMILES"},
    )

    assert "smiles_csv" in called["files"]
    assert called["params"] == {"smiles_field": "SMILES"}


@pytest.mark.asyncio
async def test_fetch_pdb_builtin_emits_protein_structure_standard_result(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FakeRCSBProvider:
        async def fetch_protein(self, identifier: str):
            assert identifier == "1abc"
            return ExternalArtifactPayload(
                artifact_type="protein_structure",
                standard_ref="protein_structure@1",
                name="1ABC",
                description="Imported from RCSB PDB",
                metadata={
                    "chain_ids": ["A"],
                    "residue_count": 1,
                    "atom_count": 1,
                    "structure_format": "pdb",
                    "source_filename": "1ABC.pdb",
                    "source_database": "rcsb",
                    "source_id": "1ABC",
                },
                files=[
                    ExternalArtifactFile(
                        role="structure_file",
                        filename="1ABC.pdb",
                        content=b"HEADER    TEST PDB\nEND\n",
                        content_type="chemical/x-pdb",
                    )
                ],
            )

    monkeypatch.setattr(
        builtin_tools,
        "_external_database_providers",
        lambda: {"rcsb": FakeRCSBProvider()},
    )

    result = await builtin_tools._run_fetch_pdb_tool({}, {"pdb_id": "1abc"})

    assert result.standard_result is not None
    protein = result.standard_result["artifacts"]["protein"]
    assert protein["type"] == "protein_structure@1"
    assert protein["metadata"]["source_database"] == "rcsb"
    assert set(protein["files"]) == {"structure_file", "metadata_json"}
    artifacts = {artifact.filename: artifact for artifact in result.artifacts}
    assert {"1ABC.pdb", "metadata.json", "fetch_pdb_report.json"}.issubset(artifacts)

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    for artifact in result.artifacts:
        (output_dir / artifact.filename).write_bytes(artifact.content)
    (output_dir / "result.json").write_text(
        json.dumps(result.standard_result, ensure_ascii=False),
        encoding="utf-8",
    )
    parsed = parse_standard_result(
        result_path=output_dir / "result.json",
        output_dir=output_dir,
        declared_outputs=[
            DeclaredArtifactOutput(name="protein", type="protein_structure@1"),
            DeclaredArtifactOutput(name="report", type="run_report@1", required=False),
        ],
    )
    assert [artifact.output_name for artifact in parsed.artifacts] == ["protein", "report"]


@pytest.mark.asyncio
async def test_fetch_ligand_builtin_emits_ligand_structure_standard_result(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FakePubChemProvider:
        async def fetch_ligand(self, identifier: str):
            assert identifier == "2244"
            return ExternalArtifactPayload(
                artifact_type="ligand_structure",
                standard_ref="ligand_structure@1",
                name="Aspirin",
                description="Imported from PubChem",
                metadata={
                    "ligand_id": "pubchem:2244",
                    "source_database": "pubchem",
                    "source_id": "2244",
                    "pubchem_cid": "2244",
                    "canonical_smiles": "CC(=O)OC1=CC=CC=C1C(=O)O",
                    "structure_3d_source": "pubchem_3d",
                    "hydrogens_added": False,
                },
                files=[
                    ExternalArtifactFile(
                        role="structure_file",
                        filename="pubchem-2244.sdf",
                        content=b"primary sdf",
                        content_type="chemical/x-mdl-sdfile",
                    ),
                    ExternalArtifactFile(
                        role="structure_2d_sdf",
                        filename="pubchem-2244.2d.sdf",
                        content=b"2d sdf",
                        content_type="chemical/x-mdl-sdfile",
                    ),
                    ExternalArtifactFile(
                        role="structure_3d_sdf",
                        filename="pubchem-2244.3d.sdf",
                        content=b"3d sdf",
                        content_type="chemical/x-mdl-sdfile",
                    ),
                ],
            )

    monkeypatch.setattr(
        builtin_tools,
        "_external_database_providers",
        lambda: {"pubchem": FakePubChemProvider()},
    )

    result = await builtin_tools._run_fetch_ligand_tool({}, {"pubchem_cid": "2244"})

    assert result.standard_result is not None
    ligand = result.standard_result["artifacts"]["ligand"]
    assert ligand["type"] == "ligand_structure@1"
    assert ligand["metadata"]["source_database"] == "pubchem"
    assert set(ligand["files"]) == {
        "structure_file",
        "structure_2d_sdf",
        "structure_3d_sdf",
        "metadata_json",
    }
    artifacts = {artifact.filename: artifact for artifact in result.artifacts}
    assert {"pubchem-2244.sdf", "metadata.json", "fetch_ligand_report.json"}.issubset(artifacts)

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    for artifact in result.artifacts:
        (output_dir / artifact.filename).write_bytes(artifact.content)
    (output_dir / "result.json").write_text(
        json.dumps(result.standard_result, ensure_ascii=False),
        encoding="utf-8",
    )
    parsed = parse_standard_result(
        result_path=output_dir / "result.json",
        output_dir=output_dir,
        declared_outputs=[
            DeclaredArtifactOutput(name="ligand", type="ligand_structure@1"),
            DeclaredArtifactOutput(name="report", type="run_report@1", required=False),
        ],
    )
    assert [artifact.output_name for artifact in parsed.artifacts] == ["ligand", "report"]


@pytest.mark.asyncio
async def test_run_builtin_tool_routes_protein_preparation(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "protein.pdb"
    source.write_text("ATOM      1  N   ALA A   1       0.000   0.000   0.000\nEND\n")
    called: dict[str, object] = {}

    def fake_handler(files, params=None):
        called["files"] = files
        called["params"] = params
        return builtin_tools.BuiltinToolResult()

    monkeypatch.setattr(builtin_tools, "_run_protein_preparation_tool", fake_handler)

    await builtin_tools.run_builtin_tool(
        "builtin-protein-preparation",
        {
            "protein_structure@1": builtin_tools.BuiltinToolFile(
                file_id="protein-file",
                filename="protein.pdb",
                path=source,
                content_type="chemical/x-pdb",
            )
        },
        params={"options": {"ph": 7.0}},
    )

    assert "protein_structure@1" in called["files"]
    assert called["params"] == {"options": {"ph": 7.0}}


def test_builtin_protein_preparation_emits_standard_result_v2(
    tmp_path: Path,
    monkeypatch,
) -> None:
    protein = tmp_path / "protein.pdb"
    protein.write_text(
        "ATOM      1  N   ALA A   1       0.000   0.000   0.000\n"
        "HETATM    2  O   HOH A 101       1.000   1.000   1.000\n"
        "END\n",
        encoding="utf-8",
    )

    def fake_convert(prepared_pdb: Path, receptor_pdbqt: Path, *, rigid: bool):
        assert rigid is True
        assert "HOH" not in prepared_pdb.read_text(encoding="utf-8")
        receptor_pdbqt.write_text("REMARK receptor pdbqt\n", encoding="utf-8")

    monkeypatch.setattr(
        "app.protein_preparation.engine.convert_prepared_pdb_to_pdbqt",
        fake_convert,
    )

    result = builtin_tools._run_protein_preparation_tool(
        {
            "protein_structure@1": builtin_tools.BuiltinToolFile(
                file_id="file-protein",
                filename="protein.pdb",
                path=protein,
                content_type="chemical/x-pdb",
            )
        },
        params={
            "preparation_profile": "docking_v1",
            "options": {
                "ph": 7.4,
                "remove_water": True,
                "output_formats": ["prepared_pdb", "receptor_pdbqt"],
            },
            "advanced_options": {"chain_selection": ["A"]},
        },
    )

    assert result.standard_result is not None
    assert result.standard_result["result_version"] == "aidd.sciminer/result.v2"
    prepared = result.standard_result["artifacts"]["prepared_protein"]
    assert prepared["type"] == "protein_structure@1"
    assert prepared["metadata"]["preparation_status"] == "prepared"
    assert prepared["metadata"]["preparation_profile"] == "docking_v1"
    assert prepared["metadata"]["ph"] == 7.4
    assert set(prepared["files"]) == {
        "structure_file",
        "metadata_json",
        "prepared_pdb",
        "receptor_pdbqt",
        "preparation_report_json",
    }
    artifacts_by_filename = {artifact.filename: artifact for artifact in result.artifacts}
    assert set(artifacts_by_filename) == {
        "prepared.pdb",
        "receptor.pdbqt",
        "preparation_report.json",
    }
    assert b"HOH" not in artifacts_by_filename["prepared.pdb"].content
    assert prepared["files"]["prepared_pdb"]["sha256"] == hashlib.sha256(
        artifacts_by_filename["prepared.pdb"].content
    ).hexdigest()
    assert prepared["files"]["preparation_report_json"]["sha256"] == hashlib.sha256(
        artifacts_by_filename["preparation_report.json"].content
    ).hexdigest()


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


# ==========================================================================
# 新增：数据库查询 / ADMET / 毒性 / SA / MD / interaction 工具测试
# ==========================================================================


class TestReadSmilesFromCsv:
    def test_returns_smiles_list(self, tmp_path: Path):
        csv_path = tmp_path / "smiles.csv"
        csv_path.write_text("SMILES,id\nCCO,mol_1\nCC(=O)Oc1ccccc1C(=O)O,mol_2\n")
        result = builtin_tools._read_smiles_from_csv(csv_path)
        assert result == ["CCO", "CC(=O)Oc1ccccc1C(=O)O"]

    def test_handles_empty_csv(self, tmp_path: Path):
        csv_path = tmp_path / "empty.csv"
        csv_path.write_text("SMILES,id\n")
        result = builtin_tools._read_smiles_from_csv(csv_path)
        assert result == []

    def test_handles_lowercase_column(self, tmp_path: Path):
        csv_path = tmp_path / "smiles.csv"
        csv_path.write_text("smiles,id\nCCO,mol_1\n")
        result = builtin_tools._read_smiles_from_csv(csv_path)
        assert result == ["CCO"]


class TestDictsToCsvBytes:
    def test_empty_list(self):
        assert builtin_tools._dicts_to_csv_bytes([]) == b""

    def test_converts_records(self):
        records = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        result = builtin_tools._dicts_to_csv_bytes(records).decode("utf-8")
        lines = result.strip().split("\n")
        assert lines[0] == "a,b"
        assert len(lines) == 3


class TestQueryChemblBuiltinTool:
    @pytest.mark.asyncio
    async def test_extracts_smiles_and_calls_query(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("app.config.settings.ENABLE_DATABASE_TOOLS", True)

        csv_path = tmp_path / "smiles.csv"
        csv_path.write_text("SMILES,id\nCCO,mol_1\n")

        mock_result = {"source": "chembl", "record_count": 1, "records": []}

        with patch(
            "app.agents.aidd.database_tools.query_chembl",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = await builtin_tools._run_query_chembl_tool({
                "smiles_csv": builtin_tools.BuiltinToolFile(
                    file_id="f1", filename="smiles.csv", path=csv_path,
                )
            })

        assert len(result.outputs) == 1
        assert result.outputs[0].semantic_type == "database_query_result"
        assert result.outputs[0].data["source"] == "chembl"
        assert len(result.artifacts) == 0

    @pytest.mark.asyncio
    async def test_disabled_flag_raises(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("app.config.settings.ENABLE_DATABASE_TOOLS", False)

        csv_path = tmp_path / "smiles.csv"
        csv_path.write_text("SMILES,id\nCCO,mol_1\n")

        with pytest.raises(ValidationException, match="已禁用"):
            await builtin_tools._run_query_chembl_tool({
                "smiles_csv": builtin_tools.BuiltinToolFile(
                    file_id="f1", filename="smiles.csv", path=csv_path,
                )
            })

    @pytest.mark.asyncio
    async def test_missing_smiles_csv_raises(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("app.config.settings.ENABLE_DATABASE_TOOLS", True)
        with pytest.raises(ValidationException, match="需要 smiles_csv"):
            await builtin_tools._run_query_chembl_tool({})


class TestQueryPubchemBuiltinTool:
    @pytest.mark.asyncio
    async def test_extracts_smiles_and_calls_query(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("app.config.settings.ENABLE_DATABASE_TOOLS", True)

        csv_path = tmp_path / "smiles.csv"
        csv_path.write_text("SMILES,id\nCC(=O)Oc1ccccc1C(=O)O,mol_1\n")

        mock_result = {"source": "pubchem", "record_count": 1, "records": []}

        with patch(
            "app.agents.aidd.database_tools.query_pubchem",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = await builtin_tools._run_query_pubchem_tool({
                "smiles_csv": builtin_tools.BuiltinToolFile(
                    file_id="f1", filename="smiles.csv", path=csv_path,
                )
            })

        assert len(result.outputs) == 1
        assert result.outputs[0].semantic_type == "database_query_result"
        assert result.outputs[0].data["source"] == "pubchem"


class TestQueryPdbbindBuiltinTool:
    @pytest.mark.asyncio
    async def test_extracts_pdb_id_from_filename(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("app.config.settings.ENABLE_DATABASE_TOOLS", True)

        mock_result = {"source": "pdbbind", "record_count": 1, "records": []}

        with patch(
            "app.agents.aidd.database_tools.query_pdbbind",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = await builtin_tools._run_query_pdbbind_tool({
                "protein_pdb": builtin_tools.BuiltinToolFile(
                    file_id="f1", filename="3T5G_protein.pdb",
                    path=tmp_path / "dummy.pdb",
                )
            })

        assert len(result.outputs) == 1
        assert result.outputs[0].semantic_type == "database_query_result"
        assert result.outputs[0].data["source"] == "pdbbind"

    @pytest.mark.asyncio
    async def test_works_without_any_files(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("app.config.settings.ENABLE_DATABASE_TOOLS", True)

        mock_result = {"source": "pdbbind", "record_count": 0, "records": []}

        with patch(
            "app.agents.aidd.database_tools.query_pdbbind",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = await builtin_tools._run_query_pdbbind_tool({})

        assert len(result.outputs) == 1


class TestAdmetPredictionBuiltinTool:
    def test_produces_csv_report(self, tmp_path: Path):
        csv_path = tmp_path / "smiles.csv"
        csv_path.write_text("SMILES,id\nCCO,mol_1\nCC(=O)Oc1ccccc1C(=O)O,mol_2\n")

        result = builtin_tools._run_admet_prediction_tool({
            "smiles_csv": builtin_tools.BuiltinToolFile(
                file_id="f1", filename="smiles.csv", path=csv_path,
            )
        })

        assert len(result.artifacts) == 1
        artifact = result.artifacts[0]
        assert artifact.semantic_type == "admet_report"
        assert artifact.content_type == "text/csv"

        reader = csv.DictReader(io.StringIO(artifact.content.decode("utf-8")))
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["smiles"] == "CCO"
        assert rows[0]["prediction_status"] == "unconfigured"
        assert rows[0]["endpoint_ref"] == "unknown"
        assert rows[0]["unit_or_label"] == "unknown"
        assert rows[0]["model_version"] == "unknown"
        assert rows[0]["evidence_level"] == "engineering_smoke_only"
        assert rows[0]["applicability_domain_status"] == "unknown"
        assert rows[0]["value"] == ""
        assert "configure a real ADMET endpoint" in rows[0]["note"]


class TestToxicityPredictionBuiltinTool:
    def test_produces_csv_report(self, tmp_path: Path):
        csv_path = tmp_path / "smiles.csv"
        csv_path.write_text("SMILES,id\nCCO,mol_1\n")

        result = builtin_tools._run_toxicity_prediction_tool({
            "smiles_csv": builtin_tools.BuiltinToolFile(
                file_id="f1", filename="smiles.csv", path=csv_path,
            )
        })

        assert len(result.artifacts) == 1
        assert result.artifacts[0].semantic_type == "toxicity_report"


class TestSyntheticAccessibilityBuiltinTool:
    def test_produces_csv_report(self, tmp_path: Path):
        csv_path = tmp_path / "smiles.csv"
        csv_path.write_text("SMILES,id\nCCO,mol_1\n")

        result = builtin_tools._run_synthetic_accessibility_tool({
            "smiles_csv": builtin_tools.BuiltinToolFile(
                file_id="f1", filename="smiles.csv", path=csv_path,
            )
        })

        assert len(result.artifacts) == 1
        assert result.artifacts[0].semantic_type == "synthetic_accessibility"


class TestMolecularDynamicsBuiltinTool:
    def test_requires_protein_and_ligand(self, tmp_path: Path):
        with pytest.raises(ValidationException, match="protein_pdb"):
            builtin_tools._run_molecular_dynamics_tool({
                "ligand_pdb": builtin_tools.BuiltinToolFile(
                    file_id="f1", filename="ligand.pdb",
                    path=tmp_path / "ligand.pdb",
                )
            })

    def test_produces_structured_output(self, tmp_path: Path):
        protein = tmp_path / "protein.pdb"
        protein.write_text("")
        ligand = tmp_path / "ligand.pdb"
        ligand.write_text("")

        result = builtin_tools._run_molecular_dynamics_tool({
            "protein_pdb": builtin_tools.BuiltinToolFile(
                file_id="f1", filename="protein.pdb", path=protein,
            ),
            "ligand_pdb": builtin_tools.BuiltinToolFile(
                file_id="f2", filename="ligand.pdb", path=ligand,
            ),
        })

        assert len(result.outputs) == 1
        assert result.outputs[0].semantic_type == "molecular_dynamics_trajectory"


class TestInteractionAnalysisBuiltinTool:
    def test_produces_json_report(self, tmp_path: Path):
        protein = tmp_path / "protein.pdb"
        protein.write_text("")
        ligand = tmp_path / "ligand.pdb"
        ligand.write_text("")

        result = builtin_tools._run_interaction_analysis_tool({
            "protein_pdb": builtin_tools.BuiltinToolFile(
                file_id="f1", filename="protein.pdb", path=protein,
            ),
            "ligand_pdb": builtin_tools.BuiltinToolFile(
                file_id="f2", filename="ligand.pdb", path=ligand,
            ),
        })

        assert len(result.artifacts) == 1
        assert result.artifacts[0].semantic_type == "interaction_report"
        assert result.artifacts[0].content_type == "application/json"
        data = json.loads(result.artifacts[0].content)
        assert "interactions" in data


class TestRunBuiltinToolDispatch:
    def test_registry_covers_all_virtual_capabilities(self):
        """确保所有注册的虚拟工具都有分发处理。"""
        from app.agents.aidd.capabilities import AIDD_TOOL_CAPABILITIES

        virtual_slugs = {
            slug for slug, cap in AIDD_TOOL_CAPABILITIES.items() if cap.virtual
        }
        for slug in virtual_slugs:
            assert slug in builtin_tools._BUILTIN_TOOL_REGISTRY, (
                f"虚拟工具 {slug} 缺少 builtin handler 注册"
            )

    @pytest.mark.asyncio
    async def test_registry_routes_to_correct_handler(self, tmp_path: Path, monkeypatch):
        """验证每个注册的 tool slug 都能正确分发。"""
        monkeypatch.setattr("app.config.settings.ENABLE_DATABASE_TOOLS", True)

        csv_path = tmp_path / "smiles.csv"
        csv_path.write_text("SMILES,id\nCCO,mol_1\n")
        csv_file = builtin_tools.BuiltinToolFile(
            file_id="f1", filename="smiles.csv", path=csv_path,
        )
        files = {"smiles_csv": csv_file}

        mock_result = {"source": "test", "record_count": 0, "records": []}

        with patch(
            "app.agents.aidd.database_tools.query_chembl",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            r = await builtin_tools.run_builtin_tool("builtin-query-chembl", files)
            assert r.outputs[0].semantic_type == "database_query_result"

        with patch(
            "app.agents.aidd.database_tools.query_pubchem",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            r = await builtin_tools.run_builtin_tool("builtin-query-pubchem", files)
            assert r.outputs[0].semantic_type == "database_query_result"

        for slug in (
            "builtin-admet-prediction",
            "builtin-toxicity-prediction",
            "builtin-synthetic-accessibility",
            "builtin-molecular-dynamics",
            "builtin-interaction-analysis",
        ):
            with pytest.raises(ValidationException, match="尚未接入真实执行引擎"):
                await builtin_tools.run_builtin_tool(slug, files)

    @pytest.mark.asyncio
    async def test_unknown_tool_raises(self):
        with pytest.raises(ValidationException, match="未知内置智能体工具"):
            await builtin_tools.run_builtin_tool("builtin-unknown-tool", {})

    @pytest.mark.asyncio
    async def test_query_tool_dispatch_runs_inside_existing_event_loop(
        self,
        tmp_path: Path,
        monkeypatch,
    ):
        """数据库查询内置工具不能在已有事件循环中嵌套 asyncio.run。"""
        monkeypatch.setattr("app.config.settings.ENABLE_DATABASE_TOOLS", True)

        csv_path = tmp_path / "smiles.csv"
        csv_path.write_text("SMILES,id\nCCO,mol_1\n")
        files = {
            "smiles_csv": builtin_tools.BuiltinToolFile(
                file_id="f1",
                filename="smiles.csv",
                path=csv_path,
            )
        }
        mock_result = {"source": "chembl", "record_count": 0, "records": []}

        with patch(
            "app.agents.aidd.database_tools.query_chembl",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = await builtin_tools.run_builtin_tool("builtin-query-chembl", files)

        assert result.outputs[0].data == mock_result
