import sys
from pathlib import Path
import os
from unittest.mock import AsyncMock

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
import main as backend_main
from auth_helpers import mock_admin_user, get_auth_headers

def mock_require_admin_role():
    """Mock admin authentication dependency"""
    async def _mock():
        return mock_admin_user()
    return _mock


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


def test_get_district_by_id_found(monkeypatch):
    client = TestClient(backend_main.app)

    monkeypatch.setattr(
        backend_main.DynamoDBDistrictService,
        'get_district',
        staticmethod(lambda table, district_id: _resp_district(id=district_id))
    )

    r = client.get('/api/districts/DISTRICT%23xyz')
    assert r.status_code == 200
    body = r.json()
    assert body['id'] == 'DISTRICT#xyz'
    assert body['district_type'] == 'municipal'


def test_get_district_by_id_not_found(monkeypatch):
    client = TestClient(backend_main.app)

    monkeypatch.setattr(
        backend_main.DynamoDBDistrictService,
        'get_district',
        staticmethod(lambda table, district_id: None)
    )

    r = client.get('/api/districts/DISTRICT%23notfound')
    assert r.status_code == 404


def test_create_district_success(monkeypatch):
    # Override auth dependency to return mock admin user
    backend_main.app.dependency_overrides[backend_main.require_admin_role] = mock_require_admin_role()

    client = TestClient(backend_main.app)

    created = _resp_district(name='New District')

    def fake_create(table, district_data):
        return created

    monkeypatch.setattr(
        backend_main.DynamoDBDistrictService,
        'create_district',
        staticmethod(fake_create)
    )

    payload = {
        'name': 'New District',
        'main_address': '99 Broadway',
        'towns': ['TownC'],
        'district_type': 'municipal'
    }
    r = client.post('/api/districts', json=payload)
    assert r.status_code == 201
    assert r.json()['name'] == 'New District'

    # Clean up
    backend_main.app.dependency_overrides.clear()


def test_update_district_success(monkeypatch):
    # Override auth dependency
    backend_main.app.dependency_overrides[backend_main.require_admin_role] = mock_require_admin_role()

    client = TestClient(backend_main.app)

    updated = _resp_district(name='Updated District')

    def fake_update(table, district_id, district_data):
        return updated

    monkeypatch.setattr(
        backend_main.DynamoDBDistrictService,
        'update_district',
        staticmethod(fake_update)
    )

    payload = {'name': 'Updated District'}
    r = client.put('/api/districts/DIST%231', json=payload)
    assert r.status_code == 200
    assert r.json()['name'] == 'Updated District'

    # Clean up
    backend_main.app.dependency_overrides.clear()


def test_update_district_not_found(monkeypatch):
    # Override auth dependency
    backend_main.app.dependency_overrides[backend_main.require_admin_role] = mock_require_admin_role()

    client = TestClient(backend_main.app)

    def fake_update(table, district_id, district_data):
        return None

    monkeypatch.setattr(
        backend_main.DynamoDBDistrictService,
        'update_district',
        staticmethod(fake_update)
    )

    r = client.put('/api/districts/DIST%23missing', json={'name': 'X'})
    assert r.status_code == 404

    # Clean up
    backend_main.app.dependency_overrides.clear()


def test_delete_district_success(monkeypatch):
    # Override auth dependency
    backend_main.app.dependency_overrides[backend_main.require_admin_role] = mock_require_admin_role()

    client = TestClient(backend_main.app)

    monkeypatch.setattr(
        backend_main.DynamoDBDistrictService,
        'delete_district',
        staticmethod(lambda table, district_id: True)
    )

    r = client.delete('/api/districts/DIST%231')
    assert r.status_code == 204

    # Clean up
    backend_main.app.dependency_overrides.clear()


def test_delete_district_not_found(monkeypatch):
    # Override auth dependency
    backend_main.app.dependency_overrides[backend_main.require_admin_role] = mock_require_admin_role()

    client = TestClient(backend_main.app)

    monkeypatch.setattr(
        backend_main.DynamoDBDistrictService,
        'delete_district',
        staticmethod(lambda table, district_id: False)
    )

    r = client.delete('/api/districts/DIST%23404')
    assert r.status_code == 404

    # Clean up
    backend_main.app.dependency_overrides.clear()


def test_create_district_unauthorized_no_api_key(monkeypatch):
    """Test that POST without authentication returns 401"""
    # Clear any dependency overrides from previous tests
    backend_main.app.dependency_overrides.clear()

    client = TestClient(backend_main.app)

    payload = {
        'name': 'New District',
        'main_address': '99 Broadway',
        'towns': ['TownC'],
        'district_type': 'municipal'
    }
    r = client.post('/api/districts', json=payload)
    assert r.status_code == 401
    # Check for Cognito auth error message
    assert 'Authentication required' in r.json()['detail'] or 'log in' in r.json()['detail'].lower()


def test_create_district_forbidden_invalid_api_key(monkeypatch):
    """Test that POST with invalid auth token returns 401"""
    # Clear any dependency overrides from previous tests
    backend_main.app.dependency_overrides.clear()

    # Mock get_cognito_keys to return valid keys structure
    # This prevents HTTP calls to Cognito in tests
    import cognito_auth
    monkeypatch.setattr(
        cognito_auth,
        'get_cognito_keys',
        lambda: {
            "keys": [
                {
                    "kid": "test-key-id",
                    "kty": "RSA",
                    "use": "sig",
                    "n": "test-n",
                    "e": "AQAB"
                }
            ]
        }
    )

    client = TestClient(backend_main.app)

    payload = {
        'name': 'New District',
        'main_address': '99 Broadway',
        'towns': ['TownC'],
        'district_type': 'municipal'
    }
    headers = {'Authorization': 'Bearer invalid-token'}
    r = client.post('/api/districts', json=payload, headers=headers)
    assert r.status_code == 401
    assert 'Invalid token' in r.json()['detail'] or 'Token' in r.json()['detail']


def test_update_district_unauthorized_no_api_key(monkeypatch):
    """Test that PUT without API key returns 401"""
    # Clear any dependency overrides from previous tests
    backend_main.app.dependency_overrides.clear()

    client = TestClient(backend_main.app)

    payload = {'name': 'Updated District'}
    r = client.put('/api/districts/DIST%231', json=payload)
    assert r.status_code == 401


def test_delete_district_unauthorized_no_api_key(monkeypatch):
    """Test that DELETE without API key returns 401"""
    # Clear any dependency overrides from previous tests
    backend_main.app.dependency_overrides.clear()

    client = TestClient(backend_main.app)

    r = client.delete('/api/districts/DIST%231')
    assert r.status_code == 401


def test_get_district_no_auth_required(monkeypatch):
    """Test that GET endpoints work without API key"""
    client = TestClient(backend_main.app)

    monkeypatch.setattr(
        backend_main.DynamoDBDistrictService,
        'get_district',
        staticmethod(lambda table, district_id: _resp_district(id=district_id))
    )

    # GET should work without API key
    r = client.get('/api/districts/DISTRICT%23xyz')
    assert r.status_code == 200
    assert r.json()['id'] == 'DISTRICT#xyz'
