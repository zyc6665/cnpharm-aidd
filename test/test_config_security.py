"""Tests for configuration security rules."""

import json
import os
from pathlib import Path

import pytest

from app.config import Settings


LOCAL_DEVELOPMENT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://localhost:8585",
    "http://127.0.0.1:8585",
]


def _production_runtime_settings(environment: str) -> dict[str, object]:
    """为只测试安全规则的用例补齐生产运行依赖。"""
    if environment != "production":
        return {}
    return {
        "DATABASE_URL": "postgresql+asyncpg://scitool:secret@postgres:5432/scitool",
        "STORAGE_BACKEND": "minio",
        "MINIO_ENDPOINT": "minio:9000",
        "MINIO_ACCESS_KEY": "minio-user",
        "MINIO_SECRET_KEY": "minio-password",
        "CACHE_BACKEND": "redis",
        "REDIS_HOST": "redis",
        "REDIS_PASSWORD": "redis-password",
        "CELERY_BROKER_URL": "redis://:redis-password@redis:6379/1",
        "CELERY_RESULT_BACKEND": "redis://:redis-password@redis:6379/2",
        "TASK_EXECUTION_BACKEND": "celery",
        "COOKIE_SECURE": True,
        "ALLOWED_HOSTS": ["sciminer.example.com"],
    }


class TestCorsDefaults:
    def test_development_default_cors_origins_are_restricted_to_local_frontends(self):
        """开发环境默认 CORS 仅允许本地前端地址。"""
        default_origins = Settings.model_fields["CORS_ORIGINS"].default
        assert default_origins == LOCAL_DEVELOPMENT_CORS_ORIGINS
        assert "*" not in default_origins

    def test_env_example_documents_safe_cors_and_settings_encryption_key(self):
        """环境示例不得启用通配 CORS，且必须说明独立配置加密密钥。"""
        example = Path(__file__).resolve().parents[1] / "backend" / ".env.example"
        contents = example.read_text(encoding="utf-8")

        cors_line = next(
            line for line in contents.splitlines() if line.startswith("CORS_ORIGINS=")
        )
        assert (
            json.loads(cors_line.removeprefix("CORS_ORIGINS="))
            == LOCAL_DEVELOPMENT_CORS_ORIGINS
        )
        assert "*" not in json.loads(cors_line.removeprefix("CORS_ORIGINS="))
        assert "SETTINGS_ENCRYPTION_KEY=" in contents
        assert "预发布/生产环境" in contents
        assert "独立" in contents
        assert "自动生成临时密钥" in contents
        assert "加密操作会回退到 JWT_SECRET_KEY" in contents
        assert "否则拒绝启动" in contents


class TestKubernetesExecutionSettings:
    def test_k8s_executor_requires_platform_binding_settings(self):
        with pytest.raises(ValueError, match="EXECUTOR_ENABLED_K8S requires"):
            Settings(
                ENVIRONMENT="development",
                EXECUTOR_ENABLED_K8S=True,
            )

    def test_k8s_executor_accepts_complete_platform_binding_settings(self):
        settings = Settings(
            ENVIRONMENT="development",
            EXECUTOR_ENABLED_K8S=True,
            K8S_ADAPTER_CLUSTER_ALIAS="platform",
            K8S_ADAPTER_NAMESPACE="model-jobs",
            K8S_ADAPTER_CREDENTIAL_REF="platform-k8s",
            K8S_ADAPTER_SERVICE_ACCOUNT="model-runner",
        )

        assert settings.EXECUTOR_ENABLED_K8S is True
        assert settings.K8S_ADAPTER_NAMESPACE == "model-jobs"


class TestRedisSettings:
    def test_effective_redis_url_uses_host_settings_when_url_is_not_explicit(self):
        settings = Settings(
            ENVIRONMENT="development",
            REDIS_HOST="redis.internal",
            REDIS_PORT=6380,
            REDIS_DB=4,
            REDIS_PASSWORD="redis-password",
        )

        assert (
            settings.effective_redis_url
            == "redis://:redis-password@redis.internal:6380/4"
        )

    def test_effective_redis_url_preserves_an_explicit_url(self):
        settings = Settings(
            ENVIRONMENT="development",
            REDIS_URL="redis://redis.internal:6381/5",
            REDIS_HOST="unused",
            REDIS_PORT=6390,
            REDIS_DB=6,
            REDIS_PASSWORD="unused-password",
        )

        assert settings.effective_redis_url == "redis://redis.internal:6381/5"


