from pathlib import Path


def test_workflow_service_modules_exist():
    root = Path(__file__).resolve().parents[1] / "backend" / "app" / "services"
    expected = [
        "workflow_artifacts.py",
        "workflow_cancellation.py",
        "workflow_condition_scheduler.py",
        "workflow_conditions.py",
        "workflow_dependencies.py",
        "workflow_inputs.py",
        "workflow_loop_convergence.py",
        "workflow_loop_scheduler.py",
        "workflow_map_items.py",
        "workflow_map_scheduler.py",
        "workflow_node_states.py",
        "workflow_reconciliation.py",
        "workflow_run_access.py",
        "workflow_run_failures.py",
        "workflow_run_materialization.py",
        "workflow_run_queries.py",
        "workflow_runs.py",
        "workflow_scheduler.py",
        "workflow_skip.py",
        "workflow_task_lookup.py",
        "workflow_tool_lookup.py",
        "workflow_tool_scheduler.py",
        "workflow_task_outputs.py",
        "workflow_validation.py",
        "run_preparation.py",
    ]

    for name in expected:
        assert (root / name).exists(), name
