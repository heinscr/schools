import sys
from pathlib import Path

# Ensure backend package is importable when running from repo root
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
import main as backend_main


def test_health():
    client = TestClient(backend_main.app)
    r = client.get('/health')
    assert r.status_code == 200
    assert r.json().get('status') == 'healthy'


def test_list_districts_by_town_monkeypatch(monkeypatch):
    client = TestClient(backend_main.app)

    # Fake return from service
    def fake_get_districts(table, name, town, limit, offset):
        assert town == 'Egremont'
        return ([{
            'id': 'DISTRICT#egremont-1',
            'name': 'Egremont Public Schools',
            'towns': ['Egremont'],
            'district_type': 'municipal',
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-02T00:00:00Z'
        }], 1)

    monkeypatch.setattr(
        backend_main.DynamoDBDistrictService,
        'get_districts',
        staticmethod(fake_get_districts)
    )

    r = client.get('/api/districts?town=Egremont')
    assert r.status_code == 200
    body = r.json()
    assert body['total'] == 1
    assert len(body['data']) == 1


def test_search_districts_monkeypatch(monkeypatch):
    client = TestClient(backend_main.app)

    def fake_search_districts(table, query_text, limit, offset):
        assert query_text == 'Tisbury'
        return ([{
            'id': 'DISTRICT#tis-1',
            'name': 'Tisbury Public Schools',
            'towns': ['Tisbury'],
            'district_type': 'municipal',
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-02T00:00:00Z'
        }], 1)

    monkeypatch.setattr(
        backend_main.DynamoDBDistrictService,
        'search_districts',
        staticmethod(fake_search_districts)
    )

    r = client.get('/api/districts/search?q=Tisbury')
    assert r.status_code == 200
    body = r.json()
    assert body['total'] == 1
    assert body['data'][0]['name'].startswith('Tisbury')
