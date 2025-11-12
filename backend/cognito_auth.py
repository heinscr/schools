"""
AWS Cognito JWT authentication utilities
Validates JWT tokens from AWS Cognito and extracts user information
"""
import os
import json
from typing import Optional, Dict
from functools import lru_cache
import requests
from jose import jwt, JWTError
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# HTTP Bearer token security
security = HTTPBearer(auto_error=False)


@lru_cache()
def get_cognito_config() -> Dict[str, str]:
    """Get Cognito configuration from environment variables"""
    return {
        "user_pool_id": os.getenv("COGNITO_USER_POOL_ID", ""),
        "client_id": os.getenv("COGNITO_CLIENT_ID", ""),
        "region": os.getenv("COGNITO_REGION", "us-east-1"),
    }


@lru_cache()
def get_cognito_keys():
    """
    Fetch and cache Cognito public keys for JWT verification
    Keys are cached to avoid repeated requests
    """
    config = get_cognito_config()
    user_pool_id = config["user_pool_id"]
    region = config["region"]

    if not user_pool_id:
        return {}

    keys_url = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/jwks.json"

    try:
        response = requests.get(keys_url, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        # If we can't fetch keys, return empty dict
        # This allows the app to start without Cognito being fully configured
        return {}


def verify_cognito_token(token: str) -> Dict:
    """
    Verify and decode a Cognito JWT token

    Args:
        token: JWT token string

    Returns:
        Dict containing decoded token claims

    Raises:
        HTTPException: If token is invalid or verification fails
    """
    config = get_cognito_config()

    if not config["user_pool_id"]:
        raise HTTPException(
            status_code=500,
            detail="Cognito authentication not configured"
        )

    # Get Cognito public keys
    keys = get_cognito_keys()
    if not keys or "keys" not in keys:
        raise HTTPException(
            status_code=500,
            detail="Unable to verify tokens - Cognito keys unavailable"
        )

    try:
        # Get the key ID from the token header
        try:
            headers = jwt.get_unverified_headers(token)
        except Exception:
            # Invalid JWT format
            raise HTTPException(
                status_code=401,
                detail="Invalid token format"
            )

        kid = headers.get("kid")

        if not kid:
            raise HTTPException(
                status_code=401,
                detail="Invalid token: missing key ID"
            )

        # Find the matching key
        key = None
        for k in keys["keys"]:
            if k["kid"] == kid:
                key = k
                break

        if not key:
            raise HTTPException(
                status_code=401,
                detail="Invalid token: key not found"
            )

        # Verify and decode the token
        issuer = f"https://cognito-idp.{config['region']}.amazonaws.com/{config['user_pool_id']}"

        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=config["client_id"],
            issuer=issuer,
            options={
                "verify_exp": True,
                "verify_at_hash": False  # Skip at_hash verification since we only have ID token
            }
        )

        return claims

    except HTTPException:
        # Re-raise HTTPExceptions as-is
        raise
    except JWTError as e:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid token: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail=f"Token verification failed: {str(e)}"
        )


def get_user_from_token(claims: Dict) -> Dict:
    """
    Extract user information from JWT claims

    Args:
        claims: Decoded JWT claims

    Returns:
        Dict containing user information (email, sub, groups, custom:role)
    """
    # Get user groups from token (if present)
    groups = claims.get("cognito:groups", [])

    return {
        "sub": claims.get("sub"),  # User ID
        "email": claims.get("email"),
        "groups": groups,
        "is_admin": "admins" in groups,
        "custom_role": claims.get("custom:role", ""),
        "username": claims.get("cognito:username", claims.get("email", ""))
    }


async def require_cognito_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> Dict:
    """
    FastAPI dependency to require Cognito JWT authentication

    Args:
        credentials: HTTP Bearer token credentials

    Returns:
        Dict containing user information

    Raises:
        HTTPException: 401 if authentication fails
    """
    # Local dev shortcut: allow a fake user when LOCAL_DEV=1
    if os.getenv("LOCAL_DEV", "0") == "1":
        return {
            "sub": "local-test-user",
            "email": "local@localhost",
            "groups": ["admins"],
            "is_admin": True,
            "username": "local"
        }

    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please log in."
        )

    token = credentials.credentials
    claims = verify_cognito_token(token)
    user = get_user_from_token(claims)

    return user


async def require_admin_role(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> Dict:
    """
    FastAPI dependency to require admin role

    Args:
        credentials: HTTP Bearer token credentials

    Returns:
        Dict containing user information

    Raises:
        HTTPException: 401 if not authenticated, 403 if not admin
    """
    user = await require_cognito_auth(credentials)

    if not user.get("is_admin"):
        raise HTTPException(
            status_code=403,
            detail="Admin role required for this operation"
        )

    return user


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> Optional[Dict]:
    """
    FastAPI dependency to optionally get current user
    Returns user info if authenticated, None if not

    Args:
        credentials: HTTP Bearer token credentials

    Returns:
        Dict containing user information or None
    """
    if not credentials:
        return None

    try:
        token = credentials.credentials
        claims = verify_cognito_token(token)
        user = get_user_from_token(claims)
        return user
    except HTTPException:
        return None
