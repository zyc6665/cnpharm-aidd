from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import resolve_database_url  # noqa: E402


def test_resolve_database_url_anchors_relative_sqlite_path_to_backend_root() -> None:
    resolved = resolve_database_url("sqlite+aiosqlite:///./storage/scitool.db")
    expected_path = (BACKEND_ROOT / "storage" / "scitool.db").resolve()

    assert resolved == f"sqlite+aiosqlite:///{expected_path.as_posix()}"


def test_resolve_database_url_keeps_non_sqlite_url_unchanged() -> None:
    raw = "postgresql+asyncpg://user:pass@localhost:5432/scitool"
    assert resolve_database_url(raw) == raw
