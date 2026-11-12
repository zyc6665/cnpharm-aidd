# backend/app/config.py
"""应用配置管理"""

import ipaddress
import json
import logging
import os
import re
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Optional, List, Literal
from urllib.parse import urlparse

from dotenv import load_dotenv
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
_DNS_LABEL_PATTERN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
_IPV4_NUMERIC_HOST_PATTERN = re.compile(
    r"(?:0x[0-9a-f]+|0[0-7]*|[1-9][0-9]*)(?:\.(?:0x[0-9a-f]+|0[0-7]*|[1-9][0-9]*)){0,3}"
)
# 已知的示例/占位符密钥片段（不区分大小写）。这些值一旦进入运行环境就等同于
# 公开密钥：预发布/生产环境必须拒绝启动，开发环境告警并回退到随机值。
_PLACEHOLDER_SECRET_MARKERS = (
    "change-me",
    "changeme",
    "replace-with",
    "replace_with",
    "your-secret",
    "your_secret",
    "your-access-key",
    "your-email",
    "example-secret",
    "example-secret-key",
)
_PLACEHOLDER_SECRET_PREFIXES = ("dev-", "dev_")


def _looks_like_placeholder_secret(value: str) -> bool:
    """判断密钥是否为仓库示例里出现过的占位符/可猜值。"""
    normalized = value.strip().lower()
    if not normalized:
        return False
    if normalized.startswith(_PLACEHOLDER_SECRET_PREFIXES):
        return True
    return any(marker in normalized for marker in _PLACEHOLDER_SECRET_MARKERS)


_AIDD_FEATURE_FLAG_DESCRIPTIONS = {
    "AIDD_PROJECT_WORKSPACE_ENABLED": "项目优先研究工作台入口",
    "TOOL_PACKAGE_V1_ENABLED": "Tool Package v1 导入、迁移和验证等级",
    "LEGACY_AIDD_API_ENABLED": "旧 AIDD API 已下线",
}

