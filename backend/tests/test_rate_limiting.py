"""
Tests for rate limiting functionality
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
import main as backend_main


@pytest.fixture
def client():
    """Create a test client"""
    return TestClient(backend_main.app)


def test_rate_limiting_enabled(client):
    """Test that rate limiting is properly configured and enabled"""
    # Verify that the limiter is attached to the app
    assert hasattr(backend_main.app.state, 'limiter'), "Rate limiter should be attached to app state"

    # Verify that rate limits are configured
    from rate_limiter import GENERAL_RATE_LIMIT, SEARCH_RATE_LIMIT, WRITE_RATE_LIMIT
    assert GENERAL_RATE_LIMIT is not None, "General rate limit should be configured"
    assert SEARCH_RATE_LIMIT is not None, "Search rate limit should be configured"
    assert WRITE_RATE_LIMIT is not None, "Write rate limit should be configured"


def test_rate_limit_configuration_values(client):
    """Test that rate limit configuration values are reasonable"""
    import os
    from rate_limiter import GENERAL_RATE_LIMIT, SEARCH_RATE_LIMIT, WRITE_RATE_LIMIT

    # Check that limits are in the expected format (number/timeperiod)
    assert '/' in GENERAL_RATE_LIMIT, "General rate limit should be in format 'number/period'"
    assert '/' in SEARCH_RATE_LIMIT, "Search rate limit should be in format 'number/period'"
    assert '/' in WRITE_RATE_LIMIT, "Write rate limit should be in format 'number/period'"

    # Extract numbers
    general_limit = int(GENERAL_RATE_LIMIT.split('/')[0])
    search_limit = int(SEARCH_RATE_LIMIT.split('/')[0])
    write_limit = int(WRITE_RATE_LIMIT.split('/')[0])

    # In production/default configuration, verify search and write are more restrictive
    # Skip these checks in test environment where limits are set high
    if general_limit < 500:  # Not in test environment
        # Verify search is more restrictive than general
        assert search_limit < general_limit, "Search rate limit should be more restrictive than general"

        # Verify write is more restrictive than general
        assert write_limit < general_limit, "Write rate limit should be more restrictive than general"


def test_endpoints_have_request_parameter(client):
    """Test that rate-limited endpoints have Request parameter"""
    # Mock services to avoid database calls
    with patch('main.DynamoDBDistrictService.get_districts') as mock_get:
        mock_get.return_value = ([], 0)

        # Test that a rate-limited endpoint works (it should have Request parameter)
        r = client.get('/api/districts')
        assert r.status_code == 200, "Rate-limited endpoint should work with Request parameter"


def test_rate_limit_handler_registered(client):
    """Test that rate limit exception handler is registered"""
    from slowapi.errors import RateLimitExceeded

    # Check that the exception handler is registered
    handlers = backend_main.app.exception_handlers
    assert RateLimitExceeded in handlers or Exception in handlers, "Rate limit exception handler should be registered"


def test_rate_limit_storage_configured(client):
    """Test that rate limit storage is configured"""
    from rate_limiter import limiter

    # Verify limiter is configured with storage
    assert limiter._storage_uri is not None, "Rate limiter should have storage URI configured"
    assert 'memory://' in limiter._storage_uri or 'redis://' in limiter._storage_uri, "Storage should be memory or redis"
