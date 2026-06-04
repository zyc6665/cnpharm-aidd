import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.aidd.graph import build_aidd_graph
from app.agents.aidd.graph_nodes import (
    classify_input_node,
    discover_tools_node,
    route_after_replan,
    validate_plan_node,
)


def test_classify_input_node_uses_uploaded_file_context():
    state = classify_input_node(
        {
            "message": "上传蛋白后进行口袋探索",
            "input_file_id": "file-1",
            "input_filename": "protein.pdb",
        }
    )

    assert state["input_type"] == "protein_pdb"
    assert state["semantic_inputs"]["protein_pdb"]["source"] == "agent_input"


def test_discover_tools_filters_configured_slugs():
    state = discover_tools_node(
        {
            "configured_tool_slugs": [
                "lvpocket-pocket-prediction",
                "not-a-capability",
            ]
        }
    )

    assert [tool["tool_slug"] for tool in state["available_tools"]] == [
        "lvpocket-pocket-prediction"
    ]


def test_validate_plan_node_parses_model_output():
    state = validate_plan_node(
        {
            "available_tools": [
                {
                    "tool_slug": "gcdm-pocket-generation",
                    "capability": "molecule_generation",
                    "inputs": ["pocket_pdb"],
                    "outputs": ["generated_ligand"],
                }
            ],
            "raw_plan": """
            {
              "intent": "generate_molecules_from_pocket",
              "steps": [
                {
                  "step_key": "molecule_generation",
                  "capability": "molecule_generation",
                  "tool_slug": "gcdm-pocket-generation",
                  "inputs": {"pocket_pdb": "agent_input"},
                  "params": {}
                }
              ]
            }
            """,
        }
    )

    assert state["plan"]["intent"] == "generate_molecules_from_pocket"
    assert state["status"] == "planned"


def test_route_after_replan_maps_terminal_and_waiting_states():
    assert route_after_replan({"status": "waiting_task"}) == "waiting_task"
    assert route_after_replan({"status": "success"}) == "success"
    assert route_after_replan({"status": "failure"}) == "failure"
    assert route_after_replan({"status": "planned"}) == "execute_step"


def test_build_aidd_graph_compiles_langgraph_state_graph():
    graph = build_aidd_graph()

    assert hasattr(graph, "ainvoke")
