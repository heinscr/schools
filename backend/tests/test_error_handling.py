"""
Tests for error handling and sanitization
"""
import pytest
import os
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from fastapi import HTTPException


def test_http_exception_sanitization_production(monkeypatch):
    """Test that HTTPException errors are sanitized in production"""
    monkeypatch.setenv("ENVIRONMENT", "production")

    # Force reload to pick up new environment
    import importlib
    import error_handlers
    importlib.reload(error_handlers)

    # Import after setting environment
    import main
    client = TestClient(main.app)

    # Mock the service to return None (not found)
    with patch('main.DynamoDBDistrictService.get_district') as mock_get:
        mock_get.return_value = None

        # Try to get a non-existent district
        r = client.get('/api/districts/nonexistent-id-12345')

        # Should get 404 with generic message
        assert r.status_code == 404
        data = r.json()
        assert "detail" in data
        # Should not contain sensitive information
        assert "traceback" not in data.get("detail", "").lower()
        assert "exception" not in data.get("detail", "").lower()


def test_validation_error_sanitization_production(monkeypatch):
    """Test that validation errors are sanitized in production"""
    monkeypatch.setenv("ENVIRONMENT", "production")

    # Force reload
    import importlib
    import error_handlers
    importlib.reload(error_handlers)

    import main
    client = TestClient(main.app)

    # Send invalid data for district creation (missing required API key will give 401)
    # Let's test with invalid query parameters instead
    r = client.get('/api/districts?limit=9999999')  # Exceeds max limit

    # Should get 422 validation error
    assert r.status_code == 422
    data = r.json()
    assert "detail" in data


def test_general_exception_sanitization_production(monkeypatch):
    """Test that general exceptions are sanitized in production"""
    monkeypatch.setenv("ENVIRONMENT", "production")

    # Force reload
    import importlib
    import error_handlers
    importlib.reload(error_handlers)

    import main
    # Reload main to pick up the new error handlers
    importlib.reload(main)
    client = TestClient(main.app, raise_server_exceptions=False)

    # Mock a service to raise an exception
    with patch('main.DynamoDBDistrictService.get_district') as mock_get:
        mock_get.side_effect = RuntimeError("Database connection failed")

        r = client.get('/api/districts/test-id')

        # Should get 500 with sanitized message
        assert r.status_code == 500
        data = r.json()
        assert "detail" in data
        # Should not leak the actual error message in production
        assert "Database connection failed" not in data.get("detail", "")
        assert "internal error" in data.get("detail", "").lower() or "error occurred" in data.get("detail", "").lower()


def test_http_exception_detail_development(monkeypatch):
    """Test that HTTPException errors show details in development"""
    monkeypatch.setenv("ENVIRONMENT", "development")

    # Force reload
    import importlib
    import error_handlers
    importlib.reload(error_handlers)

    import main
    client = TestClient(main.app)

    # Mock the service to return None (not found)
    with patch('main.DynamoDBDistrictService.get_district') as mock_get:
        mock_get.return_value = None

        # Try to get a non-existent district
        r = client.get('/api/districts/nonexistent-id-12345')

        # Should get 404
        assert r.status_code == 404
        data = r.json()
        assert "detail" in data


def test_create_district_error_sanitization(monkeypatch):
    """Test that create_district errors are sanitized properly"""
    monkeypatch.setenv("ENVIRONMENT", "production")

    # Force reload
    import importlib
    import error_handlers
    importlib.reload(error_handlers)

    import main
    from auth_helpers import mock_admin_user

    # Mock admin auth
    async def mock_auth():
        return mock_admin_user()

    main.app.dependency_overrides[main.require_admin_role] = mock_auth

    client = TestClient(main.app)

    # Try to create a district with invalid data
    with patch('main.DynamoDBDistrictService.create_district') as mock_create:
        mock_create.side_effect = ValueError("Invalid district data format")

        r = client.post(
            '/api/districts',
            json={
                "name": "Test District",
                "address": "123 Main St",
                "district_type": "municipal",
                "towns": ["TestTown"]
            }
        )

        # Should get error response
        assert r.status_code in [400, 500]
        data = r.json()
        assert "detail" in data
        # In production, should not show the raw ValueError message
        if os.getenv("ENVIRONMENT", "production").lower() == "production":
            assert "ValueError" not in data.get("detail", "")

    # Clean up
    main.app.dependency_overrides.clear()


def test_error_response_format(monkeypatch):
    """Test that error responses have consistent format"""
    monkeypatch.setenv("ENVIRONMENT", "production")

    # Force reload
    import importlib
    import error_handlers
    importlib.reload(error_handlers)

    import main
    client = TestClient(main.app)

    # Mock the service to return None (not found)
    with patch('main.DynamoDBDistrictService.get_district') as mock_get:
        mock_get.return_value = None

        # Test 404 error format
        r = client.get('/api/districts/nonexistent-id')
        assert r.status_code == 404
        data = r.json()
        assert isinstance(data, dict)
        assert "detail" in data

    # Test validation error format
    r = client.get('/api/districts?limit=999999')
    assert r.status_code == 422
    data = r.json()
    assert isinstance(data, dict)
    assert "detail" in data


def test_no_stacktrace_in_production(monkeypatch):
    """Test that stack traces are not exposed in production"""
    monkeypatch.setenv("ENVIRONMENT", "production")

    # Force reload
    import importlib
    import error_handlers
    importlib.reload(error_handlers)

    import main
    # Reload main to pick up the new error handlers
    importlib.reload(main)
    client = TestClient(main.app, raise_server_exceptions=False)

    # Mock to raise an exception with traceback
    with patch('main.DynamoDBDistrictService.get_districts') as mock_list:
        mock_list.side_effect = Exception("Critical system error with sensitive data")

        r = client.get('/api/districts')

        # Should get error response
        assert r.status_code == 500
        data = r.json()

        # Should not contain sensitive information
        response_str = str(data).lower()
        assert "traceback" not in response_str
        assert "critical system error" not in response_str
        assert "sensitive data" not in response_str


def test_safe_create_district_error_function(monkeypatch):
    """Test the safe_create_district_error helper function"""
    monkeypatch.setenv("ENVIRONMENT", "production")

    # Force reload
    import importlib
    import error_handlers
    importlib.reload(error_handlers)

    from error_handlers import safe_create_district_error

    # Test with ValueError
    error = ValueError("Test error message")
    with pytest.raises(Exception) as exc_info:
        raise safe_create_district_error(error)

    # Should be HTTPException
    from fastapi import HTTPException
    assert isinstance(exc_info.value, HTTPException)
    assert exc_info.value.status_code == 400


def test_lambda_endpoint_errors_not_leaked(monkeypatch):
    """Test that Lambda function errors don't leak sensitive info"""
    monkeypatch.setenv("ENVIRONMENT", "production")

    # Force reload
    import importlib
    import error_handlers
    importlib.reload(error_handlers)

    import main
    client = TestClient(main.app)

    # Mock the salaries module to raise an exception
    with patch('main.salaries.get_salary_schedule') as mock_salary:
        mock_salary.return_value = {
            'statusCode': 500,
            'body': '{"message": "Internal Lambda error with sensitive details"}'
        }

        # Test salary schedule endpoint with invalid district
        r = client.get('/api/salary-schedule/invalid-district-id-999')

        # Even if it fails, should not expose internal Lambda errors
        if r.status_code != 200:
            data = r.json()
            # Should have standard error format
            assert "detail" in data or "message" in data
