# backend/app/services/verification/__init__.py
"""验证码服务模块"""

from app.services.verification.service import VerificationService
from app.services.verification.storage import (
    VerificationStorageBase,
    DatabaseStorage,
    CacheStorage,
    get_verification_storage
)

__all__ = [
    "VerificationService",
    "VerificationStorageBase",
    "DatabaseStorage",
    "CacheStorage",
    "get_verification_storage",
]
