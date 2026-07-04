"""主应用入口日志规范测试。"""

import logging
from types import SimpleNamespace

import pytest

from app.main import general_exception_handler

from pathlib import Path


def test_main_uses_logger_instead_of_print() -> None:
    """入口文件生命周期事件应进入统一日志系统。"""
    source = Path("backend/app/main.py").read_text(encoding="utf-8")

    assert "print(" not in source
    assert "logger.info(\"数据库初始化完成\")" in source
    assert "logger.info(\"应用关闭\")" in source


@pytest.mark.asyncio
async def test_general_exception_handler_logs_request_context(caplog) -> None:
    """未知异常返回 500 的同时应记录请求上下文。"""
    request = SimpleNamespace(
        method="GET",
        url=SimpleNamespace(path="/api/v1/tools"),
    )

    with caplog.at_level(logging.ERROR, logger="app.main"):
        response = await general_exception_handler(request, RuntimeError("boom"))

    assert response.status_code == 500
    assert "Unhandled API exception: GET /api/v1/tools" in caplog.text
    assert "RuntimeError: boom" in caplog.text
