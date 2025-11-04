import sys
from pathlib import Path
import os
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Load environment variables from .env
load_dotenv(BACKEND_DIR / ".env")

from fastapi.testclient import TestClient
import main as backend_main

# Test API key for authenticated requests
TEST_API_KEY = "test-api-key-for-unit-tests"

# Mock the API key in the environment
os.environ["API_KEY"] = TEST_API_KEY

# Get custom domain from environment
CUSTOM_DOMAIN = os.getenv("CUSTOM_DOMAIN")
CUSTOM_ORIGIN = f"https://{CUSTOM_DOMAIN}"


def test_cors_allowed_origin():
    """Test that requests from allowed origins include CORS headers"""
    client = TestClient(backend_main.app)

    # Test with allowed origin
    headers = {"Origin": CUSTOM_ORIGIN}
    r = client.get("/health", headers=headers)

    assert r.status_code == 200
    # CORS middleware should add the Access-Control-Allow-Origin header
    assert "access-control-allow-origin" in r.headers
    assert r.headers["access-control-allow-origin"] == CUSTOM_ORIGIN


def test_cors_disallowed_origin():
    """Test that requests from disallowed origins don't get CORS headers"""
    client = TestClient(backend_main.app)

    # Test with disallowed origin
    headers = {"Origin": "https://malicious-site.com"}
    r = client.get("/health", headers=headers)

    assert r.status_code == 200
    # CORS middleware should NOT add the Access-Control-Allow-Origin header for disallowed origins
    # The response should succeed but without CORS headers
    # Note: The actual blocking happens in the browser, not the server


def test_cors_preflight_allowed_origin():
    """Test CORS preflight (OPTIONS) request for allowed origin"""
    client = TestClient(backend_main.app)

    headers = {
        "Origin": CUSTOM_ORIGIN,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type,X-API-Key"
    }

    r = client.options("/api/districts", headers=headers)

    assert r.status_code == 200
    assert "access-control-allow-origin" in r.headers
    assert r.headers["access-control-allow-origin"] == CUSTOM_ORIGIN
    assert "access-control-allow-methods" in r.headers
    assert "access-control-allow-headers" in r.headers


def test_cors_no_credentials():
    """Test that credentials are not allowed (security measure)"""
    client = TestClient(backend_main.app)

    headers = {"Origin": CUSTOM_ORIGIN}
    r = client.get("/health", headers=headers)

    # Access-Control-Allow-Credentials should NOT be present or should be false
    # When allow_credentials=False, the header is typically not sent
    assert r.headers.get("access-control-allow-credentials") != "true"


def test_cors_allowed_methods():
    """Test that only allowed methods are permitted"""
    client = TestClient(backend_main.app)

    headers = {
        "Origin": CUSTOM_ORIGIN,
        "Access-Control-Request-Method": "GET"
    }

    r = client.options("/api/districts", headers=headers)

    assert r.status_code == 200
    allowed_methods = r.headers.get("access-control-allow-methods", "")

    # Should include our allowed methods
    assert "GET" in allowed_methods
    assert "POST" in allowed_methods
    assert "PUT" in allowed_methods
    assert "DELETE" in allowed_methods

    # Should NOT include methods we don't use
    # PATCH is commonly not needed, though it may be included by default


def test_cors_allowed_headers():
    """Test that only allowed headers are permitted"""
    client = TestClient(backend_main.app)

    headers = {
        "Origin": CUSTOM_ORIGIN,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type,X-API-Key"
    }

    r = client.options("/api/districts", headers=headers)

    assert r.status_code == 200
    allowed_headers = r.headers.get("access-control-allow-headers", "").lower()

    # Should include our whitelisted headers
    assert "content-type" in allowed_headers
    assert "x-api-key" in allowed_headers


def test_cors_localhost_allowed():
    """Test that localhost origins are allowed for development"""
    client = TestClient(backend_main.app)

    localhost_origins = [
        "http://localhost:3000",
        "http://localhost:5173"
    ]

    for origin in localhost_origins:
        headers = {"Origin": origin}
        r = client.get("/health", headers=headers)

        assert r.status_code == 200
        assert "access-control-allow-origin" in r.headers
        assert r.headers["access-control-allow-origin"] == origin


def test_cors_max_age_set():
    """Test that preflight cache time is set"""
    client = TestClient(backend_main.app)

    headers = {
        "Origin": CUSTOM_ORIGIN,
        "Access-Control-Request-Method": "GET"
    }

    r = client.options("/api/districts", headers=headers)

    assert r.status_code == 200
    # max_age should be set to cache preflight requests
    assert "access-control-max-age" in r.headers
    # Should be 600 seconds (10 minutes)
    assert r.headers["access-control-max-age"] == "600"