class TestAiddFeatureFlags:
    def test_development_feature_flags_default_open_for_local_iteration(self):
        """开发环境默认开启新项目入口，但旧 AIDD API 默认关闭。"""
        settings = Settings(ENVIRONMENT="development")
        flags = {item["key"]: item for item in settings.aidd_feature_flags()}

        assert flags["AIDD_PROJECT_WORKSPACE_ENABLED"]["enabled"] is True
        assert flags["TOOL_PACKAGE_V1_ENABLED"]["enabled"] is True
        assert flags["LEGACY_AIDD_API_ENABLED"]["enabled"] is False
        assert flags["LEGACY_AIDD_API_ENABLED"]["rollout"]["scope"] == "closed"
        assert {item["source"] for item in flags.values()} == {"default"}

    def test_production_feature_flags_default_closed_until_release_enablement(self):
        """生产环境默认关闭新入口，发布时必须显式打开。"""
        settings = Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            CORS_ORIGINS=["https://sciminer.example.com"],
            JWT_SECRET_KEY="j" * 32,
            SETTINGS_ENCRYPTION_KEY="e" * 32,
            **_production_runtime_settings("production"),
        )
        flags = {item["key"]: item for item in settings.aidd_feature_flags()}

        assert flags["AIDD_PROJECT_WORKSPACE_ENABLED"]["enabled"] is False
        assert flags["TOOL_PACKAGE_V1_ENABLED"]["enabled"] is False
        assert flags["LEGACY_AIDD_API_ENABLED"]["enabled"] is False
        assert flags["LEGACY_AIDD_API_ENABLED"]["rollout"]["scope"] == "closed"

    def test_production_rollout_allowlist_enables_only_named_internal_users(self):
        """生产灰度用户白名单应只放行命中的内部测试账号。"""
        settings = Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            CORS_ORIGINS=["https://sciminer.example.com"],
            JWT_SECRET_KEY="j" * 32,
            SETTINGS_ENCRYPTION_KEY="e" * 32,
            AIDD_ROLLOUT_USER_EMAILS=["internal@example.com"],
            **_production_runtime_settings("production"),
        )
        flags = {item["key"]: item for item in settings.aidd_feature_flags()}

        assert flags["AIDD_PROJECT_WORKSPACE_ENABLED"]["enabled"] is False
        assert flags["AIDD_PROJECT_WORKSPACE_ENABLED"]["rollout"]["user_count"] == 1
        assert flags["AIDD_PROJECT_WORKSPACE_ENABLED"]["rollout"]["scope"] == "allowlist"
        assert settings.is_aidd_feature_enabled_for_user(
            "AIDD_PROJECT_WORKSPACE_ENABLED",
            user_email="internal@example.com",
        ) is True
        assert settings.is_aidd_feature_enabled_for_user(
            "AIDD_PROJECT_WORKSPACE_ENABLED",
            user_email="other@example.com",
        ) is False
        assert settings.is_aidd_feature_enabled_for_user(
            "LEGACY_AIDD_API_ENABLED",
            user_email="internal@example.com",
        ) is False

    def test_legacy_aidd_api_flag_cannot_reopen_removed_api(self):
        """旧 AIDD API 已下线，显式配置也不应让审计状态重新变为开启。"""
        settings = Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            CORS_ORIGINS=["https://sciminer.example.com"],
            JWT_SECRET_KEY="j" * 32,
            SETTINGS_ENCRYPTION_KEY="e" * 32,
            LEGACY_AIDD_API_ENABLED=True,
            **_production_runtime_settings("production"),
        )
        flags = {item["key"]: item for item in settings.aidd_feature_flags()}

        assert flags["LEGACY_AIDD_API_ENABLED"]["enabled"] is False
        assert flags["LEGACY_AIDD_API_ENABLED"]["rollout"]["scope"] == "closed"

    def test_rollout_allowlist_normalizes_email_case_and_whitespace(self):
        """灰度邮箱白名单应规范化，避免大小写或空格导致误拒。"""
        settings = Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            CORS_ORIGINS=["https://sciminer.example.com"],
            JWT_SECRET_KEY="j" * 32,
            SETTINGS_ENCRYPTION_KEY="e" * 32,
            AIDD_ROLLOUT_USER_EMAILS=[" Internal@Example.com ", ""],
            **_production_runtime_settings("production"),
        )

        assert settings.is_aidd_feature_enabled_for_user(
            "AIDD_PROJECT_WORKSPACE_ENABLED",
            user_email="internal@example.com",
        ) is True


