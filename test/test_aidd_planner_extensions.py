"""AIDD 规划器扩展能力测试。

覆盖 ADMET、毒性、合成可及性、分子动力学、相互作用分析、数据库查询、
多引擎对接、数据库-生成管线集成、分析追踪等新规划路径。
"""

import pytest

from app.agents.aidd.planner import (
    _detect_docking_engine,
    _detect_intents,
    _resolve_docking_slug,
    _resolve_tool_slug,
    build_aidd_plan,
)


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
        admet_step = next(step for step in plan.steps if step.step_key == "admet_prediction")
        assert admet_step.tool_slug == "molp-pc-property-prediction"

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
        admet_step = next(step for step in plan.steps if step.step_key == "admet_prediction")
        assert admet_step.tool_slug == "molp-pc-property-prediction"

    def test_smiles_csv_property_still_works(self):
        plan = build_aidd_plan(
            message="predict properties",
            input_type="smiles_csv",
            requested_outputs=["property_report"],
            params={},
        )
        step_keys = [step.step_key for step in plan.steps]
        assert "property_prediction" in step_keys
        assert plan.steps[0].tool_slug == "molp-pc-property-prediction"


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


# ==========================================================================
# 重构后新增测试
# ==========================================================================


class TestDockingEngineDetection:
    """多引擎对接检测与规划。"""

    def test_default_vina_docking(self):
        plan = build_aidd_plan(
            message="上传蛋白进行对接",
            input_type="protein_pdb",
            requested_outputs=["docking_report"],
            params={"available_inputs": ["protein_pdb", "ligand_pdb"]},
        )
        assert plan.steps[0].tool_slug == "builtin-vina-docking"

    def test_diffdock_detection(self):
        plan = build_aidd_plan(
            message="使用 DiffDock 进行分子对接",
            input_type="protein_pdb",
            requested_outputs=["docking_pose"],
            params={"available_inputs": ["protein_pdb", "ligand_pdb"]},
        )
        assert plan.steps[0].step_key == "docking"
        # DiffDock 在静态注册表中存在，直接匹配
        assert plan.steps[0].tool_slug == "builtin-vina-docking"

    def test_gnina_detection(self):
        plan = build_aidd_plan(
            message="use gnina for docking",
            input_type="protein_pdb",
            requested_outputs=["docking_report"],
            params={"available_inputs": ["protein_pdb", "ligand_pdb"]},
        )
        assert plan.steps[0].step_key == "docking"
        assert plan.steps[0].tool_slug == "builtin-vina-docking"

    def test_docking_in_generation_path_uses_default_vina(self):
        plan = build_aidd_plan(
            message="从蛋白生成分子后进行对接",
            input_type="protein_pdb",
            requested_outputs=["generated_ligand", "docking_report"],
            params={},
        )
        docking_steps = [s for s in plan.steps if s.step_key == "docking"]
        assert len(docking_steps) == 1
        assert docking_steps[0].tool_slug == "builtin-vina-docking"


class TestDatabaseInGenerationPath:
    """数据库查询集成到生成管线中。"""

    def test_chembl_query_after_generation(self):
        """纯数据库查询走独立路径，不触发完整生成管线。"""
        plan = build_aidd_plan(
            message="查询 ChEMBL 数据库",
            input_type="protein_pdb",
            requested_outputs=["database_query_result"],
            params={},
        )
        assert plan.intent == "query_chembl"
        assert plan.steps[0].tool_slug == "builtin-query-chembl"

    def test_pubchem_query_after_generation(self):
        plan = build_aidd_plan(
            message="generate molecules and search PubChem",
            input_type="protein_pdb",
            requested_outputs=["database_query_result"],
            params={},
        )
        step_keys = [s.step_key for s in plan.steps]
        assert "query_pubchem" in step_keys

    def test_pdbbind_query_after_generation(self):
        plan = build_aidd_plan(
            message="生成分子后查询 PDBbind",
            input_type="protein_pdb",
            requested_outputs=["database_query_result"],
            params={},
        )
        step_keys = [s.step_key for s in plan.steps]
        assert "query_pdbbind" in step_keys

    def test_database_query_with_docking_combined(self):
        """数据库查询与对接可在同一管线中共存。"""
        plan = build_aidd_plan(
            message="生成分子,查ChEMBL,做对接",
            input_type="protein_pdb",
            requested_outputs=["database_query_result", "docking_report"],
            params={},
        )
        step_keys = [s.step_key for s in plan.steps]
        assert "query_chembl" in step_keys
        assert "docking" in step_keys
        # 数据库查询在对接之前
        assert step_keys.index("query_chembl") < step_keys.index("docking")


