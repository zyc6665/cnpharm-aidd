"""AIDD 规划器扩展能力测试。

覆盖 ADMET、毒性、合成可及性、分子动力学、相互作用分析、数据库查询等
新规划路径。
"""

import pytest

from app.agents.aidd.planner import build_aidd_plan


class TestMoleculeLevelPlanning:
    """分子级别预测规划（smiles_csv / generated_ligand 输入）。"""

    def test_smiles_csv_admet_plan(self):
        plan = build_aidd_plan(
            message="预测这些分子的 ADMET 性质",
            input_type="smiles_csv",
            requested_outputs=["admet_report"],
            params={},
        )
        assert plan.intent == "predict_molecule_properties_from_smiles"
        step_keys = [step.step_key for step in plan.steps]
        assert "admet_prediction" in step_keys
        assert step_keys.index("admet_prediction") >= 0

    def test_smiles_csv_toxicity_and_sa_plan(self):
        plan = build_aidd_plan(
            message="预测毒性和合成可及性",
            input_type="smiles_csv",
            requested_outputs=["toxicity_report", "synthetic_accessibility"],
            params={},
        )
        step_keys = [step.step_key for step in plan.steps]
        assert "toxicity_prediction" in step_keys
        assert "synthetic_accessibility" in step_keys

    def test_generated_ligand_admet_plan_converts_to_smiles(self):
        plan = build_aidd_plan(
            message="ADMET prediction",
            input_type="generated_ligand",
            requested_outputs=["admet_report"],
            params={},
        )
        step_keys = [step.step_key for step in plan.steps]
        assert "sdf_to_smiles" in step_keys
        assert "admet_prediction" in step_keys
        assert step_keys.index("admet_prediction") > step_keys.index("sdf_to_smiles")

    def test_smiles_csv_property_still_works(self):
        plan = build_aidd_plan(
            message="predict properties",
            input_type="smiles_csv",
            requested_outputs=["property_report"],
            params={},
        )
        step_keys = [step.step_key for step in plan.steps]
        assert "property_prediction" in step_keys


class TestProteinComplexPlanning:
    """蛋白/复合物级别预测规划（MD / interaction）。"""

    def test_md_with_protein_and_ligand_pdb(self):
        plan = build_aidd_plan(
            message="run molecular dynamics",
            input_type="protein_pdb",
            requested_outputs=["molecular_dynamics_trajectory"],
            params={"available_inputs": ["protein_pdb", "ligand_pdb"]},
        )
        assert plan.intent == "run_molecular_dynamics"
        step = plan.steps[0]
        assert step.tool_slug == "builtin-molecular-dynamics"
        assert step.inputs["protein_pdb"] == "agent_input:protein_pdb"
        assert step.inputs["ligand_pdb"] == "agent_input:ligand_pdb"

    def test_interaction_with_protein_and_ligand_pdb(self):
        plan = build_aidd_plan(
            message="分析蛋白配体相互作用",
            input_type="protein_pdb",
            requested_outputs=["interaction_report"],
            params={"available_inputs": ["protein_pdb", "ligand_pdb"]},
        )
        assert plan.intent == "analyze_interactions"
        step = plan.steps[0]
        assert step.tool_slug == "builtin-interaction-analysis"


class TestDatabaseQueryPlanning:
    """数据库查询规划路径。"""

    def test_chembl_query_plan(self):
        plan = build_aidd_plan(
            message="查询 ChEMBL 数据库",
            input_type=None,
            requested_outputs=["database_query_result"],
            params={},
        )
        assert plan.intent == "query_chembl"
        assert plan.steps[0].tool_slug == "builtin-query-chembl"

    def test_pubchem_query_plan(self):
        plan = build_aidd_plan(
            message="search pubchem for aspirin",
            input_type=None,
            requested_outputs=["database_query_result"],
            params={},
        )
        assert plan.intent == "query_pubchem"
        assert plan.steps[0].tool_slug == "builtin-query-pubchem"

    def test_pdbbind_query_plan(self):
        plan = build_aidd_plan(
            message="查询 PDBbind 数据",
            input_type=None,
            requested_outputs=["database_query_result"],
            params={},
        )
        assert plan.intent == "query_pdbbind"
        assert plan.steps[0].tool_slug == "builtin-query-pdbbind"


class TestGenerationPathExtensions:
    """默认 generation 路径末尾追加新能力。"""

    def test_protein_generation_appends_admet_toxicity_sa(self):
        plan = build_aidd_plan(
            message="生成分子并预测 ADMET、毒性和合成可及性",
            input_type="protein_pdb",
            requested_outputs=["admet_report", "toxicity_report", "synthetic_accessibility"],
            params={},
        )
        step_keys = [step.step_key for step in plan.steps]
        assert "pocket_prediction" in step_keys
        assert "molecule_generation" in step_keys
        assert "sdf_to_smiles" in step_keys
        assert "admet_prediction" in step_keys
        assert "toxicity_prediction" in step_keys
        assert "synthetic_accessibility" in step_keys
        assert step_keys.index("sdf_to_smiles") < step_keys.index("admet_prediction")

    def test_protein_generation_appends_interaction(self):
        plan = build_aidd_plan(
            message="生成分子并分析相互作用",
            input_type="protein_pdb",
            requested_outputs=["interaction_report"],
            params={},
        )
        step_keys = [step.step_key for step in plan.steps]
        assert "molecule_generation" in step_keys
        assert "sdf_to_ligand_pdb" in step_keys
        assert "interaction_analysis" in step_keys
        assert step_keys.index("sdf_to_ligand_pdb") < step_keys.index("interaction_analysis")


class TestMissingToolError:
    """所需工具未配置时给出明确错误。"""

    def test_unsupported_input_type_raises(self):
        with pytest.raises(ValueError, match="Unsupported AIDD input_type"):
            build_aidd_plan(
                message="do something",
                input_type="unsupported_type",
                requested_outputs=["generated_ligand"],
                params={},
            )