class TestDeploymentCorsOrigins:
    @pytest.mark.parametrize("environment", ["staging", "production"])
    @pytest.mark.parametrize(
        "origin",
        [
            "http://sciminer.example.com",
            "https://*.sciminer.example.com",
            "https://",
            " https://sciminer.example.com",
            "https://sciminer.example.com ",
            "https://%73ciminer.example.com",
            "https://sciminer.example.com:0",
            "https://sciminer.example.com/path",
            "https://sciminer.example.com?query=value",
            "https://sciminer.example.com#fragment",
            "https://user@sciminer.example.com",
            "https://[2001:0db8::1]",
            "https://[2001:db8:0:0:0:0:0:1]",
            "https://192.168.001.001",
            "https://0x7f.0.0.1",
            "https://127.1",
            "https://2130706433",
            "https://0x7f.1",
        ],
    )
    def test_deployment_environment_rejects_invalid_cors_origin(
        self, environment, origin
    ):
        """预发布和生产环境仅接受带有效主机名的 HTTPS Origin。"""
        with pytest.raises(
            ValueError, match="CORS_ORIGINS must contain only HTTPS origins"
        ):
            Settings(
                ENVIRONMENT=environment,
                DEBUG=False,
                CORS_ORIGINS=[origin],
                JWT_SECRET_KEY="j" * 32,
                SETTINGS_ENCRYPTION_KEY="e" * 32,
            )

    @pytest.mark.parametrize("environment", ["staging", "production"])
    @pytest.mark.parametrize(
        "origin",
        [
            "https://sciminer.example.com",
            "https://203.0.113.1",
            "https://[2001:db8::1]",
            "https://sciminer.example.com:1",
            "https://sciminer.example.com:8443",
            "https://sciminer.example.com:65535",
        ],
    )
    def test_deployment_environment_accepts_valid_https_cors_origin(
        self, environment, origin
    ):
        """预发布和生产环境接受受控 HTTPS Origin。"""
        settings = Settings(
            ENVIRONMENT=environment,
            DEBUG=False,
            CORS_ORIGINS=[origin],
            JWT_SECRET_KEY="j" * 32,
            SETTINGS_ENCRYPTION_KEY="e" * 32,
            **_production_runtime_settings(environment),
        )
        assert settings.CORS_ORIGINS == [origin]

    @pytest.mark.parametrize("environment", ["staging", "production"])
    def test_deployment_environment_rejects_mixed_valid_and_invalid_cors_origins(
        self, environment
    ):
        """部署环境的 Origin 列表不能夹带不安全来源。"""
        with pytest.raises(
            ValueError, match="CORS_ORIGINS must contain only HTTPS origins"
        ):
            Settings(
                ENVIRONMENT=environment,
                DEBUG=False,
                CORS_ORIGINS=["https://sciminer.example.com", "http://localhost:8585"],
                JWT_SECRET_KEY="j" * 32,
                SETTINGS_ENCRYPTION_KEY="e" * 32,
            )

    @pytest.mark.parametrize("environment", ["staging", "production"])
    @pytest.mark.parametrize(
        "origin",
        [
            "HTTPS://sciminer.example.com",
            "https://SCIMINER.example.com",
            "https://sciminer.example.com:443",
            "https://sciminer.example.com:08443",
        ],
    )
    def test_deployment_environment_rejects_noncanonical_cors_origin(
        self, environment, origin
    ):
        """部署环境拒绝会与浏览器 Origin 精确匹配不一致的来源。"""
        with pytest.raises(
            ValueError, match="CORS_ORIGINS must contain only HTTPS origins"
        ):
            Settings(
                ENVIRONMENT=environment,
                DEBUG=False,
                CORS_ORIGINS=[origin],
                JWT_SECRET_KEY="j" * 32,
                SETTINGS_ENCRYPTION_KEY="e" * 32,
            )

    @pytest.mark.parametrize("environment", ["staging", "production"])
    def test_deployment_environment_accepts_canonical_custom_https_port(
        self, environment
    ):
        """部署环境接受规范化的非默认 HTTPS 端口。"""
        origin = "https://sciminer.example.com:8443"
        settings = Settings(
            ENVIRONMENT=environment,
            DEBUG=False,
            CORS_ORIGINS=[origin],
            JWT_SECRET_KEY="j" * 32,
            SETTINGS_ENCRYPTION_KEY="e" * 32,
            **_production_runtime_settings(environment),
        )
        assert settings.CORS_ORIGINS == [origin]

    @pytest.mark.parametrize("environment", ["staging", "production"])
    def test_deployment_environment_accepts_canonical_ipv6_with_custom_https_port(
        self, environment
    ):
        """部署环境接受压缩格式的 IPv6 HTTPS Origin。"""
        origin = "https://[2001:db8::1]:8443"
        settings = Settings(
            ENVIRONMENT=environment,
            DEBUG=False,
            CORS_ORIGINS=[origin],
            JWT_SECRET_KEY="j" * 32,
            SETTINGS_ENCRYPTION_KEY="e" * 32,
            **_production_runtime_settings(environment),
        )
        assert settings.CORS_ORIGINS == [origin]

    def test_development_does_not_reject_noncanonical_cors_origin(self):
        """开发环境保留自定义 CORS 来源的兼容行为。"""
        origin = "HTTPS://SCIMINER.example.com:443"
        settings = Settings(ENVIRONMENT="development", CORS_ORIGINS=[origin])
        assert settings.CORS_ORIGINS == [origin]


