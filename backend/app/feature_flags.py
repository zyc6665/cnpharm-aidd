"""Runtime feature flag helpers for staged AIDD rollout."""

from collections.abc import Callable

from fastapi import HTTPException

from app.config import settings


def require_feature_flag(flag_key: str) -> Callable[[], None]:
    """Return a FastAPI dependency that hides disabled feature surfaces."""

    def dependency() -> None:
        if not settings.is_aidd_feature_enabled(flag_key):
            raise HTTPException(status_code=404, detail=f"功能未启用: {flag_key}")

    return dependency
