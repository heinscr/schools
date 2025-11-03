import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
import main as backend_main
from decimal import Decimal


class FakeTable:
    def __init__(self, items):
        self._items = items

    def query(self, **kwargs):
        return {'Items': self._items}


class FakeDynamoClient:
    def __init__(self, towns_map):
        self.towns_map = towns_map

    def batch_get_item(self, RequestItems):
        # Emulate DynamoDB low-level format
        # Return towns for each requested district
        table_name = next(iter(RequestItems.keys()))
        keys = RequestItems[table_name]['Keys']
        items = []
        for k in keys:
            did = k['PK']['S'].replace('DISTRICT#', '')
            towns = self.towns_map.get(did, [])
            items.append({
                'district_id': {'S': did},
                'towns': {'L': [{'S': t} for t in towns]},
            })
        return {'Responses': {table_name: items}}


def test_salary_compare_local(monkeypatch):
    # Prepare fake salary rows
    items = [
        {
            'district_id': 'd1',
            'district_name': 'Alpha',
            'district_type': 'municipal',
            'school_year': '2021-2022',
            'period': 'A',
            'education': 'M',
            'credits': 30,
            'step': 5,
            'salary': 80000,
        },
        {
            'district_id': 'd2',
            'district_name': 'Beta',
            'district_type': 'municipal',
            'school_year': '2021-2022',
            'period': 'A',
            'education': 'M',
            'credits': 30,
            'step': 5,
            'salary': 75000,
        },
    ]

    # Patch backend module state
    monkeypatch.setattr(backend_main, '_salaries_table', FakeTable(items))
    monkeypatch.setattr(backend_main, '_districts_table_name', 'crackpow-schools-districts')
    monkeypatch.setattr(backend_main, '_dynamodb_client', FakeDynamoClient({'d1': ['Town1'], 'd2': ['Town2']}))

    client = TestClient(backend_main.app)
    r = client.get('/api/salary-compare?education=M&credits=30&step=5')
    assert r.status_code == 200
    body = r.json()
    assert body['total'] == 2
    assert body['results'][0]['district_name'] == 'Alpha'


def test_salary_schedule_404(monkeypatch):
    # No items -> 404
    monkeypatch.setattr(backend_main, '_schedules_table', FakeTable([]))
    client = TestClient(backend_main.app)
    r = client.get('/api/salary-schedule/DISTRICT_X')
    assert r.status_code == 404


def test_salary_heatmap_local(monkeypatch):
    items = [
        {
            'district_id': 'd1',
            'district_name': 'Alpha',
            'district_type': 'municipal',
            'salary': Decimal('90000.5'),
        },
        {
            'district_id': 'd2',
            'district_name': 'Beta',
            'district_type': 'regional',
            'salary': 75000,
        },
    ]
    monkeypatch.setattr(backend_main, '_salaries_table', FakeTable(items))
    client = TestClient(backend_main.app)
    r = client.get('/api/salary-heatmap?education=M&credits=30&step=5')
    assert r.status_code == 200
    body = r.json()
    assert body['statistics']['max'] == 90000.5
    assert len(body['data']) == 2


def test_salary_schedule_success(monkeypatch):
    items = [
        {
            'district_id': 'd1',
            'schedule_key': '2023-2024#A',
            'school_year': '2023-2024',
            'salaries': [{'step': 1, 'salary': Decimal('65000.0')}],
        }
    ]
    monkeypatch.setattr(backend_main, '_schedules_table', FakeTable(items))
    client = TestClient(backend_main.app)
    r = client.get('/api/salary-schedule/d1')
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list) and body[0]['salaries'][0]['salary'] == 65000.0


def test_salary_metadata_success(monkeypatch):
    items = [
        {
            'district_id': 'd1',
            'district_name': 'Alpha',
            'school_year': '2022-2023',
            'period': 'A',
            'salaries': [{'step': 1, 'salary': Decimal('60000.0')}, {'step': 2, 'salary': 70000}],
            'contract_term': '2021-2024',
            'contract_expiration': '2024-08-31'
        },
        {
            'district_id': 'd1',
            'district_name': 'Alpha',
            'school_year': '2023-2024',
            'period': 'B',
            'salaries': [{'step': 1, 'salary': 65000}, {'step': 2, 'salary': 80000}],
            'contract_term': '2021-2024',
            'contract_expiration': '2024-08-31'
        }
    ]
    monkeypatch.setattr(backend_main, '_schedules_table', FakeTable(items))
    client = TestClient(backend_main.app)
    r = client.get('/api/districts/d1/salary-metadata')
    assert r.status_code == 200
    meta = r.json()
    assert meta['latest_year'] == '2023-2024'
    assert meta['salary_range']['min'] == 65000.0
    assert meta['salary_range']['max'] == 80000.0