class TestJWTSecretKey:
    def test_development_generates_ephemeral_jwt_secret_when_empty(self, caplog):
        """开发环境 JWT_SECRET_KEY 为空时自动生成一次性随机密钥并告警。"""
        with caplog.at_level("WARNING"):
            settings = Settings(ENVIRONMENT="development", JWT_SECRET_KEY="")
        assert settings.JWT_SECRET_KEY
        assert len(settings.JWT_SECRET_KEY) >= 32
        assert "JWT_SECRET_KEY is not configured" in caplog.text

    def test_development_replaces_placeholder_jwt_secret(self, caplog):
        """开发环境遇到占位符 JWT 密钥时告警并回退到随机值。"""
        with caplog.at_level("WARNING"):
            settings = Settings(
                ENVIRONMENT="development", JWT_SECRET_KEY="change-me-in-production"
            )
        assert settings.JWT_SECRET_KEY != "change-me-in-production"
        assert len(settings.JWT_SECRET_KEY) >= 32
        assert "placeholder/example value" in caplog.text

    @pytest.mark.parametrize("environment", ["staging", "production"])
    def test_deployment_environment_rejects_placeholder_jwt_secret(self, environment):
        """预发布/生产环境拒绝示例占位符 JWT 密钥。"""
        with pytest.raises(ValueError, match="placeholder/example value"):
            Settings(
                ENVIRONMENT=environment,
                JWT_SECRET_KEY="change-me-in-production-for-jwt",
            )

    @pytest.mark.parametrize("environment", ["staging", "production"])
    def test_deployment_environment_rejects_placeholder_settings_encryption_key(
        self, environment
    ):
        """预发布/生产环境拒绝示例占位符配置加密密钥。"""
        with pytest.raises(ValueError, match="SETTINGS_ENCRYPTION_KEY must not use"):
            Settings(
                ENVIRONMENT=environment,
                JWT_SECRET_KEY="j" * 32,
                SETTINGS_ENCRYPTION_KEY="replace-with-a-real-settings-key-min-32-chars",
            )

    def test_staging_rejects_short_jwt_secret(self):
        """预发布环境拒绝长度不足的 JWT_SECRET_KEY。"""
        with pytest.raises(
            ValueError, match="JWT_SECRET_KEY must be at least 32 characters"
        ):
            Settings(ENVIRONMENT="staging", JWT_SECRET_KEY="short")

    def test_production_rejects_short_jwt_secret(self):
        """生产环境拒绝长度不足的 JWT_SECRET_KEY。"""
        with pytest.raises(
            ValueError, match="JWT_SECRET_KEY must be at least 32 characters"
        ):
            Settings(ENVIRONMENT="production", JWT_SECRET_KEY="short")

    def test_staging_accepts_long_jwt_secret(self):
        """预发布环境接受长度不少于 32 的 JWT_SECRET_KEY。"""
        long_key = "a" * 32
        settings = Settings(
            ENVIRONMENT="staging",
            CORS_ORIGINS=["https://staging.sciminer.example.com"],
            JWT_SECRET_KEY=long_key,
            SETTINGS_ENCRYPTION_KEY="e" * 32,
        )
        assert settings.JWT_SECRET_KEY == long_key

    def test_production_accepts_long_jwt_secret(self):
        """生产环境接受长度不少于 32 的 JWT_SECRET_KEY。"""
        long_key = "a" * 32
        settings = Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            CORS_ORIGINS=["https://sciminer.example.com"],
            JWT_SECRET_KEY=long_key,
            SETTINGS_ENCRYPTION_KEY="e" * 32,
            **_production_runtime_settings("production"),
        )
        assert settings.JWT_SECRET_KEY == long_key

    def test_production_rejects_debug_mode(self):
        """生产环境拒绝开启 DEBUG。"""
        with pytest.raises(ValueError, match="DEBUG must be disabled"):
            Settings(
                ENVIRONMENT="production",
                DEBUG=True,
                CORS_ORIGINS=["https://sciminer.example.com"],
                JWT_SECRET_KEY="a" * 32,
                SETTINGS_ENCRYPTION_KEY="e" * 32,
            )

    def test_production_rejects_wildcard_cors_with_credentials(self):
        """生产环境拒绝通配 CORS。"""
        with pytest.raises(
            ValueError, match="CORS_ORIGINS must contain only HTTPS origins"
        ):
            Settings(
                ENVIRONMENT="production",
                DEBUG=False,
                CORS_ORIGINS=["*"],
                JWT_SECRET_KEY="a" * 32,
                SETTINGS_ENCRYPTION_KEY="e" * 32,
            )

    def test_staging_rejects_wildcard_cors_with_credentials(self):
        """预发布环境拒绝通配 CORS。"""
        with pytest.raises(
            ValueError, match="CORS_ORIGINS must contain only HTTPS origins"
        ):
            Settings(
                ENVIRONMENT="staging",
                CORS_ORIGINS=["*"],
                JWT_SECRET_KEY="a" * 32,
                SETTINGS_ENCRYPTION_KEY="e" * 32,
            )


