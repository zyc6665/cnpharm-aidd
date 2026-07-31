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
        assert "生产/预发布环境" in contents
        assert "独立" in contents
        assert "自动生成临时密钥" not in contents
        assert "SETTINGS_ENCRYPTION_KEY 缺失时回退到 JWT_SECRET_KEY" in contents
        assert "二者都缺失时，加密操作会失败" in contents


class TestAiddFeatureFlags:
    def test_development_feature_flags_default_open_for_local_iteration(self):
        """开发环境默认开启首月 AIDD 功能，避免本地页面不可访问。"""
        settings = Settings(ENVIRONMENT="development")
        flags = {item["key"]: item for item in settings.aidd_feature_flags()}

        assert flags["AIDD_PROJECT_WORKSPACE_ENABLED"]["enabled"] is True
        assert flags["AIDD_PROJECT_CONVERSATIONS_ENABLED"]["enabled"] is True
        assert flags["TOOL_PACKAGE_V1_ENABLED"]["enabled"] is True
        assert flags["PROJECT_RESEARCH_BOARD_ENABLED"]["enabled"] is True
        assert flags["LEGACY_AIDD_API_ENABLED"]["enabled"] is True
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
        assert flags["AIDD_PROJECT_CONVERSATIONS_ENABLED"]["enabled"] is False
        assert flags["TOOL_PACKAGE_V1_ENABLED"]["enabled"] is False
        assert flags["PROJECT_RESEARCH_BOARD_ENABLED"]["enabled"] is False
        assert flags["LEGACY_AIDD_API_ENABLED"]["enabled"] is True

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
            "AIDD_PROJECT_CONVERSATIONS_ENABLED",
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
    def test_development_allows_empty_jwt_secret(self):
        """开发环境允许 JWT_SECRET_KEY 为空。"""
        settings = Settings(ENVIRONMENT="development", JWT_SECRET_KEY="")
        assert settings.JWT_SECRET_KEY == ""

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
