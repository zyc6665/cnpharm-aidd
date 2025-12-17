# backend/app/auth/__init__.py
"""认证授权模块"""
from app.auth.jwt_handler import jwt_handler, create_access_token, create_refresh_token
from app.auth.password import hash_password, verify_password
from app.auth.dependencies import get_current_user, get_current_user_optional, get_admin_user
from app.auth.guest_manager import (
    GuestManager,
    GuestSessionError,
    GuestQuotaExceededError,
    guest_manager
)

__all__ = [
    "jwt_handler",
    "create_access_token",
    "create_refresh_token",
    "hash_password",
    "verify_password",
    "get_current_user",
    "get_current_user_optional",
    "get_admin_user",
    "GuestManager",
    "GuestSessionError",
    "GuestQuotaExceededError",
    "guest_manager",
]
