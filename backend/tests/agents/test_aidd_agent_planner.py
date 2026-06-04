import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.agents.aidd.planner import infer_aidd_input_type
from app.schemas.agent import AIDDRunCreate


def test_agent_run_create_allows_agent_to_infer_input_type():
    run_data = AIDDRunCreate(
        message="上传蛋白后进行口袋探索，并生成候选分子",
        input_file_id="file-1",
    )

    assert run_data.input_type is None


def test_infer_input_type_prefers_uploaded_protein_context_over_goal_words():
    assert (
        infer_aidd_input_type(
            message="上传蛋白后进行口袋探索，并生成候选分子",
            filename="target_structure.pdb",
        )
        == "protein_pdb"
    )


def test_infer_input_type_detects_uploaded_pocket_from_file_context():
    assert (
        infer_aidd_input_type(
            message="基于上传的口袋结构生成候选分子",
            filename="3rfm_a2a-pocket10.pdb",
        )
        == "pocket_pdb"
    )
