import sys
from pathlib import Path
from decimal import Decimal
import json

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import salaries as lambda_mod
from utils.dynamodb import get_district_towns


class FakeTable:
    """Mock DynamoDB table for testing"""
    def __init__(self, items):
        self._items = items
        self._query_responses = {}

    def query(self, **kwargs):
        # Handle different query patterns based on KeyConditionExpression
        if 'IndexName' in kwargs:
            index_name = kwargs['IndexName']
            if index_name == 'ExactMatchIndex':
                # GSI1 query for exact matches
                # Extract the partition key from the KeyConditionExpression
                return {'Items': [i for i in self._items if i.get('GSI1PK')]}
            elif index_name == 'FallbackQueryIndex':
                # GSI2 query for fallback
                return {'Items': [i for i in self._items if i.get('GSI2PK')]}

        # Main table query
        return {'Items': self._items}

    def scan(self, **kwargs):
        return {'Items': self._items}


def test_compare_salaries_basic(monkeypatch):
    """Test basic compare salaries with exact matches only (fallback disabled)"""
    # Metadata items
    metadata_items = [
        {
            'PK': 'METADATA#SCHEDULES',
            'SK': 'YEAR#2022-2023#PERIOD#full-year',
            'school_year': '2022-2023',
            'period': 'full-year'
        }
    ]

    # Exact match items
    exact_match_items = [
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

    all_items = metadata_items + exact_match_items

    # Mock the tables
    monkeypatch.setattr(lambda_mod, 'table', FakeTable(all_items))

    # Mock get_district_towns
    monkeypatch.setattr('utils.dynamodb.get_district_towns', lambda ids, table_name: {'d1': ['Town1'], 'd2': ['Town2']})

    # Test with fallback disabled (default)
    resp = lambda_mod.compare_salaries({'education': 'M', 'credits': '30', 'step': '5'})
    assert resp['statusCode'] == 200
    body = json.loads(resp['body'])
    assert body['total'] == 2
    assert body['results'][0]['district_id'] == 'd1'
    assert body['results'][0]['salary'] == 82000.25
    assert body['summary']['exact_matches'] == 2
    assert body['summary']['fallback_matches'] == 0
    assert body['summary']['fallback_enabled'] is False
    assert body['query']['note'] == 'Each district uses its own most recent year/period'


def test_determine_current_year_period():
    """Test year/period determination logic"""
    metadata_items = [
        {'school_year': '2021-2022', 'period': 'fall'},
        {'school_year': '2021-2022', 'period': 'spring'},
        {'school_year': '2022-2023', 'period': 'fall'},
        {'school_year': '2022-2023', 'period': 'full-year'},
    ]

    year, period = lambda_mod.determine_current_year_period(metadata_items)

    # Should pick latest year (2022-2023) and last period alphabetically (spring > full-year > fall)
    assert year == '2022-2023'
    assert period == 'spring'


def test_get_salary_schedule(monkeypatch):
    """Test get salary schedule for a district"""
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

    monkeypatch.setattr(lambda_mod, 'table', FakeTable(items))

    resp = lambda_mod.get_salary_schedule('d1')
    assert resp['statusCode'] == 200
    body = json.loads(resp['body'])
    assert isinstance(body, list) and len(body[0]['salaries']) == 2
    assert body[0]['school_year'] == '2023-2024'
    assert body[0]['period'] == 'full-year'


def test_get_salary_metadata(monkeypatch):
    """Test get salary metadata for a district"""
    items = [
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

    monkeypatch.setattr(lambda_mod, 'table', FakeTable(items))

    resp = lambda_mod.get_salary_metadata('d1')
    assert resp['statusCode'] == 200
    meta = json.loads(resp['body'])
    assert meta['latest_year'] == '2023-2024'
    assert meta['salary_range']['min'] == 60000.0
    assert meta['salary_range']['max'] == 80000.0
    assert len(meta['schedules']) == 2


def test_lambda_handler_routes(monkeypatch):
    """Test Lambda handler routing"""
    # Patch functions used by handler
    monkeypatch.setattr(lambda_mod, 'get_salary_schedule', lambda did, year=None: lambda_mod.create_response(200, {'s': did, 'y': year}))
    monkeypatch.setattr(lambda_mod, 'compare_salaries', lambda params: lambda_mod.create_response(200, {'compare': True}))
    monkeypatch.setattr(lambda_mod, 'get_salary_heatmap', lambda params: lambda_mod.create_response(200, {'heatmap': True}))
    monkeypatch.setattr(lambda_mod, 'get_salary_metadata', lambda did: lambda_mod.create_response(200, {'meta': did}))

    # salary schedule with year
    e = {'path': '/api/salary-schedule/d1/2023-2024', 'httpMethod': 'GET'}
    r = lambda_mod.handler(e, {})
    assert r['statusCode'] == 200 and json.loads(r['body']) == {'s': 'd1', 'y': '2023-2024'}

    # salary compare
    e = {'path': '/api/salary-compare', 'httpMethod': 'GET', 'queryStringParameters': {'education': 'M', 'credits': '30', 'step': '5'}}
    r = lambda_mod.handler(e, {})
    assert r['statusCode'] == 200 and json.loads(r['body']) == {'compare': True}

    # salary heatmap
    e = {'path': '/api/salary-heatmap', 'httpMethod': 'GET', 'queryStringParameters': {'education': 'M', 'credits': '30', 'step': '5'}}
    r = lambda_mod.handler(e, {})
    assert r['statusCode'] == 200 and json.loads(r['body']) == {'heatmap': True}

    # salary metadata
    e = {'path': '/api/districts/d1/salary-metadata', 'httpMethod': 'GET'}
    r = lambda_mod.handler(e, {})
    assert r['statusCode'] == 200 and json.loads(r['body']) == {'meta': 'd1'}

    # not found
    e = {'path': '/nope', 'httpMethod': 'GET'}
    r = lambda_mod.handler(e, {})
    assert r['statusCode'] == 404


def test_find_fallback_salary(monkeypatch):
    """Test fallback salary matching logic"""
    # Create a set of salary entries for a district
    fallback_items = [
        {
            'PK': 'DISTRICT#d1',
            'SK': 'SCHEDULE#2023-2024#full-year#EDU#M#CR#030#STEP#05',
            'GSI2PK': 'YEAR#2023-2024#PERIOD#full-year#DISTRICT#d1',
            'GSI2SK': 'EDU#M#CR#030#STEP#05',
            'district_id': 'd1',
            'district_name': 'Alpha',
            'education': 'M',
            'credits': 30,
            'step': 5,
            'salary': Decimal('70000')
        },
        {
            'PK': 'DISTRICT#d1',
            'SK': 'SCHEDULE#2023-2024#full-year#EDU#M#CR#030#STEP#10',
            'GSI2PK': 'YEAR#2023-2024#PERIOD#full-year#DISTRICT#d1',
            'GSI2SK': 'EDU#M#CR#030#STEP#10',
            'district_id': 'd1',
            'district_name': 'Alpha',
            'education': 'M',
            'credits': 30,
            'step': 10,
            'salary': Decimal('80000')
        },
        {
            'PK': 'DISTRICT#d1',
            'SK': 'SCHEDULE#2023-2024#full-year#EDU#M#CR#060#STEP#05',
            'GSI2PK': 'YEAR#2023-2024#PERIOD#full-year#DISTRICT#d1',
            'GSI2SK': 'EDU#M#CR#060#STEP#05',
            'district_id': 'd1',
            'district_name': 'Alpha',
            'education': 'M',
            'credits': 60,
            'step': 5,
            'salary': Decimal('75000')
        },
        {
            'PK': 'DISTRICT#d1',
            'SK': 'SCHEDULE#2023-2024#full-year#EDU#B#CR#030#STEP#10',
            'GSI2PK': 'YEAR#2023-2024#PERIOD#full-year#DISTRICT#d1',
            'GSI2SK': 'EDU#B#CR#030#STEP#10',
            'district_id': 'd1',
            'district_name': 'Alpha',
            'education': 'B',
            'credits': 30,
            'step': 10,
            'salary': Decimal('65000')
        }
    ]

    monkeypatch.setattr(lambda_mod, 'table', FakeTable(fallback_items))

    # Test 1: Query for M+60 at step 10 (should get M+60@step5, highest step available)
    result = lambda_mod.find_fallback_salary('d1', '2023-2024', 'full-year', 'M', 60, 10)
    assert result is not None
    assert result['credits'] == 60
    assert result['step'] == 5
    assert float(result['salary']) == 75000.0

    # Test 2: Query for M+45 at step 8 (should get M+30@step10, highest credit <= 45)
    result = lambda_mod.find_fallback_salary('d1', '2023-2024', 'full-year', 'M', 45, 8)
    assert result is not None
    assert result['credits'] == 30
    assert result['step'] == 5  # Highest step <= 8 for M+30
    assert float(result['salary']) == 70000.0

    # Test 3: Query for D+60 at step 5 (should step down to M+60@step5)
    result = lambda_mod.find_fallback_salary('d1', '2023-2024', 'full-year', 'D', 60, 5)
    assert result is not None
    assert result['education'] == 'M'
    assert result['credits'] == 60

    # Test 4: Query for B+30 at step 15 (should get B+30@step10, max step)
    result = lambda_mod.find_fallback_salary('d1', '2023-2024', 'full-year', 'B', 30, 15)
    assert result is not None
    assert result['credits'] == 30
    assert result['step'] == 10
    assert float(result['salary']) == 65000.0


def test_pad_number():
    """Test number padding helper"""
    assert lambda_mod.pad_number(5, 2) == '05'
    assert lambda_mod.pad_number(30, 3) == '030'
    assert lambda_mod.pad_number(100, 3) == '100'