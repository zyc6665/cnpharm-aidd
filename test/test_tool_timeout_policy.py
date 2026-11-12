"""工具时限策略的守护测试。

三件事必须同时成立，否则「任务跑几小时」这件事在某个环节会悄悄退回一小时：

1. 迁移与 seeding 的 ``TOOL_TIMEOUT_MINUTES`` 一致（迁移负责已有库回填，seeding
   负责新库与启动期同步，两处漂移会让同一个库在两个入口拿到不同时限）。
2. 平台上限（``TASK_TIMEOUT_MAX_SECONDS`` 默认 7 天）之外的时限会被截断并告警，
   而不是把 ``activeDeadlineSeconds`` 写成天文数字。
3. Celery 的 soft/hard time limit 必须大于任何工具时限，否则模型还在算，Celery
   已经先把 worker 掐掉——表现为「任务莫名失败、日志里看不到模型错误」。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import settings  # noqa: E402
from app.services import platform_tool_seeding  # noqa: E402
from app.tasks.resource_profile import build_resource_request  # noqa: E402

VERSIONS_DIR = BACKEND_ROOT / "alembic" / "versions"
MIGRATION = VERSIONS_DIR / "20261112_01_pocket2mol_batch_and_tool_timeouts.py"


def _load_migration():
    spec = importlib.util.spec_from_file_location("_test_tool_timeouts_migration", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_and_seeding_share_the_same_timeout_table() -> None:
    migration = _load_migration()
    assert migration.TOOL_TIMEOUT_MINUTES == platform_tool_seeding.TOOL_TIMEOUT_MINUTES


def test_every_seeded_tool_has_a_timeout() -> None:
    """所有会种进库的模型工具都要在表里登记，否则会退回 60 分钟默认值。"""
    models = platform_tool_seeding._load_head_models()
    missing = sorted(slug for slug in models if slug not in platform_tool_seeding.TOOL_TIMEOUT_MINUTES)
    assert missing == []


def test_long_running_tools_are_not_capped_at_one_hour() -> None:
    minutes = platform_tool_seeding.TOOL_TIMEOUT_MINUTES
    # MD 一次能跑几小时到几天，Pocket2Mol 生成 100 个分子也要接近一小时。
    assert minutes["gromacs-md"] > 60 * 24
    assert minutes["pocket2mol-pocket-ligand-generation"] > 60
    assert min(minutes.values()) >= 60


def test_timeout_is_truncated_to_the_platform_upper_bound() -> None:
    request = build_resource_request(
        {
            "type": "k8s_job",
            "resource_profile": {
                "tier": "gpu",
                "cpu": 4,
                "memory_gb": 16,
                "gpu_required": True,
                "gpu_memory_gb": 8,
                "timeout_minutes": 60 * 24 * 30,
                "parallelism": 1,
            },
        }
    )
    assert request.timeout_sec == settings.TASK_TIMEOUT_MAX_SECONDS


def test_default_timeout_is_untouched_when_below_the_bound() -> None:
    request = build_resource_request(
        {
            "type": "k8s_job",
            "resource_profile": {
                "tier": "gpu",
                "cpu": 4,
                "memory_gb": 16,
                "gpu_required": True,
                "gpu_memory_gb": 8,
                "timeout_minutes": 720,
                "parallelism": 1,
            },
        }
    )
    assert request.timeout_sec == 720 * 60


@pytest.mark.parametrize("limit_name", ["CELERY_TASK_SOFT_TIME_LIMIT", "CELERY_TASK_TIME_LIMIT"])
def test_celery_limits_exceed_every_tool_timeout(limit_name: str) -> None:
    limit = int(getattr(settings, limit_name))
    longest = max(platform_tool_seeding.TOOL_TIMEOUT_MINUTES.values()) * 60
    assert limit > longest
