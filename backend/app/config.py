# backend/app/config.py
"""应用配置管理"""

import ipaddress
import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional, List, Literal
from urllib.parse import urlparse

from dotenv import load_dotenv
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[1]
_DNS_LABEL_PATTERN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
_IPV4_NUMERIC_HOST_PATTERN = re.compile(
    r"(?:0x[0-9a-f]+|0[0-7]*|[1-9][0-9]*)(?:\.(?:0x[0-9a-f]+|0[0-7]*|[1-9][0-9]*)){0,3}"
)
_AIDD_FEATURE_FLAG_DESCRIPTIONS = {
    "AIDD_PROJECT_WORKSPACE_ENABLED": "项目优先研究工作台入口",
    "AIDD_PROJECT_CONVERSATIONS_ENABLED": "项目研究对话与 Agent 审批链路",
    "TOOL_PACKAGE_V1_ENABLED": "Tool Package v1 导入、迁移和验证等级",
    "PROJECT_RESEARCH_BOARD_ENABLED": "项目级整页科研白板",
    "LEGACY_AIDD_API_ENABLED": "旧 AIDD API 已下线",
}


def _is_valid_deployment_cors_origin(origin: str) -> bool:
    """验证预发布和生产环境允许的 HTTPS Origin。"""
    if (
        origin != origin.strip()
        or origin != origin.lower()
        or "*" in origin
        or "%" in origin
    ):
        return False

    try:
        parsed_origin = urlparse(origin)
        port = parsed_origin.port
    except ValueError:
        return False

    hostname = parsed_origin.hostname
    if (
        parsed_origin.scheme != "https"
        or not hostname
        or parsed_origin.username
        or parsed_origin.password
        or parsed_origin.path
        or parsed_origin.params
        or parsed_origin.query
        or parsed_origin.fragment
        or parsed_origin.netloc.endswith(":")
        or port == 443
        or (port is not None and not 1 <= port <= 65535)
        or (port is not None and parsed_origin.netloc.rsplit(":", 1)[-1] != str(port))
    ):
        return False

    try:
        ip_address = ipaddress.ip_address(hostname)
    except ValueError:
        if _IPV4_NUMERIC_HOST_PATTERN.fullmatch(hostname):
            return False
        return len(hostname) <= 253 and all(
            _DNS_LABEL_PATTERN.fullmatch(label) for label in hostname.split(".")
        )

    canonical_host = (
        f"[{ip_address.compressed}]"
        if ip_address.version == 6
        else ip_address.compressed
    )
    canonical_netloc = (
        f"{canonical_host}:{port}" if port is not None else canonical_host
    )
    return parsed_origin.netloc == canonical_netloc


def bootstrap_process_env(env_file: str = ".env") -> bool:
    """将 .env 中的额外 secret 变量注入当前进程环境。"""
    env_path = Path(env_file)
    if not env_path.exists():
        fallback_path = BACKEND_ROOT / ".env"
        if not fallback_path.exists():
            return False
        env_path = fallback_path

    return load_dotenv(env_path, override=False)


def resolve_database_url(database_url: str) -> str:
    """将相对 SQLite URL 固定到 backend 目录，避免受运行 cwd 影响。"""
    prefixes = (
        "sqlite+aiosqlite:///./",
        "sqlite:///./",
    )
    for prefix in prefixes:
        if not database_url.startswith(prefix):
            continue
        relative_part = database_url[len(prefix) :]
        absolute_path = (BACKEND_ROOT / relative_part).resolve()
        base_prefix = prefix.split("./", 1)[0]
        return f"{base_prefix}{absolute_path}"
    return database_url


bootstrap_process_env()


