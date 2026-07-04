from types import SimpleNamespace

from app.tools.version_manager import ToolVersionManager


def test_version_manager_uses_cache_backend_factory(monkeypatch):
    """版本管理器应使用真实缓存工厂函数初始化缓存。"""
    cache = object()

    monkeypatch.setattr(
        "app.cache.factory.get_cache_backend",
        lambda: cache,
    )

    manager = ToolVersionManager(db=SimpleNamespace())

    assert manager.cache is cache


def test_version_manager_logs_cache_factory_failure_once(monkeypatch, caplog):
    """缓存初始化失败时应一次性告警，而不是静默降级。"""
    def raise_cache_error():
        raise RuntimeError("cache unavailable")

    monkeypatch.setattr("app.cache.factory.get_cache_backend", raise_cache_error)
    manager = ToolVersionManager(db=SimpleNamespace())

    with caplog.at_level("WARNING", logger="app.tools.version_manager"):
        assert manager.cache is None
        assert manager.cache is None

    warnings = [
        record
        for record in caplog.records
        if "Tool version cache is unavailable" in record.message
    ]
    assert len(warnings) == 1
