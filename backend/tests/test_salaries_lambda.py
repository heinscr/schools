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
    def __init__(self, items):
        self._items = items

    def query(self, **kwargs):
        return {'Items': self._items}

    def scan(self, **kwargs):
        return {'Items': self._items}


def test_compare_salaries_lambda(monkeypatch):
    # Exact match items for salaries table
    items = [
        {
            'district_id': 'd1',
            'district_name': 'Alpha',
            'district_type': 'municipal',
            'school_year': '2022-2023',
            'period': 'B',
            'education': 'M',
            'credits': 30,
            'step': 5,
            'salary': Decimal('82000.25'),
        },
        {
            'district_id': 'd1',  # older period should be dropped
            'district_name': 'Alpha',
            'district_type': 'municipal',
            'school_year': '2022-2023',
            'period': 'A',
            'education': 'M',
            'credits': 30,
            'step': 5,
            'salary': Decimal('80000.00'),
        },
        {
            'district_id': 'd2',
            'district_name': 'Beta',
            'district_type': 'regional',
            'school_year': '2022-2023',
            'period': 'A',
            'education': 'M',
            'credits': 30,
            'step': 5,
            'salary': 75000,
        },
    ]

    # Empty schedules (no fallback matches needed)
    schedules = []

    monkeypatch.setattr(lambda_mod, 'salaries_table', FakeTable(items))
    monkeypatch.setattr(lambda_mod, 'schedules_table', FakeTable(schedules))
    monkeypatch.setattr('utils.dynamodb.get_district_towns', lambda ids, table_name: {'d1': ['Town1'], 'd2': ['Town2']})

    resp = lambda_mod.compare_salaries({'education': 'M', 'credits': '30', 'step': '5'})
    assert resp['statusCode'] == 200
    body = json.loads(resp['body'])
    assert body['total'] == 2
    assert body['results'][0]['district_id'] == 'd1'
    assert body['results'][0]['salary'] == 82000.25
    assert body['summary']['exact_matches'] == 2
    assert body['summary']['fallback_matches'] == 0


def test_get_salary_heatmap_lambda(monkeypatch):
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
            'salary': Decimal('90000.5'),
        },
        {
            'district_id': 'd2',
            'district_name': 'Beta',
            'district_type': 'regional',
            'school_year': '2021-2022',
            'period': 'A',
            'education': 'M',
            'credits': 30,
            'step': 5,
            'salary': 75000,
        },
    ]
    monkeypatch.setattr(lambda_mod, 'salaries_table', FakeTable(items))

    resp = lambda_mod.get_salary_heatmap({'education': 'M', 'credits': '30', 'step': '5', 'year': '2021-2022'})
    assert resp['statusCode'] == 200
    body = json.loads(resp['body'])
    assert body['statistics']['max'] == 90000.5
    assert len(body['data']) == 2


def test_get_salary_schedule_lambda(monkeypatch):
    items = [
        {
            'district_id': 'd1',
            'schedule_key': '2023-2024#A',
            'school_year': '2023-2024',
            'salaries': [{'step': 1, 'salary': Decimal('65000.0')}],
        }
    ]
    monkeypatch.setattr(lambda_mod, 'schedules_table', FakeTable(items))

    resp = lambda_mod.get_salary_schedule('d1')
    assert resp['statusCode'] == 200
    body = json.loads(resp['body'])
    assert isinstance(body, list) and body[0]['salaries'][0]['salary'] == 65000.0


def test_get_salary_metadata_lambda(monkeypatch):
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
    monkeypatch.setattr(lambda_mod, 'schedules_table', FakeTable(items))

    resp = lambda_mod.get_salary_metadata('d1')
    assert resp['statusCode'] == 200
    meta = json.loads(resp['body'])
    assert meta['latest_year'] == '2023-2024'
    assert meta['salary_range']['min'] == 65000.0
    assert meta['salary_range']['max'] == 80000.0


def test_lambda_handler_routes(monkeypatch):
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


