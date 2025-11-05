import sys
from pathlib import Path
import os

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
import pytest
import main as backend_main

def _resp_district(**overrides):
    base = {
        'id': 'DISTRICT#abc',
        'name': 'Sample District',
        'main_address': '123 Main St',
        'towns': ['TownA', 'TownB'],
        'district_type': 'municipal',
        'created_at': '2024-01-01T00:00:00Z',
        'updated_at': '2024-01-02T00:00:00Z',
    }
    base.update(overrides)
    return base


def test_search_with_valid_query(monkeypatch):
    """Test that valid search queries work correctly"""
    client = TestClient(backend_main.app)

    monkeypatch.setattr(
        backend_main.DynamoDBDistrictService,
        'search_districts',
        staticmethod(lambda table, query_text, limit, offset: ([_resp_district()], 1))
    )

    # Valid queries with allowed characters
    valid_queries = [
        "Boston",
        "New York",
        "Springfield-West",
        "O'Brien",
        "District No. 5",
        "School & Learning Center",
        "District (Main Campus)",
    ]

    for query in valid_queries:
        r = client.get(f'/api/districts/search?q={query}')
        assert r.status_code == 200, f"Failed for query: {query}"


def test_search_with_too_long_query(monkeypatch):
    """Test that search queries exceeding max length are rejected"""
    client = TestClient(backend_main.app)

    # Create a query that's too long (>100 characters)
    long_query = "A" * 101

    r = client.get(f'/api/districts/search?q={long_query}')
    assert r.status_code == 400
    assert "too long" in r.json()['detail'].lower()


def test_search_with_invalid_characters(monkeypatch):
    """Test that search queries with invalid characters are rejected"""
    client = TestClient(backend_main.app)

    # Invalid characters that are commonly used in injection attacks
    # Note: Some characters are URL-encoded to pass through the HTTP layer
    invalid_queries = [
        "<script>alert('xss')</script>",
        "test; DROP TABLE districts;",
        "test{injection}",
        "test[brackets]",
        "test$variable",
        "test%wildcard",
        "test*wildcard",
        "test@email",
        "test^caret",
        "test|pipe",
        "test~tilde",
        "test`backtick",
    ]

    for query in invalid_queries:
        r = client.get(f'/api/districts/search?q={query}')
        assert r.status_code == 400, f"Should reject query: {query}"
        assert "invalid characters" in r.json()['detail'].lower()


def test_list_with_valid_name_filter(monkeypatch):
    """Test that valid name filters work correctly"""
    client = TestClient(backend_main.app)

    monkeypatch.setattr(
        backend_main.DynamoDBDistrictService,
        'get_districts',
        staticmethod(lambda table, name, town, limit, offset: ([_resp_district()], 1))
    )

    valid_names = [
        "Boston",
        "Springfield Public Schools",
        "District-123",
        "O'Brien School",
        "School & College Prep",
    ]

    for name in valid_names:
        r = client.get(f'/api/districts?name={name}')
        assert r.status_code == 200, f"Failed for name: {name}"


def test_list_with_too_long_name_filter(monkeypatch):
    """Test that name filters exceeding max length are rejected"""
    client = TestClient(backend_main.app)

    # Create a name that's too long (>200 characters)
    long_name = "A" * 201

    r = client.get(f'/api/districts?name={long_name}')
    assert r.status_code == 400
    assert "too long" in r.json()['detail'].lower()


def test_list_with_invalid_name_characters(monkeypatch):
    """Test that name filters with invalid characters are rejected"""
    client = TestClient(backend_main.app)

    invalid_names = [
        "<script>alert('xss')</script>",
        "test; DROP TABLE",
        "test{injection}",
        "test@email",
    ]

    for name in invalid_names:
        r = client.get(f'/api/districts?name={name}')
        assert r.status_code == 400, f"Should reject name: {name}"
        assert "invalid characters" in r.json()['detail'].lower()


def test_list_with_valid_town_filter(monkeypatch):
    """Test that valid town filters work correctly"""
    client = TestClient(backend_main.app)

    monkeypatch.setattr(
        backend_main.DynamoDBDistrictService,
        'get_districts',
        staticmethod(lambda table, name, town, limit, offset: ([_resp_district()], 1))
    )

    valid_towns = [
        "Boston",
        "New York",
        "Springfield-West",
        "O'Brien",
    ]

    for town in valid_towns:
        r = client.get(f'/api/districts?town={town}')
        assert r.status_code == 200, f"Failed for town: {town}"


def test_list_with_too_long_town_filter(monkeypatch):
    """Test that town filters exceeding max length are rejected"""
    client = TestClient(backend_main.app)

    # Create a town that's too long (>100 characters)
    long_town = "A" * 101

    r = client.get(f'/api/districts?town={long_town}')
    assert r.status_code == 400
    assert "too long" in r.json()['detail'].lower()


def test_list_with_invalid_town_characters(monkeypatch):
    """Test that town filters with invalid characters are rejected"""
    client = TestClient(backend_main.app)

    invalid_towns = [
        "<script>",
        "test{injection}",
        "test@email",
    ]

    for town in invalid_towns:
        r = client.get(f'/api/districts?town={town}')
        assert r.status_code == 400, f"Should reject town: {town}"
        assert "invalid characters" in r.json()['detail'].lower()


def test_search_with_empty_query_returns_all(monkeypatch):
    """Test that empty search query returns all results"""
    client = TestClient(backend_main.app)

    monkeypatch.setattr(
        backend_main.DynamoDBDistrictService,
        'search_districts',
        staticmethod(lambda table, query_text, limit, offset: ([_resp_district()], 1))
    )

    # Empty query should work
    r = client.get('/api/districts/search?q=')
    assert r.status_code == 200

    # No query parameter should work
    r = client.get('/api/districts/search')
    assert r.status_code == 200


def test_list_with_whitespace_only_filters(monkeypatch):
    """Test that filters with only whitespace are treated as None"""
    client = TestClient(backend_main.app)

    monkeypatch.setattr(
        backend_main.DynamoDBDistrictService,
        'get_districts',
        staticmethod(lambda table, name, town, limit, offset: ([_resp_district()], 1))
    )

    # Whitespace-only filters should be treated as no filter
    r = client.get('/api/districts?name=   ')
    assert r.status_code == 200

    r = client.get('/api/districts?town=   ')
    assert r.status_code == 200
