import sys
from pathlib import Path
from decimal import Decimal

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services import salary_service_optimized as svc


class FakeTable:
    """Mock DynamoDB table for testing"""
    def __init__(self, items):
        self._items = items

    def query(self, **kwargs):
        # Simple heuristic: return items that match IndexName presence
        if 'IndexName' in kwargs:
            index_name = kwargs['IndexName']
            if index_name == 'ExactMatchIndex':
                return {'Items': [i for i in self._items if i.get('GSI1PK')]}
            if index_name == 'FallbackQueryIndex':
                return {'Items': [i for i in self._items if i.get('GSI2PK')]}
        return {'Items': self._items}

    def get_item(self, **kwargs):
        key = kwargs.get('Key', {})
        pk = key.get('PK')
        sk = key.get('SK')
        for it in self._items:
            if it.get('PK') == pk and it.get('SK') == sk:
                return {'Item': it}
        return {}

    def scan(self, **kwargs):
        return {'Items': self._items}


def test_compare_salaries_basic(monkeypatch):
    metadata_items = [
        {'PK': 'METADATA#SCHEDULES', 'SK': 'YEAR#2022-2023#PERIOD#full-year', 'school_year': '2022-2023', 'period': 'full-year'},
        {'PK': 'METADATA#MAXVALUES', 'SK': 'GLOBAL', 'max_step': 15, 'edu_credit_combos': ['B', 'M+30', 'M+45', 'M+60', 'D']}
    ]

    # District metadata items (for district type filtering)
    district_metadata_items = [
        {'PK': 'DISTRICT#d1', 'SK': 'METADATA', 'district_type': 'municipal'},
        {'PK': 'DISTRICT#d2', 'SK': 'METADATA', 'district_type': 'regional_academic'}
    ]

    exact_items = [
        {
            'PK': 'DISTRICT#d1',
            'SK': 'SCHEDULE#2022-2023#full-year#EDU#M#CR#030#STEP#05',
            'GSI1PK': 'YEAR#2022-2023#PERIOD#full-year#EDU#M#CR#030#STEP#05',
            'GSI1SK': 'DISTRICT#d1',
            'district_id': 'd1',
            'district_name': 'Alpha',
            'school_year': '2022-2023',
            'period': 'full-year',
            'education': 'M',
            'credits': 30,
            'step': 5,
            'salary': Decimal('82000.25'),
        },
        {
            'PK': 'DISTRICT#d2',
            'SK': 'SCHEDULE#2022-2023#full-year#EDU#M#CR#030#STEP#05',
            'GSI1PK': 'YEAR#2022-2023#PERIOD#full-year#EDU#M#CR#030#STEP#05',
            'GSI1SK': 'DISTRICT#d2',
            'district_id': 'd2',
            'district_name': 'Beta',
            'school_year': '2022-2023',
            'period': 'full-year',
            'education': 'M',
            'credits': 30,
            'step': 5,
            'salary': Decimal('75000'),
        }
    ]

    all_items = metadata_items + district_metadata_items + exact_items
    monkeypatch.setattr(svc, 'table', FakeTable(all_items))

    resp = svc.compare_salaries_across_districts(FakeTable(all_items), 'M', 30, 5)
    assert resp['total'] == 2
    assert resp['results'][0]['district_id'] == 'd1'
    # salary may be Decimal or float depending on implementation
    assert abs(float(resp['results'][0]['salary']) - 82000.25) < 0.01
    assert resp['summary']['exact_matches'] == 2
    assert resp['summary']['fallback_matches'] == 0


def test_schedule_and_metadata(monkeypatch):
    items = [
        {
            'PK': 'DISTRICT#d1',
            'SK': 'SCHEDULE#2023-2024#full-year#EDU#M#CR#030#STEP#01',
            'district_id': 'd1',
            'school_year': '2023-2024',
            'period': 'full-year',
            'education': 'M',
            'credits': 30,
            'step': 1,
            'salary': Decimal('65000.0')
        },
        {
            'PK': 'DISTRICT#d1',
            'SK': 'SCHEDULE#2023-2024#full-year#EDU#M#CR#030#STEP#02',
            'district_id': 'd1',
            'school_year': '2023-2024',
            'period': 'full-year',
            'education': 'M',
            'credits': 30,
            'step': 2,
            'salary': Decimal('70000.0')
        }
    ]

    monkeypatch.setattr(svc, 'table', FakeTable(items))

    schedule = svc.get_salary_schedule_for_district(FakeTable(items), 'd1')
    assert isinstance(schedule, list)
    assert len(schedule[0]['salaries']) == 2

    # metadata test
    meta_items = [
        {
            'PK': 'DISTRICT#d1',
            'SK': 'SCHEDULE#2022-2023#full-year#EDU#M#CR#030#STEP#01',
            'district_id': 'd1',
            'district_name': 'Alpha',
            'school_year': '2022-2023',
            'period': 'full-year',
            'education': 'M',
            'credits': 30,
            'step': 1,
            'salary': Decimal('60000.0')
        },
        {
            'PK': 'DISTRICT#d1',
            'SK': 'SCHEDULE#2023-2024#spring#EDU#M#CR#030#STEP#01',
            'district_id': 'd1',
            'district_name': 'Alpha',
            'school_year': '2023-2024',
            'period': 'spring',
            'education': 'M',
            'credits': 30,
            'step': 1,
            'salary': Decimal('80000.0')
        }
    ]

    monkeypatch.setattr(svc, 'table', FakeTable(meta_items))
    meta = svc.get_district_salary_metadata(FakeTable(meta_items), 'd1')
    assert meta['latest_year'] == '2023-2024'
    assert meta['salary_range']['min'] == 60000.0
    assert meta['salary_range']['max'] == 80000.0