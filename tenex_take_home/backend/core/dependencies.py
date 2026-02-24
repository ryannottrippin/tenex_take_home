from fastapi import Request

from core.exceptions import AppException


async def get_current_user(request: Request) -> dict:
    """Dependency that returns the session user or raises 401."""
    user = request.session.get("user")
    if not user:
        raise AppException(401, "Not authenticated")
    return user
