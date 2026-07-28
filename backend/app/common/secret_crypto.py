"""Helpers for encrypting runtime secrets."""

import base64
import hashlib
import logging
import threading
from typing import Optional

from cryptography.fernet import Fernet

from app.config import settings


logger = logging.getLogger(__name__)
_fallback_warning_emitted = False
_fallback_warning_lock = threading.Lock()


def _fernet() -> Fernet:
    global _fallback_warning_emitted

    raw_key = settings.SETTINGS_ENCRYPTION_KEY
    if not raw_key and settings.ENVIRONMENT == "development":
        with _fallback_warning_lock:
            if not _fallback_warning_emitted:
                logger.warning(
                    "SETTINGS_ENCRYPTION_KEY is not configured; falling back to JWT_SECRET_KEY in development"
                )
                _fallback_warning_emitted = True
        raw_key = settings.JWT_SECRET_KEY

    if not raw_key:
        if settings.ENVIRONMENT == "development":
            raise RuntimeError("JWT_SECRET_KEY must be configured for development fallback")
        raise RuntimeError("SETTINGS_ENCRYPTION_KEY must be configured outside development")

    digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")


def mask_secret(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    if len(value) <= 8:
        return "****"
    return f"{value[:3]}****{value[-4:]}"