def test_compare_salaries_with_fallback(monkeypatch):
    """
    Test that compare_salaries returns both exact matches and fallback matches.
    Scenario:
    - Query for M+60 at step 10
    - District 'd1' has exact match: M+60 at step 10 = $95,000
    - District 'd2' only has M+60 at step 5 = $85,000 (fallback)
    - District 'd3' only has M+30 at step 10 = $80,000 (fallback - lower credits)
    - District 'd4' only has B+60 at step 10 = $70,000 (fallback - lower education)
    - District 'd5' only has M+75 at step 10 = $90,000 (should NOT appear - credits too high)
    """
    # Exact match items from salaries table
    exact_match_items = [
        {
            'district_id': 'd1',
            'district_name': 'District One',
            'district_type': 'municipal',
            'school_year': '2022-2023',
            'period': 'full-year',
            'education': 'M',
            'credits': 60,
            'step': 10,
            'salary': Decimal('95000.00'),
        }
    ]

    # Schedule items for fallback logic
    schedule_items = [
        # d1: has exact match (should not create fallback)
        {
            'district_id': 'd1',
            'district_name': 'District One',
            'district_type': 'municipal',
            'school_year': '2022-2023',
            'period': 'full-year',
            'max_education': 'M',
            'max_by_education': {
                'M': {'60': 10}  # M+60 has max step 10
            },
            'salaries': [
                {'education': 'M', 'credits': 60, 'step': 10, 'salary': Decimal('95000.00')}
            ]
        },
        # d2: only has step 5 (fallback by step)
        {
            'district_id': 'd2',
            'district_name': 'District Two',
            'district_type': 'municipal',
            'school_year': '2022-2023',
            'period': 'full-year',
            'max_education': 'M',
            'max_by_education': {
                'M': {'60': 5}  # M+60 has max step 5
            },
            'salaries': [
                {'education': 'M', 'credits': 60, 'step': 5, 'salary': Decimal('85000.00')}
            ]
        },
        # d3: has lower credits (fallback by credits)
        {
            'district_id': 'd3',
            'district_name': 'District Three',
            'district_type': 'municipal',
            'school_year': '2022-2023',
            'period': 'full-year',
            'max_education': 'M',
            'max_by_education': {
                'M': {'30': 10}  # M+30 has max step 10
            },
            'salaries': [
                {'education': 'M', 'credits': 30, 'step': 10, 'salary': Decimal('80000.00')}
            ]
        },
        # d4: has lower education (fallback by education)
        {
            'district_id': 'd4',
            'district_name': 'District Four',
            'district_type': 'municipal',
            'school_year': '2022-2023',
            'period': 'full-year',
            'max_education': 'B',
            'max_by_education': {
                'B': {'60': 10}  # B+60 has max step 10
            },
            'salaries': [
                {'education': 'B', 'credits': 60, 'step': 10, 'salary': Decimal('70000.00')}
            ]
        },
        # d5: has HIGHER credits (should NOT match - can't step up)
        {
            'district_id': 'd5',
            'district_name': 'District Five',
            'district_type': 'municipal',
            'school_year': '2022-2023',
            'period': 'full-year',
            'max_education': 'M',
            'max_by_education': {
                'M': {'75': 10}  # M+75 has max step 10
            },
            'salaries': [
                {'education': 'M', 'credits': 75, 'step': 10, 'salary': Decimal('90000.00')}
            ]
        }
    ]

    monkeypatch.setattr(lambda_mod, 'salaries_table', FakeTable(exact_match_items))
    monkeypatch.setattr(lambda_mod, 'schedules_table', FakeTable(schedule_items))
    monkeypatch.setattr('utils.dynamodb.get_district_towns', lambda ids, table_name: {
        'd1': ['Town1'], 'd2': ['Town2'], 'd3': ['Town3'], 'd4': ['Town4'], 'd5': ['Town5']
    })

    # Query for M+60 at step 10
    resp = lambda_mod.compare_salaries({'education': 'M', 'credits': '60', 'step': '10'})
    assert resp['statusCode'] == 200

    body = json.loads(resp['body'])

    # Should have 4 results (d1 exact, d2/d3/d4 fallback, d5 excluded)
    assert body['total'] == 4, f"Expected 4 results, got {body['total']}"

    # Check summary
    assert body['summary']['exact_matches'] == 1
    assert body['summary']['fallback_matches'] == 3

    # Results should be sorted by salary descending
    results = body['results']
    assert results[0]['district_id'] == 'd1'
    assert results[0]['salary'] == 95000.0
    assert results[0]['is_exact_match'] is True
    assert 'queried_for' not in results[0]  # No queried_for for exact matches

    assert results[1]['district_id'] == 'd2'
    assert results[1]['salary'] == 85000.0
    assert results[1]['is_exact_match'] is False
    assert results[1]['queried_for'] == {'education': 'M', 'credits': 60, 'step': 10}

    assert results[2]['district_id'] == 'd3'
    assert results[2]['salary'] == 80000.0
    assert results[2]['is_exact_match'] is False

    assert results[3]['district_id'] == 'd4'
    assert results[3]['salary'] == 70000.0
    assert results[3]['is_exact_match'] is False

    # Verify d5 is NOT in results (has higher credits)
    district_ids = [r['district_id'] for r in results]
    assert 'd5' not in district_ids


