"""
Tests for authentication endpoints
"""
import sys
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
import main as backend_main


class TestAuthEndpoints:
    """Tests for /api/auth endpoints"""

    def test_get_current_user_not_authenticated(self):
        """Test /me endpoint when user is not authenticated"""
        client = TestClient(backend_main.app)

        # Mock the dependency to return None (not authenticated)
        def mock_get_current_user_optional():
            return None

        backend_main.app.dependency_overrides[backend_main.get_current_user_optional] = mock_get_current_user_optional

        try:
            response = client.get('/api/auth/me')

            assert response.status_code == 200
            data = response.json()
            assert data["authenticated"] is False
            assert data["user"] is None
        finally:
            backend_main.app.dependency_overrides.clear()

    def test_get_current_user_authenticated(self):
        """Test /me endpoint when user is authenticated"""
        client = TestClient(backend_main.app)

        # Mock the dependency to return a user
        def mock_get_current_user_optional():
            return {
                "sub": "user-123",
                "email": "test@example.com",
                "username": "testuser",
                "is_admin": False,
                "groups": ["users"]
            }

        backend_main.app.dependency_overrides[backend_main.get_current_user_optional] = mock_get_current_user_optional

        try:
            response = client.get('/api/auth/me')

            assert response.status_code == 200
            data = response.json()
            assert data["authenticated"] is True
            assert data["user"]["email"] == "test@example.com"
            assert data["user"]["username"] == "testuser"
            assert data["user"]["is_admin"] is False
            assert data["user"]["groups"] == ["users"]
        finally:
            backend_main.app.dependency_overrides.clear()

    def test_get_current_user_admin(self):
        """Test /me endpoint when user is an admin"""
        client = TestClient(backend_main.app)

        # Mock the dependency to return an admin user
        def mock_get_current_user_optional():
            return {
                "sub": "admin-123",
                "email": "admin@example.com",
                "username": "admin",
                "is_admin": True,
                "groups": ["admins", "users"]
            }

        backend_main.app.dependency_overrides[backend_main.get_current_user_optional] = mock_get_current_user_optional

        try:
            response = client.get('/api/auth/me')

            assert response.status_code == 200
            data = response.json()
            assert data["authenticated"] is True
            assert data["user"]["is_admin"] is True
            assert "admins" in data["user"]["groups"]
        finally:
            backend_main.app.dependency_overrides.clear()

    def test_get_current_user_partial_data(self):
        """Test /me endpoint handles missing optional user data"""
        client = TestClient(backend_main.app)

        # Mock the dependency to return a user with minimal data
        def mock_get_current_user_optional():
            return {
                "email": "test@example.com"
                # Missing is_admin, groups, username
            }

        backend_main.app.dependency_overrides[backend_main.get_current_user_optional] = mock_get_current_user_optional

        try:
            response = client.get('/api/auth/me')

            assert response.status_code == 200
            data = response.json()
            assert data["authenticated"] is True
            assert data["user"]["email"] == "test@example.com"
            assert data["user"]["is_admin"] is False  # Default value
            assert data["user"]["groups"] == []  # Default value
        finally:
            backend_main.app.dependency_overrides.clear()
