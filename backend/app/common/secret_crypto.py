"""Helpers for encrypting runtime secrets."""

import base64
import hashlib
import logging
import threading
from typing import Optional

from cryptography.fernet import Fernet, MultiFernet

from app.config import settings


logger = logging.getLogger(__name__)
_fallback_warning_emitted = False
_fallback_warning_lock = threading.Lock()
_rotation_warning_emitted = False


def _warn_if_single_key_not_in_list(keys: list[str]) -> None:
    """半程轮换告警：列表已生效，但原单钥不在列表里 → 旧密文全部解不开。

    这是最容易被忽略的轮换形态：运维把新钥写进 ``SETTINGS_ENCRYPTION_KEYS``，
    却忘了把原来的 ``SETTINGS_ENCRYPTION_KEY`` 一起列进去。结果是「新会话正常、
    所有存量会话下次刷新 40103」——症状看起来像 IAM 侧踢人，实际是自己把旧钥丢了。
    配置本身合法（列表非空即可），只能靠日志提示。
    """
    global _rotation_warning_emitted

    single = str(getattr(settings, "SETTINGS_ENCRYPTION_KEY", "") or "").strip()
    if not single or single in keys or _rotation_warning_emitted:
        return
    with _fallback_warning_lock:
        if _rotation_warning_emitted:
            return
        _rotation_warning_emitted = True
    logger.warning(
        "SETTINGS_ENCRYPTION_KEY is not included in SETTINGS_ENCRYPTION_KEYS; "
        "ciphertext written with the former key can no longer be decrypted "
        "(all SSO sessions will fail renewal with 40103)"
    )


def _key_material() -> list[str]:
    """按优先级给出加密钥列表：首钥加密，其余只解密。

    ``SETTINGS_ENCRYPTION_KEYS`` 非空时以它为准；为空则退回单钥路径
    （``SETTINGS_ENCRYPTION_KEY``，开发环境可回退 ``JWT_SECRET_KEY``），
    此时只有一把钥，行为与改造前一致。

    用 ``getattr`` 读取新配置：``test/test_secret_crypto.py`` 用不带该属性的
    ``SimpleNamespace`` 替换 ``settings``，直接访问会 AttributeError。
    """
    global _fallback_warning_emitted

    keys = [
        str(key).strip()
        for key in (getattr(settings, "SETTINGS_ENCRYPTION_KEYS", None) or [])
    ]
    keys = [key for key in keys if key]
    if keys:
        _warn_if_single_key_not_in_list(keys)
        return keys

    raw_key = getattr(settings, "SETTINGS_ENCRYPTION_KEY", None)
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

    return [raw_key]


def _derive_fernet(raw_key: str) -> Fernet:
    """派生方式与改造前逐字一致：sha256 -> urlsafe_b64 -> Fernet。

    一个字节都不能变：存量 ``IAM_*_TOKEN_ENC`` 就是按这套派生写下的，
    改了等于把所有旧密文作废，轮换能力又从零开始。
    """
    digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _multi_fernet() -> MultiFernet:
    """首钥加密、其余钥解密；**每次调用重建**（配置改动即时生效，别加缓存）。"""
    fernets = [_derive_fernet(key) for key in _key_material()]
    if not fernets:
        # 实际不可达（``_key_material()`` 要么非空、要么已经抛），保留它是为了
        # 「别把 MultiFernet 的 ValueError 漏出去」这条口径可读：那会让
        # iam_session 的 ``except InvalidToken`` 兜不住。
        raise RuntimeError("SETTINGS_ENCRYPTION_KEY must be configured outside development")
    return MultiFernet(fernets)


def encrypt_secret(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return _multi_fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return _multi_fernet().decrypt(value.encode("utf-8")).decode("utf-8")


def mask_secret(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    if len(value) <= 8:
        return "****"
    return f"{value[:3]}****{value[-4:]}"
