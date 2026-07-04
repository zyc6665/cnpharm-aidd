import pytest

from app.api.v1.auth import validate_invitation_code
from app.schemas.users import InvitationCodeValidateRequest


@pytest.mark.asyncio
async def test_validate_invitation_code_returns_disabled_state():
    """没有邀请数据源时，邀请码校验应明确返回无效，避免前端模拟有效。"""
    response = await validate_invitation_code(InvitationCodeValidateRequest(code="ABC123"))

    assert response["code"] == 200
    assert response["data"] == {"valid": False, "bonus": None}
    assert "未启用" in response["message"]
