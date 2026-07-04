"""兼容入口：工具导入配置校验实现已迁移到 backend/app/services。"""

from __future__ import annotations

import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.tool_import_config import *  # noqa: F401,F403
