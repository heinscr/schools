"""
Tests for Cognito authentication utilities
"""
import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from jose import jwt, JWTError
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import cognito_auth


class TestGetCognitoConfig:
    """Tests for get_cognito_config function"""

    def test_get_cognito_config_with_env_vars(self, monkeypatch):
        """Test retrieving Cognito config from environment variables"""
        monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_testpool")
        monkeypatch.setenv("COGNITO_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("COGNITO_REGION", "us-west-2")

        # Clear the cache to get fresh config
        cognito_auth.get_cognito_config.cache_clear()

        config = cognito_auth.get_cognito_config()

        assert config["user_pool_id"] == "us-east-1_testpool"
        assert config["client_id"] == "test-client-id"
        assert config["region"] == "us-west-2"

    def test_get_cognito_config_defaults(self, monkeypatch):
        """Test default values when environment variables are not set"""
        monkeypatch.delenv("COGNITO_USER_POOL_ID", raising=False)
        monkeypatch.delenv("COGNITO_CLIENT_ID", raising=False)
        monkeypatch.delenv("COGNITO_REGION", raising=False)

        cognito_auth.get_cognito_config.cache_clear()

        config = cognito_auth.get_cognito_config()

        assert config["user_pool_id"] == ""
        assert config["client_id"] == ""
        assert config["region"] == "us-east-1"  # Default region


class TestGetCognitoKeys:
    """Tests for get_cognito_keys function"""

    def test_get_cognito_keys_success(self, monkeypatch):
        """Test successfully fetching Cognito public keys"""
        monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_testpool")
        monkeypatch.setenv("COGNITO_REGION", "us-east-1")

        cognito_auth.get_cognito_config.cache_clear()
        cognito_auth.get_cognito_keys.cache_clear()

        mock_response = Mock()
        mock_response.json.return_value = {
            "keys": [
                {
                    "kid": "test-key-id",
                    "kty": "RSA",
                    "n": "test-modulus",
                    "e": "AQAB"
                }
            ]
        }
        mock_response.raise_for_status = Mock()

        with patch('requests.get', return_value=mock_response) as mock_get:
            keys = cognito_auth.get_cognito_keys()

            assert "keys" in keys
            assert len(keys["keys"]) == 1
            assert keys["keys"][0]["kid"] == "test-key-id"

            # Verify the URL was constructed correctly
            mock_get.assert_called_once()
            call_args = mock_get.call_args
            assert "cognito-idp.us-east-1.amazonaws.com" in call_args[0][0]
            assert "us-east-1_testpool" in call_args[0][0]

    def test_get_cognito_keys_no_pool_id(self, monkeypatch):
        """Test behavior when user pool ID is not configured"""
        monkeypatch.setenv("COGNITO_USER_POOL_ID", "")

        cognito_auth.get_cognito_config.cache_clear()
        cognito_auth.get_cognito_keys.cache_clear()

        keys = cognito_auth.get_cognito_keys()

        assert keys == {}

    def test_get_cognito_keys_request_failure(self, monkeypatch):
        """Test handling of network failures when fetching keys"""
        import requests

        monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_testpool")
        monkeypatch.setenv("COGNITO_REGION", "us-east-1")

        cognito_auth.get_cognito_config.cache_clear()
        cognito_auth.get_cognito_keys.cache_clear()

        with patch('requests.get', side_effect=requests.RequestException("Network error")):
            keys = cognito_auth.get_cognito_keys()

            # Should return empty dict on failure
            assert keys == {}


class TestVerifyCognitoToken:
    """Tests for verify_cognito_token function"""

    def test_verify_token_no_pool_id(self, monkeypatch):
        """Test error when Cognito is not configured"""
        monkeypatch.setenv("COGNITO_USER_POOL_ID", "")

        cognito_auth.get_cognito_config.cache_clear()

        with pytest.raises(HTTPException) as exc_info:
            cognito_auth.verify_cognito_token("fake-token")

        assert exc_info.value.status_code == 500
        assert "not configured" in exc_info.value.detail

    def test_verify_token_no_keys_available(self, monkeypatch):
        """Test error when Cognito keys are unavailable"""
        monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_testpool")

        cognito_auth.get_cognito_config.cache_clear()
        cognito_auth.get_cognito_keys.cache_clear()

        with patch.object(cognito_auth, 'get_cognito_keys', return_value={}):
            with pytest.raises(HTTPException) as exc_info:
                cognito_auth.verify_cognito_token("fake-token")

            assert exc_info.value.status_code == 500
            assert "keys unavailable" in exc_info.value.detail

    def test_verify_token_invalid_format(self, monkeypatch):
        """Test error with invalid token format"""
        monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_testpool")

        cognito_auth.get_cognito_config.cache_clear()
        cognito_auth.get_cognito_keys.cache_clear()

        mock_keys = {"keys": [{"kid": "test-key-id"}]}

        with patch.object(cognito_auth, 'get_cognito_keys', return_value=mock_keys):
            with pytest.raises(HTTPException) as exc_info:
                cognito_auth.verify_cognito_token("not-a-valid-jwt")

            assert exc_info.value.status_code == 401
            assert "Invalid token format" in exc_info.value.detail

    def test_verify_token_missing_kid(self, monkeypatch):
        """Test error when token header is missing key ID"""
        monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_testpool")

        cognito_auth.get_cognito_config.cache_clear()
        cognito_auth.get_cognito_keys.cache_clear()

        mock_keys = {"keys": [{"kid": "test-key-id"}]}

        with patch.object(cognito_auth, 'get_cognito_keys', return_value=mock_keys):
            with patch('jose.jwt.get_unverified_headers', return_value={}):
                with pytest.raises(HTTPException) as exc_info:
                    cognito_auth.verify_cognito_token("fake-token")

                assert exc_info.value.status_code == 401
                assert "missing key ID" in exc_info.value.detail

    def test_verify_token_key_not_found(self, monkeypatch):
        """Test error when token's key ID doesn't match any Cognito keys"""
        monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_testpool")

        cognito_auth.get_cognito_config.cache_clear()
        cognito_auth.get_cognito_keys.cache_clear()

        mock_keys = {"keys": [{"kid": "different-key-id"}]}

        with patch.object(cognito_auth, 'get_cognito_keys', return_value=mock_keys):
            with patch('jose.jwt.get_unverified_headers', return_value={"kid": "test-key-id"}):
                with pytest.raises(HTTPException) as exc_info:
                    cognito_auth.verify_cognito_token("fake-token")

                assert exc_info.value.status_code == 401
                assert "key not found" in exc_info.value.detail

    def test_verify_token_jwt_error(self, monkeypatch):
        """Test handling of JWT decode errors"""
        monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_testpool")
        monkeypatch.setenv("COGNITO_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("COGNITO_REGION", "us-east-1")

        cognito_auth.get_cognito_config.cache_clear()
        cognito_auth.get_cognito_keys.cache_clear()

        mock_keys = {"keys": [{"kid": "test-key-id", "kty": "RSA"}]}

        with patch.object(cognito_auth, 'get_cognito_keys', return_value=mock_keys):
            with patch('jose.jwt.get_unverified_headers', return_value={"kid": "test-key-id"}):
                with patch('jose.jwt.decode', side_effect=JWTError("Token expired")):
                    with pytest.raises(HTTPException) as exc_info:
                        cognito_auth.verify_cognito_token("fake-token")

                    assert exc_info.value.status_code == 401
                    assert "Invalid token" in exc_info.value.detail

    def test_verify_token_success(self, monkeypatch):
        """Test successful token verification"""
        monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_testpool")
        monkeypatch.setenv("COGNITO_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("COGNITO_REGION", "us-east-1")

        cognito_auth.get_cognito_config.cache_clear()
        cognito_auth.get_cognito_keys.cache_clear()

        mock_keys = {"keys": [{"kid": "test-key-id", "kty": "RSA"}]}
        mock_claims = {
            "sub": "user-123",
            "email": "test@example.com",
            "cognito:groups": ["users"]
        }

        with patch.object(cognito_auth, 'get_cognito_keys', return_value=mock_keys):
            with patch('jose.jwt.get_unverified_headers', return_value={"kid": "test-key-id"}):
                with patch('jose.jwt.decode', return_value=mock_claims):
                    claims = cognito_auth.verify_cognito_token("valid-token")

                    assert claims["sub"] == "user-123"
                    assert claims["email"] == "test@example.com"


class TestGetUserFromToken:
    """Tests for get_user_from_token function"""

    def test_get_user_basic_claims(self):
        """Test extracting user info from basic token claims"""
        claims = {
            "sub": "user-123",
            "email": "test@example.com",
            "cognito:groups": []
        }

        user = cognito_auth.get_user_from_token(claims)

        assert user["sub"] == "user-123"
        assert user["email"] == "test@example.com"
        assert user["groups"] == []
        assert user["is_admin"] is False
        assert user["username"] == "test@example.com"

    def test_get_user_with_admin_group(self):
        """Test admin detection from groups"""
        claims = {
            "sub": "admin-123",
            "email": "admin@example.com",
            "cognito:groups": ["admins", "users"]
        }

        user = cognito_auth.get_user_from_token(claims)

        assert user["is_admin"] is True
        assert "admins" in user["groups"]

    def test_get_user_with_custom_role(self):
        """Test extracting custom role claim"""
        claims = {
            "sub": "user-123",
            "email": "test@example.com",
            "cognito:groups": [],
            "custom:role": "editor"
        }

        user = cognito_auth.get_user_from_token(claims)

        assert user["custom_role"] == "editor"

    def test_get_user_with_username(self):
        """Test extracting username from cognito:username claim"""
        claims = {
            "sub": "user-123",
            "email": "test@example.com",
            "cognito:username": "testuser",
            "cognito:groups": []
        }

        user = cognito_auth.get_user_from_token(claims)

        assert user["username"] == "testuser"


class TestRequireCognitoAuth:
    """Tests for require_cognito_auth dependency"""

    @pytest.mark.asyncio
    async def test_require_auth_local_dev_mode(self, monkeypatch):
        """Test local dev shortcut when LOCAL_DEV=1"""
        monkeypatch.setenv("LOCAL_DEV", "1")
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        user = await cognito_auth.require_cognito_auth(None)

        assert user["email"] == "local@localhost"
        assert user["is_admin"] is True

    @pytest.mark.asyncio
    async def test_require_auth_no_local_dev_in_tests(self, monkeypatch):
        """Test that local dev shortcut is disabled during tests"""
        monkeypatch.setenv("LOCAL_DEV", "1")
        # PYTEST_CURRENT_TEST is automatically set by pytest

        with pytest.raises(HTTPException) as exc_info:
            await cognito_auth.require_cognito_auth(None)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_require_auth_no_credentials(self):
        """Test error when no credentials provided"""
        with pytest.raises(HTTPException) as exc_info:
            await cognito_auth.require_cognito_auth(None)

        assert exc_info.value.status_code == 401
        assert "Authentication required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_require_auth_success(self, monkeypatch):
        """Test successful authentication"""
        monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_testpool")

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="valid-token"
        )

        mock_claims = {
            "sub": "user-123",
            "email": "test@example.com",
            "cognito:groups": []
        }

        with patch.object(cognito_auth, 'verify_cognito_token', return_value=mock_claims):
            user = await cognito_auth.require_cognito_auth(credentials)

            assert user["sub"] == "user-123"
            assert user["email"] == "test@example.com"


class TestRequireAdminRole:
    """Tests for require_admin_role dependency"""

    @pytest.mark.asyncio
    async def test_require_admin_not_authenticated(self):
        """Test error when user is not authenticated"""
        with pytest.raises(HTTPException) as exc_info:
            await cognito_auth.require_admin_role(None)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_require_admin_not_admin(self, monkeypatch):
        """Test error when user is not an admin"""
        monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_testpool")

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="valid-token"
        )

        mock_claims = {
            "sub": "user-123",
            "email": "test@example.com",
            "cognito:groups": ["users"]  # Not in admins group
        }

        with patch.object(cognito_auth, 'verify_cognito_token', return_value=mock_claims):
            with pytest.raises(HTTPException) as exc_info:
                await cognito_auth.require_admin_role(credentials)

            assert exc_info.value.status_code == 403
            assert "Admin role required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_require_admin_success(self, monkeypatch):
        """Test successful admin authentication"""
        monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_testpool")

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="valid-token"
        )

        mock_claims = {
            "sub": "admin-123",
            "email": "admin@example.com",
            "cognito:groups": ["admins"]
        }

        with patch.object(cognito_auth, 'verify_cognito_token', return_value=mock_claims):
            user = await cognito_auth.require_admin_role(credentials)

            assert user["is_admin"] is True
            assert user["email"] == "admin@example.com"


class TestGetCurrentUserOptional:
    """Tests for get_current_user_optional dependency"""

    @pytest.mark.asyncio
    async def test_optional_auth_no_credentials(self):
        """Test returning None when no credentials provided"""
        user = await cognito_auth.get_current_user_optional(None)

        assert user is None

    @pytest.mark.asyncio
    async def test_optional_auth_invalid_token(self, monkeypatch):
        """Test returning None when token is invalid"""
        monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_testpool")

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="invalid-token"
        )

        with patch.object(cognito_auth, 'verify_cognito_token', side_effect=HTTPException(401, "Invalid")):
            user = await cognito_auth.get_current_user_optional(credentials)

            assert user is None

    @pytest.mark.asyncio
    async def test_optional_auth_success(self, monkeypatch):
        """Test successful optional authentication"""
        monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_testpool")

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="valid-token"
        )

        mock_claims = {
            "sub": "user-123",
            "email": "test@example.com",
            "cognito:groups": []
        }

        with patch.object(cognito_auth, 'verify_cognito_token', return_value=mock_claims):
            user = await cognito_auth.get_current_user_optional(credentials)

            assert user is not None
            assert user["email"] == "test@example.com"
