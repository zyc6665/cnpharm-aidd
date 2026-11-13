"""Celery Worker 可用性探测。

背景：`CELERY_BROKER_URL` 一旦配置，任务走「入队 + Worker 消费」的异步路径。
入队本身是**盲写**——Broker 收下消息就算成功，不管有没有 Worker 在消费。
于是最常见的部署事故是：`CELERY_BROKER_URL` 配了、Worker 没起（或起的 Worker
没有订阅任务被路由到的队列），任务永远停在「排队中」，**日志里一句报错都没有**。
链路上的每一环都正常工作，只是没人拿货。

因此平台需要在两个时机主动问一次「有没有 Worker」：

1. 派发任务前（`app/tasks/service.py::dispatch_tool_task`）——没有 Worker 时把
   `dispatch.worker_available=False` 写进任务的 `extra_data.dispatch`，并打一条
   warning。任务仍然入队（Broker 里的消息会在 Worker 起来后被消费，丢掉反而更糟），
   但「为什么一直排队」从此有据可查。
2. 健康检查（`app/api/v1/system.py::_check_celery`）——返回 degraded，让部署脚本
   与监控能看见。

关于探测本身的两个约束，务必保留：

* **`inspect()` 是广播 + 等等回包**，每次调用有固定开销，所以结果做短时缓存
  （`CELERY_WORKER_PROBE_CACHE_SECONDS`），避免每次提交任务都付一次。
  **但「没探测到 Worker」不缓存**：Worker 刚起、正在重启时把 negative 结果缓存住，
  `/health` 会在一段时间里持续显示 degraded，而 Worker 其实已经就绪（#112）。
* **外层 `wait_for` 的预算必须比 `inspect(timeout)` 宽**：`control.inspect(timeout=T)`
  本身就至少要等 T 秒（广播 + 收回复），再叠加连 broker、序列化、线程调度，实测是
  `T + 0.3~0.4s`；Worker 冷启动时线程里首次 import celery 生态还要再加 ~1.7s。
  以前只给了 `T + 1.0`，默认 `T=2.0` 时预算 3.0s < 实测 3.30s，**必然超时误报**。
  现在是 `T * 1.5 + 2.0`（T=2 → 5.0s）。
* **`--pool=solo` 下探测会失真**：单线程 Worker 在执行长任务时无法回应控制通道，
  会被判成「没有 Worker」。本地/生产都应当用 `prefork`（Linux）或 `threads`
  （Windows）池。这一条已写进 `docs/internal/17` 的部署前置条件。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkerAvailability:
    """一次 Worker 探测的结果。"""

    configured: bool
    workers: tuple[str, ...]
    checked_at: float

    @property
    def available(self) -> bool:
        return bool(self.workers)

    def describe(self) -> str:
        if not self.configured:
            return "未配置 Celery Broker（进程内 direct 执行）"
        if not self.workers:
            return "Celery Broker 已配置，但没有 Worker 响应"
        return f"Celery Worker 在线: {', '.join(self.workers)}"


_cached: WorkerAvailability | None = None
_lock = asyncio.Lock()


def _ping_workers_sync(timeout: float) -> tuple[str, ...]:
    from app.worker.celery_app import celery_app

    inspector = celery_app.control.inspect(timeout=timeout)
    if inspector is None:
        return ()
    replies = inspector.ping() or {}
    return tuple(sorted(str(name) for name in replies))


def _effective_broker_url() -> str:
    """返回实际生效的 Broker 地址。

    `settings.CELERY_BROKER_URL` 是唯一正规配置入口，但 Celery 也允许在
    `celery_app.conf` 里程序化设置（测试替身、嵌入式部署都用这条路）。
    两者都为空才算「没配 Broker」。
    """
    configured = str(getattr(settings, "CELERY_BROKER_URL", "") or "")
    if configured:
        return configured
    from app.worker.celery_app import celery_app

    return str(celery_app.conf.broker_url or "")


async def probe_workers(*, timeout: float | None = None) -> WorkerAvailability:
    """立即探测一次（不走缓存）。"""

    if not _effective_broker_url():
        return WorkerAvailability(configured=False, workers=(), checked_at=time.monotonic())

    wait_seconds = float(timeout if timeout is not None else settings.CELERY_WORKER_PROBE_TIMEOUT_SECONDS)
    # 预算要覆盖「inspect 自己等满 wait_seconds」+ 连接/序列化/调度 + 冷启动 import。
    # 详细推导见模块 docstring（#112）。
    budget = wait_seconds * 1.5 + 2.0
    try:
        workers = await asyncio.wait_for(
            asyncio.to_thread(_ping_workers_sync, wait_seconds),
            timeout=budget,
        )
    except Exception as exc:  # noqa: BLE001 - 探测失败等价「不可用」，不能影响主流程
        logger.debug("Celery Worker 探测失败（预算 %.1fs）: %s", budget, exc)
        workers = ()
    return WorkerAvailability(
        configured=True, workers=tuple(workers), checked_at=time.monotonic()
    )


async def worker_availability(*, refresh: bool = False) -> WorkerAvailability:
    """带短时缓存的探测结果。

    「探到了 Worker」才写缓存；没探到时清空缓存并直接返回这次的结果。理由：Worker
    刚起或正在重启的窗口里，缓存住 degraded 会让任务派发在 TTL 内一直写
    `worker_available=false`，界面显示「等待 Worker 接单」——而 Worker 其实已经好了
    （#112）。代价只是多探几次，探测本身有 `wait_for` 兜底，不会挂住调用方。
    """

    global _cached
    ttl = float(settings.CELERY_WORKER_PROBE_CACHE_SECONDS)
    async with _lock:
        if not refresh and _cached is not None and (time.monotonic() - _cached.checked_at) < ttl:
            return _cached
        result = await probe_workers()
        _cached = result if result.available else None
        return result


def reset_worker_availability_cache() -> None:
    """清空缓存（测试与「刚启动 Worker 后立刻复查」时使用）。"""

    global _cached
    _cached = None
