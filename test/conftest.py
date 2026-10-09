"""测试导入路径初始化。"""

from __future__ import annotations

import sys
import os
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"

# Tests must never inherit the developer's persistent service endpoints.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("STORAGE_BACKEND", "local")
os.environ.setdefault("CACHE_BACKEND", "memory")
os.environ.setdefault("TASK_EXECUTION_BACKEND", "direct")
os.environ.setdefault("CELERY_BROKER_URL", "")
os.environ.setdefault("CELERY_RESULT_BACKEND", "")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@pytest.fixture(autouse=True)
def reset_in_memory_rate_limit_cache():
    """隔离主应用的进程级内存限流状态，避免测试相互影响。"""
    from app.cache import get_cache
    from app.cache.memory import MemoryCacheBackend

    cache = get_cache()
    if isinstance(cache, MemoryCacheBackend):
        cache._cache.clear()

    yield

    if isinstance(cache, MemoryCacheBackend):
        cache._cache.clear()
