"""主应用入口日志规范测试。"""

from pathlib import Path


def test_main_uses_logger_instead_of_print() -> None:
    """入口文件生命周期事件应进入统一日志系统。"""
    source = Path("backend/app/main.py").read_text(encoding="utf-8")

    assert "print(" not in source
    assert "logger.info(\"数据库初始化完成\")" in source
    assert "logger.info(\"应用关闭\")" in source