class TestCookieSettings:
    def test_development_cookie_defaults_allow_local_http(self):
        """开发环境默认允许 http，且不设置 Domain。"""
        settings = Settings(ENVIRONMENT="development")
        assert settings.COOKIE_SECURE is False
        assert settings.COOKIE_DOMAIN is None
        assert settings.COOKIE_SAMESITE == "lax"

    def test_production_rejects_insecure_cookie(self):
        """生产环境仅允许 Secure Cookie，否则拒绝启动。"""
        runtime = dict(_production_runtime_settings("production"))
        runtime["COOKIE_SECURE"] = False
        with pytest.raises(
            ValueError, match="COOKIE_SECURE must be enabled in production environment"
        ):
            Settings(
                ENVIRONMENT="production",
                DEBUG=False,
                CORS_ORIGINS=["https://sciminer.example.com"],
                JWT_SECRET_KEY="a" * 32,
                SETTINGS_ENCRYPTION_KEY="e" * 32,
                **runtime,
            )


class TestSettingsEncryptionKey:
    @pytest.mark.parametrize("environment", ["staging", "production"])
    def test_deployment_environment_rejects_missing_settings_encryption_key(
        self, environment
    ):
        """预发布和生产环境必须设置独立的配置加密密钥。"""
        with pytest.raises(
            ValueError, match="SETTINGS_ENCRYPTION_KEY must be configured"
        ):
            Settings(
                ENVIRONMENT=environment,
                DEBUG=False,
                CORS_ORIGINS=["https://sciminer.example.com"],
                JWT_SECRET_KEY="j" * 32,
                SETTINGS_ENCRYPTION_KEY=None,
            )

    @pytest.mark.parametrize("environment", ["staging", "production"])
    def test_deployment_environment_rejects_empty_settings_encryption_key(
        self, environment
    ):
        """预发布和生产环境拒绝空字符串配置加密密钥。"""
        with pytest.raises(
            ValueError, match="SETTINGS_ENCRYPTION_KEY must be configured"
        ):
            Settings(
                ENVIRONMENT=environment,
                DEBUG=False,
                CORS_ORIGINS=["https://sciminer.example.com"],
                JWT_SECRET_KEY="j" * 32,
                SETTINGS_ENCRYPTION_KEY="",
            )

    @pytest.mark.parametrize("environment", ["staging", "production"])
    def test_deployment_environment_rejects_short_settings_encryption_key(
        self, environment
    ):
        """预发布和生产环境拒绝过短的配置加密密钥。"""
        with pytest.raises(
            ValueError, match="SETTINGS_ENCRYPTION_KEY must be at least 32 characters"
        ):
            Settings(
                ENVIRONMENT=environment,
                DEBUG=False,
                CORS_ORIGINS=["https://sciminer.example.com"],
                JWT_SECRET_KEY="j" * 32,
                SETTINGS_ENCRYPTION_KEY="short",
            )

    @pytest.mark.parametrize("environment", ["staging", "production"])
    def test_deployment_environment_rejects_reused_jwt_secret_as_settings_encryption_key(
        self, environment
    ):
        """预发布和生产环境禁止复用 JWT 密钥作为配置加密密钥。"""
        shared_key = "s" * 32
        with pytest.raises(
            ValueError, match="SETTINGS_ENCRYPTION_KEY must differ from JWT_SECRET_KEY"
        ):
            Settings(
                ENVIRONMENT=environment,
                DEBUG=False,
                CORS_ORIGINS=["https://sciminer.example.com"],
                JWT_SECRET_KEY=shared_key,
                SETTINGS_ENCRYPTION_KEY=shared_key,
            )

    @pytest.mark.parametrize("environment", ["staging", "production"])
    def test_deployment_environment_accepts_distinct_valid_settings_encryption_key(
        self, environment
    ):
        """预发布和生产环境接受独立且足够长的配置加密密钥。"""
        settings = Settings(
            ENVIRONMENT=environment,
            DEBUG=False,
            CORS_ORIGINS=["https://sciminer.example.com"],
            JWT_SECRET_KEY="j" * 32,
            SETTINGS_ENCRYPTION_KEY="e" * 32,
            **_production_runtime_settings(environment),
        )
        assert settings.SETTINGS_ENCRYPTION_KEY == "e" * 32

    def test_development_allows_missing_settings_encryption_key(self):
        """开发环境保留缺失配置加密密钥的兼容行为。"""
        settings = Settings(ENVIRONMENT="development", SETTINGS_ENCRYPTION_KEY=None)
        assert settings.SETTINGS_ENCRYPTION_KEY is None