_DEFAULT_RESOURCE_PROFILE_REGISTRY_JSON = json.dumps(
    {
        "cpu-small": {
            "tier": "cpu-small",
            "cpu": 2,
            "memory_gb": 4,
            "gpu_required": False,
            "gpu_memory_gb": 0,
            "timeout_minutes": 30,
            "parallelism": 1,
        },
        "cpu-medium": {
            "tier": "cpu-medium",
            "cpu": 4,
            "memory_gb": 8,
            "gpu_required": False,
            "gpu_memory_gb": 0,
            "timeout_minutes": 60,
            "parallelism": 1,
        },
        "gpu-large": {
            "tier": "gpu-large",
            "cpu": 16,
            "memory_gb": 64,
            "gpu_required": True,
            "gpu_memory_gb": 24,
            "timeout_minutes": 480,
            "parallelism": 1,
        },
    },
    separators=(",", ":"),
)


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
        # URL 中使用 POSIX 分隔符，Windows 盘符路径也能被 SQLAlchemy 正确解析。
        return f"{base_prefix}{absolute_path.as_posix()}"
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
    # Prometheus 指标端点 /metrics。内部部署默认开启；如需在公网入口彻底隐藏可置 false。
    METRICS_ENABLED: bool = True

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

    # ==================== 主机白名单 / 反向代理 / 文档开关 ====================
    # TrustedHostMiddleware 的白名单。开发环境默认放行任意 Host；预发布/生产
    # 必须显式配置具体域名（生产缺省或为 "*" 时拒绝启动，见下方校验）。
    ALLOWED_HOSTS: List[str] = ["*"]
    # 是否暴露 /docs、/redoc、/openapi.json。None 表示按环境推导：
    # development 打开，预发布/生产关闭。
    ENABLE_DOCS: Optional[bool] = None
    # 是否强制 HTTPS 跳转。None 表示「生产 + COOKIE_SECURE」时启用；
    # 显式 true/false 可覆盖，便于反向代理已终止 TLS 的内部部署。
    ENFORCE_HTTPS: Optional[bool] = None
    # 反向代理会改写 Host/X-Forwarded-Proto 时置 true；默认不信任外部头。
    TRUST_PROXY_HEADERS: bool = False

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

    # ==================== Cookie 认证配置 ====================
    # 令牌优先通过 httpOnly Cookie 下发。COOKIE_SECURE=False 仅适合本地 http 开发；
    # 预发布/生产环境必须为 True（见 _validate_production_security），否则拒绝启动。
    COOKIE_SECURE: bool = False
    # 留空表示不设置 Domain（主机域 Cookie）。
    COOKIE_DOMAIN: Optional[str] = None
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"

    # ==================== LDAP（企业内网目录认证）====================
    # 全部有默认值；LDAP_ENABLED=False 时登录链路完全不触发 LDAP。
    LDAP_ENABLED: bool = False
    LDAP_SERVER_URI: str = ""
    LDAP_START_TLS: bool = False
    LDAP_BASE_DN: str = ""
    LDAP_USER_FILTER: str = "(uid={username})"
    LDAP_ATTR_UID: str = "uid"
    LDAP_ATTR_MAIL: str = "mail"
    LDAP_ATTR_DISPLAY_NAME: str = "cn"
    LDAP_BIND_DN: str = ""
    LDAP_BIND_PASSWORD: str = ""
    LDAP_TIMEOUT_SECONDS: float = 5.0
    LDAP_CA_CERT_FILE: str = ""
    LDAP_TLS_VALIDATE: bool = True

    @model_validator(mode="after")
    def _validate_production_security(self):
        """生产环境强制校验安全关键配置。"""
        if self.EXECUTOR_ENABLED_K8S:
            required_k8s_settings = {
                "K8S_ADAPTER_CLUSTER_ALIAS": self.K8S_ADAPTER_CLUSTER_ALIAS,
                "K8S_ADAPTER_NAMESPACE": self.K8S_ADAPTER_NAMESPACE,
                "K8S_ADAPTER_CREDENTIAL_REF": self.K8S_ADAPTER_CREDENTIAL_REF,
                "K8S_ADAPTER_SERVICE_ACCOUNT": self.K8S_ADAPTER_SERVICE_ACCOUNT,
            }
            missing_k8s_settings = [
                name for name, value in required_k8s_settings.items() if not value
            ]
            if missing_k8s_settings:
                raise ValueError(
                    "EXECUTOR_ENABLED_K8S requires: "
                    + ", ".join(missing_k8s_settings)
                )

        # 所有环境都拒绝明显的占位符/示例密钥：预发布/生产直接拒绝启动，
        # 开发环境告警并回退到一次性的随机值。
        if self.JWT_SECRET_KEY and _looks_like_placeholder_secret(self.JWT_SECRET_KEY):
            if self.ENVIRONMENT in {"staging", "production"}:
                raise ValueError(
                    f"JWT_SECRET_KEY must not use a placeholder/example value in {self.ENVIRONMENT} environment"
                )
            logger.warning(
                "JWT_SECRET_KEY looks like a placeholder/example value in %s environment; "
                "generating an ephemeral random key instead",
                self.ENVIRONMENT,
            )
            self.JWT_SECRET_KEY = secrets.token_urlsafe(48)

        if not self.JWT_SECRET_KEY:
            if self.ENVIRONMENT == "development":
                # 空密钥会让 HS256 签名可被任意伪造。开发环境自动生成一次性随机密钥，
                # 避免本地启动/测试因缺少配置大面积失败，同时保证进程内密钥不可预测。
                self.JWT_SECRET_KEY = secrets.token_urlsafe(48)
                logger.warning(
                    "JWT_SECRET_KEY is not configured; generated an ephemeral random key "
                    "for development. Sessions will be invalidated on restart; set "
                    "JWT_SECRET_KEY explicitly to persist them."
                )
            else:
                raise ValueError(
                    f"JWT_SECRET_KEY must be at least 32 characters long in {self.ENVIRONMENT} environment"
                )

        if (
            self.ENVIRONMENT in {"staging", "production"}
            and len(self.JWT_SECRET_KEY) < 32
        ):
            raise ValueError(
                f"JWT_SECRET_KEY must be at least 32 characters long in {self.ENVIRONMENT} environment"
            )

        if self.SETTINGS_ENCRYPTION_KEY and _looks_like_placeholder_secret(
            self.SETTINGS_ENCRYPTION_KEY
        ):
            if self.ENVIRONMENT in {"staging", "production"}:
                raise ValueError(
                    f"SETTINGS_ENCRYPTION_KEY must not use a placeholder/example value in {self.ENVIRONMENT} environment"
                )
            logger.warning(
                "SETTINGS_ENCRYPTION_KEY looks like a placeholder/example value in %s "
                "environment; ignoring it and falling back to existing derivation logic",
                self.ENVIRONMENT,
            )
            self.SETTINGS_ENCRYPTION_KEY = None

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
            # Host 头是路由与缓存键的一部分；生产放行 "*" 等于允许任意 Host
            # 注入（密码重置链接投毒、缓存混淆）。必须显式配置。
            allowed_hosts = [
                host.strip() for host in self.ALLOWED_HOSTS if host and host.strip()
            ]
            if not allowed_hosts or "*" in allowed_hosts:
                raise ValueError(
                    "ALLOWED_HOSTS must list explicit hostnames in production environment"
                )
            if self.RATE_LIMIT_BACKEND == "memory":
                raise ValueError(
                    "RATE_LIMIT_BACKEND must use redis in production environment"
                )
            if self.RATE_LIMIT_FAIL_MODE != "closed":
                raise ValueError(
                    "RATE_LIMIT_FAIL_MODE must be closed in production environment"
                )
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
            # Cookie 认证只应经 HTTPS 传输：生产环境关闭 Secure 会让会话 Cookie 明文暴露。
            if not self.COOKIE_SECURE:
                raise ValueError(
                    "COOKIE_SECURE must be enabled in production environment"
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
    IMAGE_REGISTRY_ENDPOINT: str = "http://localhost:5000"
    IMAGE_REGISTRY_USERNAME: str = ""
    IMAGE_REGISTRY_PASSWORD: str = ""
    IMAGE_REGISTRY_TIMEOUT_SECONDS: int = 120
    IMAGE_IMPORT_MAX_SIZE_MB: int = 16384
    IMAGE_IMPORT_ALLOWED_REPOSITORY_PREFIX: str = "sciminer"

    # ==================== 缓存配置 ====================
    # 缓存后端: memory | redis
    CACHE_BACKEND: Literal["memory", "redis"] = "memory"
    # 单页应用一次页面加载会并发多个列表/统计/详情请求，60 次/分钟会让正常
    # 浏览和连续操作频繁触发 429。登录暴力破解由 login_throttle 单独约束，
    # 因此这里使用更宽松的全局 IP 上限。
    REQUEST_RATE_LIMIT_PER_MINUTE: int = 600
    RATE_LIMIT_TRUST_PROXY_HEADERS: bool = False
    # 限流计数后端：auto 表示预发布/生产用 Redis、开发用进程内缓存；
    # redis/memory 可显式覆盖。多 worker 部署必须使用 redis，否则各进程计数
    # 互不可见，等于把阈值放大 N 倍。
    RATE_LIMIT_BACKEND: Literal["auto", "redis", "memory"] = "auto"
    # 计数后端不可用时的行为。closed 返回 503（生产默认，防止绕过限流）；
    # open 放行并告警（仅建议本地开发使用）。
    RATE_LIMIT_FAIL_MODE: Literal["open", "closed"] = "closed"

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

    @property
    def effective_redis_url(self) -> str:
        """返回 Redis 客户端实际使用的连接 URL。"""
        if "REDIS_URL" in self.model_fields_set:
            return self.REDIS_URL
        return self.redis_url_with_auth

    @property
    def docs_enabled(self) -> bool:
        """是否暴露 Swagger/ReDoc/OpenAPI。"""
        if self.ENABLE_DOCS is not None:
            return self.ENABLE_DOCS
        return self.ENVIRONMENT == "development"

    @property
    def https_redirect_enabled(self) -> bool:
        """是否启用 HTTP -> HTTPS 跳转。"""
        if self.ENFORCE_HTTPS is not None:
            return self.ENFORCE_HTTPS
        return self.ENVIRONMENT == "production" and self.COOKIE_SECURE

    @property
    def resolved_rate_limit_backend(self) -> Literal["redis", "memory"]:
        """限流计数实际使用的后端。"""
        if self.RATE_LIMIT_BACKEND == "auto":
            return "redis" if self.ENVIRONMENT in {"staging", "production"} else "memory"
        return self.RATE_LIMIT_BACKEND

    # ==================== Celery 配置 ====================
    # 为空时使用内存队列（同步执行），生产环境设置为 Redis URL
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None
    # 数据库连接池模式。`pooled` 是常规的进程级连接池；`null` 表示「每个会话新建
    # 连接、用完即关」。
    #
    # 为什么需要这个开关：Celery 的 threads/prefork 池里，同一个任务函数可能在不同
    # 线程/进程的不同事件循环中执行，而 asyncpg 的连接**绑定到创建它的事件循环**。
    # 共享一个进程级池，第二个并发任务会拿到绑在别人循环上的连接，报
    # `Future attached to a different loop` / `another operation is in progress`。
    # 因此 Worker 进程必须用 `null`（任务本身是分钟级，每条任务一条连接的代价可忽略），
    # API 进程保持 `pooled`。见 docs/internal/17「Celery Worker 部署前置条件」。
    DB_POOL_MODE: Literal["pooled", "null"] = "pooled"
    CELERY_TIMEZONE: str = "Asia/Shanghai"
    # 任务执行时限的上限（秒）。工具自己的 timeout_minutes 可以很长（MD 轨迹要跑几天），
    # 但平台必须有一个封顶值，否则一个卡死的 Job 能占着卡位到天荒地老。
    # 7 天既覆盖长轨迹，又留出「迟早会有人发现」的窗口。
    TASK_TIMEOUT_MAX_SECONDS: int = 7 * 24 * 60 * 60
    # Celery 的软/硬超时是**最后一道**兜底，必须大于任何工具的执行时限——
    # 否则工具侧还没到时限，Celery 先以 SoftTimeLimitExceeded 把 worker 任务掐掉，
    # 表现为「任务莫名其妙失败、日志里看不到模型错误」。
    # 因此这里从 TASK_TIMEOUT_MAX_SECONDS 派生，而不是各自写死一个数。
    CELERY_TASK_SOFT_TIME_LIMIT: int = TASK_TIMEOUT_MAX_SECONDS + 1800
    CELERY_TASK_TIME_LIMIT: int = TASK_TIMEOUT_MAX_SECONDS + 3600
    TASK_EXECUTION_BACKEND: Literal["celery", "direct"] = "celery"
    # Worker 可用性探测：派发任务与健康检查都先问一次「有没有 Worker 在消费」。
    # 单次 ping 的等待上限，以及结果缓存时长（避免每次提交任务都付一次广播开销）。
    CELERY_WORKER_PROBE_TIMEOUT_SECONDS: float = 2.0
    CELERY_WORKER_PROBE_CACHE_SECONDS: float = 10.0
    WORKFLOW_RECONCILE_INTERVAL_SECONDS: int = 5
    WORKFLOW_RECONCILE_BATCH_SIZE: int = 20
    WORKFLOW_RECONCILE_LOCK_TTL_SECONDS: int = 60
    # 单个工作流 run 的最长存活时间（默认 12 小时）；超过即由巡检置为 failure。
    WORKFLOW_RUN_TIMEOUT_SECONDS: int = 12 * 60 * 60
    EXECUTION_RECORD_RECONCILE_INTERVAL_SECONDS: int = 60
    EXECUTION_RECORD_RECONCILE_BATCH_SIZE: int = 100
    EXECUTION_RECORD_STALE_AFTER_SECONDS: int = 86400
    # 取消请求超时后只升级为人工介入，不自动释放运行中租约。
    TASK_CANCELLATION_STALE_AFTER_SECONDS: int = 900
    TASK_CANCELLATION_RECONCILE_BATCH_SIZE: int = 100
    # 排队超时（docs/18 B-2b）：任务在 QUEUED 停留超过阈值即判 TIMEOUT。
    # 状态机早就留了 QUEUED -> TIMEOUT 这条边，但此前没有任何东西去用——
    # 一旦调度器不再捞这条任务（集群掉卡、配额被占死、消息丢了），任务会永远挂在
    # QUEUED，页面显示「排队中」而实际永远不会开始。这里给一个兜底上限：
    # 默认 6 小时，比最大单任务执行时长（k8s/ssh 3600s）留足余量，
    # 只兜「排不进来」而不是「跑得慢」。
    TASK_QUEUE_TIMEOUT_SECONDS: int = 21600
    TASK_QUEUE_TIMEOUT_SCAN_INTERVAL_SECONDS: int = 300
    TASK_QUEUE_TIMEOUT_SCAN_BATCH_SIZE: int = 200
    TASK_QUEUE_TIMEOUT_ENABLED: bool = True
    # 项目配额（docs/04 §5.3、docs/05 §9）：表与端点始终存在，这个开关只控制
    # 「提交准入是否拦截」与「漏核销兜底巡检是否启动」两件事。
    # 默认开启是安全的：准入只在**存在配额记录**时才生效，而记录只会由
    # `PUT /projects/{id}/quota` 显式创建（`GET` 是纯读，**不会**顺手建记录——
    # 否则「有没有人点开过配额页」就会决定这个项目还能不能提交任务）。
    # 没有任何记录的项目一律不限，升级不会因为「还没人配过」而挡住存量项目。
    PROJECT_QUOTA_ENABLED: bool = True
    # 兜底补核销：状态机终态核销是主路径，这里只补「不经过状态机」的历史/异常数据。
    # 5 分钟一轮、每轮 200 条，与排队超时巡检同量级——配额是分钟级资源，
    # 不需要秒级精度，扫得太勤只是白占连接。
    QUOTA_SETTLEMENT_INTERVAL_SECONDS: float = 300.0
    QUOTA_SETTLEMENT_BATCH_SIZE: int = 200
    GPU_RETRY_INITIAL_BACKOFF_SECONDS: int = 30
    GPU_RETRY_MAX_BACKOFF_SECONDS: int = 900
    # 任务事件 SSE（docs/05 §1.5、§9；docs/10 API-08）。
    # 连接建立后先下发快照，之后按 poll 间隔回读数据库；数据库是唯一真值，
    # 进程内广播只用来把下一次回读提前，不承担正确性。
    TASK_EVENT_POLL_INTERVAL_SECONDS: float = 1.0
    TASK_EVENT_HEARTBEAT_SECONDS: float = 15.0
    # 单条 SSE 连接的最长存活时间：数小时级的 MD 任务不占着连接不放，
    # 到点后前端凭 Last-Event-ID 重连续订（docs/12 HA-T-06）。
    TASK_EVENT_MAX_DURATION_SECONDS: int = 1800
    TASK_EVENT_INCLUDE_LOGS: bool = True
    # 容器日志归档：任务进入终态时把 Pod 日志抓一次写进 task_logs，
    # 让「看日志」不再依赖 Pod 是否还活着，Job 的保留时长也才能调短。
    # 关掉它等于回到「TTL 一到日志永久消失」，生产不应关闭。
    TASK_LOG_HARVEST_ENABLED: bool = True
    # 单任务最多归档多少字节；超出部分截断并标注，避免刷屏模型撑爆日志表。
    TASK_LOG_MAX_BYTES: int = 2_000_000
    # 运行期日志与进度同步（docs/26 H-2、H-3）：执行侧往 stdout 打
    # `__DRP_PROGRESS__ {"pct": 45, "message": "..."}`，平台按间隔增量拉日志、
    # 解析进度写回 task.progress。关掉它长任务在页面上就只剩「运行中」三个字。
    TASK_RUNTIME_LOG_SYNC_ENABLED: bool = True
    # 间隔取 10s 是折中：K8s `sinceTime` 拉取本身很轻，但每轮都要为每个运行中
    # 任务发一次 API 请求；再密对进度条的肉眼观感没有帮助（SSE 也只有 1s 粒度）。
    TASK_RUNTIME_LOG_SYNC_INTERVAL_SECONDS: float = 10.0
    # 单任务单轮最多处理多少字符，只保留尾部——进度标记总在最新几行。
    TASK_RUNTIME_LOG_SYNC_MAX_CHARS: int = 200_000
    # 单轮最多同步多少个运行中任务，避免某次长尾把一轮拖成分钟级。
    TASK_RUNTIME_LOG_SYNC_MAX_TASKS: int = 50
    # 卡位调度（docs/09 §5.6、docs/13 §4.1）：卡位由 slots.yaml 静态声明，
    # 状态由 drp-node-agent 维护并上报，平台只消费与展示。
    # 内联 YAML 优先于文件路径；两者都为空时按「无卡位」启动，回退到本机 GPU 探测。
    DRP_NODE_SLOTS_YAML: Optional[str] = None
    DRP_NODE_SLOTS_FILE: Optional[str] = None
    DRP_SLOT_STATE_TTL_SECONDS: int = 120
    # Agent HTTP 通道（docs/13 §4.2：平台 → Agent 8780/TCP）。
    DRP_NODE_AGENT_BASE_URL: Optional[str] = None
    DRP_NODE_AGENT_TOKEN: Optional[str] = None
    DRP_NODE_AGENT_TIMEOUT_SECONDS: float = 5.0
    # Agent → 平台上报用的 token（docs/13 §4.3：DCU 机 /etc/drp/agent/report.token）。
    # 与出站 token 分开，泄露时互不影响。
    DRP_NODE_AGENT_REPORT_TOKEN: Optional[str] = None
    RESOURCE_ADMISSION_RETRY_INITIAL_BACKOFF_SECONDS: int = 30
    RESOURCE_ADMISSION_RETRY_MAX_BACKOFF_SECONDS: int = 900
    WORKER_CAPABILITY_JSON: Optional[str] = None
    RESOURCE_PROFILE_REGISTRY_JSON: Optional[str] = _DEFAULT_RESOURCE_PROFILE_REGISTRY_JSON
    WORKER_CAPABILITY_TTL_SECONDS: int = 90
    WORKER_CAPABILITY_HEARTBEAT_QUEUES: Optional[str] = None
    WORKER_CAPABILITY_ADMISSION_ENABLED: bool = False
    WORKER_CAPABILITY_ROUTING_ENABLED: bool = False
    WORKER_CAPABILITY_RESERVATION_ENABLED: bool = False
    RESOURCE_DISPATCH_RESERVATION_TTL_SECONDS: int = 60
    RESOURCE_RESERVATION_STALE_AFTER_SECONDS: int = 120
    RESOURCE_SCOPE_QUOTA_ENABLED: bool = False
    RESOURCE_USER_MAX_CPU: Optional[float] = None
    RESOURCE_USER_MAX_MEMORY_GB: Optional[float] = None
    RESOURCE_USER_MAX_PARALLELISM: Optional[int] = None
    RESOURCE_PROJECT_MAX_CPU: Optional[float] = None
    RESOURCE_PROJECT_MAX_MEMORY_GB: Optional[float] = None
    RESOURCE_PROJECT_MAX_PARALLELISM: Optional[int] = None
    RESOURCE_QUOTA_LOCK_TTL_SECONDS: int = 10
    RESOURCE_QUOTA_REJECTION_TTL_SECONDS: int = 86400
    WORKER_LISTEN_QUEUES: Optional[str] = None

    # 受控 Job 执行器开关。具体 K8s/SSH adapter 由 worker 启动时注入。
    EXECUTOR_ENABLED_K8S: bool = False
    EXECUTOR_ENABLED_SSH: bool = True
    K8S_ADAPTER_CLUSTER_ALIAS: Optional[str] = None
    K8S_ADAPTER_NAMESPACE: Optional[str] = None
    K8S_ADAPTER_CREDENTIAL_REF: Optional[str] = None
    K8S_ADAPTER_SERVICE_ACCOUNT: Optional[str] = None
    K8S_ADAPTER_JOB_NAME_PREFIX: str = "sciminer"
    # 已结束的 Job（及其 Pod）保留多久。Pod 一删容器日志就没了，所以这个值只在
    # TASK_LOG_HARVEST_ENABLED 把日志落库之后才能安全调短。
    # 默认 1800 秒：够运维在页面上看到刚失败任务的现场，又不至于让
    # 「每天任务数」等于「常驻 Pod 数」（原默认 24h 会长期堆几百个 Completed Pod）。
    K8S_ADAPTER_JOB_TTL_SECONDS: int = 1800
    K8S_ADAPTER_API_SERVER: Optional[str] = None
    # 集群外运行时（平台进程跑在 Windows 工作站、算力跑在远程 k3s）用 kubeconfig 拿凭证。
    # 设了它就走集群外模式，否则走 Pod 内 ServiceAccount（生产形态）。
    K8S_ADAPTER_KUBECONFIG: Optional[str] = None
    K8S_ADAPTER_KUBECONFIG_CONTEXT: Optional[str] = None
    # 默认不信任环境里的 HTTP(S)_PROXY：内网机器普遍配了公司代理，httpx/urllib 默认会
    # 把到集群 APIServer 的请求也交给代理，表现为连接超时而不是认证失败（很难查）。
    K8S_ADAPTER_TRUST_ENV: bool = False
    K8S_ADAPTER_TOKEN_FILE: str = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    K8S_ADAPTER_CA_FILE: str = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
    K8S_ADAPTER_REQUEST_TIMEOUT_SECONDS: int = 30
    K8S_ADAPTER_OBJECT_STORAGE_ENDPOINT: Optional[str] = None
    K8S_ADAPTER_OBJECT_STORAGE_BUCKET: Optional[str] = None
    K8S_ADAPTER_OBJECT_STORAGE_SECRET_REF: Optional[str] = None
    K8S_ADAPTER_OBJECT_STORAGE_INPUT_PREFIX: str = "inputs"
    K8S_ADAPTER_OBJECT_STORAGE_OUTPUT_PREFIX: str = "executions"
    K8S_ADAPTER_OBJECT_STORAGE_STAGING_ROOT: str = "/tmp/sciminer-k8s-artifacts"

    IMAGE_REGISTRY_ENDPOINT: str = "http://sciminer-registry.sciminer-storage.svc.cluster.local:5000"
    IMAGE_REGISTRY_IMAGE_PREFIX: str = "sciminer-registry.sciminer-storage.svc.cluster.local:5000"
    IMAGE_REGISTRY_USERNAME: Optional[str] = None
    IMAGE_REGISTRY_PASSWORD: Optional[str] = None
    IMAGE_IMPORT_MAX_SIZE_MB: int = 16384
    IMAGE_IMPORT_ALLOWED_REPOSITORY_PREFIX: str = "sciminer/"

    # ==================== Docker 执行器配置 ====================
    # 生产环境默认强制不可变 digest；该列表可进一步收紧为精确允许的镜像引用。
    DOCKER_ALLOWED_IMAGES: List[str] = []
    DOCKER_REQUIRE_IMAGE_DIGEST_IN_DEPLOYMENT: bool = True
    # Python 脚本在预发布/生产环境必须匹配此 SHA-256 信任列表。
    TRUSTED_PYTHON_SCRIPT_SHA256: List[str] = []

    # ==================== AIDD Agent 配置 ====================
    AIDD_SYSTEM_USER_ID: Optional[str] = None
    # 分子库导入上限。PRD M1-FR-03 要求化合物导入单文件 ≤200MB，与通用的
    # MAX_FILE_SIZE_MB（100MB）不同：通用上限约束「工具输入附件」，分子库是批量
    # 业务数据，两者体量口径不同，因此单独开一项而不是把通用上限整体抬高。
    COMPOUND_IMPORT_MAX_FILE_SIZE_MB: int = 200
    # 项目内候选物数量上限（docs/04 §5.7）。一期相似性检索是全表扫描 + 应用内
    # Tanimoto，2 万条 × 2048bit ≈ 5MB，全扫 <200ms；超过这个量级必须改为专用
    # 索引或外部检索服务，属二期范围。
    MAX_PROJECT_CANDIDATES: int = 20000

    # 分片上传（docs/04 §5.8、docs/05 §4.2）。>100MB 的文件强制 Multipart
    # （docs/04 §13.2），分片大小由服务端决定，客户端只按 partCount 循环上报。
    # 16MB × 128 片 = 2GB，正好覆盖单文件上限。
    UPLOAD_PART_SIZE_BYTES: int = 16777216
    # 会话 24 小时过期：未完成的分片会在存储上长期占空间，必须有过期兜底。
    # 三个入口（上报分片/合并/取消）都会校验 expires_at，另有过期清理任务兜底。
    UPLOAD_SESSION_TTL_HOURS: int = 24
    # 服务端合并上限。合并已改成逐片流式落盘（峰值内存只有一片），不再受进程内存
    # 约束；这里只用于限制临时盘/对象存储占用，默认与单文件上限 2GB 同口径。
    UPLOAD_MAX_ASSEMBLY_BYTES: int = 2 * 1024**3
    # 过期会话清理任务的执行间隔（秒）与开关。测试环境可用
    # ``UPLOAD_SWEEP_ENABLED=false`` 关掉，避免后台任务干扰断言。
    UPLOAD_SWEEP_INTERVAL_SECONDS: int = 3600
    UPLOAD_SWEEP_ENABLED: bool = True

    # 无引用 File 回收（计划 §5.6）。产物版本/项目删除只删行会留下对象存储孤儿，
    # 需要一个与用户行为无关的兜底。保留 30 天：先删版本再恢复的窗口。
    ARTIFACT_GC_ENABLED: bool = True
    ARTIFACT_GC_INTERVAL_SECONDS: int = 3600
    ARTIFACT_GC_RETENTION_DAYS: int = 30

    # 对象存储生命周期规则（docs/04 §5.8、docs/03 §4.5、docs/15 §3.2）。
    # 平台侧清理（上传会话巡检）跑在 backend 进程里，进程没起来就不清理；
    # 桶上的 lifecycle 由 MinIO 自己执行，是最后一道保险。两者都要有。
    MINIO_LIFECYCLE_TEMP_EXPIRATION_DAYS: int = 30
    MINIO_LIFECYCLE_ABORT_INCOMPLETE_DAYS: int = 7
    MINIO_LIFECYCLE_NONCURRENT_KEEP_DAYS: int = 90
    # 转低频的 storage class。**留空表示不生成过渡规则**：MinIO 是单层存储，
    # 过渡目标必须先用 `mc ilm tier add` 建出远程层，否则整份 lifecycle 配置会被拒——
    # 一条配错的过渡规则会把「临时区清分片」这种关键规则一起带下水。
    MINIO_LIFECYCLE_TRANSITION_STORAGE_CLASS: Optional[str] = None
    # 启动时自动应用一次。默认关闭：改桶配置属于运维动作，应由部署脚本或
    # `python -m app.cli.storage_lifecycle --apply` 显式执行并留痕。
    MINIO_LIFECYCLE_APPLY_ON_STARTUP: bool = False

    # 请求级幂等（docs/04 §5.5、docs/05 §12、docs/18 §6.3 G-10）。
    # 键的保留期 24 小时与上传会话同口径：覆盖「客户端断网重试」的合理窗口，
    # 同时让 idempotency_keys 不至于无限增长。
    IDEMPOTENCY_TTL_HOURS: int = 24
    # 总开关。关闭后没有 ``X-Idempotency-Key`` 的语义（请求头被忽略、原样放行），
    # 但不会让任何端点报错——幂等是增强而不是前置条件。
    IDEMPOTENCY_ENABLED: bool = True
    # 过期幂等记录清理任务的执行间隔（秒）与开关。测试环境可用
    # ``IDEMPOTENCY_SWEEP_ENABLED=false`` 关掉，避免后台任务干扰断言。
    IDEMPOTENCY_SWEEP_INTERVAL_SECONDS: int = 3600
    IDEMPOTENCY_SWEEP_ENABLED: bool = True

    # 启动期平台工具 seeding（见 app/services/platform_tool_seeding.py）。
    # 历史遗留：部分「种子迁移」在没有任何 admin 时会静默空转（只推 alembic_version，
    # 一行数据都不建）。在「先跑迁移、后创建第一个 admin」的部署顺序下，新部署/重建库
    # 会重演该缺陷。这里在 init_db() 之后按 slug 幂等补齐平台必备工具兜底；无 owner 时
    # 只跳过、绝不阻断启动。默认开启，测试环境可用 false 关掉。
    SEED_PLATFORM_TOOLS_ON_STARTUP: bool = True

    # 首月 AIDD 发布门禁。None 表示使用环境默认值：开发环境开启新入口，
    # 预发布/生产默认关闭新入口；旧 AIDD API 默认关闭。
    AIDD_PROJECT_WORKSPACE_ENABLED: Optional[bool] = None
    TOOL_PACKAGE_V1_ENABLED: Optional[bool] = None
    LEGACY_AIDD_API_ENABLED: Optional[bool] = None
    # 生产/预发布灰度账号。全局新入口关闭时，仅这些内部账号可访问。
    AIDD_ROLLOUT_USER_EMAILS: List[str] = []
    AIDD_ROLLOUT_USER_IDS: List[str] = []

    @field_validator("ALLOWED_HOSTS", mode="before")
    @classmethod
    def _parse_allowed_hosts(cls, value):
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
