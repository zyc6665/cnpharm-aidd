"""服务配置。"""

from __future__ import annotations

import os
from pathlib import Path


class Settings:
    """模板服务运行配置。"""

    def __init__(self) -> None:
        self.app_name = os.getenv("APP_NAME", "Remote API Tool Template")
        self.app_version = os.getenv("APP_VERSION", "0.1.0")
        self.host = os.getenv("HOST", "0.0.0.0")
        self.port = int(os.getenv("PORT", "8000"))
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.model_dir = Path(os.getenv("MODEL_DIR", "/app/model"))
        self.work_dir = Path(os.getenv("WORK_DIR", "/tmp/remote-api-tool-template"))


settings = Settings()
