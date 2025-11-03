import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.dynamodb_district_service import DynamoDBDistrictService
from schemas import DistrictCreate, DistrictUpdate


class FakeTable:
    def __init__(self, get_item=None, scan_items=None, query_items=None):
        self._get_item = get_item
        self._scan_items = scan_items or []
        self._query_items = query_items or []
        self.puts = []
        self.deletes = []
        self.queries = []

    def put_item(self, Item):
        self.puts.append(Item)

    def get_item(self, **kwargs):
        if callable(self._get_item):
            got = self._get_item(**kwargs)
            return {'Item': got} if got is not None else {}
        return {'Item': self._get_item} if self._get_item is not None else {}

    def scan(self, **kwargs):
        return {'Items': self._scan_items}

    def query(self, **kwargs):
        self.queries.append(kwargs)
        return {'Items': self._query_items}

    def delete_item(self, Key):
        self.deletes.append(Key)


def test_create_district_puts_both_meta_and_towns():
    tbl = FakeTable()
    out = DynamoDBDistrictService.create_district(
        tbl,
        DistrictCreate(name='X', main_address='', towns=['A', 'B'], district_type='municipal')
    )
    # One metadata put and two town puts
    assert any(i.get('entity_type') == 'district' for i in tbl.puts)
    assert len([i for i in tbl.puts if i.get('entity_type') == 'district_town']) == 2
    assert out['name'] == 'X'


def test_get_district_none_when_missing():
    tbl = FakeTable(get_item=None)
    assert DynamoDBDistrictService.get_district(tbl, 'd1') is None


def test_delete_district_false_when_no_items():
    tbl = FakeTable(query_items=[])
    assert DynamoDBDistrictService.delete_district(tbl, 'd1') is False


def test_search_districts_combines_unique(monkeypatch):
    # Name scan returns d1; town query returns d1 and d2; final should include d1 and d2
    scan_items = [
        {
            'district_id': 'd1', 'name': 'Alpha', 'name_lower': 'alpha', 'main_address': '',
            'towns': [], 'district_type': 'municipal', 'created_at': 'c', 'updated_at': 'u', 'entity_type': 'district'
        }
    ]
    query_items = [{'district_id': 'd1'}, {'district_id': 'd2'}]
    tbl = FakeTable(scan_items=scan_items, query_items=query_items)

    def fake_get(table, district_id):
        return {
            'id': district_id, 'name': district_id.upper(), 'main_address': '', 'towns': [],
            'district_type': 'municipal', 'created_at': 'c', 'updated_at': 'u'
        }
    monkeypatch.setattr(DynamoDBDistrictService, 'get_district', staticmethod(fake_get))

    results, total = DynamoDBDistrictService.search_districts(tbl, 'Alpha', limit=10, offset=0)
    assert total == 2
    assert {r['id'] for r in results} == {'d1', 'd2'}


def test_update_district_returns_none_when_missing(monkeypatch):
    # get_district returns None -> update returns None
    monkeypatch.setattr(DynamoDBDistrictService, 'get_district', staticmethod(lambda table, district_id: None))
    tbl = FakeTable()
    out = DynamoDBDistrictService.update_district(tbl, 'd1', DistrictUpdate(name='X'))
    assert out is None
