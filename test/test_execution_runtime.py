"""Runtime registry tests for the managed execution gateway."""

import pytest

from app.execution.service import ExecutionService


def test_execution_runtime_can_be_replaced_for_worker_injection():
    from app.execution import runtime

    runtime.reset_execution_service_for_tests()
    original = runtime.get_execution_service()
    replacement = ExecutionService({"k8s_job": object()})
    try:
        runtime.configure_execution_service(replacement)
        assert runtime.get_execution_service() is replacement
    finally:
        runtime.configure_execution_service(original)


def test_execution_runtime_bootstraps_lazily_once(monkeypatch):
    """API 进程没有 worker 启动信号，第一次取用时必须自己按配置建出网关。"""
    from app.execution import runtime

    calls: list[str] = []
    built = ExecutionService({"k8s_job": object()})

    def fake_build():
        calls.append("build")
        return built

    monkeypatch.setattr(runtime, "_bootstrap_from_settings", fake_build)
    runtime.reset_execution_service_for_tests()
    try:
        assert runtime.get_execution_service() is built
        assert runtime.get_execution_service() is built
        assert calls == ["build"]
    finally:
        runtime.reset_execution_service_for_tests()


def test_execution_runtime_keeps_empty_gateway_when_bootstrap_fails(monkeypatch):
    """构建失败只能是「没有适配器」，不能让取用方连读取都炸。"""
    from app.execution import runtime

    def boom():
        raise RuntimeError("kubeconfig 不存在")

    monkeypatch.setattr(runtime, "_bootstrap_from_settings", boom)
    runtime.reset_execution_service_for_tests()
    try:
        service = runtime.get_execution_service()
        assert isinstance(service, ExecutionService)
        with pytest.raises(Exception):
            # 空网关在真正调用适配器时才报「不支持的执行器类型」
            service._adapter("k8s_job")
    finally:
        runtime.reset_execution_service_for_tests()
