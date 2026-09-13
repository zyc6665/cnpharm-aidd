from pathlib import Path


def test_workflow_service_modules_exist():
    root = Path(__file__).resolve().parents[1] / "backend" / "app" / "services"
    expected = [
        "workflow_validation.py",
        "workflow_conditions.py",
        "workflow_loop_convergence.py",
        "workflow_map_items.py",
        "workflow_runs.py",
        "workflow_scheduler.py",
        "workflow_skip.py",
        "workflow_artifacts.py",
        "run_preparation.py",
    ]

    for name in expected:
        assert (root / name).exists(), name