def test_find_best_salary_match_helper():
    """Test the per-credit max step tracking fallback logic"""
    # Test schedule with B and M education levels, different max steps per credit
    schedule = {
        'max_education': 'M',
        'max_by_education': {
            'B': {
                '0': 1,   # B+0 has max step 1
                '30': 5   # B+30 has max step 5
            },
            'M': {
                '30': 5,   # M+30 has max step 5
                '60': 10   # M+60 has max step 10
            }
        },
        'salaries': [
            {'education': 'B', 'credits': 0, 'step': 1, 'salary': Decimal('50000')},
            {'education': 'B', 'credits': 30, 'step': 5, 'salary': Decimal('60000')},
            {'education': 'M', 'credits': 30, 'step': 5, 'salary': Decimal('70000')},
            {'education': 'M', 'credits': 60, 'step': 5, 'salary': Decimal('80000')},
            {'education': 'M', 'credits': 60, 'step': 10, 'salary': Decimal('90000')},
        ]
    }

    # Query for M+60 at step 10 (exact match exists)
    result = lambda_mod.find_best_salary_match(schedule, 'M', 60, 10)
    assert result['salary'] == Decimal('90000')
    assert result['education'] == 'M'
    assert result['credits'] == 60
    assert result['step'] == 10

    # Query for M+60 at step 15 (should return M+60@step10, max for M+60)
    result = lambda_mod.find_best_salary_match(schedule, 'M', 60, 15)
    assert result['salary'] == Decimal('90000')
    assert result['step'] == 10

    # Query for M+75 at step 10 (should return M+60@step10, highest credit <= 75)
    result = lambda_mod.find_best_salary_match(schedule, 'M', 75, 10)
    assert result['salary'] == Decimal('90000')
    assert result['credits'] == 60
    assert result['step'] == 10

    # Query for M+45 at step 8 (should return M+30@step5, highest credit <= 45, max step at M+30 is 5)
    result = lambda_mod.find_best_salary_match(schedule, 'M', 45, 8)
    assert result['salary'] == Decimal('70000')
    assert result['credits'] == 30
    assert result['step'] == 5  # M+30 only goes up to step 5

    # Query for D+60 at step 10 (should return M+60@step10, M is highest education)
    result = lambda_mod.find_best_salary_match(schedule, 'D', 60, 10)
    assert result['salary'] == Decimal('90000')
    assert result['education'] == 'M'

    # Query for B+60 at step 10 (should return B+30@step5, max for B)
    result = lambda_mod.find_best_salary_match(schedule, 'B', 60, 10)
    assert result['salary'] == Decimal('60000')
    assert result['credits'] == 30
    assert result['step'] == 5

    # Query for empty schedule (should return None)
    empty_schedule = {'max_by_education': {}, 'salaries': []}
    result = lambda_mod.find_best_salary_match(empty_schedule, 'M', 30, 5)
    assert result is None