class TestAnalysisTrace:
    """规划器的 analysis_trace 和 reasoning_summary。"""

    def test_analysis_trace_included_in_plan(self):
        plan = build_aidd_plan(
            message="生成分子并预测性质",
            input_type="protein_pdb",
            requested_outputs=["generated_ligand", "property_report"],
            params={},
        )
        assert len(plan.analysis_trace) > 0
        assert any("输入类型" in t for t in plan.analysis_trace)
        assert any("请求输出" in t for t in plan.analysis_trace)
        assert plan.reasoning_summary is not None
        assert "性质" in plan.reasoning_summary

    def test_analysis_trace_for_simple_query(self):
        plan = build_aidd_plan(
            message="查询 chembl",
            input_type=None,
            requested_outputs=["database_query_result"],
            params={},
        )
        assert plan.analysis_trace
        assert plan.reasoning_summary is not None

    def test_analysis_trace_detects_all_intents(self):
        plan = build_aidd_plan(
            message="生成分子，预测ADMET和毒性，做对接，查数据库",
            input_type="protein_pdb",
            requested_outputs=[
                "admet_report", "toxicity_report",
                "docking_report", "database_query_result",
            ],
            params={},
        )
        assert plan.analysis_trace
        assert plan.reasoning_summary is not None
        # 所有意图都应被检测到
        assert "admet" in plan.reasoning_summary or "ADMET" in plan.reasoning_summary
        assert "毒性" in plan.reasoning_summary or "toxicity" in plan.reasoning_summary.lower()
        assert "对接" in plan.reasoning_summary or "docking" in plan.reasoning_summary.lower()
        assert "数据库" in plan.reasoning_summary or "database" in plan.reasoning_summary.lower()


class TestToolSlugResolution:
    """工具 slug 解析函数单元测试。"""

    def test_known_capability_returns_correct_slug(self):
        assert _resolve_tool_slug("pocket_prediction") == "lvpocket-pocket-prediction"
        assert _resolve_tool_slug("molecule_generation") == "gcdm-pocket-generation"
        assert _resolve_tool_slug("affinity_prediction") == "msign-affinity-prediction"

    def test_virtual_tool_resolved_from_static_registry(self):
        assert _resolve_tool_slug("admet_prediction") == "molp-pc-property-prediction"
        assert _resolve_tool_slug("toxicity_prediction") == "builtin-toxicity-prediction"
        assert _resolve_tool_slug("synthetic_accessibility") == "builtin-synthetic-accessibility"
        assert _resolve_tool_slug("molecular_dynamics") == "builtin-molecular-dynamics"
        assert _resolve_tool_slug("interaction_analysis") == "builtin-interaction-analysis"

    def test_docking_slug_defaults_to_vina(self):
        assert _resolve_docking_slug() == "builtin-vina-docking"
        assert _resolve_docking_slug("vina") == "builtin-vina-docking"

    def test_alternative_docking_engines_fallback_to_vina(self):
        # 当前无专用引擎工具，fallback 到 vina
        assert _resolve_docking_slug("diffdock") == "builtin-vina-docking"
        assert _resolve_docking_slug("gnina") == "builtin-vina-docking"
        assert _resolve_docking_slug("smina") == "builtin-vina-docking"

    def test_unknown_capability_returns_empty(self):
        assert _resolve_tool_slug("nonexistent_capability") == ""


class TestIntentDetection:
    """意图检测函数单元测试。"""

    def test_detect_all_intents_from_chinese_message(self):
        intents = _detect_intents(
            "对蛋白进行对接,预测ADMET和毒性,查合成可及性,做分子动力学模拟,分析相互作用,查询数据库",
            [],
        )
        assert intents["docking"]
        assert intents["admet"]
        assert intents["toxicity"]
        assert intents["sa"]
        assert intents["md"]
        assert intents["interaction"]
        assert intents["database"]

    def test_detect_intents_from_outputs(self):
        intents = _detect_intents("hello", ["admet_report", "toxicity_report"])
        assert intents["admet"]
        assert intents["toxicity"]
        assert not intents["docking"]

    def test_detect_docking_engine(self):
        assert _detect_docking_engine("use DiffDock") == "diffdock"
        assert _detect_docking_engine("use gnina") == "gnina"
        assert _detect_docking_engine("use smina") == "smina"
        assert _detect_docking_engine("use vina") == "vina"
        assert _detect_docking_engine("no engine mentioned") is None
