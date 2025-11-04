"""
Authentication and authorization utilities
"""
import os
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

# API Key header
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


def get_configured_api_key() -> str:
    """Get the configured API key from environment (dynamic lookup)"""
    return os.getenv("API_KEY")


async def require_api_key(api_key: str = Security(api_key_header)):
    """
    Dependency to require API key authentication for write operations

    Raises:
        HTTPException: 401 if API key is missing or invalid
    """
    configured_key = get_configured_api_key()

    if not configured_key:
        # If no API key is configured, deny access for security
        raise HTTPException(
            status_code=500,
            detail="API authentication not configured"
        )

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required for this operation"
        )

    if api_key != configured_key:
        raise HTTPException(
            status_code=403,
            detail="Invalid API key"
        )

    return api_key