class Settings(BaseSettings):
    """
    应用配置

    支持通过环境变量或 .env 文件配置。
    生产环境建议使用环境变量覆盖默认值。
    """

    # ==================== 应用基础配置 ====================
    APP_NAME: str = "科学计算工具管理平台"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = True

    # API配置
    API_V1_PREFIX: str = "/api/v1"
    PUBLIC_API_BASE_URL: str = "http://localhost:8000"

    # CORS配置
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://localhost:8585",
        "http://127.0.0.1:8585",
    ]

    # ==================== 数据库配置 ====================
    # 开发环境: sqlite+aiosqlite:///./storage/scitool.db
    # 生产环境: postgresql+asyncpg://user:pass@host:5432/scitool
    DATABASE_URL: str = "sqlite+aiosqlite:///./storage/scitool.db"

    # 连接池配置（PostgreSQL 专用）
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_RECYCLE: int = 3600

    # ==================== JWT配置 ====================
    # 生产/预发布环境必须配置长度不少于 32 的强密钥
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    SETTINGS_ENCRYPTION_KEY: Optional[str] = None

    @model_validator(mode="after")
    def _validate_production_security(self):
        """生产环境强制校验安全关键配置。"""
        if (
            self.ENVIRONMENT in {"staging", "production"}
            and len(self.JWT_SECRET_KEY) < 32
        ):
            raise ValueError(
                f"JWT_SECRET_KEY must be at least 32 characters long in {self.ENVIRONMENT} environment"
            )

        if self.ENVIRONMENT in {"staging", "production"}:
            if not self.SETTINGS_ENCRYPTION_KEY:
                raise ValueError(
                    f"SETTINGS_ENCRYPTION_KEY must be configured in {self.ENVIRONMENT} environment"
                )
            if len(self.SETTINGS_ENCRYPTION_KEY) < 32:
                raise ValueError(
                    f"SETTINGS_ENCRYPTION_KEY must be at least 32 characters long in {self.ENVIRONMENT} environment"
                )
            if self.SETTINGS_ENCRYPTION_KEY == self.JWT_SECRET_KEY:
                raise ValueError(
                    f"SETTINGS_ENCRYPTION_KEY must differ from JWT_SECRET_KEY in {self.ENVIRONMENT} environment"
                )

        if self.ENVIRONMENT in {"staging", "production"}:
            for origin in self.CORS_ORIGINS:
                if not _is_valid_deployment_cors_origin(origin):
                    raise ValueError(
                        f"CORS_ORIGINS must contain only HTTPS origins with a valid hostname "
                        f"in {self.ENVIRONMENT} environment"
                    )

        if self.ENVIRONMENT == "production":
            if self.DEBUG:
                raise ValueError("DEBUG must be disabled in production environment")
            if not self.DATABASE_URL.startswith("postgresql"):
                raise ValueError(
                    "DATABASE_URL must use PostgreSQL in production environment"
                )
            if self.STORAGE_BACKEND != "minio":
                raise ValueError(
                    "STORAGE_BACKEND must be minio in production environment"
                )
            if (
                not self.MINIO_ENDPOINT
                or not self.MINIO_ACCESS_KEY
                or not self.MINIO_SECRET_KEY
            ):
                raise ValueError(
                    "MinIO endpoint and credentials must be configured in production environment"
                )
            if self.CACHE_BACKEND != "redis":
                raise ValueError(
                    "CACHE_BACKEND must be redis in production environment"
                )
            if not self.REDIS_PASSWORD:
                raise ValueError(
                    "REDIS_PASSWORD must be configured in production environment"
                )
            if not self.CELERY_BROKER_URL:
                raise ValueError(
                    "CELERY_BROKER_URL must be configured in production environment"
                )
            if not self.CELERY_RESULT_BACKEND:
                raise ValueError(
                    "CELERY_RESULT_BACKEND must be configured in production environment"
                )
            if self.TASK_EXECUTION_BACKEND != "celery":
                raise ValueError(
                    "TASK_EXECUTION_BACKEND must be celery in production environment"
                )

        return self

    # ==================== 存储配置 ====================
    # 存储后端: local | minio
    STORAGE_BACKEND: Literal["local", "minio"] = "local"

    # 本地存储路径
    STORAGE_PATH: str = "./storage/uploads"

    # MinIO 配置（生产环境）
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = ""
    MINIO_SECRET_KEY: str = ""
    MINIO_BUCKET: str = "scitool-files"
    MINIO_SECURE: bool = False

    # 文件大小限制
    MAX_FILE_SIZE_MB: int = 100

    # ==================== 缓存配置 ====================
    # 缓存后端: memory | redis
    CACHE_BACKEND: Literal["memory", "redis"] = "memory"
    REQUEST_RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_TRUST_PROXY_HEADERS: bool = False

    # Redis 配置（生产环境）
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""

    @property
    def redis_url_with_auth(self) -> str:
        """构建带认证的Redis连接URL"""
        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # ==================== Celery 配置 ====================
    # 为空时使用内存队列（同步执行），生产环境设置为 Redis URL
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None
    CELERY_TIMEZONE: str = "Asia/Shanghai"
    CELERY_TASK_SOFT_TIME_LIMIT: int = 3600  # 1小时软超时
    CELERY_TASK_TIME_LIMIT: int = 7200  # 2小时硬超时
    TASK_EXECUTION_BACKEND: Literal["celery", "direct"] = "celery"
    WORKFLOW_RECONCILE_INTERVAL_SECONDS: int = 5
    WORKFLOW_RECONCILE_BATCH_SIZE: int = 20

    # ==================== Docker 执行器配置 ====================
    # 生产环境默认强制不可变 digest；该列表可进一步收紧为精确允许的镜像引用。
    DOCKER_ALLOWED_IMAGES: List[str] = []
    DOCKER_REQUIRE_IMAGE_DIGEST_IN_DEPLOYMENT: bool = True
    # Python 脚本在预发布/生产环境必须匹配此 SHA-256 信任列表。
    TRUSTED_PYTHON_SCRIPT_SHA256: List[str] = []

    # ==================== AIDD Agent 配置 ====================
    ENABLE_DATABASE_TOOLS: bool = False
    AIDD_SYSTEM_USER_ID: Optional[str] = None
    # 首月 AIDD 发布门禁。None 表示使用环境默认值：开发环境开启新入口，
    # 预发布/生产默认关闭新入口；旧 AIDD API 默认关闭。
    AIDD_PROJECT_WORKSPACE_ENABLED: Optional[bool] = None
    AIDD_PROJECT_CONVERSATIONS_ENABLED: Optional[bool] = None
    TOOL_PACKAGE_V1_ENABLED: Optional[bool] = None
    PROJECT_RESEARCH_BOARD_ENABLED: Optional[bool] = None
    LEGACY_AIDD_API_ENABLED: Optional[bool] = None
    # 生产/预发布灰度账号。全局新入口关闭时，仅这些内部账号可访问。
    AIDD_ROLLOUT_USER_EMAILS: List[str] = []
    AIDD_ROLLOUT_USER_IDS: List[str] = []

    @field_validator("AIDD_ROLLOUT_USER_EMAILS", "AIDD_ROLLOUT_USER_IDS", mode="before")
    @classmethod
    def _parse_rollout_user_list(cls, value):
        """兼容 JSON 数组和逗号分隔环境变量。"""
        if value is None:
            return []
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return json.loads(stripped)
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    def aidd_feature_flags(self) -> list[dict[str, object]]:
        """返回首月 AIDD 发布门禁的解析状态，用于管理员审计。"""
        return [
            {
                "key": key,
                "enabled": self._resolve_aidd_feature_flag(key),
                "source": self._feature_flag_source(key),
                "description": description,
                "rollout": self._feature_flag_rollout(key),
            }
            for key, description in _AIDD_FEATURE_FLAG_DESCRIPTIONS.items()
        ]

    def is_aidd_feature_enabled(self, key: str) -> bool:
        """判断 AIDD 发布门禁是否开启。"""
        if key not in _AIDD_FEATURE_FLAG_DESCRIPTIONS:
            raise ValueError(f"Unknown AIDD feature flag: {key}")
        return self._resolve_aidd_feature_flag(key)

    def is_aidd_feature_enabled_for_user(
        self,
        key: str,
        *,
        user_email: str | None = None,
        user_id: str | None = None,
    ) -> bool:
        """判断用户是否可访问 AIDD 功能，支持生产灰度白名单。"""
        if self.is_aidd_feature_enabled(key):
            return True
        if key == "LEGACY_AIDD_API_ENABLED":
            return False
        return self._is_rollout_user(user_email=user_email, user_id=user_id)

    def _resolve_aidd_feature_flag(self, key: str) -> bool:
        if key == "LEGACY_AIDD_API_ENABLED":
            return False
        configured_value = getattr(self, key)
        if configured_value is not None:
            return bool(configured_value)
        return self.ENVIRONMENT == "development"

    def _feature_flag_source(self, key: str) -> str:
        if key in os.environ:
            return "environment"
        if getattr(self, key) is not None:
            return "configured"
        return "default"

    def _feature_flag_rollout(self, key: str) -> dict[str, object]:
        user_count = len(self._normalized_rollout_user_emails()) + len(
            self._normalized_rollout_user_ids()
        )
        if self._resolve_aidd_feature_flag(key):
            scope = "all"
        elif key == "LEGACY_AIDD_API_ENABLED":
            scope = "closed"
        elif user_count:
            scope = "allowlist"
        else:
            scope = "closed"
        return {"scope": scope, "user_count": user_count}

    def _is_rollout_user(
        self,
        *,
        user_email: str | None,
        user_id: str | None,
    ) -> bool:
        email = (user_email or "").strip().lower()
        normalized_id = (user_id or "").strip()
        return (
            bool(email and email in self._normalized_rollout_user_emails())
            or bool(normalized_id and normalized_id in self._normalized_rollout_user_ids())
        )

    def _normalized_rollout_user_emails(self) -> set[str]:
        return {
            item.strip().lower()
            for item in self.AIDD_ROLLOUT_USER_EMAILS
            if item and item.strip()
        }

    def _normalized_rollout_user_ids(self) -> set[str]:
        return {
            item.strip()
            for item in self.AIDD_ROLLOUT_USER_IDS
            if item and item.strip()
        }

    # ==================== 日志配置 ====================
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # ==================== SMTP 邮件配置 ====================
    SMTP_HOST: str = "smtp.example.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_FROM_NAME: str = "科学计算平台"
    SMTP_USE_TLS: bool = True

    # ==================== 验证码配置 ====================
    VERIFICATION_CODE_LENGTH: int = 6
    VERIFICATION_CODE_EXPIRE_MINUTES: int = 5
    VERIFICATION_CODE_RATE_LIMIT_SECONDS: int = 60
    VERIFICATION_CODE_DAILY_LIMIT: int = 10

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


settings = get_settings()


# ==================== 环境检测辅助函数 ====================


def is_development() -> bool:
    """是否为开发环境"""
    return settings.ENVIRONMENT == "development"


def is_production() -> bool:
    """是否为生产环境"""
    return settings.ENVIRONMENT == "production"


def use_async_tasks() -> bool:
    """是否使用异步任务队列"""
    return bool(settings.CELERY_BROKER_URL)


def use_direct_task_execution() -> bool:
    """是否使用当前进程内 direct 任务执行。"""
    if settings.TASK_EXECUTION_BACKEND == "direct":
        return True

    if settings.TASK_EXECUTION_BACKEND == "celery" and not settings.CELERY_BROKER_URL:
        return True

    return False
