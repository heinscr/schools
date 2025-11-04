import sys
from pathlib import Path
import os
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
import main as backend_main
from pydantic import ValidationError
from schemas import DistrictCreate, DistrictUpdate

# Test API key for authenticated requests
TEST_API_KEY = "test-api-key-for-unit-tests"

# Mock the API key in the environment
os.environ["API_KEY"] = TEST_API_KEY


def test_create_district_valid_data(monkeypatch):
    """Test creating district with valid data"""
    client = TestClient(backend_main.app)

    def fake_create(table, district_data):
        return {
            'id': 'DISTRICT#123',
            'name': 'Valid District',
            'main_address': '123 Main St',
            'towns': ['Boston', 'Cambridge'],
            'district_type': 'municipal',
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-01T00:00:00Z',
        }

    monkeypatch.setattr(
        backend_main.DynamoDBDistrictService,
        'create_district',
        staticmethod(fake_create)
    )

    payload = {
        'name': 'Valid District',
        'main_address': '123 Main St',
        'towns': ['Boston', 'Cambridge'],
        'district_type': 'municipal'
    }
    headers = {'X-API-Key': TEST_API_KEY}
    r = client.post('/api/districts', json=payload, headers=headers)
    assert r.status_code == 201


def test_create_district_invalid_name_characters(monkeypatch):
    """Test that invalid characters in name are rejected"""
    client = TestClient(backend_main.app)

    invalid_names = [
        '<script>alert("xss")</script>',
        'Test {injection}',
        'Test @email',
        'Test$variable',
    ]

    for name in invalid_names:
        payload = {
            'name': name,
            'main_address': '123 Main St',
            'towns': ['Boston'],
            'district_type': 'municipal'
        }
        headers = {'X-API-Key': TEST_API_KEY}
        r = client.post('/api/districts', json=payload, headers=headers)
        assert r.status_code == 422 or r.status_code == 400, f"Should reject name: {name}"


def test_create_district_valid_name_characters(monkeypatch):
    """Test that valid special characters in name are accepted"""
    client = TestClient(backend_main.app)

    def fake_create(table, district_data):
        return {
            'id': 'DISTRICT#123',
            'name': district_data.name,
            'main_address': '123 Main St',
            'towns': ['Boston'],
            'district_type': 'municipal',
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-01T00:00:00Z',
        }

    monkeypatch.setattr(
        backend_main.DynamoDBDistrictService,
        'create_district',
        staticmethod(fake_create)
    )

    valid_names = [
        "O'Brien School District",
        "District #5",
        "Boston & Cambridge",
        "Springfield-Longmeadow",
        "School District (Main)",
    ]

    for name in valid_names:
        payload = {
            'name': name,
            'main_address': '123 Main St',
            'towns': ['Boston'],
            'district_type': 'municipal'
        }
        headers = {'X-API-Key': TEST_API_KEY}
        r = client.post('/api/districts', json=payload, headers=headers)
        assert r.status_code == 201, f"Should accept name: {name}"


def test_create_district_invalid_district_type(monkeypatch):
    """Test that invalid district types are rejected"""
    client = TestClient(backend_main.app)

    invalid_types = [
        'invalid_type',
        'public',
        'private',
        'municipal; DROP TABLE',
    ]

    for district_type in invalid_types:
        payload = {
            'name': 'Test District',
            'main_address': '123 Main St',
            'towns': ['Boston'],
            'district_type': district_type
        }
        headers = {'X-API-Key': TEST_API_KEY}
        r = client.post('/api/districts', json=payload, headers=headers)
        assert r.status_code == 422 or r.status_code == 400, f"Should reject type: {district_type}"


def test_create_district_valid_district_types(monkeypatch):
    """Test that all valid district types are accepted"""
    client = TestClient(backend_main.app)

    def fake_create(table, district_data):
        return {
            'id': 'DISTRICT#123',
            'name': 'Test District',
            'main_address': '123 Main St',
            'towns': ['Boston'],
            'district_type': district_data.district_type,
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-01T00:00:00Z',
        }

    monkeypatch.setattr(
        backend_main.DynamoDBDistrictService,
        'create_district',
        staticmethod(fake_create)
    )

    valid_types = [
        'municipal',
        'regional_academic',
        'regional_vocational',
        'charter',
        'collaborative',
        'virtual',
        'other',
    ]

    for district_type in valid_types:
        payload = {
            'name': 'Test District',
            'main_address': '123 Main St',
            'towns': ['Boston'],
            'district_type': district_type
        }
        headers = {'X-API-Key': TEST_API_KEY}
        r = client.post('/api/districts', json=payload, headers=headers)
        assert r.status_code == 201, f"Should accept type: {district_type}"


