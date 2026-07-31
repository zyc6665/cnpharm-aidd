"""Runtime feature flag helpers for staged AIDD rollout."""

from collections.abc import Callable

from fastapi import Depends, HTTPException

from app.auth.dependencies import get_current_user
from app.config import settings
from app.models.users import User


def require_feature_flag(flag_key: str) -> Callable[..., None]:
    """Return a FastAPI dependency that hides disabled feature surfaces."""

    def dependency(current_user: User = Depends(get_current_user)) -> None:
        if not settings.is_aidd_feature_enabled_for_user(
            flag_key,
            user_email=current_user.email,
            user_id=current_user.id,
        ):
            raise HTTPException(status_code=404, detail=f"功能未启用: {flag_key}")

    return dependency
