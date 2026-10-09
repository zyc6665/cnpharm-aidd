"""Deployment hardening contract tests."""

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


def test_compose_backend_healthcheck_uses_system_health_endpoint() -> None:
    """Compose 后端健康检查应使用真实存在的系统健康端点。"""
    compose_source = (ROOT_DIR / "deploy/compose/docker-compose.dev.yml").read_text(encoding="utf-8")

    assert "http://localhost:8000/api/v1/system/health" in compose_source
    assert "http://localhost:8000/api/v1/health" not in compose_source


def test_production_dockerfile_runs_as_non_root_user() -> None:
    """生产镜像应使用非 root 用户运行应用。"""
    dockerfile_source = (ROOT_DIR / "backend/Dockerfile").read_text(encoding="utf-8")
    production_stage = dockerfile_source.split("FROM python:3.11-slim AS production", 1)[1]

    assert "USER scitool" in production_stage
