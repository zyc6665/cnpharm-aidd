import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.common.secret_crypto import decrypt_secret, encrypt_secret, mask_secret


def test_secret_round_trip():
    encrypted = encrypt_secret("sk-test-secret")

    assert encrypted != "sk-test-secret"
    assert decrypt_secret(encrypted) == "sk-test-secret"


def test_secret_masking():
    assert mask_secret(None) is None
    assert mask_secret("sk-1234567890") == "sk-****7890"
