"""Swagger/ReDoc/OpenAPI 暴露面与安全响应头测试。"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import create_app


def _configure(monkeypatch, *, environment: str, docs: bool | None, allowed_hosts):
    monkeypatch.setattr(settings, "ENVIRONMENT", environment, raising=False)
    monkeypatch.setattr(settings, "ENABLE_DOCS", docs, raising=False)
    monkeypatch.setattr(settings, "ALLOWED_HOSTS", allowed_hosts, raising=False)


@pytest.mark.asyncio
async def test_production_disables_docs_endpoints(monkeypatch):
    """生产配置下 /docs、/redoc、/openapi.json 均应 404。"""
    _configure(
        monkeypatch,
        environment="production",
        docs=None,
        allowed_hosts=["testserver"],
    )
    application = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="https://testserver"
    ) as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            response = await client.get(path)
            assert response.status_code == 404, path


@pytest.mark.asyncio
async def test_development_exposes_docs_endpoints(monkeypatch):
    """开发配置下 /docs 与 /openapi.json 应可访问。"""
    _configure(
        monkeypatch,
        environment="development",
        docs=None,
        allowed_hosts=["*"],
    )
    application = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://testserver"
    ) as client:
        docs = await client.get("/docs")
        redoc = await client.get("/redoc")
        openapi = await client.get("/openapi.json")

    assert docs.status_code == 200
    assert redoc.status_code == 200
    assert openapi.status_code == 200
    assert openapi.json()["info"]["title"] == settings.APP_NAME


@pytest.mark.asyncio
async def test_enable_docs_can_override_production_default(monkeypatch):
    """显式 ENABLE_DOCS=true 时生产也可开放（供内网受控场景）。"""
    _configure(
        monkeypatch,
        environment="production",
        docs=True,
        allowed_hosts=["testserver"],
    )
    application = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="https://testserver"
    ) as client:
        assert (await client.get("/docs")).status_code == 200


@pytest.mark.asyncio
async def test_security_headers_add_hsts_only_for_production_https(monkeypatch):
    """HSTS 只应在生产且请求已 HTTPS 时下发。"""
    _configure(
        monkeypatch,
        environment="production",
        docs=False,
        allowed_hosts=["testserver"],
    )
    application = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="https://testserver"
    ) as client:
        https_response = await client.get("/health")

    assert https_response.headers["X-Content-Type-Options"] == "nosniff"
    assert "Strict-Transport-Security" in https_response.headers


@pytest.mark.asyncio
async def test_security_headers_trust_forwarded_proto_for_hsts(monkeypatch):
    """反向代理终止 TLS 时，按 X-Forwarded-Proto 判定 HTTPS。"""
    _configure(
        monkeypatch,
        environment="production",
        docs=False,
        allowed_hosts=["testserver"],
    )
    application = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/health", headers={"X-Forwarded-Proto": "https"}
        )

    assert "Strict-Transport-Security" in response.headers


@pytest.mark.asyncio
async def test_https_redirect_respects_forwarded_proto(monkeypatch):
    """启用强制 HTTPS 时，已由代理加密的请求不应再被重定向。"""
    _configure(
        monkeypatch,
        environment="production",
        docs=False,
        allowed_hosts=["testserver"],
    )
    monkeypatch.setattr(settings, "ENFORCE_HTTPS", True, raising=False)
    application = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://testserver"
    ) as client:
        proxied = await client.get(
            "/health", headers={"X-Forwarded-Proto": "https"}
        )
        plain = await client.get("/", follow_redirects=False)

    assert proxied.status_code == 200
    assert plain.status_code == 307
    assert plain.headers["location"].startswith("https://")