class TestDeploymentHardeningSettings:
    """P2 配置加固：主机白名单、文档开关、限流后端与失败模式。"""

    def _base(self, **overrides):
        kwargs = {
            "ENVIRONMENT": "production",
            "DEBUG": False,
            "CORS_ORIGINS": ["https://sciminer.example.com"],
            "JWT_SECRET_KEY": "j" * 32,
            "SETTINGS_ENCRYPTION_KEY": "e" * 32,
            **_production_runtime_settings("production"),
        }
        kwargs.update(overrides)
        return kwargs

    def test_production_rejects_wildcard_or_missing_allowed_hosts(self):
        for hosts in (["*"], [], ["  "]):
            with pytest.raises(ValueError, match="ALLOWED_HOSTS"):
                Settings(**self._base(ALLOWED_HOSTS=hosts))

    def test_production_rejects_memory_rate_limit_backend(self):
        with pytest.raises(ValueError, match="RATE_LIMIT_BACKEND"):
            Settings(**self._base(RATE_LIMIT_BACKEND="memory"))

    def test_production_rejects_fail_open_rate_limit(self):
        with pytest.raises(ValueError, match="RATE_LIMIT_FAIL_MODE"):
            Settings(**self._base(RATE_LIMIT_FAIL_MODE="open"))

    def test_development_defaults_are_safe_and_overridable(self):
        dev = Settings(ENVIRONMENT="development")
        assert dev.docs_enabled is True
        assert dev.resolved_rate_limit_backend == "memory"
        assert dev.RATE_LIMIT_FAIL_MODE == "closed"

        explicit = Settings(
            ENVIRONMENT="development",
            ENABLE_DOCS=False,
            RATE_LIMIT_BACKEND="redis",
            RATE_LIMIT_FAIL_MODE="open",
        )
        assert explicit.docs_enabled is False
        assert explicit.resolved_rate_limit_backend == "redis"
        assert explicit.RATE_LIMIT_FAIL_MODE == "open"


