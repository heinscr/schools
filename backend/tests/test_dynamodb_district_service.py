import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.dynamodb_district_service import DynamoDBDistrictService
from schemas import DistrictCreate, DistrictUpdate


class FakeTable:
    def __init__(self, scan_items=None, query_items=None, get_item=None):
        self._scan_items = scan_items or []
        self._query_items = query_items or []
        self._get_item = get_item
        self.put_calls = []
        self.delete_calls = []
        self.update_calls = []

    def scan(self, **kwargs):
        return {'Items': self._scan_items}

    def query(self, **kwargs):
        return {'Items': self._query_items}

    def get_item(self, **kwargs):
        if callable(self._get_item):
            return {'Item': self._get_item(**kwargs)}
        if self._get_item is None:
            return {}
        return {'Item': self._get_item}

    def put_item(self, Item):
        self.put_calls.append(Item)
        return {}

    def delete_item(self, Key):
        self.delete_calls.append(Key)
        return {}

    def update_item(self, **kwargs):
        self.update_calls.append(kwargs)
        return {}


def test_item_to_dict():
    item = {
        'district_id': 'd1',
        'name': 'Alpha',
        'main_address': '123',
        'towns': ['T1'],
        'district_type': 'municipal',
        'created_at': 'now',
        'updated_at': 'later',
    }
    out = DynamoDBDistrictService._item_to_dict(item)
    assert out['id'] == 'd1'
    assert out['name'] == 'Alpha'
    assert out['district_type'] == 'municipal'


def test_get_all_districts_pagination():
    items = [
        {
            'district_id': f'd{i}',
            'name': f'N{i}',
            'main_address': '',
            'towns': [],
            'district_type': 'municipal',
            'created_at': 'c',
            'updated_at': 'u',
            'entity_type': 'district',
        } for i in range(5)
    ]
    tbl = FakeTable(scan_items=items)
    results, total = DynamoDBDistrictService._get_all_districts(tbl, limit=2, offset=1)
    assert total == 5
    assert len(results) == 2
    assert results[0]['id'] == 'd1'


def test_scan_by_name():
    items = [
        {
            'district_id': 'd1',
            'name': 'Alpha',
            'name_lower': 'alpha',
            'main_address': '',
            'towns': [],
            'district_type': 'municipal',
            'created_at': 'c',
            'updated_at': 'u',
            'entity_type': 'district',
        }
    ]
    tbl = FakeTable(scan_items=items)
    results, total = DynamoDBDistrictService._scan_by_name(tbl, 'Alpha', limit=10, offset=0)
    assert total == 1
    assert results[0]['name'] == 'Alpha'


def test_query_by_town(monkeypatch):
    # Two relationships pointing to two district ids
    q_items = [
        {'district_id': 'd1'},
        {'district_id': 'd2'},
    ]
    tbl = FakeTable(query_items=q_items)

    def fake_get(table, district_id):
        return {
            'id': district_id,
            'name': district_id.upper(),
            'main_address': '',
            'towns': [],
            'district_type': 'municipal',
            'created_at': 'c',
            'updated_at': 'u',
        }

    monkeypatch.setattr(DynamoDBDistrictService, 'get_district', staticmethod(fake_get))

    results, total = DynamoDBDistrictService._query_by_town(tbl, 'Egremont', limit=10, offset=0)
    assert total == 2
    assert {r['id'] for r in results} == {'d1', 'd2'}


def test_update_district_towns(monkeypatch):
    # Existing district
    existing = {
        'id': 'd1', 'name': 'OLD', 'main_address': '', 'towns': ['OLD'],
        'district_type': 'municipal', 'created_at': 'c', 'updated_at': 'u'
    }

    def fake_get_existing(table, district_id):
        if district_id == 'd1':
            return existing
        return None

    def fake_get_after(table, district_id):
        return {
            'id': 'd1', 'name': 'NEW', 'main_address': '', 'towns': ['A', 'B'],
            'district_type': 'municipal', 'created_at': 'c', 'updated_at': 'u2'
        }

    tbl = FakeTable(query_items=[{'PK': 'DISTRICT#d1', 'SK': 'TOWN#OLD'}])

    # First call returns existing, second call (after update) returns updated
    calls = {'n': 0}

    def fake_get(table, district_id):
        calls['n'] += 1
        return fake_get_existing(table, district_id) if calls['n'] == 1 else fake_get_after(table, district_id)

    monkeypatch.setattr(DynamoDBDistrictService, 'get_district', staticmethod(fake_get))

    updated = DynamoDBDistrictService.update_district(
        tbl,
        'd1',
        DistrictUpdate(name='NEW', towns=['A', 'B'])
    )

    assert updated['name'] == 'NEW'
    # Town delete then two puts for new towns
    assert any(k['SK'] == 'TOWN#OLD' for k in tbl.delete_calls)
    assert len([c for c in tbl.put_calls if c.get('entity_type') == 'district_town']) == 2
