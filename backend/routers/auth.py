"""
Authentication endpoints
"""
from fastapi import APIRouter, Depends, Request

from cognito_auth import get_current_user_optional
from rate_limiter import limiter, GENERAL_RATE_LIMIT

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/me")
@limiter.limit(GENERAL_RATE_LIMIT)
async def get_current_user(
    request: Request,
    user: dict = Depends(get_current_user_optional)
):
    """Get current authenticated user information"""
    if not user:
        return {
            "authenticated": False,
            "user": None
        }

    return {
        "authenticated": True,
        "user": {
            "email": user.get("email"),
            "username": user.get("username"),
            "is_admin": user.get("is_admin", False),
            "groups": user.get("groups", [])
        }
    }
