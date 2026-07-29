from pathlib import Path


def test_production_requirements_exclude_development_tools():
    requirements = Path("backend/requirements.txt").read_text(encoding="utf-8")

    for package in ("watchfiles", "flower", "pytest", "pytest-asyncio"):
        assert package not in requirements


def test_dockerfile_installs_profile_specific_requirements():
    dockerfile = Path("backend/Dockerfile").read_text(encoding="utf-8")

    assert "-r requirements-dev.txt" in dockerfile
    assert "--find-links=/wheels -r requirements.txt" in dockerfile