def test_create_district_too_many_towns(monkeypatch):
    """Test that too many towns are rejected"""
    client = TestClient(backend_main.app)

    # Create more than 50 towns
    too_many_towns = [f'Town{i}' for i in range(51)]

    payload = {
        'name': 'Test District',
        'main_address': '123 Main St',
        'towns': too_many_towns,
        'district_type': 'municipal'
    }
    headers = {'X-API-Key': TEST_API_KEY}
    r = client.post('/api/districts', json=payload, headers=headers)
    assert r.status_code == 422 or r.status_code == 400
    response_json = r.json()
    # Check both old and new error formats
    if isinstance(response_json['detail'], list) and len(response_json['detail']) > 0:
        error_msg = response_json['detail'][0].get('msg') or response_json['detail'][0].get('message')
        assert 'too many towns' in error_msg.lower() or 'too many towns' in str(response_json).lower()
    else:
        assert 'too many towns' in str(response_json).lower()


def test_create_district_invalid_town_characters(monkeypatch):
    """Test that invalid characters in town names are rejected"""
    client = TestClient(backend_main.app)

    invalid_towns = [
        ['Boston', '<script>'],
        ['Test{injection}'],
        ['Town@email'],
    ]

    for towns in invalid_towns:
        payload = {
            'name': 'Test District',
            'main_address': '123 Main St',
            'towns': towns,
            'district_type': 'municipal'
        }
        headers = {'X-API-Key': TEST_API_KEY}
        r = client.post('/api/districts', json=payload, headers=headers)
        assert r.status_code == 422 or r.status_code == 400, f"Should reject towns: {towns}"


def test_create_district_town_too_long(monkeypatch):
    """Test that town names that are too long are rejected"""
    client = TestClient(backend_main.app)

    long_town = 'A' * 101

    payload = {
        'name': 'Test District',
        'main_address': '123 Main St',
        'towns': [long_town],
        'district_type': 'municipal'
    }
    headers = {'X-API-Key': TEST_API_KEY}
    r = client.post('/api/districts', json=payload, headers=headers)
    assert r.status_code == 422 or r.status_code == 400


def test_get_district_invalid_id_format(monkeypatch):
    """Test that invalid district ID format is rejected"""
    client = TestClient(backend_main.app)

    # Mock to prevent actual DB calls
    monkeypatch.setattr(
        backend_main.DynamoDBDistrictService,
        'get_district',
        staticmethod(lambda table, district_id: {'id': district_id, 'name': 'Test', 'main_address': '', 'towns': [], 'district_type': 'municipal', 'created_at': '2024-01-01T00:00:00Z', 'updated_at': '2024-01-01T00:00:00Z'})
    )

    # Test IDs that will be rejected by validation (alphanumeric + hyphens only)
    invalid_ids_for_validation = [
        'test;injection',  # Semicolon
        'test@email.com',  # @ symbol
        'test$var',  # $ symbol
        'test/slash',  # Slash
        'test.period',  # Period
    ]

    for district_id in invalid_ids_for_validation:
        r = client.get(f'/api/districts/{district_id}')
        # Should be 400 for validation error or 404 if routing doesn't match
        assert r.status_code in [400, 404], f"Should reject ID: {district_id}, got {r.status_code}"


def test_get_district_valid_id_format(monkeypatch):
    """Test that valid district ID formats are accepted"""
    client = TestClient(backend_main.app)

    def fake_get(table, district_id):
        return {
            'id': district_id,
            'name': 'Test District',
            'main_address': '123 Main St',
            'towns': ['Boston'],
            'district_type': 'municipal',
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-01T00:00:00Z',
        }

    monkeypatch.setattr(
        backend_main.DynamoDBDistrictService,
        'get_district',
        staticmethod(fake_get)
    )

    valid_ids = [
        'DISTRICT%23abc123',  # URL-encoded #
        'DISTRICT%23uuid-with-dashes',
        'ENTITY%23123',
        '0f60fef3-cee7-43da-a8a8-b74826e3dfa0',  # Plain UUID
        'abc-123',  # Short format
    ]

    for district_id in valid_ids:
        r = client.get(f'/api/districts/{district_id}')
        assert r.status_code == 200, f"Should accept ID: {district_id}"


def test_update_district_validation(monkeypatch):
    """Test that update validation works correctly"""
    client = TestClient(backend_main.app)

    def fake_update(table, district_id, district_data):
        return {
            'id': district_id,
            'name': district_data.name or 'Test District',
            'main_address': '123 Main St',
            'towns': district_data.towns or ['Boston'],
            'district_type': district_data.district_type or 'municipal',
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-01T00:00:00Z',
        }

    monkeypatch.setattr(
        backend_main.DynamoDBDistrictService,
        'update_district',
        staticmethod(fake_update)
    )

    # Test invalid name
    payload = {'name': '<script>alert("xss")</script>'}
    headers = {'X-API-Key': TEST_API_KEY}
    r = client.put('/api/districts/DISTRICT%23123', json=payload, headers=headers)
    assert r.status_code == 422 or r.status_code == 400

    # Test invalid district type
    payload = {'district_type': 'invalid_type'}
    headers = {'X-API-Key': TEST_API_KEY}
    r = client.put('/api/districts/DISTRICT%23123', json=payload, headers=headers)
    assert r.status_code == 422 or r.status_code == 400

    # Test valid update
    payload = {'name': 'Updated District'}
    headers = {'X-API-Key': TEST_API_KEY}
    r = client.put('/api/districts/DISTRICT%23123', json=payload, headers=headers)
    assert r.status_code == 200
