import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
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

    r = client.get('/api/districts/NOPE')
    assert r.status_code == 404


def test_create_district_success(monkeypatch):
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


def test_update_district_success(monkeypatch):
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
    r = client.put('/api/districts/DIST#1', json=payload)
    assert r.status_code == 200
    assert r.json()['name'] == 'Updated District'


def test_update_district_not_found(monkeypatch):
    client = TestClient(backend_main.app)

    def fake_update(table, district_id, district_data):
        return None

    monkeypatch.setattr(
        backend_main.DynamoDBDistrictService,
        'update_district',
        staticmethod(fake_update)
    )

    r = client.put('/api/districts/DIST#missing', json={'name': 'X'})
    assert r.status_code == 404


def test_delete_district_success(monkeypatch):
    client = TestClient(backend_main.app)

    monkeypatch.setattr(
        backend_main.DynamoDBDistrictService,
        'delete_district',
        staticmethod(lambda table, district_id: True)
    )

    r = client.delete('/api/districts/DIST#1')
    assert r.status_code == 204


def test_delete_district_not_found(monkeypatch):
    client = TestClient(backend_main.app)

    monkeypatch.setattr(
        backend_main.DynamoDBDistrictService,
        'delete_district',
        staticmethod(lambda table, district_id: False)
    )

    r = client.delete('/api/districts/DIST#404')
    assert r.status_code == 404
