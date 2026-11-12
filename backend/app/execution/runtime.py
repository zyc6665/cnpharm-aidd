"""Process-local execution Gateway registry.

Infrastructure bootstrap code configures provider adapters once per worker
process. Task code only retrieves the stable ``ExecutionService`` boundary.

**每个会用到执行网关的进程都要配置它，不只 worker。** API 进程里也有两条链路
需要适配器：取消任务（``cancel_platform_task`` → ``get_execution_service().cancel``）
与运行期日志同步。以前只有 worker 在启动信号里注册，API 进程拿到的是空表，
表现为「点取消 500 / 日志同步报『不支持的执行器类型: k8s_job』」，而任务其实还
在集群里跑——这类「看起来取消了、实际没取消」的问题比直接报错更难查。
所以这里在第一次取用时按 ``settings`` 惰性构建一次，构建失败就保持空表并只告警一次。
"""

from __future__ import annotations

import logging
from threading import RLock

from app.execution.service import ExecutionService


logger = logging.getLogger(__name__)

_lock = RLock()
_execution_service = ExecutionService({})
_bootstrap_attempted = False


def configure_execution_service(service: ExecutionService) -> None:
    """Replace the process-local Gateway used by task workers."""
    if not isinstance(service, ExecutionService):
        raise TypeError("execution service must be an ExecutionService")
    global _execution_service, _bootstrap_attempted
    with _lock:
        _execution_service = service
        _bootstrap_attempted = True


def _bootstrap_from_settings() -> ExecutionService | None:
    """按配置构建一次托管执行网关；不可用时返回 ``None``。"""
    from app.config import settings
    from app.execution.transports.kubernetes_runtime import build_kubernetes_runtime

    runtime = build_kubernetes_runtime(settings)
    if runtime is None:
        return None
    return runtime.service


def get_execution_service() -> ExecutionService:
    """Return the currently configured execution Gateway, bootstrapping once."""
    global _execution_service, _bootstrap_attempted
    with _lock:
        if _bootstrap_attempted:
            return _execution_service
        _bootstrap_attempted = True
        try:
            service = _bootstrap_from_settings()
        except Exception as exc:  # noqa: BLE001 - 构建失败不能拖垮取用方
            logger.warning("执行网关按配置构建失败，本进程将没有可用适配器：%s", exc)
            return _execution_service
        if service is not None:
            _execution_service = service
        return _execution_service


def reset_execution_service_for_tests() -> None:
    """测试用：清回未配置状态，下一次取用会重新按配置构建。"""
    global _execution_service, _bootstrap_attempted
    with _lock:
        _execution_service = ExecutionService({})
        _bootstrap_attempted = False
