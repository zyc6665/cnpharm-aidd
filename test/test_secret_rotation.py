"""G-05：加密密钥轮换。

`MultiFernet` 的语义钉子（首钥加密、其余钥解密）+ `iam_session` 在轮换后不掉线。
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.fernet import InvalidToken

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.common import secret_crypto  # noqa: E402


OLD_KEY = "old" * 11  # 33 字符，够 32
NEW_KEY = "new" * 11


def _install(monkeypatch, *, keys=None, single=None, environment="production", jwt="j" * 32):
    """替换 secret_crypto 模块里的 settings。

    ``keys=None`` 表示**不设**该属性：禁改的 ``test/test_secret_crypto.py`` 用的正是
    这种 ``SimpleNamespace``，逼着实现必须用 ``getattr`` 兜底。
    """
    from types import SimpleNamespace

    fake = SimpleNamespace(
        ENVIRONMENT=environment,
        JWT_SECRET_KEY=jwt,
        SETTINGS_ENCRYPTION_KEY=single,
    )
    if keys is not None:
        fake.SETTINGS_ENCRYPTION_KEYS = keys
    monkeypatch.setattr(secret_crypto, "settings", fake)
    return fake


def _single(raw_key):
    """用同一派生逻辑造「单钥 Fernet」，模拟旧版本写下的密文。"""
    return secret_crypto._derive_fernet(raw_key)


def test_rotate_keeps_old_ciphertext_readable(monkeypatch):
    """轮换的核心承诺：换钥后旧密文仍能解开，不需要迁移脚本。"""
    _install(monkeypatch, keys=None, single=OLD_KEY)
    old_ciphertext = secret_crypto.encrypt_secret("iam-refresh-token")

    _install(monkeypatch, keys=[NEW_KEY, OLD_KEY])

    assert secret_crypto.decrypt_secret(old_ciphertext) == "iam-refresh-token"


def test_new_ciphertext_is_not_decryptable_by_old_key(monkeypatch):
    """加密只用首钥：切回旧钥必须解不开（异常类型仍是 InvalidToken）。"""
    _install(monkeypatch, keys=[NEW_KEY, OLD_KEY])
    fresh = secret_crypto.encrypt_secret("fresh")

    _install(monkeypatch, keys=None, single=OLD_KEY)

    with pytest.raises(InvalidToken):
        secret_crypto.decrypt_secret(fresh)


def test_empty_keys_falls_back_to_single_key(monkeypatch):
    """空列表 = 退回单键路径：既有部署不改配置也不会变行为。"""
    _install(monkeypatch, keys=[], single=OLD_KEY)

    assert secret_crypto.decrypt_secret(secret_crypto.encrypt_secret("x")) == "x"
    # 旧版本（引入列表之前）写下的密文同样可读。
    legacy = _single(OLD_KEY).encrypt(b"legacy").decode("utf-8")
    assert secret_crypto.decrypt_secret(legacy) == "legacy"


def test_first_key_in_list_encrypts(monkeypatch):
    """顺序即语义：写反了等于用旧钥加密，轮换白做。"""
    _install(monkeypatch, keys=[NEW_KEY, OLD_KEY])

    ciphertext = secret_crypto.encrypt_secret("payload")

    assert _single(NEW_KEY).decrypt(ciphertext.encode("utf-8")) == b"payload"
    with pytest.raises(InvalidToken):
        _single(OLD_KEY).decrypt(ciphertext.encode("utf-8"))


def test_missing_new_attribute_uses_single_key_path(monkeypatch):
    """没有 SETTINGS_ENCRYPTION_KEYS 属性的 settings 也要能跑（getattr 兜底）。"""
    _install(monkeypatch, keys=None, single=OLD_KEY)

    assert secret_crypto.decrypt_secret(secret_crypto.encrypt_secret("y")) == "y"


def test_missing_keys_outside_development_raises_runtimeerror(monkeypatch):
    """非开发环境缺密钥：异常类型与原文都不能变（运维按文案排障）。"""
    _install(monkeypatch, keys=[], single=None, environment="production")

    with pytest.raises(
        RuntimeError, match="SETTINGS_ENCRYPTION_KEY must be configured outside development"
    ):
        secret_crypto.encrypt_secret("z")


def test_iam_session_survives_rotation(monkeypatch):
    """端到端：轮换后 iam_session 打开旧票据仍成功，不会 40103 全员掉线。"""
    from app.services import iam_session

    _install(monkeypatch, keys=None, single=OLD_KEY)
    sealed = iam_session.seal_ticket_columns(
        iam_session.IamTickets(
            access_token="a-token",
            refresh_token="r-token",
            access_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            checked_at=datetime.now(timezone.utc),
        )
    )

    _install(monkeypatch, keys=[NEW_KEY, OLD_KEY])
    opened = iam_session.open_tickets(
        access_token_enc=sealed["access_token_enc"],
        refresh_token_enc=sealed["refresh_token_enc"],
        access_expires_at=sealed["access_expires_at"],
        checked_at=sealed["checked_at"],
    )

    assert opened.access_token == "a-token"
    assert opened.refresh_token == "r-token"
