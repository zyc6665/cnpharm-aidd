from pathlib import Path


def test_readme_matches_current_platform_entrypoints():
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "游客模式" not in readme
    assert "`v1.0-7.28`" in readme
    assert "http://localhost:8000/api/v1/system/health" in readme
    assert "├── frontend/" in readme
    assert "├── test/" in readme
