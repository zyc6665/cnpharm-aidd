from pathlib import Path

import yaml


def test_frontend_exposes_playwright_dependency_install_script():
    package_json = Path("frontend/package.json").read_text(encoding="utf-8")
    install_script = Path("frontend/scripts/install-playwright-deps.sh")

    assert "test:e2e:deps" in package_json
    assert install_script.exists()

    script = install_script.read_text(encoding="utf-8")
    assert "playwright install --with-deps chromium" in script


def test_ci_installs_playwright_system_dependencies_before_e2e():
    workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
    job = workflow["jobs"]["frontend-e2e"]
    commands = [step.get("run", "") for step in job["steps"]]

    assert any("npm run test:e2e:deps" in command for command in commands)
    assert any("npm run test:e2e" in command for command in commands)
