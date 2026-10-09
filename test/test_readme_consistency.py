from pathlib import Path


def test_readme_matches_current_platform_entrypoints():
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "游客模式" not in readme
    assert "`v1.0-7.28`" in readme
    assert "http://localhost:8000/api/v1/system/health" in readme
    assert "├── frontend/" in readme
    assert "├── test/" in readme
    assert "├── .github/workflows/" in readme
    assert "├── deploy/compose/docker-compose.prod.yml" in readme
    assert "pip install -r requirements-dev.txt" in readme
    assert "docker compose -f deploy/compose/docker-compose.prod.yml up -d --build" in readme
    assert "- [ ] Docker部署配置" not in readme
    assert "**最后更新**：2026-07-29" in readme
