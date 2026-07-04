import pytest

from app.api.v1 import auth
from app.api.v1.auth import guest_login, validate_invitation_code
from app.schemas.users import InvitationCodeValidateRequest


@pytest.mark.asyncio
async def test_validate_invitation_code_returns_disabled_state():
    """没有邀请数据源时，邀请码校验应明确返回无效，避免前端模拟有效。"""
    response = await validate_invitation_code(InvitationCodeValidateRequest(code="ABC123"))

    assert response["code"] == 200
    assert response["data"] == {"valid": False, "bonus": None}
    assert "未启用" in response["message"]


@pytest.mark.asyncio
async def test_guest_login_uses_guest_session_manager(monkeypatch):
    """游客登录应创建真实游客会话，而不是返回前端模拟 token。"""
    captured = {}

    class FakeGuestManager:
        async def create_guest_session(self, db, ip_address=None, user_agent=None):
            captured["db"] = db
            captured["ip_address"] = ip_address
            captured["user_agent"] = user_agent
            return {
                "guest_session_id": "guest-session-id",
                "limitations": {"daily_task_limit": 5},
                "expires_at": "2026-07-05T00:00:00",
            }

    class FakeClient:
        host = "127.0.0.1"

    class FakeRequest:
        client = FakeClient()
        headers = {"user-agent": "pytest"}

    fake_db = object()
    monkeypatch.setattr(auth, "guest_manager", FakeGuestManager())

    response = await guest_login(request=FakeRequest(), db=fake_db)

    assert captured == {
        "db": fake_db,
        "ip_address": "127.0.0.1",
        "user_agent": "pytest",
    }
    assert response["code"] == 200
    assert response["data"] == {
        "session_id": "guest-session-id",
        "expires_in": 86400,
        "limitations": {"daily_task_limit": 5},
    }