class TestSsoSessionSettings:
    """统一认证会话续期/登出相关配置：宽限期上下界与登出回跳地址校验。"""

    def _base(self, **overrides):
        kwargs = {
            "ENVIRONMENT": "production",
            "DEBUG": False,
            "CORS_ORIGINS": ["https://sciminer.example.com"],
            "JWT_SECRET_KEY": "j" * 32,
            "SETTINGS_ENCRYPTION_KEY": "e" * 32,
            **_production_runtime_settings("production"),
        }
        kwargs.update(overrides)
        return kwargs

    def test_negative_offline_grace_is_rejected(self):
        """宽限期为负没有含义，直接拒绝启动。"""
        with pytest.raises(ValueError, match="SSO_OFFLINE_GRACE_SECONDS must be >= 0"):
            Settings(ENVIRONMENT="development", SSO_OFFLINE_GRACE_SECONDS=-1)

    def test_offline_grace_longer_than_refresh_lifetime_is_rejected(self):
        """宽限期不得长于平台 refresh 本身寿命，否则等于永久放行。"""
        with pytest.raises(
            ValueError,
            match="SSO_OFFLINE_GRACE_SECONDS must not exceed refresh token lifetime",
        ):
            Settings(
                ENVIRONMENT="development",
                REFRESH_TOKEN_EXPIRE_DAYS=1,
                SSO_OFFLINE_GRACE_SECONDS=86401,
            )

    def test_offline_grace_equal_to_refresh_lifetime_is_accepted(self):
        settings = Settings(
            ENVIRONMENT="development",
            REFRESH_TOKEN_EXPIRE_DAYS=1,
            SSO_OFFLINE_GRACE_SECONDS=86400,
        )
        assert settings.SSO_OFFLINE_GRACE_SECONDS == 86400

    def test_zero_offline_grace_means_strict_fail_closed(self):
        settings = Settings(ENVIRONMENT="development", SSO_OFFLINE_GRACE_SECONDS=0)
        assert settings.SSO_OFFLINE_GRACE_SECONDS == 0

    @pytest.mark.parametrize(
        "redirect",
        [
            "/login?sso_logout=1",
            "javascript:alert(1)",
            "https://aidd.example.internal/login?sso_logout=1\nX-Injected: 1",
            "https:///login",
        ],
    )
    def test_logout_redirect_requires_absolute_http_url(self, redirect):
        """相对路径、伪协议、含控制字符、缺主机名的地址一律拒绝。"""
        with pytest.raises(ValueError, match="SSO_LOGOUT_REDIRECT_URI"):
            Settings(ENVIRONMENT="development", SSO_LOGOUT_REDIRECT_URI=redirect)

    @pytest.mark.parametrize("environment", ["staging", "production"])
    def test_logout_redirect_must_be_https_in_deployment(self, environment):
        with pytest.raises(
            ValueError,
            match="SSO_LOGOUT_REDIRECT_URI must use https in staging/production",
        ):
            Settings(
                **self._base(
                    ENVIRONMENT=environment,
                    SSO_LOGOUT_REDIRECT_URI=(
                        "http://aidd.example.internal/login?sso_logout=1"
                    ),
                )
            )

    def test_logout_redirect_accepts_https_in_production(self):
        settings = Settings(
            SSO_LOGOUT_REDIRECT_URI="https://aidd.example.internal/login?sso_logout=1",
            **self._base(),
        )
        assert settings.SSO_LOGOUT_REDIRECT_URI.startswith("https://aidd.example.internal/")

    def test_empty_logout_redirect_falls_back_to_derivation(self):
        """留空合法：由 SSO_REDIRECT_URI 推导，不算配置错误。"""
        settings = Settings(ENVIRONMENT="development", SSO_LOGOUT_REDIRECT_URI="  ")
        assert settings.SSO_LOGOUT_REDIRECT_URI == "  "

    def test_env_example_documents_sso_session_keys(self):
        """示例环境文件必须同时给出宽限期与登出回跳地址，避免上线时靠猜。"""
        example = Path(__file__).resolve().parents[1] / "backend" / ".env.example"
        contents = example.read_text(encoding="utf-8")

        assert "SSO_OFFLINE_GRACE_SECONDS=86400" in contents
        assert "SSO_LOGOUT_REDIRECT_URI=https://aidd.example.internal/login?sso_logout=1" in contents
        assert "0 表示严格失败关闭" in contents
