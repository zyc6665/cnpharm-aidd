"""同步入口调用 async coroutine 的兼容运行工具。"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar, cast


T = TypeVar("T")


def run_coro_sync(coro: Coroutine[Any, Any, T]) -> T:
    """运行 coroutine；若当前线程已有事件循环，则转到独立线程执行。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: T | None = None
    error: BaseException | None = None

    def _runner() -> None:
        nonlocal result, error
        try:
            result = asyncio.run(coro)
        except BaseException as exc:
            error = exc

    thread = threading.Thread(target=_runner, name="async-runtime-runner")
    thread.start()
    thread.join()

    if error is not None:
        raise error
    return cast(T, result)
