"""Workflow run access helper tests."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.common.exceptions import ForbiddenException  # noqa: E402
from app.services.workflow_run_access import (  # noqa: E402
    ensure_run_operation_access,
    is_admin,
)


def test_is_admin_checks_role_value():
    assert is_admin(SimpleNamespace(role="admin")) is True
    assert is_admin(SimpleNamespace(role="user")) is False


@pytest.mark.asyncio
async def test_ensure_run_operation_access_allows_owner_without_project_lookup():
    user = SimpleNamespace(id="owner-1", role="user")
    run = SimpleNamespace(owner_id="owner-1", project_id=None)

    await ensure_run_operation_access(None, run=run, current_user=user)


@pytest.mark.asyncio
async def test_ensure_run_operation_access_rejects_projectless_non_owner():
    user = SimpleNamespace(id="user-1", role="user")
    run = SimpleNamespace(owner_id="owner-1", project_id=None)

    with pytest.raises(ForbiddenException, match="No permission"):
        await ensure_run_operation_access(None, run=run, current_user=user)
