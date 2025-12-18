# backend/app/logging/config.py
"""日志配置模块

根据详细设计说明书 9.1 节实现。
负责日志系统的配置和初始化。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import json
import logging
import logging.handlers
import os
import sys


@dataclass
class LogConfig:
    """日志配置"""
    level: str = "INFO"
    format: str = "json"                    # json 或 text
    output: str = "console"                 # console, file, both
    log_dir: str = "logs"
    max_bytes: int = 10 * 1024 * 1024       # 10MB
    backup_count: int = 5
    enable_colors: bool = True
    include_hostname: bool = True
    app_name: str = "sciminer"
    environment: str = "development"


class CustomJsonFormatter(logging.Formatter):
    """自定义JSON日志格式化器

    输出结构化的JSON日志，便于日志收集和分析。
    """

    def __init__(
        self,
        app_name: str = "sciminer",
        environment: str = "development",
        include_hostname: bool = True
    ):
        super().__init__()
        self.app_name = app_name
        self.environment = environment
        self.include_hostname = include_hostname

        if include_hostname:
            import socket
            self.hostname = socket.gethostname()
        else:
            self.hostname = None

    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录"""
        log_data = {
            "@timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "app": self.app_name,
            "environment": self.environment
        }

        # 添加主机名
        if self.hostname:
            log_data["hostname"] = self.hostname

        # 添加位置信息
        log_data["location"] = {
            "file": record.filename,
            "line": record.lineno,
            "function": record.funcName
        }

        # 添加异常信息
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # 添加额外字段
        if hasattr(record, "__dict__"):
            extra_fields = {}
            for key, value in record.__dict__.items():
                if key not in (
                    "name", "msg", "args", "created", "filename", "funcName",
                    "levelname", "levelno", "lineno", "module", "msecs",
                    "pathname", "process", "processName", "relativeCreated",
                    "stack_info", "exc_info", "exc_text", "thread", "threadName",
                    "message"
                ):
                    try:
                        json.dumps(value)  # 确保可序列化
                        extra_fields[key] = value
                    except (TypeError, ValueError):
                        extra_fields[key] = str(value)

            if extra_fields:
                log_data["extra"] = extra_fields

        return json.dumps(log_data, ensure_ascii=False)


class ColoredFormatter(logging.Formatter):
    """带颜色的文本日志格式化器"""

    COLORS = {
        "DEBUG": "\033[36m",      # Cyan
        "INFO": "\033[32m",       # Green
        "WARNING": "\033[33m",    # Yellow
        "ERROR": "\033[31m",      # Red
        "CRITICAL": "\033[35m",   # Magenta
    }
    RESET = "\033[0m"

    def __init__(self, fmt: Optional[str] = None, enable_colors: bool = True):
        if fmt is None:
            fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        super().__init__(fmt)
        self.enable_colors = enable_colors

    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录"""
        if self.enable_colors and record.levelname in self.COLORS:
            record.levelname = (
                f"{self.COLORS[record.levelname]}{record.levelname}{self.RESET}"
            )
        return super().format(record)


def setup_logging(config: Optional[LogConfig] = None) -> None:
    """配置日志系统

    Args:
        config: 日志配置
    """
    if config is None:
        config = LogConfig()

    # 获取根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.level.upper()))

    # 清除现有处理器
    root_logger.handlers.clear()

    # 创建格式化器
    if config.format == "json":
        formatter = CustomJsonFormatter(
            app_name=config.app_name,
            environment=config.environment,
            include_hostname=config.include_hostname
        )
    else:
        formatter = ColoredFormatter(enable_colors=config.enable_colors)

    # 控制台处理器
    if config.output in ("console", "both"):
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # 文件处理器
    if config.output in ("file", "both"):
        os.makedirs(config.log_dir, exist_ok=True)
        log_file = os.path.join(config.log_dir, f"{config.app_name}.log")

        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=config.max_bytes,
            backupCount=config.backup_count
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # 设置第三方库日志级别
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("celery").setLevel(logging.INFO)

    root_logger.info(
        f"Logging configured: level={config.level}, format={config.format}, output={config.output}"
    )


def setup_logging_from_env() -> None:
    """从环境变量配置日志"""
    config = LogConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format=os.getenv("LOG_FORMAT", "json"),
        output=os.getenv("LOG_OUTPUT", "console"),
        log_dir=os.getenv("LOG_DIR", "logs"),
        app_name=os.getenv("APP_NAME", "sciminer"),
        environment=os.getenv("ENVIRONMENT", "development")
    )
    setup_logging(config)


# 日志级别配置
LOG_LEVELS = {
    "development": logging.DEBUG,
    "testing": logging.INFO,
    "staging": logging.INFO,
    "production": logging.WARNING
}


def get_log_level_for_environment(environment: str) -> int:
    """根据环境获取日志级别"""
    return LOG_LEVELS.get(environment, logging.INFO)
