from concurrent.futures import ThreadPoolExecutor
import logging
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.common import secret_crypto
from app.common.secret_crypto import decrypt_secret, encrypt_secret, mask_secret
from app.config import Settings


def test_secret_round_trip():
    encrypted = encrypt_secret("sk-test-secret")

    assert encrypted != "sk-test-secret"
    assert decrypt_secret(encrypted) == "sk-test-secret"


def test_secret_masking():
    assert mask_secret(None) is None
    assert mask_secret("sk-1234567890") == "sk-****7890"


def test_development_fallback_to_jwt_key_warns_once(monkeypatch, caplog):
    development_settings = Settings(
        ENVIRONMENT="development",
        JWT_SECRET_KEY="j" * 32,
        SETTINGS_ENCRYPTION_KEY=None,
    )
    monkeypatch.setattr(secret_crypto, "settings", development_settings)
    monkeypatch.setattr(secret_crypto, "_fallback_warning_emitted", False)

    with caplog.at_level(logging.WARNING, logger=secret_crypto.__name__):
        encrypted_first = secret_crypto.encrypt_secret("first-secret")
        encrypted_second = secret_crypto.encrypt_secret("second-secret")

    assert secret_crypto.decrypt_secret(encrypted_first) == "first-secret"
    assert secret_crypto.decrypt_secret(encrypted_second) == "second-secret"
    warnings = [
        record
        for record in caplog.records
        if record.name == secret_crypto.__name__
        and "SETTINGS_ENCRYPTION_KEY" in record.getMessage()
    ]
    assert len(warnings) == 1


def test_development_uses_dedicated_encryption_key_without_fallback_warning(monkeypatch, caplog):
    development_settings = Settings(
        ENVIRONMENT="development",
        JWT_SECRET_KEY="j" * 32,
        SETTINGS_ENCRYPTION_KEY="e" * 32,
    )
    monkeypatch.setattr(secret_crypto, "settings", development_settings)
    monkeypatch.setattr(secret_crypto, "_fallback_warning_emitted", False)

    with caplog.at_level(logging.WARNING, logger=secret_crypto.__name__):
        encrypted = secret_crypto.encrypt_secret("dedicated-key-secret")

    monkeypatch.setattr(
        secret_crypto,
        "settings",
        Settings(
            ENVIRONMENT="development",
            JWT_SECRET_KEY="different-jwt-secret-key-value-123",
            SETTINGS_ENCRYPTION_KEY="e" * 32,
        ),
    )
    assert secret_crypto.decrypt_secret(encrypted) == "dedicated-key-secret"
    assert not [
        record
        for record in caplog.records
        if record.name == secret_crypto.__name__
        and "SETTINGS_ENCRYPTION_KEY" in record.getMessage()
    ]


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_non_development_missing_encryption_key_does_not_fallback_to_jwt(
    monkeypatch, caplog, environment
):
    monkeypatch.setattr(
        secret_crypto,
        "settings",
        SimpleNamespace(
            ENVIRONMENT=environment,
            JWT_SECRET_KEY="j" * 32,
            SETTINGS_ENCRYPTION_KEY=None,
        ),
    )
    monkeypatch.setattr(secret_crypto, "_fallback_warning_emitted", False)

    with caplog.at_level(logging.WARNING, logger=secret_crypto.__name__):
        with pytest.raises(RuntimeError, match="SETTINGS_ENCRYPTION_KEY"):
            secret_crypto.encrypt_secret("must-not-use-jwt")

    assert not [record for record in caplog.records if record.name == secret_crypto.__name__]


def test_development_missing_both_encryption_keys_explains_fallback_requirement(monkeypatch):
    monkeypatch.setattr(
        secret_crypto,
        "settings",
        SimpleNamespace(
            ENVIRONMENT="development",
            JWT_SECRET_KEY="",
            SETTINGS_ENCRYPTION_KEY=None,
        ),
    )
    monkeypatch.setattr(secret_crypto, "_fallback_warning_emitted", False)

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY must be configured for development fallback"):
        secret_crypto.encrypt_secret("no-key")


def test_concurrent_development_fallback_warns_once(monkeypatch, caplog):
    lock_entered = threading.Event()

    class TrackingLock:
        def __init__(self):
            self._lock = threading.Lock()

        def __enter__(self):
            lock_entered.set()
            self._lock.acquire()
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            self._lock.release()

    class RacingFlag:
        def __init__(self, barrier):
            self._barrier = barrier

        def __bool__(self):
            if lock_entered.is_set():
                return False
            try:
                self._barrier.wait()
            except threading.BrokenBarrierError:
                pass
            return False

    development_settings = Settings(
        ENVIRONMENT="development",
        JWT_SECRET_KEY="j" * 32,
        SETTINGS_ENCRYPTION_KEY=None,
    )
    monkeypatch.setattr(secret_crypto, "settings", development_settings)
    monkeypatch.setattr(secret_crypto, "_fallback_warning_lock", TrackingLock())
    monkeypatch.setattr(
        secret_crypto,
        "_fallback_warning_emitted",
        RacingFlag(threading.Barrier(4, timeout=2)),
    )

    with caplog.at_level(logging.WARNING, logger=secret_crypto.__name__):
        with ThreadPoolExecutor(max_workers=4) as executor:
            encrypted_values = list(
                executor.map(secret_crypto.encrypt_secret, ["a", "b", "c", "d"])
            )

    assert [secret_crypto.decrypt_secret(value) for value in encrypted_values] == ["a", "b", "c", "d"]
    warnings = [
        record
        for record in caplog.records
        if record.name == secret_crypto.__name__
        and "SETTINGS_ENCRYPTION_KEY" in record.getMessage()
    ]
    assert lock_entered.is_set()
    assert len(warnings) == 1
