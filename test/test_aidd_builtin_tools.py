"""AIDD builtin tool unit tests."""

from __future__ import annotations

import csv
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


def test_sdf_to_smiles_csv_uses_molp_compatible_header() -> None:
    content = builtin_tools._smiles_csv_content(["CCO"]).decode("utf-8")

    assert content == "SMILES,id\nCCO,mol_1\n"


def test_placeholder_scientific_capabilities_are_not_executable() -> None:
    placeholder_slugs = {
        "builtin-admet-prediction",
        "builtin-toxicity-prediction",
        "builtin-synthetic-accessibility",
        "builtin-molecular-dynamics",
        "builtin-interaction-analysis",
    }

    assert not (placeholder_slugs & set(AIDD_TOOL_CAPABILITIES))


@pytest.mark.asyncio
async def test_run_builtin_tool_routes_protein_preparation(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "protein.pdb"
    source.write_text("ATOM      1  N   ALA A   1       0.000   0.000   0.000\nEND\n")
    called: dict[str, object] = {}

    def fake_handler(files):
        called["files"] = files
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
    )

    assert "protein_structure@1" in called["files"]


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
