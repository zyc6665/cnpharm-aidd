from pathlib import Path

import yaml


def test_backend_development_dependencies_pin_flake8():
    requirements = Path("backend/requirements-dev.txt").read_text(encoding="utf-8").splitlines()

    assert "flake8==7.1.1" in requirements


def test_backend_ci_installs_development_dependencies_and_checks_unused_imports():
    workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["backend-test"]["steps"]
    commands = [step.get("run", "") for step in steps]

    assert any("pip install -r backend/requirements-dev.txt" in command for command in commands)
    assert any("python -m flake8 backend/app --select F401" in command for command in commands)
