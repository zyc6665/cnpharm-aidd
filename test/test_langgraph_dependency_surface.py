from pathlib import Path


def test_backend_declares_langgraph_and_secret_dependencies():
    requirements = Path("backend/requirements.txt").read_text(encoding="utf-8")

    assert "langgraph" in requirements
    assert "cryptography" in requirements
