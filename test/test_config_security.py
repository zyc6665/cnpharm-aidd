"""Tests for configuration security rules."""

import os

import pytest

from app.config import Settings


class TestJWTSecretKey:
    def test_development_allows_empty_jwt_secret(self):
        """开发环境允许 JWT_SECRET_KEY 为空。"""
        settings = Settings(ENVIRONMENT="development", JWT_SECRET_KEY="")
        assert settings.JWT_SECRET_KEY == ""

    def test_staging_rejects_short_jwt_secret(self):
        """预发布环境拒绝长度不足的 JWT_SECRET_KEY。"""
        with pytest.raises(ValueError, match="JWT_SECRET_KEY must be at least 32 characters"):
            Settings(ENVIRONMENT="staging", JWT_SECRET_KEY="short")

    def test_production_rejects_short_jwt_secret(self):
        """生产环境拒绝长度不足的 JWT_SECRET_KEY。"""
        with pytest.raises(ValueError, match="JWT_SECRET_KEY must be at least 32 characters"):
            Settings(ENVIRONMENT="production", JWT_SECRET_KEY="short")

    def test_staging_accepts_long_jwt_secret(self):
        """预发布环境接受长度不少于 32 的 JWT_SECRET_KEY。"""
        long_key = "a" * 32
        settings = Settings(
            ENVIRONMENT="staging",
            CORS_ORIGINS=["https://staging.sciminer.example.com"],
            JWT_SECRET_KEY=long_key,
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
            )

    def test_production_rejects_wildcard_cors_with_credentials(self):
        """生产环境拒绝通配 CORS。"""
        with pytest.raises(ValueError, match="CORS_ORIGINS must not contain"):
            Settings(
                ENVIRONMENT="production",
                DEBUG=False,
                CORS_ORIGINS=["*"],
                JWT_SECRET_KEY="a" * 32,
            )

    def test_staging_rejects_wildcard_cors_with_credentials(self):
        """预发布环境拒绝通配 CORS。"""
        with pytest.raises(ValueError, match="CORS_ORIGINS must not contain"):
            Settings(
                ENVIRONMENT="staging",
                CORS_ORIGINS=["*"],
                JWT_SECRET_KEY="a" * 32,
            )
