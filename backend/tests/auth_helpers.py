"""
Test helpers for authentication
Provides mock authentication for unit tests
"""
from unittest.mock import MagicMock


def mock_admin_user():
    """Return a mock admin user for testing"""
    return {
        'sub': 'test-user-123',
        'email': 'admin@test.com',
        'groups': ['admins'],
        'is_admin': True,
        'custom_role': 'admin',
        'username': 'admin@test.com'
    }


def mock_regular_user():
    """Return a mock regular user for testing"""
    return {
        'sub': 'test-user-456',
        'email': 'user@test.com',
        'groups': [],
        'is_admin': False,
        'custom_role': '',
        'username': 'user@test.com'
    }


def get_auth_headers(token='mock-jwt-token'):
    """Get authentication headers for test requests"""
    return {
        'Authorization': f'Bearer {token}'
    }


def get_api_key_headers(api_key='test-api-key-for-unit-tests'):
    """Get API key headers for backward compatibility tests"""
    return {
        'X-API-Key': api_key
    }
